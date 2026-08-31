"""Gmail API client for gmail-cleanup: lazy-loading the Google API client
libraries (with an interactive install prompt on first missing-dependency
run), OAuth token refresh/re-auth, the GmailApiClient wrapper around the
Gmail REST API (list/get/insert/trash/label with quota pacing and retry),
and raw-message base64 encode/decode helpers.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
Depends only on the standard library plus gmail_cleanup.constants,
gmail_cleanup.models, gmail_cleanup.system_tools, and
gmail_cleanup.gmail_retry (all already extracted), so it moved as the
ninth self-contained piece. No behavior changes.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import sys
import time

from gmail_cleanup.constants import (
    GMAIL_HTTP_TIMEOUT_SECONDS,
    GMAIL_QUOTA_LABELS_CREATE,
    GMAIL_QUOTA_LABELS_LIST,
    GMAIL_QUOTA_MESSAGES_GET,
    GMAIL_QUOTA_MESSAGES_INSERT,
    GMAIL_QUOTA_MESSAGES_LIST,
    GMAIL_QUOTA_MESSAGES_MODIFY,
    GMAIL_QUOTA_MESSAGES_TRASH,
    GMAIL_QUOTA_THREADS_GET,
    GMAIL_WRITE_MAX_ATTEMPTS,
    SKIPPED_LABEL_IDS,
)
from gmail_cleanup.gmail_retry import (
    execute_retryable_gmail_write,
    gmail_retry_delay,
    is_invalid_scope_refresh_error,
    is_retryable_gmail_request_error,
    is_retryable_gmail_transport_error,
    is_retryable_gmail_write_error,
)
from gmail_cleanup.models import (
    BatchFetchResult,
    GmailMessageRecord,
    GmailQuotaPacer,
    GmailRateLimitError,
    GmailTransientReadError,
)
from gmail_cleanup.system_tools import (
    confirm,
    dependency_install_command,
    detect_os,
    detect_pkg_manager,
    run_install_command,
)


def load_google_modules(*, assume_yes: bool = False):
    try:
        import httplib2
        from google.auth.transport.requests import Request
        from google.oauth2.credentials import Credentials
        from google_auth_httplib2 import AuthorizedHttp
        from google_auth_oauthlib.flow import InstalledAppFlow
        from googleapiclient.discovery import build
        from googleapiclient.errors import HttpError
    except ImportError as exc:  # pragma: no cover - exercised through runtime help path
        os_name = detect_os()
        pkg_manager = detect_pkg_manager(os_name)
        command = dependency_install_command("gmail-api-python", os_name, pkg_manager)
        if command:
            print("Missing Gmail API Python dependencies.", file=sys.stderr)
            print(f"Detected OS: {os_name}", file=sys.stderr)
            print(f"Detected package manager: {pkg_manager}", file=sys.stderr)
            print(f"Planned install command: {command}", file=sys.stderr)
            if confirm("Run this install command now so gmail-cleanup can continue?", default_yes=True, assume_yes=assume_yes):
                result = run_install_command(command, os_name)
                if result == 0:
                    import httplib2
                    from google.auth.transport.requests import Request
                    from google.oauth2.credentials import Credentials
                    from google_auth_httplib2 import AuthorizedHttp
                    from google_auth_oauthlib.flow import InstalledAppFlow
                    from googleapiclient.discovery import build
                    from googleapiclient.errors import HttpError

                    return Request, Credentials, InstalledAppFlow, build, AuthorizedHttp, httplib2, HttpError
                raise RuntimeError(f"Install command failed with exit code {result}: {command}") from exc
        raise RuntimeError(
            "Missing Gmail API dependencies. "
            f"Install them with: {command or 'python3 -m pip install --user google-api-python-client google-auth-oauthlib google-auth-httplib2'}"
        ) from exc
    return Request, Credentials, InstalledAppFlow, build, AuthorizedHttp, httplib2, HttpError


class GmailApiClient:
    def __init__(
        self,
        service,
        user_id: str,
        *,
        service_factory=None,
        quota_pacer: GmailQuotaPacer | None = None,
    ) -> None:
        self.service = service
        self.user_id = user_id
        self.service_factory = service_factory
        self.quota_pacer = quota_pacer

    def list_message_ids(self, query: str, max_results: int) -> list[str]:
        ids: list[str] = []
        page_token: str | None = None
        remaining = max_results
        while remaining > 0:
            batch_size = min(remaining, 500)
            response = self.execute_with_quota(
                GMAIL_QUOTA_MESSAGES_LIST,
                lambda: (
                    self.service.users()
                    .messages()
                    .list(
                        userId=self.user_id,
                        q=query,
                        maxResults=batch_size,
                        pageToken=page_token,
                    )
                    .execute()
                ),
            )
            ids.extend(message["id"] for message in response.get("messages", ()))
            page_token = response.get("nextPageToken")
            remaining = max_results - len(ids)
            if not page_token:
                break
        return ids[:max_results]

    def get_message_raw(self, message_id: str) -> GmailMessageRecord:
        response = self.execute_with_quota(
            GMAIL_QUOTA_MESSAGES_GET,
            lambda: (
                self.service.users()
                .messages()
                .get(userId=self.user_id, id=message_id, format="raw")
                .execute()
            ),
        )
        return GmailMessageRecord(
            message_id=response["id"],
            thread_id=response["threadId"],
            label_ids=tuple(response.get("labelIds", ())),
            raw_bytes=decode_gmail_raw(response["raw"]),
            history_id=str(response["historyId"]) if response.get("historyId") is not None else None,
            internal_date=int(response["internalDate"]) if response.get("internalDate") is not None else None,
        )

    def clone(self) -> "GmailApiClient":
        if self.service_factory is None:
            return self
        return GmailApiClient(
            self.service_factory(),
            self.user_id,
            service_factory=self.service_factory,
            quota_pacer=self.quota_pacer,
        )

    def wait_for_quota(self, units: float) -> None:
        if self.quota_pacer is not None:
            self.quota_pacer.wait(units)

    def execute_with_quota(self, units: float, operation):
        if self.quota_pacer is not None:
            return self.quota_pacer.run(units, operation)
        return operation()

    def get_message_raw_batch(self, message_ids: tuple[str, ...]) -> BatchFetchResult:
        results: dict[str, GmailMessageRecord] = {}
        errors: dict[str, BaseException] = {}
        batch = self.service.new_batch_http_request()

        def callback(request_id, response, exception):
            if exception is not None:
                errors[str(request_id)] = exception
                return
            results[str(request_id)] = GmailMessageRecord(
                message_id=response["id"],
                thread_id=response["threadId"],
                label_ids=tuple(response.get("labelIds", ())),
                raw_bytes=decode_gmail_raw(response["raw"]),
                history_id=str(response["historyId"]) if response.get("historyId") is not None else None,
                internal_date=int(response["internalDate"]) if response.get("internalDate") is not None else None,
            )

        for message_id in message_ids:
            request = self.service.users().messages().get(userId=self.user_id, id=message_id, format="raw")
            batch.add(request, callback=callback, request_id=message_id)
        try:
            self.execute_with_quota(GMAIL_QUOTA_MESSAGES_GET * len(message_ids), batch.execute)
        except Exception as exc:  # pragma: no cover - exercised with integration/runtime behavior
            if is_retryable_gmail_request_error(exc):
                raise GmailRateLimitError(str(exc)) from exc
            if is_retryable_gmail_transport_error(exc):
                raise GmailTransientReadError(str(exc)) from exc
            raise
        if errors:
            retryable = next((exc for exc in errors.values() if is_retryable_gmail_request_error(exc)), None)
            if retryable is not None:
                raise GmailRateLimitError(str(retryable)) from retryable
            retryable_transport = next((exc for exc in errors.values() if is_retryable_gmail_transport_error(exc)), None)
            if retryable_transport is not None:
                raise GmailTransientReadError(str(retryable_transport)) from retryable_transport
            first_message_id, first_error = next(iter(errors.items()))
            raise RuntimeError(f"Failed to fetch Gmail message {first_message_id}: {first_error}") from first_error
        ordered = [results[message_id] for message_id in message_ids if message_id in results]
        if len(ordered) != len(message_ids):
            missing = [message_id for message_id in message_ids if message_id not in results]
            raise RuntimeError(f"Missing Gmail batch response for message(s): {', '.join(missing)}")
        return BatchFetchResult(chunk_index=-1, message_ids=message_ids, records=ordered)

    def get_message_raw_many(
        self,
        message_ids: list[str],
        *,
        batch_size: int,
        max_inflight: int,
    ) -> list[GmailMessageRecord]:
        if not message_ids:
            return []
        chunks = [tuple(message_ids[index : index + batch_size]) for index in range(0, len(message_ids), batch_size)]
        if max_inflight <= 1 or self.service_factory is None:
            records: list[GmailMessageRecord] = []
            for chunk in chunks:
                records.extend(self.get_message_raw_batch(chunk).records)
            return records
        ordered: list[list[GmailMessageRecord] | None] = [None] * len(chunks)
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_inflight) as executor:
            future_map = {
                executor.submit(self.clone().get_message_raw_batch, chunk): index
                for index, chunk in enumerate(chunks)
            }
            for future in concurrent.futures.as_completed(future_map):
                index = future_map[future]
                ordered[index] = future.result().records
        flattened: list[GmailMessageRecord] = []
        for chunk_records in ordered:
            if chunk_records is None:
                raise RuntimeError("Missing Gmail batch records")
            flattened.extend(chunk_records)
        return flattened

    def find_cleanup_replacement_message_id(self, thread_id: str, original_message_id: str) -> str | None:
        def request():
            return self.execute_with_quota(
                GMAIL_QUOTA_THREADS_GET,
                lambda: (
                    self.service.users()
                    .threads()
                    .get(
                        userId=self.user_id,
                        id=thread_id,
                        format="metadata",
                        metadataHeaders=["X-Maj-Scripts-Gmail-Cleanup"],
                    )
                    .execute()
                ),
            )

        response = execute_retryable_gmail_write(request, action="threads.get")
        for message in response.get("messages", ()):
            message_id = message.get("id")
            if not isinstance(message_id, str) or message_id == original_message_id:
                continue
            labels = set(message.get("labelIds", ()))
            if labels & {"TRASH", "SPAM", "DRAFT"}:
                continue
            payload = message.get("payload", {})
            headers = payload.get("headers", []) if isinstance(payload, dict) else []
            for header in headers:
                if not isinstance(header, dict):
                    continue
                if str(header.get("name", "")).lower() != "x-maj-scripts-gmail-cleanup":
                    continue
                if original_message_id in str(header.get("value", "")):
                    return message_id
        return None

    def insert_message(
        self,
        thread_id: str,
        label_ids: tuple[str, ...],
        raw_bytes: bytes,
        *,
        original_message_id: str | None = None,
    ) -> str:
        body = {
            "threadId": thread_id,
            "labelIds": [label for label in label_ids if label not in SKIPPED_LABEL_IDS],
            "raw": encode_gmail_raw(raw_bytes),
        }

        def request():
            return self.execute_with_quota(
                GMAIL_QUOTA_MESSAGES_INSERT,
                lambda: (
                    self.service.users()
                    .messages()
                    .insert(
                        userId=self.user_id,
                        internalDateSource="dateHeader",
                        body=body,
                    )
                    .execute()
                ),
            )

        last_error: BaseException | None = None
        for attempt in range(1, GMAIL_WRITE_MAX_ATTEMPTS + 1):
            try:
                response = request()
                return response["id"]
            except Exception as exc:
                if not is_retryable_gmail_write_error(exc) or attempt == GMAIL_WRITE_MAX_ATTEMPTS:
                    raise
                last_error = exc
                time.sleep(gmail_retry_delay(attempt))
                if original_message_id is not None:
                    try:
                        found = self.find_cleanup_replacement_message_id(thread_id, original_message_id)
                    except Exception as lookup_exc:
                        if not is_retryable_gmail_write_error(lookup_exc):
                            raise
                    else:
                        if found is not None:
                            return found
        raise RuntimeError("Failed Gmail insert") from last_error

    def trash_message(self, message_id: str) -> None:
        execute_retryable_gmail_write(
            lambda: self.execute_with_quota(
                GMAIL_QUOTA_MESSAGES_TRASH,
                lambda: self.service.users().messages().trash(userId=self.user_id, id=message_id).execute(),
            ),
            action="messages.trash",
        )

    def list_labels(self) -> list[dict[str, object]]:
        response = self.execute_with_quota(
            GMAIL_QUOTA_LABELS_LIST,
            lambda: self.service.users().labels().list(userId=self.user_id).execute(),
        )
        labels = response.get("labels", [])
        return [label for label in labels if isinstance(label, dict)]

    def get_or_create_label(self, name: str) -> str:
        for label in self.list_labels():
            if label.get("name") == name and isinstance(label.get("id"), str):
                return str(label["id"])

        body = {
            "name": name,
            "labelListVisibility": "labelShow",
            "messageListVisibility": "show",
        }

        def request():
            return self.execute_with_quota(
                GMAIL_QUOTA_LABELS_CREATE,
                lambda: self.service.users().labels().create(userId=self.user_id, body=body).execute(),
            )

        response = execute_retryable_gmail_write(request, action="labels.create")
        label_id = response.get("id")
        if not isinstance(label_id, str):
            raise RuntimeError(f"Gmail did not return an id for label {name!r}")
        return label_id

    def modify_message_labels(self, message_id: str, add_label_ids: tuple[str, ...]) -> None:
        if not add_label_ids:
            return
        body = {"addLabelIds": list(add_label_ids), "removeLabelIds": []}
        execute_retryable_gmail_write(
            lambda: self.execute_with_quota(
                GMAIL_QUOTA_MESSAGES_MODIFY,
                lambda: self.service.users().messages().modify(userId=self.user_id, id=message_id, body=body).execute(),
            ),
            action="messages.modify",
        )


def build_gmail_client(
    credentials_path: Path,
    token_cache_path: Path,
    scopes: tuple[str, ...],
    user_id: str,
    *,
    assume_yes: bool = False,
    quota_units_per_second: float | None = None,
) -> GmailApiClient:
    Request, Credentials, InstalledAppFlow, build, AuthorizedHttp, httplib2, _HttpError = load_google_modules(assume_yes=assume_yes)
    creds = None
    if token_cache_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_cache_path), list(scopes))
        if not creds.has_scopes(scopes):
            creds = None
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
        except Exception as exc:
            if not is_invalid_scope_refresh_error(exc):
                raise
            creds = None
    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), list(scopes))
        creds = flow.run_local_server(port=0)
        token_cache_path.parent.mkdir(parents=True, exist_ok=True)
        token_cache_path.write_text(creds.to_json(), encoding="utf-8")
    creds_json = creds.to_json()

    def service_factory():
        service_creds = Credentials.from_authorized_user_info(json.loads(creds_json), list(scopes))
        http = AuthorizedHttp(service_creds, http=httplib2.Http(timeout=GMAIL_HTTP_TIMEOUT_SECONDS))
        return build("gmail", "v1", http=http, cache_discovery=False)

    service = service_factory()
    quota_pacer = GmailQuotaPacer(quota_units_per_second) if quota_units_per_second is not None else None
    return GmailApiClient(service, user_id, service_factory=service_factory, quota_pacer=quota_pacer)


def decode_gmail_raw(raw: str) -> bytes:
    padding = "=" * (-len(raw) % 4)
    return base64.urlsafe_b64decode(raw + padding)


def encode_gmail_raw(raw_bytes: bytes) -> str:
    return base64.urlsafe_b64encode(raw_bytes).decode("ascii")
