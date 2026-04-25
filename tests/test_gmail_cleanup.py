from __future__ import annotations

import json
import os
import ssl
import tempfile
import threading
import unittest
from contextlib import redirect_stderr
from datetime import datetime, timezone
from email.message import EmailMessage
from io import StringIO
from pathlib import Path
from unittest import mock

from tests.support import load_script_module


class FakeGmailClient:
    def __init__(self, gmail_cleanup, records) -> None:
        self.gmail_cleanup = gmail_cleanup
        self.records = {record.message_id: record for record in records}
        self.inserted: list[dict[str, object]] = []
        self.existing_replacements: dict[str, str] = {}
        self.list_calls = 0
        self.label_ids_by_name: dict[str, str] = {}
        self.modified_labels: list[tuple[str, tuple[str, ...]]] = []
        self.raw_many_calls = 0
        self.trashed: list[str] = []

    def list_message_ids(self, query: str, max_results: int) -> list[str]:
        del query
        self.list_calls += 1
        return list(self.records)[:max_results]

    def get_message_raw(self, message_id: str):
        return self.records[message_id]

    def get_message_raw_many(self, message_ids, *, batch_size: int, max_inflight: int):
        del batch_size, max_inflight
        self.raw_many_calls += 1
        return [self.records[message_id] for message_id in message_ids]

    def find_cleanup_replacement_message_id(self, thread_id: str, original_message_id: str) -> str | None:
        del thread_id
        return self.existing_replacements.get(original_message_id)

    def insert_message(
        self,
        thread_id: str,
        label_ids: tuple[str, ...],
        raw_bytes: bytes,
        *,
        original_message_id: str | None = None,
    ) -> str:
        del original_message_id
        new_id = f"inserted-{len(self.inserted) + 1}"
        self.inserted.append(
            {
                "label_ids": label_ids,
                "new_id": new_id,
                "raw_bytes": raw_bytes,
                "thread_id": thread_id,
            }
        )
        return new_id

    def trash_message(self, message_id: str) -> None:
        self.trashed.append(message_id)

    def get_or_create_label(self, name: str) -> str:
        return self.label_ids_by_name.setdefault(name, f"Label_{len(self.label_ids_by_name) + 1}")

    def modify_message_labels(self, message_id: str, add_label_ids: tuple[str, ...]) -> None:
        self.modified_labels.append((message_id, add_label_ids))


class GmailCleanupTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.gmail_cleanup = load_script_module("gmail-cleanup")

    def default_settings(self):
        return self.gmail_cleanup.default_extraction_settings()

    def build_message(self) -> EmailMessage:
        message = EmailMessage()
        message["Subject"] = "Quarterly update"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        message["Message-ID"] = "<original@example.com>"
        message["Authentication-Results"] = "mx.example.com; dkim=pass"
        message.set_content("Hello from the original email body.")
        message.add_attachment(
            b"JPEGDATA",
            maintype="image",
            subtype="jpeg",
            filename="photo.jpg",
        )
        message.add_attachment(
            b"%PDF-1.7",
            maintype="application",
            subtype="pdf",
            filename="report.pdf",
        )
        message.add_attachment(
            b"VIDEODATA",
            maintype="video",
            subtype="mp4",
            filename="clip.mp4",
        )
        return message

    def build_record(self, message_id: str = "msg-1"):
        message = self.build_message()
        return self.gmail_cleanup.GmailMessageRecord(
            message_id=message_id,
            thread_id="thread-1",
            label_ids=("INBOX", "UNREAD"),
            raw_bytes=message.as_bytes(),
        )

    def build_signed_record(self, message_id: str = "signed-1"):
        message = EmailMessage()
        message["Subject"] = "Signed mail"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        body = EmailMessage()
        body.set_content("Hello")
        signature = EmailMessage()
        signature.set_type("application/pgp-signature")
        signature.set_payload("signature")
        message.set_type("multipart/signed")
        message.set_param("protocol", "application/pgp-signature")
        message.set_payload([body, signature])
        return self.gmail_cleanup.GmailMessageRecord(
            message_id=message_id,
            thread_id=f"thread-{message_id}",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )

    def test_plan_message_selects_only_image_and_video_attachments(self) -> None:
        plan = self.gmail_cleanup.plan_message(self.build_record())

        self.assertEqual(plan.subject, "Quarterly update")
        self.assertEqual(len(plan.media_parts), 2)
        self.assertEqual(
            [part.filename for part in plan.media_parts],
            ["photo.jpg", "clip.mp4"],
        )
        self.assertEqual(
            [part.mime_type for part in plan.media_parts],
            ["image/jpeg", "video/mp4"],
        )
        self.assertEqual(
            [part.saved_filename for part in plan.media_parts],
            ["gcm-msg-1-01__photo.jpg", "gcm-msg-1-02__clip.mp4"],
        )
        self.assertEqual(
            [part.search_token for part in plan.media_parts],
            ["gcm-msg-1-01", "gcm-msg-1-02"],
        )

    def test_rewrite_message_removes_media_and_adds_visible_note(self) -> None:
        plan = self.gmail_cleanup.plan_message(self.build_record())

        rewritten_raw, buffered = self.gmail_cleanup.rewrite_message_for_backup(
            plan,
            datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            backup_folder_name=plan.message_id,
            operation_id="op-123",
        )
        rewritten = self.gmail_cleanup.parse_email_message(rewritten_raw)

        filenames = [part.get_filename() for part in rewritten.walk() if part.get_filename()]
        self.assertEqual(filenames, ["report.pdf"])
        self.assertEqual([part.filename for part in buffered], ["photo.jpg", "clip.mp4"])
        self.assertEqual([part.saved_filename for part in buffered], ["gcm-msg-1-01__photo.jpg", "gcm-msg-1-02__clip.mp4"])
        self.assertIn("Local media backup note", rewritten.get_body(preferencelist=("plain",)).get_content())
        self.assertIn('saved as "gcm-msg-1-01__photo.jpg"', rewritten.get_body(preferencelist=("plain",)).get_content())
        self.assertIn('search token "gcm-msg-1-01"', rewritten.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("op-123", rewritten["X-Maj-Scripts-Gmail-Cleanup"])
        self.assertNotIn("Message-ID", rewritten)
        self.assertNotIn("Authentication-Results", rewritten)

    def test_rewrite_message_skips_when_removal_would_empty_message(self) -> None:
        plan = self.gmail_cleanup.plan_message(self.build_record())

        with mock.patch.object(self.gmail_cleanup, "prune_selected_parts", return_value=None):
            with self.assertRaises(self.gmail_cleanup.SkippableMessageError):
                self.gmail_cleanup.rewrite_message_for_backup(
                    plan,
                    datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
                    backup_folder_name=plan.message_id,
                    operation_id="op-empty",
                )

    def test_rewrite_message_can_emit_note_only_when_removal_would_empty_message(self) -> None:
        settings = self.gmail_cleanup.default_extraction_settings()
        settings = self.gmail_cleanup.replace(settings, empty_after_removal="note-only")
        plan = self.gmail_cleanup.plan_message(self.build_record())

        with mock.patch.object(self.gmail_cleanup, "prune_selected_parts", return_value=None):
            rewritten_raw, _ = self.gmail_cleanup.rewrite_message_for_backup(
                plan,
                datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
                backup_folder_name=plan.message_id,
                operation_id="op-note-only",
                settings=settings,
            )

        rewritten = self.gmail_cleanup.parse_email_message(rewritten_raw)
        self.assertIn("Local media backup note", rewritten.get_body(preferencelist=("plain",)).get_content())
        self.assertIn("Quarterly update", rewritten["Subject"])

    def test_apply_mode_writes_files_manifest_and_mailbox_changes(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(self.gmail_cleanup, "resolve_exiftool_path", return_value="/usr/bin/exiftool"), mock.patch.object(
                self.gmail_cleanup,
                "read_existing_metadata_tags",
                return_value={},
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                return_value=mock.Mock(stdout="", stderr=""),
            ) as subprocess_run:
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=self.default_settings(),
                )

            self.assertEqual(summary["candidate_messages"], 1)
            self.assertEqual(len(summary["applied"]), 1)
            self.assertEqual(len(client.inserted), 1)
            self.assertEqual(client.trashed, ["msg-1"])

            photo_path = backup_dir / "msg-1" / "gcm-msg-1-01__photo.jpg"
            clip_path = backup_dir / "msg-1" / "gcm-msg-1-02__clip.mp4"
            self.assertTrue(photo_path.is_file())
            self.assertTrue(clip_path.is_file())

            manifest_path = backup_dir / "manifest.jsonl"
            self.assertTrue(manifest_path.is_file())
            record = json.loads(manifest_path.read_text(encoding="utf-8").strip())
            self.assertEqual(record["original_message_id"], "msg-1")
            self.assertEqual(record["new_message_id"], "inserted-1")
            self.assertTrue(record["metadata_embedded"])
            self.assertEqual(
                [item["filename"] for item in record["attachments"]],
                ["gcm-msg-1-01__photo.jpg", "gcm-msg-1-02__clip.mp4"],
            )
            self.assertEqual(
                [item["search_token"] for item in record["attachments"]],
                ["gcm-msg-1-01", "gcm-msg-1-02"],
            )
            self.assertTrue(all(item["metadata_embedded"] for item in record["attachments"]))
            self.assertEqual(subprocess_run.call_count, 2)

            rewritten = self.gmail_cleanup.parse_email_message(client.inserted[0]["raw_bytes"])
            rewritten_filenames = [part.get_filename() for part in rewritten.walk() if part.get_filename()]
            self.assertEqual(rewritten_filenames, ["report.pdf"])
            self.assertIn("Local media backup note", rewritten.get_body(preferencelist=("plain",)).get_content())

            queue_records = self.gmail_cleanup.read_jsonl_records(backup_dir / "apply-queue.jsonl")
            self.assertEqual([item["message_id"] for item in queue_records if item.get("record_type") == "candidate"], ["msg-1"])
            self.assertTrue(any(item.get("record_type") == "inspection_completed" for item in queue_records))

    def test_apply_mode_can_apply_processed_and_review_labels(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record("msg-1"), self.build_signed_record("signed-1")])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(self.gmail_cleanup, "embed_marker_metadata"):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=self.default_settings(),
                    audit_label_settings=self.gmail_cleanup.AuditLabelSettings(
                        processed="gmail-cleanup/processed",
                        review="gmail-cleanup/review",
                    ),
                )

        self.assertEqual(len(summary["applied"]), 1)
        self.assertEqual(len(summary["skipped_messages"]), 1)
        self.assertEqual(
            client.label_ids_by_name,
            {
                "gmail-cleanup/processed": "Label_1",
                "gmail-cleanup/review": "Label_2",
            },
        )
        self.assertIn(("inserted-1", ("Label_1",)), client.modified_labels)
        self.assertIn(("signed-1", ("Label_2",)), client.modified_labels)

    def test_retryable_gmail_write_retries_ssl_eof(self) -> None:
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise ssl.SSLEOFError("EOF occurred in violation of protocol")
            return "ok"

        with mock.patch.object(self.gmail_cleanup.time, "sleep"):
            result = self.gmail_cleanup.execute_retryable_gmail_write(operation, action="insert")

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 2)

    def test_retryable_gmail_write_retries_httplib_read_none_error(self) -> None:
        attempts = {"count": 0}

        def operation():
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise AttributeError("'NoneType' object has no attribute 'read'")
            return "ok"

        with mock.patch.object(self.gmail_cleanup.time, "sleep"):
            result = self.gmail_cleanup.execute_retryable_gmail_write(operation, action="insert")

        self.assertEqual(result, "ok")
        self.assertEqual(attempts["count"], 2)

    def test_apply_mode_skips_already_completed_manifest_record(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            self.gmail_cleanup.append_manifest_record(
                backup_dir / "manifest.jsonl",
                {
                    "action": "extract_media",
                    "attachments": [],
                    "message_backup_folder": "msg-1",
                    "new_message_id": "already-inserted",
                    "original_message_id": "msg-1",
                },
            )
            summary = self.gmail_cleanup.run_extract_media(
                client,
                query="has:attachment",
                backup_dir=backup_dir,
                max_results=25,
                apply_mode=True,
                settings=self.default_settings(),
            )

        self.assertEqual(len(summary["applied"]), 0)
        self.assertEqual([item["new_message_id"] for item in summary["resumed_applied"]], ["already-inserted"])
        self.assertEqual(client.inserted, [])
        self.assertEqual(client.trashed, [])

    def test_apply_mode_loads_persisted_queue_without_listing_gmail(self) -> None:
        record = self.build_record("queued-1")
        client = FakeGmailClient(self.gmail_cleanup, [record])
        settings = self.default_settings()
        plan = self.gmail_cleanup.plan_message(record, settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            self.gmail_cleanup.append_apply_queue_record(backup_dir, "has:attachment", 25, settings, plan)
            self.gmail_cleanup.append_apply_queue_completed_record(backup_dir, "has:attachment", 25, settings, 1)
            with mock.patch.object(self.gmail_cleanup, "resolve_exiftool_path", return_value="/usr/bin/exiftool"), mock.patch.object(
                self.gmail_cleanup,
                "read_existing_metadata_tags",
                return_value={},
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                return_value=mock.Mock(stdout="", stderr=""),
            ):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )

        self.assertEqual(client.list_calls, 0)
        self.assertEqual(len(summary["applied"]), 1)
        self.assertEqual(summary["applied"][0]["original_message_id"], "queued-1")

    def test_apply_mode_ignores_partial_persisted_queue_and_lists_gmail(self) -> None:
        record = self.build_record("queued-1")
        client = FakeGmailClient(self.gmail_cleanup, [record])
        settings = self.default_settings()
        plan = self.gmail_cleanup.plan_message(record, settings)

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            self.gmail_cleanup.append_apply_queue_record(backup_dir, "has:attachment", 25, settings, plan)
            with mock.patch.object(self.gmail_cleanup, "resolve_exiftool_path", return_value="/usr/bin/exiftool"), mock.patch.object(
                self.gmail_cleanup,
                "read_existing_metadata_tags",
                return_value={},
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                return_value=mock.Mock(stdout="", stderr=""),
            ):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )

        self.assertEqual(client.list_calls, 1)
        self.assertEqual(len(summary["applied"]), 1)

    def test_execute_message_plan_uses_existing_cleanup_copy_before_insert(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])
        client.existing_replacements["msg-1"] = "inserted-before-crash"
        plan = self.gmail_cleanup.plan_message(self.build_record())

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            (backup_dir / "msg-1").mkdir()
            with mock.patch.object(self.gmail_cleanup, "resolve_exiftool_path", return_value="/usr/bin/exiftool"), mock.patch.object(
                self.gmail_cleanup,
                "read_existing_metadata_tags",
                return_value={},
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                return_value=mock.Mock(stdout="", stderr=""),
            ):
                record = self.gmail_cleanup.execute_message_plan(
                    client,
                    plan,
                    backup_dir,
                    query="has:attachment",
                    settings=self.default_settings(),
                )

        self.assertEqual(record["new_message_id"], "inserted-before-crash")
        self.assertEqual(client.inserted, [])
        self.assertEqual(client.trashed, ["msg-1"])

    def test_apply_mode_skips_password_protected_pdf_without_aborting(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="auto",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="auto",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(
                self.gmail_cleanup,
                "pdf_page_count",
                side_effect=RuntimeError("Command Line Error: Incorrect password"),
            ):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="filename:pdf",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )

            self.assertEqual(summary["candidate_messages"], 0)
            self.assertEqual(len(summary["applied"]), 0)
            self.assertEqual(len(summary["skipped_messages"]), 1)
            self.assertIn("password-protected or encrypted PDF", summary["skipped_messages"][0]["skip_reason"])
            self.assertEqual(client.inserted, [])
            self.assertEqual(client.trashed, [])
            self.assertFalse((backup_dir / "msg-1" / "gcm-msg-1-02__report.pdf").exists())

    def test_inline_html_reference_is_replaced_with_searchable_placeholder(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Inline photo"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        message.set_content("Plain fallback")
        message.add_alternative('<html><body><p>Hello</p><img src="cid:inline-photo"></body></html>', subtype="html")
        html_body = message.get_body(preferencelist=("html",))
        assert html_body is not None
        html_body.add_related(
            b"JPEGDATA",
            maintype="image",
            subtype="jpeg",
            cid="<inline-photo>",
            filename="inline.jpg",
            disposition="inline",
        )

        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="inline-1",
            thread_id="thread-inline",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )
        plan = self.gmail_cleanup.plan_message(record)

        rewritten_raw, _ = self.gmail_cleanup.rewrite_message_for_backup(
            plan,
            datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            backup_folder_name=plan.message_id,
            operation_id="op-inline",
        )
        rewritten = self.gmail_cleanup.parse_email_message(rewritten_raw)
        html_content = rewritten.get_body(preferencelist=("html",)).get_content()

        self.assertIn("Inline media removed", html_content)
        self.assertIn("gcm-inline-1-01__inline.jpg", html_content)
        self.assertIn("&quot;gcm-inline-1-01&quot;", html_content)
        self.assertNotIn("<img", html_content)

    def test_prepend_note_upgrades_ascii_body_to_utf8_when_needed(self) -> None:
        part = EmailMessage()
        part.set_content("Existing body", subtype="plain", charset="ascii")

        self.gmail_cleanup.prepend_note(part, "Retained PDF text – sample", html_mode=False)

        self.assertEqual(part.get_content_charset(), "utf-8")
        self.assertIn("Retained PDF text – sample", part.get_content())

    def test_metadata_marker_text_and_write_command_preserve_existing_values(self) -> None:
        attachment = self.gmail_cleanup.WrittenAttachment(
            local_path=Path("/tmp/gcm-msg-1-01__photo.jpg"),
            filename="gcm-msg-1-01__photo.jpg",
            original_filename="photo.jpg",
            search_token="gcm-msg-1-01",
            mime_type="image/jpeg",
            size_bytes=8,
            sha256="abc123",
            relative_path="msg-1/gcm-msg-1-01__photo.jpg",
            disposition="attachment",
            content_id=None,
        )
        plan = self.gmail_cleanup.plan_message(self.build_record())
        marker_text = self.gmail_cleanup.metadata_marker_text(
            attachment,
            plan,
            operation_id="op-123",
            extracted_at=datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
        )
        existing = {
            "ExifIFD:UserComment": "camera note",
            "IFD0:ImageDescription": "existing caption",
            "IPTC:Caption-Abstract": "",
            "XMP-dc:Description": "library caption",
            "XMP-dc:Subject": ["existing-keyword"],
        }

        command = self.gmail_cleanup.build_exiftool_write_command("/usr/bin/exiftool", attachment, marker_text, existing)
        joined = "\n".join(command)

        self.assertIn("gmail-cleanup marker gcm-msg-1-01", marker_text)
        self.assertIn('saved_filename="gcm-msg-1-01__photo.jpg"', marker_text)
        self.assertIn("-EXIF:UserComment=camera note\n\ngmail-cleanup marker gcm-msg-1-01", joined)
        self.assertIn("-EXIF:ImageDescription=existing caption\n\ngmail-cleanup marker gcm-msg-1-01", joined)
        self.assertIn("-XMP-dc:Description=library caption\n\ngmail-cleanup marker gcm-msg-1-01", joined)
        self.assertIn("-XMP-dc:Subject+=gcm-msg-1-01", joined)

    def test_ffmpeg_write_command_preserves_existing_comment_and_description(self) -> None:
        attachment = self.gmail_cleanup.WrittenAttachment(
            local_path=Path("/tmp/gcm-msg-1-02__clip.wmv"),
            filename="gcm-msg-1-02__clip.wmv",
            original_filename="clip.wmv",
            search_token="gcm-msg-1-02",
            mime_type="video/x-ms-wmv",
            size_bytes=8,
            sha256="def456",
            relative_path="msg-1/gcm-msg-1-02__clip.wmv",
            disposition="attachment",
            content_id=None,
        )
        command = self.gmail_cleanup.build_ffmpeg_metadata_write_command(
            "/usr/bin/ffmpeg",
            attachment,
            "gmail-cleanup marker gcm-msg-1-02",
            {"comment": "existing comment", "DESCRIPTION": "existing description"},
            Path("/tmp/output.wmv"),
        )
        joined = "\n".join(command)

        self.assertIn("comment=existing comment\n\ngmail-cleanup marker gcm-msg-1-02", joined)
        self.assertIn("description=existing description\n\ngmail-cleanup marker gcm-msg-1-02", joined)

    def test_embed_marker_metadata_falls_back_to_ffmpeg_for_videos(self) -> None:
        attachment = self.gmail_cleanup.WrittenAttachment(
            local_path=Path("/tmp/gcm-msg-1-02__clip.wmv"),
            filename="gcm-msg-1-02__clip.wmv",
            original_filename="clip.wmv",
            search_token="gcm-msg-1-02",
            mime_type="video/x-ms-wmv",
            size_bytes=8,
            sha256="def456",
            relative_path="msg-1/gcm-msg-1-02__clip.wmv",
            disposition="attachment",
            content_id=None,
        )
        plan = self.gmail_cleanup.plan_message(self.build_record())
        with mock.patch.object(
            self.gmail_cleanup,
            "resolve_exiftool_path",
            return_value="/usr/bin/exiftool",
        ), mock.patch.object(
            self.gmail_cleanup,
            "embed_marker_metadata_with_exiftool",
            side_effect=RuntimeError("wmv unsupported"),
        ) as embed_with_exiftool, mock.patch.object(
            self.gmail_cleanup,
            "embed_marker_metadata_with_ffmpeg",
        ) as embed_with_ffmpeg:
            self.gmail_cleanup.embed_marker_metadata(
                [attachment],
                plan,
                operation_id="op-123",
                extracted_at=datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            )

        embed_with_exiftool.assert_called_once()
        embed_with_ffmpeg.assert_called_once()

    def test_matching_destination_reuses_existing_deterministic_backup_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            existing = directory / "gcm-msg-1-01__photo.jpg"
            existing.write_bytes(b"JPEGDATA")

            matched = self.gmail_cleanup.matching_destination(directory, existing.name, b"JPEGDATA")
            different = self.gmail_cleanup.matching_destination(directory, existing.name, b"OTHERDATA")

            self.assertEqual(matched, existing)
            self.assertEqual(different, existing)

    def test_matching_destination_avoids_non_deterministic_name_collision(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            directory = Path(tmpdir)
            existing = directory / "photo.jpg"
            existing.write_bytes(b"JPEGDATA")

            different = self.gmail_cleanup.matching_destination(directory, existing.name, b"OTHERDATA")

            self.assertEqual(different.name, "photo__2.jpg")

    def test_parser_counts_verbose_flags(self) -> None:
        parser = self.gmail_cleanup.build_parser()
        args = parser.parse_args(["extract-media", "--query", "has:attachment", "-vvv"])

        self.assertEqual(args.verbose, 3)

    def test_pdf_archive_preset_supplies_expected_defaults(self) -> None:
        parser = self.gmail_cleanup.build_parser()
        args = parser.parse_args(["extract-media", "--preset", "pdf-archive"])

        self.gmail_cleanup.apply_preset_defaults(args)
        settings = self.gmail_cleanup.build_extraction_settings(args, {}, Path("/tmp/config.toml"))

        self.assertEqual(args.query, "filename:pdf -in:trash -in:spam")
        self.assertEqual(args.max_results, 5000)
        self.assertEqual(args.request_profile, "conservative")
        self.assertEqual(args.quota_units_per_second, 80.0)
        self.assertEqual(settings.attachment_types, ("pdf",))
        self.assertEqual(settings.pdf_original, "trash")
        self.assertEqual(settings.pdf_password_mode, "low-hanging")
        self.assertEqual(settings.pdf_password_failure_action, "trash-original")
        self.assertEqual(settings.pdf_text_mode, "auto")
        self.assertEqual(settings.empty_after_removal, "note-only")

    def test_report_classifies_actionable_false_positive_and_skipped(self) -> None:
        zip_message = EmailMessage()
        zip_message["Subject"] = "ZIP with pdf in name"
        zip_message["From"] = "sender@example.com"
        zip_message["To"] = "maj@example.com"
        zip_message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        zip_message.set_content("The attachment filename only looks like a PDF search match.")
        zip_message.add_attachment(
            b"ZIPDATA",
            maintype="application",
            subtype="zip",
            filename="manual_pdf.zip",
        )
        zip_record = self.gmail_cleanup.GmailMessageRecord(
            message_id="zip-1",
            thread_id="thread-zip",
            label_ids=("INBOX",),
            raw_bytes=zip_message.as_bytes(),
        )
        settings = self.gmail_cleanup.replace(self.default_settings(), attachment_types=("pdf",))
        client = FakeGmailClient(
            self.gmail_cleanup,
            [self.build_record("msg-1"), zip_record, self.build_signed_record("signed-1")],
        )

        report = self.gmail_cleanup.run_report(
            client,
            "filename:pdf -in:trash -in:spam",
            25,
            settings,
            request_profile="conservative",
        )

        self.assertEqual(report["counts"], {"actionable": 1, "false_positive": 1, "skipped": 1})
        categories = {item["message_id"]: item["category"] for item in report["items"]}
        self.assertEqual(categories["msg-1"], "actionable")
        self.assertEqual(categories["zip-1"], "false_positive")
        self.assertEqual(categories["signed-1"], "skipped")
        self.assertEqual(report["matched_messages"], 3)

    def test_report_marks_exported_and_completed_manifest_status(self) -> None:
        client = FakeGmailClient(
            self.gmail_cleanup,
            [self.build_record("msg-1"), self.build_record("msg-2"), self.build_record("msg-3")],
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            self.gmail_cleanup.append_manifest_record(
                backup_dir / "manifest.jsonl",
                {
                    "action": "export_attachments",
                    "attachments": [{"filename": "photo.mp4"}],
                    "exported_at": "2026-04-24T23:53:30+00:00",
                    "original_message_id": "msg-1",
                },
            )
            self.gmail_cleanup.append_manifest_record(
                backup_dir / "manifest.jsonl",
                {
                    "action": "extract_media",
                    "applied_at": "2026-04-25T00:10:00+00:00",
                    "attachments": [],
                    "new_message_id": "clean-msg-2",
                    "original_message_id": "msg-2",
                },
            )
            report = self.gmail_cleanup.run_report(
                client,
                "has:attachment -in:trash -in:spam",
                25,
                self.default_settings(),
                request_profile="conservative",
                backup_dir=backup_dir,
            )

        self.assertEqual(report["counts"], {"actionable": 3, "false_positive": 0, "skipped": 0})
        self.assertEqual(
            report["local_manifest"]["counts"],
            {"pending": 1, "exported_pending_gmail_sync": 1, "completed": 1},
        )
        self.assertEqual(report["local_manifest"]["pending_backup_candidates"], 1)
        self.assertEqual(report["local_manifest"]["exported_pending_gmail_sync"], 1)
        self.assertEqual(report["local_manifest"]["remaining_gmail_sync_candidates"], 2)
        statuses = {item["message_id"]: item["migration_status"] for item in report["items"]}
        self.assertEqual(statuses["msg-1"], "exported_pending_gmail_sync")
        self.assertEqual(statuses["msg-2"], "completed")
        self.assertEqual(statuses["msg-3"], "pending")

    def test_index_build_caches_raw_messages_for_report(self) -> None:
        settings = self.gmail_cleanup.replace(self.default_settings(), attachment_types=("pdf",))
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record("msg-1"), self.build_record("msg-2")])

        with tempfile.TemporaryDirectory() as tmpdir:
            index_db = Path(tmpdir) / "gmail-index.sqlite"
            summary = self.gmail_cleanup.run_index_build(
                client,
                "filename:pdf -in:trash -in:spam",
                25,
                index_db,
                request_profile="conservative",
            )

            self.assertEqual(summary["matched_messages"], 2)
            self.assertEqual(summary["cached_messages"], 2)
            self.assertEqual(client.list_calls, 1)
            self.assertEqual(client.raw_many_calls, 1)

            rerun = self.gmail_cleanup.run_index_build(
                client,
                "filename:pdf -in:trash -in:spam",
                25,
                index_db,
                request_profile="conservative",
            )
            self.assertEqual(rerun["cached_messages"], 2)
            self.assertEqual(rerun["fetched_messages"], 0)
            self.assertEqual(rerun["reused_cached_messages"], 2)
            self.assertEqual(client.list_calls, 2)
            self.assertEqual(client.raw_many_calls, 1)

            cached_client = self.gmail_cleanup.IndexedGmailClient(
                client,
                self.gmail_cleanup.GmailIndex(index_db),
            )
            report = self.gmail_cleanup.run_report(
                cached_client,
                "filename:pdf -in:trash -in:spam",
                25,
                settings,
                request_profile="conservative",
            )

            self.assertEqual(report["counts"], {"actionable": 2, "false_positive": 0, "skipped": 0})
            self.assertEqual(client.list_calls, 2)
            self.assertEqual(client.raw_many_calls, 1)

    def test_index_fetches_delegate_when_cached_query_is_partial(self) -> None:
        settings = self.gmail_cleanup.replace(self.default_settings(), attachment_types=("pdf",))
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record("msg-1"), self.build_record("msg-2")])

        with tempfile.TemporaryDirectory() as tmpdir:
            index_db = Path(tmpdir) / "gmail-index.sqlite"
            self.gmail_cleanup.run_index_build(
                client,
                "filename:pdf -in:trash -in:spam",
                1,
                index_db,
                request_profile="conservative",
            )

            cached_client = self.gmail_cleanup.IndexedGmailClient(
                client,
                self.gmail_cleanup.GmailIndex(index_db),
            )
            report = self.gmail_cleanup.run_report(
                cached_client,
                "filename:pdf -in:trash -in:spam",
                2,
                settings,
                request_profile="conservative",
            )

            self.assertEqual(report["counts"], {"actionable": 2, "false_positive": 0, "skipped": 0})
            self.assertEqual(client.list_calls, 2)
            self.assertEqual(client.raw_many_calls, 2)

    def test_cleanup_category_selectors_can_target_common_attachment_families(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Mixed files"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message.set_content("Please see attached.")
        message.add_attachment(
            b"DOCX",
            maintype="application",
            subtype="vnd.openxmlformats-officedocument.wordprocessingml.document",
            filename="letter.docx",
        )
        message.add_attachment(b"ZIP", maintype="application", subtype="zip", filename="bundle.zip")
        message.add_attachment(b"MP3", maintype="audio", subtype="mpeg", filename="song.mp3")
        message.add_attachment(b"JS", maintype="application", subtype="x-javascript", filename="script.js")
        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="mixed-1",
            thread_id="thread-mixed",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )

        settings = self.gmail_cleanup.replace(
            self.default_settings(),
            attachment_types=("office", "archive", "audio", "code"),
        )
        plan = self.gmail_cleanup.plan_message(record, settings)

        self.assertEqual(
            [part.filename for part in plan.media_parts],
            ["letter.docx", "bundle.zip", "song.mp3", "script.js"],
        )

    def test_audio_mode_video_writes_mp4_video_artifact(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Audio"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message.set_content("Audio attached.")
        message.add_attachment(b"MP3DATA", maintype="audio", subtype="mpeg", filename="song.mp3")
        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="audio-1",
            thread_id="thread-audio",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )
        settings = self.gmail_cleanup.replace(
            self.default_settings(),
            attachment_types=("audio",),
            audio_mode="video",
        )
        plan = self.gmail_cleanup.plan_message(record, settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(record.raw_bytes), plan)

        def fake_run(command, **kwargs):
            del kwargs
            Path(command[-1]).write_bytes(b"MP4DATA")
            return mock.Mock(returncode=0, stdout="", stderr="")

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(
            self.gmail_cleanup,
            "resolve_ffmpeg_path",
            return_value="ffmpeg",
        ), mock.patch.object(self.gmail_cleanup.subprocess, "run", side_effect=fake_run) as run:
            _, written, _ = self.gmail_cleanup.write_backup_files(
                Path(tmpdir),
                plan,
                plan.message_id,
                buffered,
                settings,
                assume_yes=True,
            )

        self.assertEqual(len(written), 1)
        self.assertEqual(written[0].mime_type, "video/mp4")
        self.assertEqual(written[0].source_attachment_mime_type, "audio/mpeg")
        self.assertEqual(written[0].source_generation, "audio-video")
        self.assertEqual(written[0].filename, "gcm-audio-1-01__song__audio-video.mp4")
        command = run.call_args.args[0]
        self.assertIn("-c:a", command)
        self.assertIn("aac", command)

    def test_export_only_writes_backup_without_changing_gmail(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record("msg-1")])

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(self.gmail_cleanup, "embed_marker_metadata"):
            summary = self.gmail_cleanup.run_extract_media(
                client,
                "has:attachment -in:trash -in:spam",
                Path(tmpdir),
                25,
                False,
                self.default_settings(),
                request_profile="conservative",
                export_only=True,
            )
            records = self.gmail_cleanup.read_jsonl_records(Path(tmpdir) / "manifest.jsonl")

        self.assertEqual(summary["mode"], "export-only")
        self.assertEqual(len(summary["exported"]), 1)
        self.assertEqual(client.inserted, [])
        self.assertEqual(client.trashed, [])
        self.assertEqual(records[0]["action"], "export_attachments")
        self.assertFalse(records[0]["gmail_modified"])

    def test_large_media_preset_filters_by_selected_message_bytes(self) -> None:
        parser = self.gmail_cleanup.build_parser()
        args = parser.parse_args(["report", "--preset", "large-media"])
        self.gmail_cleanup.apply_preset_defaults(args)
        settings = self.gmail_cleanup.build_extraction_settings(args, {}, Path("/tmp/missing.toml"))

        self.assertEqual(settings.attachment_types, ("image", "video"))
        self.assertEqual(settings.min_message_bytes, 1000000)
        self.assertEqual(args.query, "has:attachment -in:trash -in:spam")

    def test_index_analyze_summarizes_cached_attachment_categories(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record("msg-1"), self.build_record("msg-2")])

        with tempfile.TemporaryDirectory() as tmpdir:
            index_db = Path(tmpdir) / "gmail-index.sqlite"
            self.gmail_cleanup.run_index_build(
                client,
                "has:attachment -in:trash -in:spam",
                25,
                index_db,
                request_profile="conservative",
            )
            summary = self.gmail_cleanup.run_index_analyze(
                index_db,
                query="has:attachment -in:trash -in:spam",
                top=5,
            )

            categories = {item["name"]: item for item in summary["categories"]}
            self.assertEqual(summary["messages_analyzed"], 2)
            self.assertEqual(categories["image"]["parts"], 2)
            self.assertEqual(categories["pdf"]["parts"], 2)
            self.assertEqual(categories["video"]["parts"], 2)
            self.assertGreaterEqual(summary["duplicates"]["groups"], 3)

    def test_default_request_profile_uses_quota_aware_moderate(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            config = {}

            profile = self.gmail_cleanup.resolve_request_profile(None, config, config_path)
            quota = self.gmail_cleanup.resolve_quota_units_per_second(None, config, config_path, profile)

        self.assertEqual(profile, "moderate")
        self.assertEqual(quota, 125.0)

    def test_quota_units_per_second_cannot_exceed_google_user_limit(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            config_path = Path(tmpdir) / "config.toml"
            with self.assertRaises(ValueError):
                self.gmail_cleanup.resolve_quota_units_per_second(251.0, {}, config_path, "aggressive")

    def test_password_protected_pdf_error_is_detected(self) -> None:
        self.assertTrue(
            self.gmail_cleanup.is_password_protected_pdf_error(
                RuntimeError("Failed to inspect PDF page count: Command Line Error: Incorrect password")
            )
        )
        self.assertFalse(self.gmail_cleanup.is_password_protected_pdf_error(RuntimeError("pdfinfo missing from PATH")))

    def test_low_hanging_candidates_include_numeric_tails_and_date_range(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Statement for card 123456"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        message.set_content("Your card ending in 123456 is ready. DOB format may be ddmmmyyyy.")
        message.add_attachment(
            b"%PDF-1.7",
            maintype="application",
            subtype="pdf",
            filename="report.pdf",
        )
        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="msg-low",
            thread_id="thread-low",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
            pdf_password_date_range=(2026, 2026),
        )
        plan = self.gmail_cleanup.plan_message(record, settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(record.raw_bytes), plan)[0]

        candidates = self.gmail_cleanup.low_hanging_pdf_password_candidates(plan, buffered, settings)
        values = {item.value for item in candidates}
        recipes = {item.recipe for item in candidates}

        self.assertIn("123456", values)
        self.assertIn("3456", values)
        self.assertIn("01Jan2026", values)
        self.assertIn("last6", recipes)
        self.assertIn("dob_ddmmmyyyy", recipes)

    def test_low_hanging_password_learning_stores_recipe_not_password(self) -> None:
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
        )
        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(plan.raw_bytes), plan)[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            recipe_store = Path(tmpdir) / "recipes.json"
            with mock.patch.object(self.gmail_cleanup, "PASSWORD_RECIPE_STORE_PATH", recipe_store):
                self.gmail_cleanup.learn_password_recipe(plan, buffered, "last4")

            recipe_text = recipe_store.read_text(encoding="utf-8")
            self.assertIn("last4", recipe_text)
            self.assertNotIn("3456", recipe_text)

    def test_learned_password_secret_is_reused_before_generated_candidates(self) -> None:
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
        )
        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(plan.raw_bytes), plan)[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            secret_store = Path(tmpdir) / "secrets.json"
            with mock.patch.object(self.gmail_cleanup, "PASSWORD_SECRET_STORE_PATH", secret_store):
                self.gmail_cleanup.learn_password_secret(plan, buffered, "654321")
                cached = self.gmail_cleanup.cached_password_candidates(plan, buffered)

        self.assertEqual([item.value for item in cached], ["654321"])
        self.assertEqual([item.recipe for item in cached], ["cached"])

    def test_pdf_password_family_backoff_skips_after_failure_limit(self) -> None:
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
            pdf_password_date_range=(2026, 2026),
            pdf_password_family_fail_limit=1,
        )
        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(plan.raw_bytes), plan)[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_pdf = Path(tmpdir) / "report.pdf"
            staged_pdf.write_bytes(b"%PDF-1.7")
            failure_store = Path(tmpdir) / "failures.json"
            with mock.patch.object(self.gmail_cleanup, "PASSWORD_FAILURE_STORE_PATH", failure_store), mock.patch.object(
                self.gmail_cleanup,
                "select_pdf_password_backend",
                return_value="john",
            ), mock.patch.object(
                self.gmail_cleanup,
                "resolve_pdf_password_with_backend",
                return_value=None,
            ) as resolve_with_backend:
                first_password, first_recipes = self.gmail_cleanup.resolve_pdf_password(
                    plan,
                    buffered,
                    settings,
                    staged_pdf,
                )
                resolve_with_backend.reset_mock()
                second_password, second_recipes = self.gmail_cleanup.resolve_pdf_password(
                    plan,
                    buffered,
                    settings,
                    staged_pdf,
                )

        self.assertIsNone(first_password)
        self.assertIn("dob_ddmmmyyyy", first_recipes)
        self.assertIsNone(second_password)
        self.assertIn("family-backoff", second_recipes)
        resolve_with_backend.assert_not_called()

    def test_cached_pdf_password_is_tried_despite_family_backoff(self) -> None:
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
            pdf_password_date_range=(2026, 2026),
            pdf_password_family_fail_limit=1,
        )
        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(plan.raw_bytes), plan)[0]

        with tempfile.TemporaryDirectory() as tmpdir:
            staged_pdf = Path(tmpdir) / "report.pdf"
            staged_pdf.write_bytes(b"%PDF-1.7")
            secret_store = Path(tmpdir) / "secrets.json"
            failure_store = Path(tmpdir) / "failures.json"
            with mock.patch.object(self.gmail_cleanup, "PASSWORD_SECRET_STORE_PATH", secret_store), mock.patch.object(
                self.gmail_cleanup,
                "PASSWORD_FAILURE_STORE_PATH",
                failure_store,
            ), mock.patch.object(
                self.gmail_cleanup,
                "select_pdf_password_backend",
                return_value="john",
            ), mock.patch.object(
                self.gmail_cleanup,
                "resolve_pdf_password_with_backend",
                return_value="654321",
            ) as resolve_with_backend:
                self.gmail_cleanup.learn_password_secret(plan, buffered, "654321")
                self.gmail_cleanup.record_password_family_failure(
                    plan,
                    buffered,
                    backend="john",
                    attempted_recipes=("last6",),
                )
                password, recipes = self.gmail_cleanup.resolve_pdf_password(
                    plan,
                    buffered,
                    settings,
                    staged_pdf,
                )
                candidate_values = [candidate.value for candidate in resolve_with_backend.call_args.args[2]]
                candidate_recipes = [candidate.recipe for candidate in resolve_with_backend.call_args.args[2]]
                failure_count = self.gmail_cleanup.password_family_failure_count(plan, buffered)

        self.assertEqual(password, "654321")
        self.assertEqual(candidate_values, ["654321"])
        self.assertEqual(candidate_recipes, ["cached"])
        self.assertIn("family-backoff", recipes)
        self.assertEqual(failure_count, 0)

    def test_select_pdf_password_backend_prefers_john_with_pdf2john(self) -> None:
        settings = self.gmail_cleanup.default_extraction_settings()
        with mock.patch.object(self.gmail_cleanup, "optional_tool_path", side_effect=lambda name: "/usr/bin/john" if name == "john" else None), mock.patch.object(
            self.gmail_cleanup,
            "find_pdf2john_path",
            return_value=Path("/usr/share/john/pdf2john.py"),
        ):
            backend = self.gmail_cleanup.select_pdf_password_backend(settings)

        self.assertEqual(backend, "john")

    def test_parse_pdfcrack_password_extracts_found_password(self) -> None:
        password = self.gmail_cleanup.parse_pdfcrack_password(
            "PDF version 1.6\nfound user-password: '123456'\n"
        )
        self.assertEqual(password, "123456")

    def test_parse_john_show_password_extracts_found_password(self) -> None:
        password = self.gmail_cleanup.parse_john_show_password(
            "document.pdf:987654\n1 password hash cracked, 0 left\n"
        )
        self.assertEqual(password, "987654")

    def test_run_john_candidate_wordlist_uses_resolved_runtime_home(self) -> None:
        candidates = (self.gmail_cleanup.PasswordCandidate("987654", "last6"),)

        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            run_dir = root / "john-jumbo" / "run"
            bin_dir = root / "bin"
            run_dir.mkdir(parents=True)
            bin_dir.mkdir()
            real_john = run_dir / "john"
            real_pdf2john = run_dir / "pdf2john"
            real_john.write_text("#!/bin/sh\n", encoding="utf-8")
            real_pdf2john.write_text("#!/bin/sh\n", encoding="utf-8")
            os.chmod(real_john, 0o755)
            os.chmod(real_pdf2john, 0o755)
            john_link = bin_dir / "john"
            pdf2john_link = bin_dir / "pdf2john"
            john_link.symlink_to(real_john)
            pdf2john_link.symlink_to(real_pdf2john)

            calls: list[dict[str, object]] = []

            def fake_run(args, **kwargs):
                calls.append({"args": args, "kwargs": kwargs})
                if args[0] == str(pdf2john_link):
                    return self.gmail_cleanup.subprocess.CompletedProcess(args, 0, stdout="document.pdf:$pdf$hash\n", stderr="")
                if "--show" in args:
                    return self.gmail_cleanup.subprocess.CompletedProcess(
                        args,
                        0,
                        stdout="document.pdf:987654\n1 password hash cracked, 0 left\n",
                        stderr="",
                    )
                return self.gmail_cleanup.subprocess.CompletedProcess(args, 0, stdout="", stderr="")

            with mock.patch.object(
                self.gmail_cleanup,
                "optional_tool_path",
                side_effect=lambda name: str(john_link) if name == "john" else None,
            ), mock.patch.object(
                self.gmail_cleanup,
                "find_pdf2john_path",
                return_value=pdf2john_link,
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                side_effect=fake_run,
            ):
                password = self.gmail_cleanup.run_john_candidate_wordlist(Path("/tmp/document.pdf"), candidates)

        self.assertEqual(password, "987654")
        john_calls = [call for call in calls if call["args"][0] == str(john_link)]
        self.assertTrue(john_calls)
        for call in john_calls:
            env = call["kwargs"]["env"]
            self.assertEqual(env["JOHN"], str(run_dir.resolve()))
            self.assertIsInstance(call["kwargs"]["cwd"], Path)
            self.assertTrue(call["kwargs"]["cwd"].name.startswith("gmail-cleanup-john-"))
        self.assertTrue(any(arg.startswith("--pot=") for arg in john_calls[0]["args"]))

    def test_resolve_pdf_password_prefers_external_backend_over_builtin_loop(self) -> None:
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_password_mode="low-hanging",
        )
        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)
        buffered = self.gmail_cleanup.collect_buffered_media(self.gmail_cleanup.parse_email_message(plan.raw_bytes), plan)[0]

        with mock.patch.object(
            self.gmail_cleanup,
            "select_pdf_password_backend",
            return_value="pdfcrack",
        ), mock.patch.object(
            self.gmail_cleanup,
            "resolve_pdf_password_with_backend",
            return_value="123456",
        ) as resolve_backend, mock.patch.object(
            self.gmail_cleanup,
            "pdf_page_count",
        ) as pdf_page_count:
            password, attempted = self.gmail_cleanup.resolve_pdf_password(
                plan,
                buffered,
                settings,
                Path("/tmp/fake.pdf"),
            )

        self.assertEqual(password, "123456")
        self.assertTrue(attempted)
        resolve_backend.assert_called_once()
        pdf_page_count.assert_not_called()

    def test_run_extract_media_accepts_more_than_500_results(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            summary = self.gmail_cleanup.run_extract_media(
                client,
                query="has:attachment",
                backup_dir=backup_dir,
                max_results=501,
                apply_mode=False,
                settings=self.default_settings(),
            )

        self.assertEqual(summary["inspected_messages"], 1)
        self.assertEqual(summary["candidate_messages"], 1)

    def test_apply_mode_can_overlap_inspection_and_apply(self) -> None:
        record_one = self.build_record("msg-1")
        record_two = self.build_record("msg-2")
        apply_started = threading.Event()

        class BlockingClient(FakeGmailClient):
            def get_message_raw_many(self, message_ids, *, batch_size: int, max_inflight: int):
                del batch_size, max_inflight
                if message_ids == ["msg-1"]:
                    return [self.records["msg-1"]]
                if message_ids == ["msg-2"]:
                    if not apply_started.wait(timeout=1.0):
                        raise AssertionError("apply did not start before second inspection chunk")
                    return [self.records["msg-2"]]
                raise AssertionError(f"unexpected chunk: {message_ids!r}")

        client = BlockingClient(self.gmail_cleanup, [record_one, record_two])

        def fake_execute_message_plan(client, plan, backup_dir, query, settings, verbose=0, assume_yes=False, **kwargs):
            del client, backup_dir, query, settings, verbose, assume_yes, kwargs
            apply_started.set()
            return {
                "attachments": [],
                "message_backup_folder": plan.message_id,
                "new_message_id": f"new-{plan.message_id}",
                "original_message_id": plan.message_id,
            }

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            conservative = {"batch_size": 1, "max_inflight": 1}
            with mock.patch.dict(self.gmail_cleanup.REQUEST_PROFILE_CONFIG, {"conservative": conservative}, clear=False), mock.patch.object(
                self.gmail_cleanup,
                "execute_message_plan",
                side_effect=fake_execute_message_plan,
            ):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=2,
                    apply_mode=True,
                    settings=self.default_settings(),
                    request_profile="conservative",
                )

        self.assertEqual(summary["candidate_messages"], 2)
        self.assertEqual(len(summary["applied"]), 2)

    def test_inspection_retries_transient_batch_read_error(self) -> None:
        record = self.build_record("msg-1")

        class FlakyReadClient(FakeGmailClient):
            def __init__(self, gmail_cleanup, records) -> None:
                super().__init__(gmail_cleanup, records)
                self.raw_many_calls = 0

            def get_message_raw_many(self, message_ids, *, batch_size: int, max_inflight: int):
                del batch_size, max_inflight
                self.raw_many_calls += 1
                if self.raw_many_calls == 1:
                    raise self.gmail_cleanup.GmailTransientReadError("IncompleteRead(4 bytes read)")
                return [self.records[message_id] for message_id in message_ids]

        client = FlakyReadClient(self.gmail_cleanup, [record])

        with tempfile.TemporaryDirectory() as tmpdir, mock.patch.object(self.gmail_cleanup.time, "sleep"):
            summary = self.gmail_cleanup.run_extract_media(
                client,
                query="has:attachment",
                backup_dir=Path(tmpdir),
                max_results=1,
                apply_mode=False,
                settings=self.default_settings(),
                request_profile="conservative",
            )

        self.assertEqual(client.raw_many_calls, 2)
        self.assertEqual(summary["candidate_messages"], 1)

    def test_verbose_apply_reports_progress_to_stderr(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            stderr = StringIO()
            with redirect_stderr(stderr), mock.patch.object(
                self.gmail_cleanup,
                "resolve_exiftool_path",
                return_value="/usr/bin/exiftool",
            ), mock.patch.object(
                self.gmail_cleanup,
                "read_existing_metadata_tags",
                return_value={},
            ), mock.patch.object(
                self.gmail_cleanup.subprocess,
                "run",
                return_value=mock.Mock(stdout="", stderr=""),
            ):
                self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=self.default_settings(),
                    verbose=2,
                )

        output = stderr.getvalue()
        self.assertIn("Searching Gmail with query", output)
        self.assertIn("Applying 1/1 msg-1", output)
        self.assertIn("Wrote 2 backup file(s) for msg-1", output)
        self.assertIn("Applied 1/1 msg-1 -> inserted-1", output)

    def test_jsonl_progress_reports_key_events(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            stderr = StringIO()
            with redirect_stderr(stderr):
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="has:attachment",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=False,
                    settings=self.default_settings(),
                    progress_format="jsonl",
                )

        events = [json.loads(line)["event"] for line in stderr.getvalue().splitlines() if line.strip()]
        self.assertEqual(summary["matched_messages"], 1)
        self.assertIn("run_started", events)
        self.assertIn("gmail_match_count", events)
        self.assertIn("run_completed", events)

    def test_plan_message_can_include_pdf_when_requested(self) -> None:
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="auto",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="auto",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )

        plan = self.gmail_cleanup.plan_message(self.build_record(), settings)

        self.assertEqual([part.filename for part in plan.media_parts], ["report.pdf"])
        self.assertEqual([part.mime_type for part in plan.media_parts], ["application/pdf"])
        self.assertEqual([part.search_token for part in plan.media_parts], ["gcm-msg-1-01"])

    def test_plan_message_treats_octet_stream_pdf_filename_as_pdf(self) -> None:
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="auto",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="auto",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )
        message = EmailMessage()
        message["Subject"] = "Statement"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message.set_content("Attached.")
        message.add_attachment(
            b"%PDF-1.7",
            maintype="application",
            subtype="octet-stream",
            filename="statement.PDF",
        )
        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="msg-octet",
            thread_id="thread-octet",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )

        plan = self.gmail_cleanup.plan_message(record, settings)

        self.assertEqual([part.filename for part in plan.media_parts], ["statement.PDF"])
        self.assertEqual([part.mime_type for part in plan.media_parts], ["application/pdf"])
        self.assertEqual([part.search_token for part in plan.media_parts], ["gcm-msg-octet-01"])

    def test_rewrite_message_can_remove_pdf_inside_attached_email(self) -> None:
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="auto",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="auto",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )
        inner = EmailMessage()
        inner["Subject"] = "Forwarded attachment"
        inner.set_content("Nested email body.")
        inner.add_attachment(
            b"%PDF-1.7",
            maintype="application",
            subtype="pdf",
            filename="nested.pdf",
        )
        outer = EmailMessage()
        outer["Subject"] = "Outer email"
        outer["From"] = "sender@example.com"
        outer["To"] = "maj@example.com"
        outer.set_content("Outer body.")
        outer.add_attachment(inner)
        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="msg-nested",
            thread_id="thread-nested",
            label_ids=("INBOX",),
            raw_bytes=outer.as_bytes(),
        )

        plan = self.gmail_cleanup.plan_message(record, settings)
        rewritten_raw, buffered = self.gmail_cleanup.rewrite_message_for_backup(
            plan,
            datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            backup_folder_name=plan.message_id,
            operation_id="op-nested",
            settings=settings,
        )
        rewritten = self.gmail_cleanup.parse_email_message(rewritten_raw)
        filenames = [part.get_filename() for part in rewritten.walk() if part.get_filename()]
        body = rewritten.get_body(preferencelist=("plain",)).get_content()

        self.assertEqual([part.filename for part in plan.media_parts], ["nested.pdf"])
        self.assertEqual(buffered[0].path, (1, 0, 1))
        self.assertNotIn("nested.pdf", filenames)
        self.assertIn("nested.pdf", body)
        self.assertIn('"gcm-msg-nested-01"', body)

    def test_pdf_note_uses_group_token_and_page_summary(self) -> None:
        attachments = [
            self.gmail_cleanup.WrittenAttachment(
                local_path=Path("/tmp/gcm-msg-1-01-p001__report__page-001.png"),
                filename="gcm-msg-1-01-p001__report__page-001.png",
                original_filename="report.pdf",
                search_token="gcm-msg-1-01-p001",
                mime_type="image/png",
                size_bytes=1024,
                sha256="abc",
                relative_path="msg-1/gcm-msg-1-01-p001__report__page-001.png",
                disposition="attachment",
                content_id=None,
                group_search_token="gcm-msg-1-01",
                source_attachment_mime_type="application/pdf",
                source_generation="pdf-render",
                source_page_number=1,
            ),
            self.gmail_cleanup.WrittenAttachment(
                local_path=Path("/tmp/gcm-msg-1-01-p002__report__page-002.png"),
                filename="gcm-msg-1-01-p002__report__page-002.png",
                original_filename="report.pdf",
                search_token="gcm-msg-1-01-p002",
                mime_type="image/png",
                size_bytes=2048,
                sha256="def",
                relative_path="msg-1/gcm-msg-1-01-p002__report__page-002.png",
                disposition="attachment",
                content_id=None,
                group_search_token="gcm-msg-1-01",
                source_attachment_mime_type="application/pdf",
                source_generation="pdf-render",
                source_page_number=2,
            ),
        ]

        note = self.gmail_cleanup.build_note_text(
            datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            "op-123",
            "msg-1",
            [],
            written_attachments=attachments,
        )

        self.assertIn('original "report.pdf"', note)
        self.assertIn('group token "gcm-msg-1-01"', note)
        self.assertIn("2 page image(s) saved", note)
        self.assertIn('first file "gcm-msg-1-01-p001__report__page-001.png"', note)

    def test_pdf_note_can_include_retained_text(self) -> None:
        note = self.gmail_cleanup.build_note_text(
            datetime(2026, 4, 24, 4, 15, tzinfo=timezone.utc),
            "op-123",
            "msg-1",
            [],
            written_attachments=[],
            pdf_text_blocks=[
                self.gmail_cleanup.PdfTextBlock(
                    original_filename="report.pdf",
                    group_search_token="gcm-msg-1-01",
                    text="Invoice number 12345\nAmount due 900",
                    source="native",
                )
            ],
        )

        self.assertIn("Retained PDF text:", note)
        self.assertIn("--- report.pdf [\"gcm-msg-1-01\"] (native) ---", note)
        self.assertIn("Amount due 900", note)

    def test_auto_pdf_text_mode_falls_back_to_ocr(self) -> None:
        settings = self.gmail_cleanup.replace(self.gmail_cleanup.default_extraction_settings(), pdf_text_mode="auto")
        media_part = self.gmail_cleanup.BufferedMediaPart(
            path=(1,),
            filename="report.pdf",
            saved_filename="gcm-msg-1-01__report.pdf",
            search_token="gcm-msg-1-01",
            mime_type="application/pdf",
            content_bytes=b"%PDF-1.7\n",
            disposition="attachment",
            content_id=None,
        )
        with mock.patch.object(self.gmail_cleanup, "extract_pdf_text", return_value=""), mock.patch.object(
            self.gmail_cleanup,
            "extract_pdf_ocr_text",
            return_value="Scanned invoice total 900",
        ):
            blocks = self.gmail_cleanup.build_pdf_text_blocks(Path("/tmp/report.pdf"), media_part, settings)

        self.assertEqual([(block.source, block.text) for block in blocks], [("ocr", "Scanned invoice total 900")])

    def test_write_pdf_outputs_trashes_staged_pdf_after_success(self) -> None:
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="render-pages",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="png",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )
        media_part = self.gmail_cleanup.BufferedMediaPart(
            path=(1,),
            filename="report.pdf",
            saved_filename="gcm-msg-1-01__report.pdf",
            search_token="gcm-msg-1-01",
            mime_type="application/pdf",
            content_bytes=b"%PDF-1.7\n",
            disposition="attachment",
            content_id=None,
        )
        rendered_attachment = self.gmail_cleanup.WrittenAttachment(
            local_path=Path("/tmp/gcm-msg-1-01-p001__report__page-001.png"),
            filename="gcm-msg-1-01-p001__report__page-001.png",
            original_filename="report.pdf",
            search_token="gcm-msg-1-01-p001",
            mime_type="image/png",
            size_bytes=512,
            sha256="abc",
            relative_path="msg-1/gcm-msg-1-01-p001__report__page-001.png",
            disposition="attachment",
            content_id=None,
            group_search_token="gcm-msg-1-01",
            source_attachment_mime_type="application/pdf",
            source_generation="pdf-render",
            source_page_number=1,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            message_dir = backup_dir / "msg-1"
            message_dir.mkdir(parents=True, exist_ok=True)
            with mock.patch.object(
                self.gmail_cleanup,
                "pdf_page_count",
                return_value=1,
            ), mock.patch.object(
                self.gmail_cleanup,
                "render_pdf_pages_to_images",
                return_value=[rendered_attachment],
            ), mock.patch.object(
                self.gmail_cleanup,
                "send_path_to_trash",
            ) as send_to_trash:
                written, pdf_text_blocks = self.gmail_cleanup.write_pdf_outputs(
                    backup_dir,
                    message_dir,
                    self.gmail_cleanup.plan_message(self.build_record(), settings),
                    media_part,
                    settings,
                )

        self.assertEqual([item.filename for item in written], ["gcm-msg-1-01-p001__report__page-001.png"])
        self.assertEqual(pdf_text_blocks, [])
        trashed_path = send_to_trash.call_args[0][0]
        self.assertEqual(trashed_path.name, "gcm-msg-1-01__report.pdf")

    def test_apply_mode_records_passworded_pdf_for_manual_review(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])
        settings = self.gmail_cleanup.ExtractionSettings(
            attachment_types=("pdf",),
            pdf_mode="auto",
            pdf_original="trash",
            pdf_password_mode="skip",
            pdf_password_failure_action="skip",
            pdf_password_date_range=(1930, 2035),
            pdf_password_family_fail_limit=3,
            pdf_render_dpi=300,
            pdf_render_format="auto",
            pdf_text_mode="none",
            empty_after_removal="skip",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(
                self.gmail_cleanup,
                "pdf_page_count",
                side_effect=RuntimeError("Command Line Error: Incorrect password"),
            ):
                self.gmail_cleanup.run_extract_media(
                    client,
                    query="filename:pdf",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )
                self.gmail_cleanup.run_extract_media(
                    client,
                    query="filename:pdf",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )

            review_path = backup_dir / "passworded-pdfs.jsonl"
            self.assertTrue(review_path.is_file())
            review_lines = [line for line in review_path.read_text(encoding="utf-8").splitlines() if line.strip()]
            self.assertEqual(len(review_lines), 1)
            review_record = json.loads(review_lines[0])
            self.assertEqual(review_record["action"], "manual_review")
            self.assertEqual(review_record["message_id"], "msg-1")
            self.assertEqual(review_record["attachment_filenames"], ["report.pdf"])
            self.assertIn("password-protected or encrypted PDF", review_record["reason"])

    def test_passworded_pdf_failure_action_trashes_original_and_removes_gmail_attachment(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_original="trash",
            pdf_password_failure_action="trash-original",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(
                self.gmail_cleanup,
                "pdf_page_count",
                side_effect=RuntimeError("Command Line Error: Incorrect password"),
            ), mock.patch.object(
                self.gmail_cleanup,
                "embed_marker_metadata",
            ), mock.patch.object(
                self.gmail_cleanup,
                "send_path_to_trash",
            ) as send_to_trash:
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="filename:pdf",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )
                manifest = json.loads((backup_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(len(summary["applied"]), 1)
        self.assertEqual(client.trashed, ["msg-1"])
        send_to_trash.assert_called_once()
        trashed_path = send_to_trash.call_args[0][0]
        self.assertEqual(trashed_path.name, "gcm-msg-1-01__report.pdf")
        inserted = self.gmail_cleanup.parse_email_message(client.inserted[0]["raw_bytes"])
        attachment_names = [
            part.get_filename()
            for part in inserted.walk()
            if (part.get_content_disposition() or "").lower() == "attachment"
        ]
        self.assertNotIn("report.pdf", attachment_names)
        self.assertIn("photo.jpg", attachment_names)
        self.assertIn("clip.mp4", attachment_names)
        self.assertEqual(
            manifest["attachments"][0]["source_generation"],
            self.gmail_cleanup.PDF_PASSWORDED_ORIGINAL_TRASH_GENERATION,
        )
        self.assertFalse(manifest["attachments"][0]["metadata_embedded"])
        self.assertFalse(manifest["metadata_embedded"])

    def test_unreadable_pdf_failure_action_trashes_original_and_removes_gmail_attachment(self) -> None:
        client = FakeGmailClient(self.gmail_cleanup, [self.build_record()])
        settings = self.gmail_cleanup.replace(
            self.gmail_cleanup.default_extraction_settings(),
            attachment_types=("pdf",),
            pdf_original="trash",
            pdf_password_failure_action="trash-original",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)
            with mock.patch.object(
                self.gmail_cleanup,
                "pdf_page_count",
                side_effect=RuntimeError("Syntax Error: Couldn't find trailer dictionary"),
            ), mock.patch.object(
                self.gmail_cleanup,
                "embed_marker_metadata",
            ), mock.patch.object(
                self.gmail_cleanup,
                "send_path_to_trash",
            ) as send_to_trash:
                summary = self.gmail_cleanup.run_extract_media(
                    client,
                    query="filename:pdf",
                    backup_dir=backup_dir,
                    max_results=25,
                    apply_mode=True,
                    settings=settings,
                )
                manifest = json.loads((backup_dir / "manifest.jsonl").read_text(encoding="utf-8").splitlines()[0])

        self.assertEqual(len(summary["applied"]), 1)
        self.assertEqual(client.trashed, ["msg-1"])
        send_to_trash.assert_called_once()
        inserted = self.gmail_cleanup.parse_email_message(client.inserted[0]["raw_bytes"])
        attachment_names = [
            part.get_filename()
            for part in inserted.walk()
            if (part.get_content_disposition() or "").lower() == "attachment"
        ]
        self.assertNotIn("report.pdf", attachment_names)
        self.assertEqual(
            manifest["attachments"][0]["source_generation"],
            self.gmail_cleanup.PDF_UNREADABLE_ORIGINAL_TRASH_GENERATION,
        )
        self.assertFalse(manifest["attachments"][0]["metadata_embedded"])
        self.assertFalse(manifest["metadata_embedded"])

    def test_linux_trash_uses_xdg_trash_directly(self) -> None:
        path = Path("/tmp/example.pdf")

        with mock.patch.object(
            self.gmail_cleanup,
            "detect_os",
            return_value="linux",
        ), mock.patch.object(
            self.gmail_cleanup,
            "move_path_to_xdg_trash",
        ) as fallback, mock.patch.object(
            self.gmail_cleanup.subprocess,
            "run",
        ) as subprocess_run:
            self.gmail_cleanup.send_path_to_trash(path)

        fallback.assert_called_once_with(path)
        subprocess_run.assert_not_called()

    def test_local_config_can_supply_paths_and_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.toml"
            backup_dir = root / "backup"
            credentials = root / "secrets" / "client.json"
            token_cache = root / "token.json"
            credentials.parent.mkdir(parents=True, exist_ok=True)
            credentials.write_text("{}", encoding="utf-8")
            config_path.write_text(
                "\n".join(
                    (
                        'backup_dir = "backup"',
                        'credentials = "secrets/client.json"',
                        'token_cache = "token.json"',
                        'gmail_user = "maj@example.com"',
                        "max_results = 25",
                        'pdf_password_failure_action = "trash-original"',
                        "pdf_password_family_fail_limit = 4",
                        'request_profile = "conservative"',
                        "quota_units_per_second = 50",
                    )
                ),
                encoding="utf-8",
            )

            config = self.gmail_cleanup.load_config(config_path)

            self.assertEqual(
                self.gmail_cleanup.resolve_backup_dir(None, config, config_path),
                backup_dir.resolve(),
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_credentials_path(None, config, config_path),
                credentials.resolve(),
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_token_cache_path(None, config, config_path),
                token_cache.resolve(),
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_gmail_user(None, config, config_path),
                "maj@example.com",
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_max_results(None, config, config_path),
                25,
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_pdf_password_family_fail_limit(None, False, config, config_path),
                4,
            )
            self.assertEqual(
                self.gmail_cleanup.resolve_pdf_password_failure_action(None, config, config_path),
                "trash-original",
            )
            profile = self.gmail_cleanup.resolve_request_profile(None, config, config_path)
            self.assertEqual(profile, "conservative")
            self.assertEqual(
                self.gmail_cleanup.resolve_quota_units_per_second(None, config, config_path, profile),
                50.0,
            )

    def test_cli_and_env_override_config_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            config_path = root / "config.toml"
            credentials = root / "client.json"
            credentials.write_text("{}", encoding="utf-8")
            config_path.write_text(
                "\n".join(
                    (
                        'backup_dir = "config-backup"',
                        'credentials = "client.json"',
                        "max_results = 25",
                    )
                ),
                encoding="utf-8",
            )
            config = self.gmail_cleanup.load_config(config_path)
            cli_backup = root / "cli-backup"

            with mock.patch.dict(
                os.environ,
                {
                    self.gmail_cleanup.DEFAULT_BACKUP_DIR_ENV: str(root / "env-backup"),
                    self.gmail_cleanup.DEFAULT_MAX_RESULTS_ENV: "13",
                },
                clear=False,
            ):
                self.assertEqual(
                    self.gmail_cleanup.resolve_backup_dir(cli_backup, config, config_path),
                    cli_backup,
                )
                self.assertEqual(
                    self.gmail_cleanup.resolve_max_results(7, config, config_path),
                    7,
                )
                self.assertEqual(
                    self.gmail_cleanup.resolve_backup_dir(None, config, config_path),
                    (root / "env-backup"),
                )
                self.assertEqual(
                    self.gmail_cleanup.resolve_max_results(None, config, config_path),
                    13,
                )

    def test_legacy_config_path_is_used_when_new_path_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            legacy = root / "gmail_cleanup" / "config.toml"
            preferred = root / "gmail-cleanup" / "config.toml"
            legacy.parent.mkdir(parents=True, exist_ok=True)
            legacy.write_text('backup_dir = "backup"\n', encoding="utf-8")

            with mock.patch.object(self.gmail_cleanup, "DEFAULT_CONFIG_PATH", preferred), mock.patch.object(
                self.gmail_cleanup, "LEGACY_CONFIG_PATH", legacy
            ):
                self.assertEqual(self.gmail_cleanup.resolve_config_path(None), legacy)

    def test_signed_or_encrypted_messages_are_skipped(self) -> None:
        message = EmailMessage()
        message["Subject"] = "Signed mail"
        message["From"] = "sender@example.com"
        message["To"] = "maj@example.com"
        message["Date"] = "Thu, 24 Apr 2026 12:00:00 +0800"
        body = EmailMessage()
        body.set_content("Hello")
        signature = EmailMessage()
        signature.set_type("application/pgp-signature")
        signature.set_payload("signature")
        message.set_type("multipart/signed")
        message.set_param("protocol", "application/pgp-signature")
        message.set_payload([body, signature])

        record = self.gmail_cleanup.GmailMessageRecord(
            message_id="signed-1",
            thread_id="thread-signed",
            label_ids=("INBOX",),
            raw_bytes=message.as_bytes(),
        )
        plan = self.gmail_cleanup.plan_message(record)

        self.assertEqual(plan.skip_reason, "signed or encrypted messages are skipped")
        self.assertEqual(plan.media_parts, ())
