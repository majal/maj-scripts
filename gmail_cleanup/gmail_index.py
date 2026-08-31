"""Local SQLite index subsystem for gmail-cleanup: ``GmailIndex`` (the
schema/storage layer -- caches raw Gmail messages and query-match ordering
so ``report``/``extract-media`` runs can be replayed against previously
fetched data instead of re-hitting the Gmail API), the two Gmail-client
wrappers built on top of it (``IndexedGmailClient`` transparently caches
through to a real client; ``IndexOnlyGmailClient`` serves exclusively from
the local index and errors if something isn't cached), and the
``index build``/``index stats`` command implementations
(``run_index_build``, ``render_index_build``, ``render_index_stats``).

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10;
this is the "GmailIndex + IndexedGmailClient + IndexOnlyGmailClient + index
build/analyze" subsystem flagged in
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md as the largest
remaining self-contained opportunity, ~1,000 lines). Depends on the standard
library plus gmail_cleanup.constants, gmail_cleanup.models, and
gmail_cleanup.message_utils (all already extracted -- message_utils was
pulled out immediately before this module specifically because GmailIndex
needs several of its leaf helpers), so it moved as the eleventh
self-contained piece. No behavior changes.

The index-analyze command implementation (``run_index_analyze`` and its
supporting helpers) is appended to this same module in a follow-up commit
rather than split into a separate file, per the same "don't over-fragment
the index concern" guidance that shaped this module's boundary.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import sys
import zlib
from collections import Counter, defaultdict
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import parseaddr, parsedate_to_datetime
from pathlib import Path

from gmail_cleanup.constants import LARGE_MEDIA_MIN_PART_BYTES, REQUEST_PROFILE_CONFIG
from gmail_cleanup.message_utils import (
    attachment_categories_for_part,
    attachment_extension,
    derive_attachment_filename,
    header_value,
    human_size,
    infer_attachment_mime_type,
    message_filename_records,
    parse_email_message,
)
from gmail_cleanup.models import GmailMessageRecord, ProgressReporter


def iso_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def private_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not sys.platform.startswith("win"):
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass


def all_header_records(message) -> list[dict[str, str]]:
    return [{"name": str(name), "value": str(value)} for name, value in message.items()]


class GmailIndex:
    schema_version = 1

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        private_parent(self.path)
        self.connection = sqlite3.connect(str(self.path), check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.ensure_schema()
        if not sys.platform.startswith("win"):
            try:
                os.chmod(self.path, 0o600)
            except OSError:
                pass

    def close(self) -> None:
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()

    def ensure_schema(self) -> None:
        self.connection.executescript(
            """
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS messages (
                message_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                history_id TEXT,
                internal_date INTEGER,
                label_ids_json TEXT NOT NULL,
                subject TEXT NOT NULL,
                sender TEXT NOT NULL,
                recipients TEXT NOT NULL,
                date_header TEXT NOT NULL,
                message_id_header TEXT NOT NULL,
                headers_json TEXT NOT NULL,
                filenames_json TEXT NOT NULL,
                raw_zlib BLOB NOT NULL,
                raw_sha256 TEXT NOT NULL,
                raw_size_bytes INTEGER NOT NULL,
                indexed_at TEXT NOT NULL,
                source_query TEXT
            );
            CREATE TABLE IF NOT EXISTS query_matches (
                query TEXT NOT NULL,
                message_id TEXT NOT NULL,
                position INTEGER NOT NULL,
                max_results INTEGER NOT NULL,
                matched_at TEXT NOT NULL,
                PRIMARY KEY (query, message_id)
            );
            CREATE INDEX IF NOT EXISTS idx_query_matches_query_position
                ON query_matches(query, position);
            """
        )
        self.connection.execute(
            "INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)",
            ("schema_version", str(self.schema_version)),
        )
        self.connection.commit()

    def record_query_matches(self, query: str, max_results: int, message_ids: list[str]) -> None:
        matched_at = iso_now()
        with self.connection:
            self.connection.execute("DELETE FROM query_matches WHERE query = ?", (query,))
            self.connection.executemany(
                """
                INSERT INTO query_matches(query, message_id, position, max_results, matched_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (query, message_id, position, max_results, matched_at)
                    for position, message_id in enumerate(message_ids, start=1)
                ],
            )

    def upsert_message(self, record: GmailMessageRecord, *, source_query: str | None = None) -> None:
        message = parse_email_message(record.raw_bytes)
        raw_zlib = sqlite3.Binary(zlib.compress(record.raw_bytes, level=6))
        recipients = ", ".join(
            value
            for value in (
                header_value(message, "To"),
                header_value(message, "Cc"),
                header_value(message, "Bcc"),
            )
            if value
        )
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO messages(
                    message_id, thread_id, history_id, internal_date, label_ids_json,
                    subject, sender, recipients, date_header, message_id_header,
                    headers_json, filenames_json, raw_zlib, raw_sha256, raw_size_bytes,
                    indexed_at, source_query
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(message_id) DO UPDATE SET
                    thread_id = excluded.thread_id,
                    history_id = excluded.history_id,
                    internal_date = excluded.internal_date,
                    label_ids_json = excluded.label_ids_json,
                    subject = excluded.subject,
                    sender = excluded.sender,
                    recipients = excluded.recipients,
                    date_header = excluded.date_header,
                    message_id_header = excluded.message_id_header,
                    headers_json = excluded.headers_json,
                    filenames_json = excluded.filenames_json,
                    raw_zlib = excluded.raw_zlib,
                    raw_sha256 = excluded.raw_sha256,
                    raw_size_bytes = excluded.raw_size_bytes,
                    indexed_at = excluded.indexed_at,
                    source_query = excluded.source_query
                """,
                (
                    record.message_id,
                    record.thread_id,
                    record.history_id,
                    record.internal_date,
                    json.dumps(list(record.label_ids), sort_keys=True),
                    header_value(message, "Subject"),
                    header_value(message, "From"),
                    recipients,
                    header_value(message, "Date"),
                    header_value(message, "Message-ID"),
                    json.dumps(all_header_records(message), sort_keys=True),
                    json.dumps(message_filename_records(message), sort_keys=True),
                    raw_zlib,
                    hashlib.sha256(record.raw_bytes).hexdigest(),
                    len(record.raw_bytes),
                    iso_now(),
                    source_query,
                ),
            )

    def query_is_cached(self, query: str, max_results: int) -> bool:
        row = self.connection.execute(
            """
            SELECT COUNT(*) AS count, COALESCE(MAX(max_results), 0) AS max_requested
            FROM query_matches
            WHERE query = ?
            """,
            (query,),
        ).fetchone()
        count = int(row["count"])
        max_requested = int(row["max_requested"])
        if count == 0:
            return False
        if count >= max_results:
            return True
        return count < max_requested

    def query_message_ids(self, query: str, max_results: int) -> list[str]:
        rows = self.connection.execute(
            """
            SELECT message_id
            FROM query_matches
            WHERE query = ?
            ORDER BY position
            LIMIT ?
            """,
            (query, max_results),
        ).fetchall()
        return [str(row["message_id"]) for row in rows]

    def cached_message_ids(self, message_ids: list[str]) -> set[str]:
        cached: set[str] = set()
        for index in range(0, len(message_ids), 500):
            chunk = message_ids[index : index + 500]
            if not chunk:
                continue
            placeholders = ",".join("?" for _ in chunk)
            rows = self.connection.execute(
                f"SELECT message_id FROM messages WHERE message_id IN ({placeholders})",
                chunk,
            ).fetchall()
            cached.update(str(row["message_id"]) for row in rows)
        return cached

    def get_message(self, message_id: str) -> GmailMessageRecord | None:
        row = self.connection.execute(
            """
            SELECT message_id, thread_id, history_id, internal_date, label_ids_json, raw_zlib
            FROM messages
            WHERE message_id = ?
            """,
            (message_id,),
        ).fetchone()
        if row is None:
            return None
        return GmailMessageRecord(
            message_id=str(row["message_id"]),
            thread_id=str(row["thread_id"]),
            label_ids=tuple(json.loads(str(row["label_ids_json"]))),
            raw_bytes=zlib.decompress(row["raw_zlib"]),
            history_id=str(row["history_id"]) if row["history_id"] is not None else None,
            internal_date=int(row["internal_date"]) if row["internal_date"] is not None else None,
        )

    def message_records(self, *, query: str | None = None, max_results: int | None = None) -> list[GmailMessageRecord]:
        limit = max_results if max_results is not None else -1
        if limit == 0:
            return []
        if query is None:
            rows = self.connection.execute(
                """
                SELECT message_id, thread_id, history_id, internal_date, label_ids_json, raw_zlib
                FROM messages
                ORDER BY COALESCE(internal_date, 0) DESC, message_id
                LIMIT ?
                """,
                (limit,),
            ).fetchall()
        else:
            rows = self.connection.execute(
                """
                SELECT m.message_id, m.thread_id, m.history_id, m.internal_date, m.label_ids_json, m.raw_zlib
                FROM query_matches AS q
                JOIN messages AS m ON m.message_id = q.message_id
                WHERE q.query = ?
                ORDER BY q.position
                LIMIT ?
                """,
                (query, limit),
            ).fetchall()
        return [
            GmailMessageRecord(
                message_id=str(row["message_id"]),
                thread_id=str(row["thread_id"]),
                label_ids=tuple(json.loads(str(row["label_ids_json"]))),
                raw_bytes=zlib.decompress(row["raw_zlib"]),
                history_id=str(row["history_id"]) if row["history_id"] is not None else None,
                internal_date=int(row["internal_date"]) if row["internal_date"] is not None else None,
            )
            for row in rows
        ]

    def stats(self) -> dict[str, object]:
        message_row = self.connection.execute(
            """
            SELECT COUNT(*) AS count,
                   COALESCE(SUM(raw_size_bytes), 0) AS raw_size,
                   COALESCE(SUM(length(raw_zlib)), 0) AS compressed_size
            FROM messages
            """
        ).fetchone()
        query_rows = self.connection.execute(
            """
            SELECT query, COUNT(*) AS count, MAX(matched_at) AS matched_at
            FROM query_matches
            GROUP BY query
            ORDER BY matched_at DESC, query
            """
        ).fetchall()
        return {
            "index_db": str(self.path),
            "message_count": int(message_row["count"]),
            "raw_size_bytes": int(message_row["raw_size"]),
            "compressed_size_bytes": int(message_row["compressed_size"]),
            "queries": [
                {
                    "query": str(row["query"]),
                    "message_count": int(row["count"]),
                    "matched_at": row["matched_at"],
                }
                for row in query_rows
            ],
        }


class IndexedGmailClient:
    def __init__(self, delegate, index: GmailIndex) -> None:
        self.delegate = delegate
        self.index = index

    def close(self) -> None:
        self.index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()

    def list_message_ids(self, query: str, max_results: int) -> list[str]:
        if self.index.query_is_cached(query, max_results):
            return self.index.query_message_ids(query, max_results)
        message_ids = self.delegate.list_message_ids(query, max_results)
        self.index.record_query_matches(query, max_results, message_ids)
        return message_ids

    def get_message_raw(self, message_id: str) -> GmailMessageRecord:
        cached = self.index.get_message(message_id)
        if cached is not None:
            return cached
        record = self.delegate.get_message_raw(message_id)
        self.index.upsert_message(record)
        return record

    def get_message_raw_many(self, message_ids, *, batch_size: int, max_inflight: int):
        ordered: list[GmailMessageRecord | None] = []
        missing: list[str] = []
        for message_id in message_ids:
            cached = self.index.get_message(message_id)
            ordered.append(cached)
            if cached is None:
                missing.append(message_id)
        if missing:
            fetched = self.delegate.get_message_raw_many(missing, batch_size=batch_size, max_inflight=max_inflight)
            fetched_by_id = {record.message_id: record for record in fetched}
            for record in fetched:
                self.index.upsert_message(record)
            for index, message_id in enumerate(message_ids):
                if ordered[index] is None:
                    ordered[index] = fetched_by_id[message_id]
        return [record for record in ordered if record is not None]

    def find_cleanup_replacement_message_id(self, thread_id: str, original_message_id: str) -> str | None:
        return self.delegate.find_cleanup_replacement_message_id(thread_id, original_message_id)

    def insert_message(self, *args, **kwargs) -> str:
        return self.delegate.insert_message(*args, **kwargs)

    def trash_message(self, message_id: str) -> None:
        self.delegate.trash_message(message_id)

    def list_labels(self) -> list[dict[str, object]]:
        return self.delegate.list_labels()

    def get_or_create_label(self, name: str) -> str:
        return self.delegate.get_or_create_label(name)

    def modify_message_labels(self, message_id: str, add_label_ids: tuple[str, ...]) -> None:
        self.delegate.modify_message_labels(message_id, add_label_ids)


class IndexOnlyGmailClient:
    def __init__(self, index: GmailIndex) -> None:
        self.index = index

    def close(self) -> None:
        self.index.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        del exc_type, exc, traceback
        self.close()

    def list_message_ids(self, query: str, max_results: int) -> list[str]:
        if not self.index.query_is_cached(query, max_results):
            raise RuntimeError(
                "Local index does not contain enough cached messages for this query and limit. "
                "Run `gmail-cleanup index build` first, or omit --use-index so Gmail can be queried."
            )
        return self.index.query_message_ids(query, max_results)

    def get_message_raw(self, message_id: str) -> GmailMessageRecord:
        record = self.index.get_message(message_id)
        if record is None:
            raise RuntimeError(f"Local index is missing raw message: {message_id}")
        return record

    def get_message_raw_many(self, message_ids, *, batch_size: int, max_inflight: int):
        del batch_size, max_inflight
        records: list[GmailMessageRecord] = []
        missing: list[str] = []
        for message_id in message_ids:
            record = self.index.get_message(message_id)
            if record is None:
                missing.append(message_id)
            else:
                records.append(record)
        if missing:
            raise RuntimeError(f"Local index is missing {len(missing)} raw message(s): {', '.join(missing[:5])}")
        return records


def run_index_build(
    client,
    query: str,
    max_results: int,
    index_db: Path,
    *,
    request_profile: str = "moderate",
    progress_format: str = "text",
    verbose: int = 0,
) -> dict[str, object]:
    if max_results < 1:
        raise ValueError("--max-results must be 1 or greater")
    reporter = ProgressReporter(verbose=verbose, progress_format=progress_format)
    gmail_index = GmailIndex(index_db)
    try:
        reporter.log_event(
            1,
            f"Searching Gmail with query {query!r} for index build (max_results={max_results})",
            "index_search_started",
            query=query,
            max_results=max_results,
        )
        message_ids = client.list_message_ids(query, max_results)
        gmail_index.record_query_matches(query, max_results, message_ids)
        already_cached = gmail_index.cached_message_ids(message_ids)
        message_ids_to_fetch = [message_id for message_id in message_ids if message_id not in already_cached]
        reporter.log_event(
            1,
            f"Gmail matched {len(message_ids)} message(s); {len(already_cached)} already cached, fetching {len(message_ids_to_fetch)}",
            "index_match_count",
            cached_messages=len(already_cached),
            fetch_messages=len(message_ids_to_fetch),
            query=query,
            matched_messages=len(message_ids),
        )
        profile_config = REQUEST_PROFILE_CONFIG[request_profile]
        batch_size = int(profile_config["batch_size"])
        max_inflight = int(profile_config["max_inflight"])
        cached = len(already_cached)
        fetched = 0
        raw_size_bytes = 0
        cursor = 0
        while cursor < len(message_ids_to_fetch):
            chunk_ids = message_ids_to_fetch[cursor : cursor + batch_size * max_inflight]
            records = client.get_message_raw_many(chunk_ids, batch_size=batch_size, max_inflight=max_inflight)
            for record in records:
                gmail_index.upsert_message(record, source_query=query)
                cached += 1
                fetched += 1
                raw_size_bytes += len(record.raw_bytes)
            cursor += len(records)
            reporter.log_event(
                1,
                f"Cached {cached}/{len(message_ids)} message(s) into {index_db}",
                "index_cache_progress",
                cached_messages=cached,
                matched_messages=len(message_ids),
            )
        stats = gmail_index.stats()
        return {
            "cached_messages": cached,
            "fetched_messages": fetched,
            "index": stats,
            "matched_messages": len(message_ids),
            "mode": "index-build",
            "query": query,
            "raw_size_bytes": raw_size_bytes,
            "reused_cached_messages": len(already_cached),
            "request_profile": request_profile,
        }
    finally:
        gmail_index.close()


def render_index_build(summary: dict[str, object]) -> str:
    index = summary["index"]
    return "\n".join(
        [
            f"Mode: {summary['mode']}",
            f"Query: {summary['query']}",
            f"Index DB: {index['index_db']}",
            f"Matched Gmail messages: {summary['matched_messages']}",
            f"Cached messages: {summary['cached_messages']}",
            f"Fetched this run: {summary['fetched_messages']}",
            f"Reused from index: {summary['reused_cached_messages']}",
            f"Fetched raw size: {human_size(int(summary['raw_size_bytes']))}",
            f"Total indexed messages: {index['message_count']}",
            f"Compressed index payload: {human_size(int(index['compressed_size_bytes']))}",
        ]
    )


def render_index_stats(stats: dict[str, object]) -> str:
    lines = [
        "Mode: index-stats",
        f"Index DB: {stats['index_db']}",
        f"Indexed messages: {stats['message_count']}",
        f"Raw message bytes: {human_size(int(stats['raw_size_bytes']))}",
        f"Compressed payload bytes: {human_size(int(stats['compressed_size_bytes']))}",
    ]
    for query in stats["queries"]:
        lines.append(f"- {query['message_count']} message(s): {query['query']}")
    return "\n".join(lines)


def message_sender_domain(message: EmailMessage) -> str:
    address = parseaddr(header_value(message, "From"))[1].strip().lower()
    if "@" not in address:
        return "unknown"
    return address.rsplit("@", 1)[1]


def message_year(message: EmailMessage) -> int | None:
    try:
        return parsedate_to_datetime(header_value(message, "Date")).year
    except (TypeError, ValueError, IndexError, OverflowError):
        return None


def is_analyzable_attachment_part(part: EmailMessage) -> bool:
    if part.is_multipart():
        return False
    disposition = (part.get_content_disposition() or "").lower()
    if part.get_filename() or disposition in {"attachment", "inline"}:
        return True
    if part.get("Content-ID") and part.get_content_maintype().lower() in {"image", "video"}:
        return True
    return False


def counter_items(counter: Counter, *, top: int, include_bytes: Counter | None = None) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for key, count in counter.most_common(top):
        row: dict[str, object] = {"key": key, "count": count}
        if include_bytes is not None:
            size = int(include_bytes[key])
            row["bytes"] = size
            row["human"] = human_size(size)
        rows.append(row)
    return rows


def top_bytes_items(counter: Counter, *, top: int) -> list[dict[str, object]]:
    return [
        {
            "key": key,
            "bytes": int(size),
            "human": human_size(int(size)),
        }
        for key, size in counter.most_common(top)
    ]


def indexed_cleanup_suggestions(query: str | None) -> list[dict[str, str]]:
    base_query = query or "has:attachment -in:trash -in:spam"
    base = f"gmail-cleanup report --query {json.dumps(base_query)} --max-results 50000 --use-index"
    return [
        {
            "name": "large-media",
            "command": f"{base} --types image,video --min-message-bytes 1000000",
        },
        {
            "name": "office",
            "command": f"{base} --types office",
        },
        {
            "name": "archive",
            "command": f"{base} --types archive",
        },
        {
            "name": "audio",
            "command": f"{base} --types audio",
        },
        {
            "name": "older-than-2018-media",
            "command": f"{base} --types image,video --before-year 2018",
        },
    ]


def run_index_analyze(index_db: Path, *, query: str | None = None, max_results: int | None = None, top: int = 20) -> dict[str, object]:
    if max_results is not None and max_results < 1:
        raise ValueError("--max-results must be 1 or greater")
    if top < 1:
        raise ValueError("--top must be 1 or greater")
    gmail_index = GmailIndex(index_db)
    try:
        records = gmail_index.message_records(query=query, max_results=max_results)
    finally:
        gmail_index.close()
    if query is not None and not records:
        raise ValueError(f"No cached messages found for query: {query}")

    category_parts: Counter = Counter()
    category_bytes: Counter = Counter()
    category_messages: dict[str, set[str]] = defaultdict(set)
    disposition_counts: Counter = Counter()
    duplicate_payloads: dict[str, list[dict[str, object]]] = defaultdict(list)
    extension_counts: Counter = Counter()
    extension_bytes: Counter = Counter()
    mime_counts: Counter = Counter()
    mime_bytes: Counter = Counter()
    sender_counts: Counter = Counter()
    sender_bytes: Counter = Counter()
    year_counts: Counter = Counter()
    year_bytes: Counter = Counter()
    largest_messages: list[dict[str, object]] = []
    attachment_parts = 0
    attachment_bytes = 0

    for record in records:
        message = parse_email_message(record.raw_bytes)
        domain = message_sender_domain(message)
        year = message_year(message)
        if year is not None:
            year_counts[str(year)] += 1
        sender_counts[domain] += 1
        message_attachment_bytes = 0
        message_parts = 0
        biggest_part: dict[str, object] | None = None
        for part in message.walk():
            if not is_analyzable_attachment_part(part):
                continue
            payload = part.get_payload(decode=True) or b""
            size = len(payload)
            filename = derive_attachment_filename(part, message_parts + 1)
            mime_type = infer_attachment_mime_type(part)
            extension = attachment_extension(filename) or "(none)"
            categories = attachment_categories_for_part(part)
            if "media" in categories and size >= LARGE_MEDIA_MIN_PART_BYTES:
                categories.add("large-media")
            attachment_parts += 1
            attachment_bytes += size
            message_parts += 1
            message_attachment_bytes += size
            disposition = (part.get_content_disposition() or "(none)").lower()
            disposition_counts[disposition] += 1
            extension_counts[extension] += 1
            extension_bytes[extension] += size
            mime_counts[mime_type] += 1
            mime_bytes[mime_type] += size
            for category in categories:
                category_parts[category] += 1
                category_bytes[category] += size
                category_messages[category].add(record.message_id)
            if payload:
                duplicate_payloads[hashlib.sha256(payload).hexdigest()].append(
                    {
                        "message_id": record.message_id,
                        "filename": filename,
                        "mime_type": mime_type,
                        "size_bytes": size,
                        "sender_domain": domain,
                    }
                )
            if biggest_part is None or size > int(biggest_part["size_bytes"]):
                biggest_part = {
                    "filename": filename,
                    "mime_type": mime_type,
                    "size_bytes": size,
                    "human": human_size(size),
                }
        sender_bytes[domain] += message_attachment_bytes
        if year is not None:
            year_bytes[str(year)] += message_attachment_bytes
        if message_parts:
            largest_messages.append(
                {
                    "attachment_bytes": message_attachment_bytes,
                    "attachment_human": human_size(message_attachment_bytes),
                    "biggest_part": biggest_part,
                    "message_id": record.message_id,
                    "sender_domain": domain,
                    "subject": header_value(message, "Subject"),
                }
            )

    duplicate_groups = [items for items in duplicate_payloads.values() if len(items) > 1]
    duplicate_groups.sort(key=lambda items: (len(items) - 1) * int(items[0]["size_bytes"]), reverse=True)
    duplicate_reclaimable = sum((len(items) - 1) * int(items[0]["size_bytes"]) for items in duplicate_groups)
    categories = [
        {
            "bytes": int(category_bytes[name]),
            "human": human_size(int(category_bytes[name])),
            "messages": len(category_messages[name]),
            "name": name,
            "parts": int(category_parts[name]),
        }
        for name in sorted(category_parts, key=lambda item: (-category_bytes[item], item))
    ]
    return {
        "attachment_bytes": attachment_bytes,
        "attachment_human": human_size(attachment_bytes),
        "attachment_parts": attachment_parts,
        "categories": categories,
        "dispositions": counter_items(disposition_counts, top=top),
        "duplicates": {
            "groups": len(duplicate_groups),
            "instances": sum(len(items) for items in duplicate_groups),
            "reclaimable_bytes": duplicate_reclaimable,
            "reclaimable_human": human_size(duplicate_reclaimable),
            "top_groups": [
                {
                    "each_bytes": int(items[0]["size_bytes"]),
                    "each_human": human_size(int(items[0]["size_bytes"])),
                    "filename": items[0]["filename"],
                    "instances": len(items),
                    "mime_type": items[0]["mime_type"],
                    "reclaimable_bytes": (len(items) - 1) * int(items[0]["size_bytes"]),
                    "reclaimable_human": human_size((len(items) - 1) * int(items[0]["size_bytes"])),
                    "sample_sender_domains": sorted({str(item["sender_domain"]) for item in items})[:5],
                }
                for items in duplicate_groups[:top]
            ],
        },
        "extensions_by_bytes": top_bytes_items(extension_bytes, top=top),
        "extensions_by_count": counter_items(extension_counts, top=top, include_bytes=extension_bytes),
        "index_db": str(index_db),
        "largest_messages": sorted(largest_messages, key=lambda item: int(item["attachment_bytes"]), reverse=True)[:top],
        "messages_analyzed": len(records),
        "mimes_by_bytes": top_bytes_items(mime_bytes, top=top),
        "mimes_by_count": counter_items(mime_counts, top=top, include_bytes=mime_bytes),
        "mode": "index-analyze",
        "query": query,
        "sender_domains_by_bytes": top_bytes_items(sender_bytes, top=top),
        "sender_domains_by_count": counter_items(sender_counts, top=top, include_bytes=sender_bytes),
        "suggested_reports": indexed_cleanup_suggestions(query),
        "years": [
            {
                "bytes": int(year_bytes[year]),
                "count": int(year_counts[year]),
                "human": human_size(int(year_bytes[year])),
                "year": year,
            }
            for year in sorted(year_counts)
        ],
    }


def render_index_analyze(summary: dict[str, object]) -> str:
    lines = [
        f"Mode: {summary['mode']}",
        f"Index DB: {summary['index_db']}",
        f"Query: {summary['query'] or '(all indexed messages)'}",
        f"Messages analyzed: {summary['messages_analyzed']}",
        f"Attachment parts: {summary['attachment_parts']}",
        f"Attachment bytes: {summary['attachment_human']}",
        "Selectors by bytes:",
    ]
    for category in summary["categories"]:
        lines.append(
            f"- {category['name']}: {category['messages']} message(s), "
            f"{category['parts']} part(s), {category['human']}"
        )
    duplicates = summary["duplicates"]
    lines.extend(
        [
            "Duplicates:",
            f"- groups: {duplicates['groups']}",
            f"- instances: {duplicates['instances']}",
            f"- reclaimable estimate: {duplicates['reclaimable_human']}",
            "Top extensions by bytes:",
        ]
    )
    for item in summary["extensions_by_bytes"]:
        lines.append(f"- {item['key']}: {item['human']}")
    lines.append("Suggested report commands:")
    for suggestion in summary["suggested_reports"]:
        lines.append(f"- {suggestion['name']}: {suggestion['command']}")
    return "\n".join(lines)
