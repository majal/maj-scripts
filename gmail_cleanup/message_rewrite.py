"""Message planning, media selection, and backup-note rewriting for
gmail-cleanup: deciding which parts of a Gmail message to extract
(``plan_message``/``collect_media_parts``), buffering the bytes of selected
parts for local backup (``collect_buffered_media``), building the
plain-text/HTML "local media backup note" that gets prepended to what
remains of a message (``build_note_text``/``build_note_html`` and their
fragment-formatting helpers), replacing inline CID-referenced media with
placeholder text/HTML, and the top-level ``rewrite_message_for_backup``
orchestrator that ties all of the above together into the final rewritten
message bytes handed back to the Gmail API.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md). The report
flagged this region as "genuinely tangled -- deeply interleaved EmailMessage
tree-walking, MIME part selection, HTML/text note construction, and CID
rewriting that share a lot of local state and call each other in both
directions." Tracing the actual call graph (every function-to-function call
within ``detect_unsupported_message`` through ``rewrite_message_for_backup``,
via an AST walk of every name each function loads) found no back-edges: the
graph is a clean DAG with two independent entry points --
``plan_message``/``collect_media_parts`` (used while deciding what to
extract) and ``rewrite_message_for_backup`` (used once extraction bytes are
already written, to produce the replacement message) -- feeding downward
into shared leaf helpers (``note_charset``, fragment formatters, CID
placeholder builders) that call nothing else in this module. The "shared
local state" in the report's note is per-call closures (e.g. the
``nonlocal counter`` in ``collect_media_parts``'s inner ``visit``), not
shared module-level mutable state; nothing here persists across calls or is
mutated by two different callers. Every external name each function
references (checked via AST, not just grep) resolves to the standard
library or a module already extracted: gmail_cleanup.models,
gmail_cleanup.constants, gmail_cleanup.message_utils, gmail_cleanup.naming,
and gmail_cleanup.config (default_extraction_settings). No behavior
changes.
"""

from __future__ import annotations

import html
import re
from datetime import datetime, timezone
from email import policy
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from urllib.parse import quote

from gmail_cleanup.config import default_extraction_settings
from gmail_cleanup.constants import (
    DEFAULT_GMAIL_WEB_ACCOUNT,
    LARGE_MEDIA_MIN_PART_BYTES,
    PDF_DIRECT_IMAGE_GENERATIONS,
    PDF_MIME_TYPE,
    PDF_ORIGINAL_TRASH_GENERATIONS,
    PDF_UNREADABLE_ORIGINAL_TRASH_GENERATION,
    STRIP_HEADERS,
    STRIP_HEADER_PREFIXES,
    UNSUPPORTED_CONTENT_TYPES,
)
from gmail_cleanup.message_utils import (
    attachment_categories_for_part,
    derive_attachment_filename,
    header_value,
    human_size,
    infer_attachment_mime_type,
    parse_email_message,
)
from gmail_cleanup.models import (
    BufferedMediaPart,
    ExtractionSettings,
    GmailMessageRecord,
    PdfTextBlock,
    PlannedMessage,
    SelectedMediaPart,
    SkippableMessageError,
    WrittenAttachment,
)
from gmail_cleanup.naming import (
    build_saved_filename,
    build_search_token,
    normalize_content_id,
    photos_search_query,
)


def detect_unsupported_message(message: EmailMessage) -> str | None:
    for part in message.walk():
        if part.get_content_type().lower() in UNSUPPORTED_CONTENT_TYPES:
            return "signed or encrypted messages are skipped"
    return None


def plan_message(record: GmailMessageRecord, settings: ExtractionSettings | None = None) -> PlannedMessage:
    settings = settings or default_extraction_settings()
    message = parse_email_message(record.raw_bytes)
    skip_reason = detect_unsupported_message(message)
    media_parts = tuple(() if skip_reason else collect_media_parts(message, record.message_id, settings))
    if media_parts and not message_matches_before_year(message, settings.before_year):
        media_parts = ()
    if media_parts and settings.min_message_bytes and sum(part.size_bytes for part in media_parts) < settings.min_message_bytes:
        media_parts = ()
    return PlannedMessage(
        message_id=record.message_id,
        thread_id=record.thread_id,
        label_ids=record.label_ids,
        subject=header_value(message, "Subject"),
        sender=header_value(message, "From"),
        date_header=header_value(message, "Date"),
        raw_bytes=record.raw_bytes,
        media_parts=media_parts,
        skip_reason=skip_reason,
    )


def gmail_thread_url(thread_id: str, account: str = DEFAULT_GMAIL_WEB_ACCOUNT) -> str:
    return f"https://mail.google.com/mail/u/{quote(account, safe='')}/#all/{quote(thread_id, safe='')}"


def collect_media_parts(message: EmailMessage, message_id: str, settings: ExtractionSettings) -> list[SelectedMediaPart]:
    parts: list[SelectedMediaPart] = []
    counter = 1

    def visit(part: EmailMessage, path: tuple[int, ...]) -> None:
        nonlocal counter
        if part.is_multipart():
            for index, child in enumerate(part.iter_parts()):
                visit(child, path + (index,))
            return
        if not should_extract_part(part, settings):
            return
        payload = part.get_payload(decode=True) or b""
        disposition = (part.get_content_disposition() or "").lower()
        filename = derive_attachment_filename(part, counter)
        search_token = build_search_token(message_id, counter)
        parts.append(
            SelectedMediaPart(
                path=path,
                filename=filename,
                saved_filename=build_saved_filename(search_token, filename),
                search_token=search_token,
                mime_type=infer_attachment_mime_type(part),
                size_bytes=len(payload),
                disposition=disposition,
                content_id=part.get("Content-ID"),
            )
        )
        counter += 1

    visit(message, ())
    return parts


def message_matches_before_year(message: EmailMessage, before_year: int | None) -> bool:
    if before_year is None:
        return True
    try:
        parsed = parsedate_to_datetime(header_value(message, "Date"))
    except (TypeError, ValueError, IndexError, OverflowError):
        return False
    return parsed.year < before_year


def should_extract_part(part: EmailMessage, settings: ExtractionSettings) -> bool:
    disposition = (part.get_content_disposition() or "").lower()
    if not (part.get_filename() or part.get("Content-ID") or disposition in {"attachment", "inline"}):
        return False
    payload_size = len(part.get_payload(decode=True) or b"")
    if payload_size < settings.min_part_bytes:
        return False
    categories = attachment_categories_for_part(part)
    requested = set(settings.attachment_types)
    if "large-media" in requested and "media" in categories and payload_size >= LARGE_MEDIA_MIN_PART_BYTES:
        return True
    return bool(categories & requested)


def collect_buffered_media(message: EmailMessage, plan: PlannedMessage) -> list[BufferedMediaPart]:
    selected = {part.path: part for part in plan.media_parts}
    buffered: list[BufferedMediaPart] = []

    def visit(part: EmailMessage, path: tuple[int, ...]) -> None:
        if part.is_multipart():
            for index, child in enumerate(part.iter_parts()):
                visit(child, path + (index,))
            return
        selected_part = selected.get(path)
        if selected_part is None:
            return
        buffered.append(
            BufferedMediaPart(
                path=path,
                filename=selected_part.filename,
                saved_filename=selected_part.saved_filename,
                search_token=selected_part.search_token,
                mime_type=selected_part.mime_type,
                content_bytes=part.get_payload(decode=True) or b"",
                disposition=selected_part.disposition,
                content_id=selected_part.content_id,
            )
        )

    visit(message, ())
    return buffered


def prune_selected_parts(part: EmailMessage, selected_paths: set[tuple[int, ...]], path: tuple[int, ...] = ()) -> EmailMessage | None:
    if path in selected_paths:
        return None
    if not part.is_multipart():
        return part
    kept_parts: list[EmailMessage] = []
    for index, child in enumerate(part.iter_parts()):
        updated = prune_selected_parts(child, selected_paths, path + (index,))
        if updated is not None:
            kept_parts.append(updated)
    if not kept_parts:
        return None
    part.set_payload(kept_parts)
    return part


CID_ATTRIBUTE_PATTERN = re.compile(
    r"""<(?P<tag>[a-zA-Z][^>]*?\b(?:src|href)\s*=\s*(?P<quote>["'])cid:(?P<cid>[^"']+)(?P=quote)[^>]*)>""",
    re.IGNORECASE,
)
CID_TEXT_PATTERN = re.compile(r"cid:(?P<cid>[^\s\"'>)]+)", re.IGNORECASE)


def buffered_note_fragments(media_parts: list[BufferedMediaPart]) -> list[str]:
    lines: list[str] = []
    for part in media_parts:
        details = [
            f'original "{part.filename}"',
            f'saved as "{part.saved_filename}"',
            f'search token {photos_search_query(part.search_token)}',
            part.mime_type,
            human_size(len(part.content_bytes)),
        ]
        content_id = normalize_content_id(part.content_id)
        if content_id:
            details.append(f"cid:{content_id}")
        if part.disposition:
            details.append(part.disposition)
        lines.append("; ".join(details))
    return lines


def is_pdf_page_output(attachment: WrittenAttachment) -> bool:
    return attachment.source_attachment_mime_type == PDF_MIME_TYPE and attachment.source_generation in PDF_DIRECT_IMAGE_GENERATIONS


def written_note_fragments(attachments: list[WrittenAttachment]) -> list[str]:
    lines: list[str] = []
    seen_pdf_groups: set[str] = set()
    for attachment in attachments:
        if is_pdf_page_output(attachment):
            group_token = attachment.group_search_token or attachment.search_token
            if group_token in seen_pdf_groups:
                continue
            seen_pdf_groups.add(group_token)
            group_items = [item for item in attachments if is_pdf_page_output(item) and (item.group_search_token or item.search_token) == group_token]
            first = group_items[0]
            details = [
                f'original "{first.original_filename}"',
                PDF_MIME_TYPE,
                f"{len(group_items)} page image(s) saved",
                f"group token {photos_search_query(group_token)}",
                f'first file "{group_items[0].filename}"',
            ]
            if len(group_items) > 1:
                details.append(f'last file "{group_items[-1].filename}"')
            details.append(human_size(sum(item.size_bytes for item in group_items)))
            details.append("direct page extraction" if first.source_generation == "pdf-extract" else "rendered pages")
            lines.append("; ".join(details))
            continue
        details = [
            f'original "{attachment.original_filename}"',
            f'saved as "{attachment.filename}"',
            f'search token {photos_search_query(attachment.search_token)}',
            attachment.mime_type,
            human_size(attachment.size_bytes),
        ]
        if attachment.group_search_token and attachment.group_search_token != attachment.search_token:
            details.append(f"group token {photos_search_query(attachment.group_search_token)}")
        if attachment.source_page_number is not None:
            details.append(f"page {attachment.source_page_number}")
        content_id = normalize_content_id(attachment.content_id)
        if content_id:
            details.append(f"cid:{content_id}")
        if attachment.disposition:
            details.append(attachment.disposition)
        if attachment.source_generation == "pdf-original":
            details.append("saved original PDF")
        if attachment.source_generation in PDF_ORIGINAL_TRASH_GENERATIONS:
            details.append("moved original PDF to local OS Trash")
        if attachment.source_generation == PDF_UNREADABLE_ORIGINAL_TRASH_GENERATION:
            details.append("PDF could not be read or converted")
        lines.append("; ".join(details))
    return lines


def format_pdf_text_section_text(pdf_text_blocks: list[PdfTextBlock]) -> str:
    if not pdf_text_blocks:
        return ""
    sections = ["", "Retained PDF text:"]
    for block in pdf_text_blocks:
        sections.extend(
            (
                f'--- {block.original_filename} [{photos_search_query(block.group_search_token)}] ({block.source}) ---',
                block.text,
                "",
            )
        )
    return "\n".join(sections).rstrip()


def format_pdf_text_section_html(pdf_text_blocks: list[PdfTextBlock]) -> str:
    if not pdf_text_blocks:
        return ""
    parts = ["<p><strong>Retained PDF text</strong></p>"]
    for block in pdf_text_blocks:
        parts.append(
            "<div style=\"margin:12px 0;\">"
            f"<p><strong>{html.escape(block.original_filename)}</strong> "
            f"(<code>{html.escape(photos_search_query(block.group_search_token))}</code>, {html.escape(block.source)})</p>"
            f"<pre style=\"white-space:pre-wrap; overflow-wrap:anywhere; background:#ffffff; border:1px solid #d8dee4; padding:10px;\">{html.escape(block.text)}</pre>"
            "</div>"
        )
    return "".join(parts)


def build_note_text(
    timestamp: datetime,
    operation_id: str,
    backup_folder_name: str,
    media_parts: list[BufferedMediaPart],
    written_attachments: list[WrittenAttachment] | None = None,
    pdf_text_blocks: list[PdfTextBlock] | None = None,
) -> str:
    lines = [
        f"Local media backup note ({timestamp.astimezone().isoformat(timespec='seconds')})",
        f"Operation: {operation_id}",
        f"Backup folder: {backup_folder_name}",
        "Saved and removed attachments:",
    ]
    fragments = written_note_fragments(written_attachments) if written_attachments is not None else buffered_note_fragments(media_parts)
    lines.extend(f"- {fragment}" for fragment in fragments)
    note = "\n".join(lines)
    if pdf_text_blocks:
        note += format_pdf_text_section_text(pdf_text_blocks)
    return note


def build_note_html(
    timestamp: datetime,
    operation_id: str,
    backup_folder_name: str,
    media_parts: list[BufferedMediaPart],
    written_attachments: list[WrittenAttachment] | None = None,
    pdf_text_blocks: list[PdfTextBlock] | None = None,
) -> str:
    fragments = written_note_fragments(written_attachments) if written_attachments is not None else buffered_note_fragments(media_parts)
    items = "".join(f"<li>{html.escape(fragment)}</li>" for fragment in fragments)
    text_section = format_pdf_text_section_html(pdf_text_blocks or [])
    return (
        '<div style="border:1px solid #d0d7de; background:#f6f8fa; padding:12px; margin:0 0 16px 0;">'
        f"<p><strong>Local media backup note</strong> ({html.escape(timestamp.astimezone().isoformat(timespec='seconds'))})</p>"
        f"<p>Operation: <code>{html.escape(operation_id)}</code><br>"
        f"Backup folder: <code>{html.escape(backup_folder_name)}</code></p>"
        f"<p>Saved and removed attachments:</p><ul>{items}</ul>{text_section}</div>"
    )


def inject_backup_note(message: EmailMessage, note_text: str, note_html: str, operation_id: str) -> None:
    touched = False
    plain_body = message.get_body(preferencelist=("plain",))
    html_body = message.get_body(preferencelist=("html",))
    seen: set[int] = set()
    for part, html_mode in ((plain_body, False), (html_body, True)):
        if part is None:
            continue
        if id(part) in seen:
            continue
        if (part.get_content_disposition() or "").lower() == "attachment":
            continue
        seen.add(id(part))
        prepend_note(part, note_html if html_mode else note_text, html_mode=html_mode)
        touched = True
    if not touched and message.get_content_maintype().lower() == "text":
        prepend_note(message, note_html if message.get_content_subtype() == "html" else note_text, html_mode=message.get_content_subtype() == "html")
        touched = True
    if not touched:
        message["X-Maj-Scripts-Note"] = f"Local media backup applied ({operation_id})"


def note_charset(preferred_charset: str, *text_chunks: str) -> str:
    try:
        for chunk in text_chunks:
            chunk.encode(preferred_charset)
    except UnicodeEncodeError:
        return "utf-8"
    return preferred_charset


def prepend_note(part: EmailMessage, note: str, html_mode: bool) -> None:
    existing = part.get_content()
    charset = note_charset(part.get_content_charset() or "utf-8", note, existing)
    if html_mode:
        part.set_content(f"{note}\n{existing}", subtype="html", charset=charset)
    else:
        part.set_content(f"{note}\n\n{existing}", subtype="plain", charset=charset)


def inline_placeholder_text(media_part: BufferedMediaPart) -> str:
    details = [
        "Inline media removed",
        f'original "{media_part.filename}"',
        f'saved as "{media_part.saved_filename}"',
        f'search token {photos_search_query(media_part.search_token)}',
        media_part.mime_type,
        human_size(len(media_part.content_bytes)),
    ]
    content_id = normalize_content_id(media_part.content_id)
    if content_id:
        details.append(f"cid:{content_id}")
    return "; ".join(details)


def inline_placeholder_html(media_part: BufferedMediaPart) -> str:
    return (
        '<div style="display:inline-block; border:1px dashed #9aa4b2; background:#f8fafc; '
        'padding:8px 10px; margin:6px 0; color:#334155; font-size:13px; line-height:1.4;">'
        f"{html.escape(inline_placeholder_text(media_part))}</div>"
    )


def replace_inline_media_references(message: EmailMessage, media_parts: list[BufferedMediaPart]) -> None:
    by_cid = {
        normalized: media_part
        for media_part in media_parts
        for normalized in [normalize_content_id(media_part.content_id)]
        if normalized is not None
    }
    if not by_cid:
        return
    for part in message.walk():
        if part.get_content_type().lower() != "text/html":
            continue
        if (part.get_content_disposition() or "").lower() == "attachment":
            continue
        existing = part.get_content()
        replaced = replace_cid_references_in_html(existing, by_cid)
        if replaced == existing:
            continue
        charset = part.get_content_charset() or "utf-8"
        part.set_content(replaced, subtype="html", charset=charset)


def replace_cid_references_in_html(html_text: str, by_cid: dict[str, BufferedMediaPart]) -> str:
    def replace_tag(match: re.Match[str]) -> str:
        media_part = by_cid.get(normalize_content_id(match.group("cid")) or "")
        if media_part is None:
            return match.group(0)
        return inline_placeholder_html(media_part)

    replaced = CID_ATTRIBUTE_PATTERN.sub(replace_tag, html_text)

    def replace_text(match: re.Match[str]) -> str:
        media_part = by_cid.get(normalize_content_id(match.group("cid")) or "")
        if media_part is None:
            return match.group(0)
        return html.escape(inline_placeholder_text(media_part))

    return CID_TEXT_PATTERN.sub(replace_text, replaced)


def sanitize_message_for_insert(message: EmailMessage, operation_id: str, extracted_at: datetime) -> None:
    for header in list(message.keys()):
        header_lower = header.lower()
        if header_lower in STRIP_HEADERS or header_lower.startswith(STRIP_HEADER_PREFIXES):
            del message[header]
    message["X-Maj-Scripts-Gmail-Cleanup"] = (
        f"extract-media; operation={operation_id}; extracted_at={extracted_at.astimezone(timezone.utc).isoformat(timespec='seconds')}"
    )


def build_note_only_message(plan: PlannedMessage, note_text: str, note_html: str) -> EmailMessage:
    original = parse_email_message(plan.raw_bytes)
    message = EmailMessage()
    for header, value in original.items():
        header_lower = header.lower()
        if header_lower in STRIP_HEADERS or header_lower.startswith(STRIP_HEADER_PREFIXES):
            continue
        if header_lower in {"content-type", "content-transfer-encoding", "mime-version"}:
            continue
        message[header] = value
    message.set_content(note_text, subtype="plain", charset=note_charset("utf-8", note_text))
    if original.get_body(preferencelist=("html",)) is not None:
        message.add_alternative(note_html, subtype="html", charset=note_charset("utf-8", note_html))
    return message


def rewrite_message_for_backup(
    plan: PlannedMessage,
    extracted_at: datetime,
    backup_folder_name: str,
    operation_id: str,
    settings: ExtractionSettings | None = None,
    written_attachments: list[WrittenAttachment] | None = None,
    pdf_text_blocks: list[PdfTextBlock] | None = None,
) -> tuple[bytes, list[BufferedMediaPart]]:
    settings = settings or default_extraction_settings()
    message = parse_email_message(plan.raw_bytes)
    buffered = collect_buffered_media(message, plan)
    replace_inline_media_references(message, buffered)
    selected_paths = {part.path for part in plan.media_parts}
    updated = prune_selected_parts(message, selected_paths)
    note_text = build_note_text(
        extracted_at,
        operation_id,
        backup_folder_name,
        buffered,
        written_attachments=written_attachments,
        pdf_text_blocks=pdf_text_blocks,
    )
    note_html = build_note_html(
        extracted_at,
        operation_id,
        backup_folder_name,
        buffered,
        written_attachments=written_attachments,
        pdf_text_blocks=pdf_text_blocks,
    )
    note_only = False
    if updated is None:
        if settings.empty_after_removal == "note-only":
            updated = build_note_only_message(plan, note_text, note_html)
            note_only = True
        else:
            raise SkippableMessageError(f"message would be empty after removing selected attachments: {plan.message_id}")
    if not note_only:
        inject_backup_note(updated, note_text, note_html, operation_id)
    sanitize_message_for_insert(updated, operation_id, extracted_at)
    return updated.as_bytes(policy=policy.SMTP), buffered
