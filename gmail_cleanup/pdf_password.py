"""PDF password cracking for gmail-cleanup: password-recipe fingerprinting
and the learned-secret/learned-recipe/family-failure JSON stores (via
``gmail_cleanup.password_stores``), candidate generation from message
text/filename/date hints, backend selection (``john``/``pdfcrack``/``qpdf``/
builtin), and the actual ``pdfcrack``/``john``/``qpdf`` subprocess
invocation and output parsing, all tied together by
``resolve_pdf_password``.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see
docs/reports/2026-08-31-gmail-cleanup-modularity-split.md). The 2026-09-01
follow-up section of that report deliberately deferred this cluster to its
own dedicated pass, given its size (~25 functions, ~535 lines) and its real
subprocess/persistent-state stakes, even though the call-graph trace it
recorded already found this cluster to be a clean DAG with no back-edges:
nothing outside this module calls any of these functions except
``write_pdf_outputs`` (still in the top-level script), which calls only the
single entry point ``resolve_pdf_password``. This module's own only
outward dependency on PDF processing is one-directional
(``resolve_pdf_password`` calls ``gmail_cleanup.pdf_processing.
pdf_page_count`` for the builtin backend's trial-decrypt loop).

Every external name this module's functions reference resolves to the
standard library or an already-extracted module: gmail_cleanup.constants
(the password regex patterns), gmail_cleanup.models (PlannedMessage,
BufferedMediaPart, ExtractionSettings, PasswordCandidate,
ProgressReporter), gmail_cleanup.password_stores (the JSON-file-backed
recipe/secret/failure stores), gmail_cleanup.system_tools
(optional_tool_path), gmail_cleanup.tool_paths (resolve_qpdf_path,
resolve_pdfcrack_path, find_pdf2john_path, john_runtime_home),
gmail_cleanup.pdf_processing (pdf_page_count, extract_message_search_text),
and gmail_cleanup.config (is_password_protected_pdf_error). No behavior
changes: candidate-generation order, retry counts, timeouts, subprocess
argument construction, and the learned-password cache file format/location
are all unchanged from the top-level script.
"""

from __future__ import annotations

import os
import re
import subprocess
import tempfile
from datetime import date, datetime, timedelta, timezone
from email.utils import parseaddr
from pathlib import Path

from gmail_cleanup.config import is_password_protected_pdf_error
from gmail_cleanup.constants import (
    JOHN_SHOW_PASSWORD_PATTERN,
    NUMERIC_TOKEN_PATTERN,
    PASSWORD_HINT_PATTERN,
    PASSWORD_TOKEN_PATTERN,
    PDFCRACK_FOUND_PASSWORD_PATTERN,
)
from gmail_cleanup.models import (
    BufferedMediaPart,
    ExtractionSettings,
    PasswordCandidate,
    PlannedMessage,
    ProgressReporter,
)
from gmail_cleanup.password_stores import (
    load_password_failure_store,
    load_password_recipe_store,
    load_password_secret_store,
    save_password_failure_store,
    save_password_recipe_store,
    save_password_secret_store,
)
from gmail_cleanup.pdf_processing import extract_message_search_text, pdf_page_count
from gmail_cleanup.system_tools import optional_tool_path
from gmail_cleanup.tool_paths import (
    find_pdf2john_path,
    john_runtime_home,
    resolve_pdfcrack_path,
    resolve_qpdf_path,
)


def password_candidate_variants(token: str) -> tuple[str, ...]:
    cleaned = token.strip().strip("\"'()[]{}<>")
    variants: list[str] = []
    for candidate in (cleaned, re.sub(r"[^A-Za-z0-9]", "", cleaned)):
        if 4 <= len(candidate) <= 64 and candidate not in variants:
            variants.append(candidate)
    return tuple(variants)


def sender_domain(plan: PlannedMessage) -> str:
    address = parseaddr(plan.sender)[1].strip().lower()
    if "@" not in address:
        return "unknown"
    return address.rsplit("@", 1)[1]


def filename_recipe_pattern(filename: str) -> str:
    return re.sub(r"\d", "#", Path(filename).name.lower())


def password_recipe_fingerprint(plan: PlannedMessage, media_part: BufferedMediaPart) -> str:
    return f"{sender_domain(plan)}|{filename_recipe_pattern(media_part.filename)}"


def learned_password_secrets(plan: PlannedMessage, media_part: BufferedMediaPart) -> tuple[str, ...]:
    store = load_password_secret_store()
    payload = store.get(password_recipe_fingerprint(plan, media_part), {})
    if isinstance(payload, dict):
        values = payload.get("passwords", ())
    elif isinstance(payload, list):
        values = payload
    elif isinstance(payload, str):
        values = [payload]
    else:
        values = ()
    learned: list[str] = []
    for value in values:
        if isinstance(value, str) and value and value not in learned:
            learned.append(value)
    return tuple(learned)


def learn_password_secret(plan: PlannedMessage, media_part: BufferedMediaPart, password: str) -> None:
    if not password:
        return
    fingerprint = password_recipe_fingerprint(plan, media_part)
    store = load_password_secret_store()
    passwords = [password]
    for value in learned_password_secrets(plan, media_part):
        if value != password:
            passwords.append(value)
    store[fingerprint] = {
        "passwords": passwords[:5],
        "updated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    try:
        save_password_secret_store(store)
    except OSError:
        return


def password_family_failure_count(plan: PlannedMessage, media_part: BufferedMediaPart) -> int:
    store = load_password_failure_store()
    payload = store.get(password_recipe_fingerprint(plan, media_part), {})
    if not isinstance(payload, dict):
        return 0
    count = payload.get("failure_count", 0)
    return int(count) if isinstance(count, int) else 0


def record_password_family_failure(
    plan: PlannedMessage,
    media_part: BufferedMediaPart,
    *,
    backend: str,
    attempted_recipes: tuple[str, ...],
) -> None:
    fingerprint = password_recipe_fingerprint(plan, media_part)
    store = load_password_failure_store()
    existing = store.get(fingerprint, {})
    current_count = int(existing.get("failure_count", 0)) if isinstance(existing, dict) else 0
    store[fingerprint] = {
        "attempted_recipes": list(attempted_recipes),
        "backend": backend,
        "failure_count": current_count + 1,
        "filename_pattern": filename_recipe_pattern(media_part.filename),
        "last_failed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "last_filename": media_part.filename,
        "last_message_id": plan.message_id,
        "sender_domain": sender_domain(plan),
    }
    try:
        save_password_failure_store(store)
    except OSError:
        return


def reset_password_family_failure(plan: PlannedMessage, media_part: BufferedMediaPart) -> None:
    fingerprint = password_recipe_fingerprint(plan, media_part)
    store = load_password_failure_store()
    if fingerprint not in store:
        return
    del store[fingerprint]
    try:
        save_password_failure_store(store)
    except OSError:
        return


def merge_password_candidates(*groups: tuple[PasswordCandidate, ...]) -> tuple[PasswordCandidate, ...]:
    merged: list[PasswordCandidate] = []
    seen: set[str] = set()
    for group in groups:
        for item in group:
            if item.value in seen:
                continue
            seen.add(item.value)
            merged.append(item)
    return tuple(merged)


def cached_password_candidates(plan: PlannedMessage, media_part: BufferedMediaPart) -> tuple[PasswordCandidate, ...]:
    return tuple(PasswordCandidate(value, "cached") for value in learned_password_secrets(plan, media_part))


def learned_password_recipe_order(plan: PlannedMessage, media_part: BufferedMediaPart) -> tuple[str, ...]:
    store = load_password_recipe_store()
    recipe_counts = store.get(password_recipe_fingerprint(plan, media_part), {})
    if not isinstance(recipe_counts, dict):
        return ()
    ordered = [
        recipe
        for recipe, count in sorted(recipe_counts.items(), key=lambda item: (-int(item[1]), item[0]))
        if recipe in {"last4", "last6", "dob_ddmmmyyyy"}
    ]
    return tuple(ordered)


def learn_password_recipe(plan: PlannedMessage, media_part: BufferedMediaPart, recipe: str) -> None:
    if recipe not in {"last4", "last6", "dob_ddmmmyyyy"}:
        return
    store = load_password_recipe_store()
    fingerprint = password_recipe_fingerprint(plan, media_part)
    recipe_counts = store.get(fingerprint)
    if not isinstance(recipe_counts, dict):
        recipe_counts = {}
    recipe_counts[recipe] = int(recipe_counts.get(recipe, 0)) + 1
    store[fingerprint] = recipe_counts
    try:
        save_password_recipe_store(store)
    except OSError:
        return


def infer_pdf_password_candidates(plan: PlannedMessage, media_part: BufferedMediaPart, *, limit: int = 250) -> tuple[PasswordCandidate, ...]:
    sources = [
        media_part.filename,
        Path(media_part.filename).stem,
        plan.subject,
        plan.sender,
        plan.date_header,
        extract_message_search_text(plan.raw_bytes),
    ]
    candidates: list[PasswordCandidate] = []
    seen: set[tuple[str, str]] = set()

    def add(candidate: str, recipe: str) -> None:
        if not candidate:
            return
        key = (candidate, recipe)
        if key in seen:
            return
        seen.add(key)
        item = PasswordCandidate(candidate, recipe)
        if item not in candidates:
            candidates.append(item)

    for source in sources:
        if not source:
            continue
        for match in PASSWORD_HINT_PATTERN.finditer(source):
            for candidate in password_candidate_variants(match.group(1)):
                add(candidate, "explicit_hint")
                if len(candidates) >= limit:
                    return tuple(candidates)
        for token in PASSWORD_TOKEN_PATTERN.findall(source):
            for candidate in password_candidate_variants(token):
                add(candidate, "token")
                if len(candidates) >= limit:
                    return tuple(candidates)
    return tuple(candidates)


def extract_numeric_tail_candidates(plan: PlannedMessage, media_part: BufferedMediaPart, recipe: str) -> tuple[PasswordCandidate, ...]:
    tail_length = 6 if recipe == "last6" else 4
    sources = (
        media_part.filename,
        Path(media_part.filename).stem,
        plan.subject,
        plan.sender,
        plan.date_header,
        extract_message_search_text(plan.raw_bytes),
    )
    candidates: list[PasswordCandidate] = []
    seen: set[str] = set()
    for source in sources:
        if not source:
            continue
        for token in NUMERIC_TOKEN_PATTERN.findall(source):
            if len(token) >= tail_length:
                candidate = token[-tail_length:]
                if candidate in seen:
                    continue
                seen.add(candidate)
                candidates.append(PasswordCandidate(candidate, recipe))
    return tuple(candidates)


def generate_date_password_candidates(year_range: tuple[int, int]) -> tuple[PasswordCandidate, ...]:
    start_date = date(year_range[0], 1, 1)
    end_date = date(year_range[1], 12, 31)
    current = start_date
    candidates: list[PasswordCandidate] = []
    while current <= end_date:
        month = current.strftime("%b")
        for value in (
            current.strftime("%d") + month.lower() + current.strftime("%Y"),
            current.strftime("%d") + month.upper() + current.strftime("%Y"),
            current.strftime("%d") + month.title() + current.strftime("%Y"),
        ):
            candidates.append(PasswordCandidate(value, "dob_ddmmmyyyy"))
        current += timedelta(days=1)
    return tuple(candidates)


def low_hanging_pdf_password_candidates(
    plan: PlannedMessage,
    media_part: BufferedMediaPart,
    settings: ExtractionSettings,
    *,
    limit: int = 150000,
) -> tuple[PasswordCandidate, ...]:
    candidates: list[PasswordCandidate] = list(infer_pdf_password_candidates(plan, media_part, limit=250))
    seen: set[tuple[str, str]] = {(item.value, item.recipe) for item in candidates}
    ordered_recipes: list[str] = ["last6", "last4", "dob_ddmmmyyyy"]
    for learned in reversed(learned_password_recipe_order(plan, media_part)):
        if learned in ordered_recipes:
            ordered_recipes.remove(learned)
            ordered_recipes.insert(0, learned)
    for recipe in ordered_recipes:
        generated = (
            generate_date_password_candidates(settings.pdf_password_date_range)
            if recipe == "dob_ddmmmyyyy"
            else extract_numeric_tail_candidates(plan, media_part, recipe)
        )
        for item in generated:
            key = (item.value, item.recipe)
            if key not in seen:
                seen.add(key)
                candidates.append(item)
            if len(candidates) >= limit:
                return tuple(candidates)
    return tuple(candidates)


def select_pdf_password_backend(settings: ExtractionSettings, *, assume_yes: bool = False) -> str:
    john_path = optional_tool_path("john")
    pdf2john_path = find_pdf2john_path()
    if john_path is not None and pdf2john_path is not None:
        return "john"
    if optional_tool_path("pdfcrack") is not None:
        return "pdfcrack"
    if optional_tool_path("qpdf") is not None:
        return "qpdf"
    if settings.pdf_password_mode == "low-hanging":
        resolve_pdfcrack_path(assume_yes=assume_yes)
        return "pdfcrack"
    return "builtin"


def parse_pdfcrack_password(output: str) -> str | None:
    match = PDFCRACK_FOUND_PASSWORD_PATTERN.search(output)
    if match is None:
        return None
    return match.group("password")


def run_pdfcrack_candidate_wordlist(
    pdf_path: Path,
    candidates: tuple[PasswordCandidate, ...],
    *,
    assume_yes: bool = False,
) -> str | None:
    pdfcrack_path = resolve_pdfcrack_path(assume_yes=assume_yes)
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-pdfcrack-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        wordlist_path = temp_dir / "candidates.txt"
        wordlist_path.write_text("".join(f"{candidate.value}\n" for candidate in candidates), encoding="utf-8")
        result = subprocess.run(
            [pdfcrack_path, "-f", str(pdf_path), "-w", str(wordlist_path), "-q"],
            check=False,
            capture_output=True,
            text=True,
        )
    output = "\n".join(part for part in (result.stdout, result.stderr) if part).strip()
    return parse_pdfcrack_password(output)


def qpdf_accepts_password(pdf_path: Path, candidate: str, *, assume_yes: bool = False) -> bool:
    qpdf_path = resolve_qpdf_path(assume_yes=assume_yes)
    result = subprocess.run(
        [qpdf_path, "--requires-password", f"--password={candidate}", str(pdf_path)],
        check=False,
        capture_output=True,
        text=True,
    )
    return result.returncode == 3


def parse_john_show_password(output: str) -> str | None:
    for line in output.splitlines():
        stripped = line.strip()
        if not stripped or "password hash cracked" in stripped or stripped.startswith("No password hashes") or stripped.startswith("0 password hashes"):
            continue
        match = JOHN_SHOW_PASSWORD_PATTERN.match(stripped)
        if match is None:
            continue
        return match.group("password")
    return None


def run_john_candidate_wordlist(
    pdf_path: Path,
    candidates: tuple[PasswordCandidate, ...],
) -> str | None:
    john_path = optional_tool_path("john")
    pdf2john_path = find_pdf2john_path()
    if john_path is None or pdf2john_path is None:
        return None
    john_home = john_runtime_home(john_path)
    with tempfile.TemporaryDirectory(prefix="gmail-cleanup-john-") as temp_dir_name:
        temp_dir = Path(temp_dir_name)
        hash_path = temp_dir / "document.hash"
        pot_path = temp_dir / "john.pot"
        wordlist_path = temp_dir / "candidates.txt"
        wordlist_path.write_text("".join(f"{candidate.value}\n" for candidate in candidates), encoding="utf-8")
        pdf2john_result = subprocess.run(
            [str(pdf2john_path), str(pdf_path)],
            check=False,
            capture_output=True,
            text=True,
        )
        if pdf2john_result.returncode != 0 or not pdf2john_result.stdout.strip():
            return None
        hash_path.write_text(pdf2john_result.stdout, encoding="utf-8")
        env = os.environ.copy()
        env["JOHN"] = str(john_home)
        session_name = "gmail-cleanup-pdf"
        subprocess.run(
            [john_path, f"--session={session_name}", f"--pot={pot_path}", "--no-log", f"--wordlist={wordlist_path}", str(hash_path)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=temp_dir,
        )
        show_result = subprocess.run(
            [john_path, f"--pot={pot_path}", "--show", str(hash_path)],
            check=False,
            capture_output=True,
            text=True,
            env=env,
            cwd=temp_dir,
        )
    return parse_john_show_password(show_result.stdout)


def resolve_pdf_password_with_backend(
    backend: str,
    staged_pdf: Path,
    candidates: tuple[PasswordCandidate, ...],
    *,
    assume_yes: bool = False,
) -> str | None:
    if not candidates:
        return None
    if backend == "john":
        return run_john_candidate_wordlist(staged_pdf, candidates)
    if backend == "pdfcrack":
        return run_pdfcrack_candidate_wordlist(staged_pdf, candidates, assume_yes=assume_yes)
    if backend == "qpdf":
        for candidate in candidates:
            if qpdf_accepts_password(staged_pdf, candidate.value, assume_yes=assume_yes):
                return candidate.value
        return None
    return None


def resolve_pdf_password(
    plan: PlannedMessage,
    media_part: BufferedMediaPart,
    settings: ExtractionSettings,
    staged_pdf: Path,
    *,
    reporter: ProgressReporter | None = None,
    assume_yes: bool = False,
) -> tuple[str | None, tuple[str, ...]]:
    reporter = reporter or ProgressReporter()
    if settings.pdf_password_mode == "skip":
        return None, ()
    if settings.pdf_password_mode == "infer":
        generated_candidates = infer_pdf_password_candidates(plan, media_part)
    else:
        generated_candidates = low_hanging_pdf_password_candidates(plan, media_part, settings)
    cached_candidates = cached_password_candidates(plan, media_part)
    family_failure_count = password_family_failure_count(plan, media_part)
    family_backoff = (
        settings.pdf_password_family_fail_limit > 0
        and family_failure_count >= settings.pdf_password_family_fail_limit
    )
    if family_backoff and not cached_candidates:
        attempted_recipes = tuple(sorted({candidate.recipe for candidate in generated_candidates} | {"family-backoff"}))
        reporter.log_event(
            1,
            (
                f"Skipping password attempts for {media_part.filename}; "
                f"family failed {family_failure_count} time(s)"
            ),
            "password_family_backoff",
            message_id=plan.message_id,
            filename=media_part.filename,
            failure_count=family_failure_count,
            fail_limit=settings.pdf_password_family_fail_limit,
            attempted_recipes=list(attempted_recipes),
        )
        return None, attempted_recipes
    candidates = cached_candidates if family_backoff else merge_password_candidates(cached_candidates, generated_candidates)
    backend = select_pdf_password_backend(settings, assume_yes=assume_yes)
    attempted_recipes: set[str] = set()
    for candidate in candidates:
        attempted_recipes.add(candidate.recipe)
    if family_backoff:
        attempted_recipes.add("family-backoff")
    resolved = resolve_pdf_password_with_backend(backend, staged_pdf, candidates, assume_yes=assume_yes)
    if resolved is not None:
        resolved_recipe = next((candidate.recipe for candidate in candidates if candidate.value == resolved), "external")
        if settings.pdf_password_mode == "low-hanging":
            learn_password_recipe(plan, media_part, resolved_recipe)
        learn_password_secret(plan, media_part, resolved)
        reset_password_family_failure(plan, media_part)
        reporter.log_event(
            2,
            f"Resolved PDF password for {media_part.filename} via {resolved_recipe} ({backend})",
            "password_recipe_attempt",
            message_id=plan.message_id,
            filename=media_part.filename,
            recipe=resolved_recipe,
            backend=backend,
            outcome="resolved",
        )
        return resolved, tuple(sorted(attempted_recipes))
    if backend != "builtin":
        if candidates and settings.pdf_password_family_fail_limit > 0:
            record_password_family_failure(
                plan,
                media_part,
                backend=backend,
                attempted_recipes=tuple(sorted(attempted_recipes)),
            )
        reporter.event(
            "password_recipe_skipped",
            message_id=plan.message_id,
            filename=media_part.filename,
            attempted_recipes=sorted(attempted_recipes),
            backend=backend,
        )
        return None, tuple(sorted(attempted_recipes))
    for candidate in candidates:
        try:
            pdf_page_count(staged_pdf, password=candidate.value, assume_yes=assume_yes)
        except RuntimeError as exc:
            if is_password_protected_pdf_error(exc):
                reporter.event(
                    "password_recipe_attempt",
                    message_id=plan.message_id,
                    filename=media_part.filename,
                    recipe=candidate.recipe,
                    outcome="miss",
                )
                continue
            raise
        if settings.pdf_password_mode == "low-hanging":
            learn_password_recipe(plan, media_part, candidate.recipe)
        learn_password_secret(plan, media_part, candidate.value)
        reset_password_family_failure(plan, media_part)
        reporter.log_event(
            2,
            f"Resolved PDF password for {media_part.filename} via {candidate.recipe} ({backend})",
            "password_recipe_attempt",
            message_id=plan.message_id,
            filename=media_part.filename,
            recipe=candidate.recipe,
            backend=backend,
            outcome="resolved",
        )
        return candidate.value, tuple(sorted(attempted_recipes))
    if attempted_recipes:
        if candidates and settings.pdf_password_family_fail_limit > 0:
            record_password_family_failure(
                plan,
                media_part,
                backend=backend,
                attempted_recipes=tuple(sorted(attempted_recipes)),
            )
        reporter.event(
            "password_recipe_skipped",
            message_id=plan.message_id,
            filename=media_part.filename,
            attempted_recipes=sorted(attempted_recipes),
            backend=backend,
        )
    return None, tuple(sorted(attempted_recipes))
