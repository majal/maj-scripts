"""Config resolution for gmail-cleanup: CLI-arg / env-var / TOML-config
precedence chains, preset defaults, and small validation helpers.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
No behavior changes -- this module depends only on the standard library
plus gmail_cleanup.constants and gmail_cleanup.models (both already
extracted), so it moved as the third self-contained piece.
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.12 in CI, fallback kept for portability
    tomllib = None

from gmail_cleanup.constants import (
    ATTACHMENT_CLEANUP_PRESET_DEFAULTS,
    DEFAULT_AUDIO_MODE_ENV,
    DEFAULT_BACKUP_DIR_ENV,
    DEFAULT_BEFORE_YEAR_ENV,
    DEFAULT_CONFIG_ENV,
    DEFAULT_CONFIG_PATH,
    DEFAULT_CREDENTIALS_ENV,
    DEFAULT_EMBEDDED_IMAGE_DIR_ENV,
    DEFAULT_EMPTY_AFTER_REMOVAL_ENV,
    DEFAULT_GMAIL_USER_ENV,
    DEFAULT_GMAIL_WEB_ACCOUNT,
    DEFAULT_GMAIL_WEB_ACCOUNT_ENV,
    DEFAULT_INDEX_DB_ENV,
    DEFAULT_INDEX_DB_PATH,
    DEFAULT_LABEL_PROCESSED_ENV,
    DEFAULT_LABEL_REVIEW_ENV,
    DEFAULT_MAX_RESULTS_ENV,
    DEFAULT_MIN_MESSAGE_BYTES_ENV,
    DEFAULT_MIN_PART_BYTES_ENV,
    DEFAULT_PDF_MODE_ENV,
    DEFAULT_PDF_ORIGINAL_ENV,
    DEFAULT_PDF_PASSWORD_DATE_RANGE,
    DEFAULT_PDF_PASSWORD_DATE_RANGE_ENV,
    DEFAULT_PDF_PASSWORD_FAILURE_ACTION_ENV,
    DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT,
    DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT_ENV,
    DEFAULT_PDF_PASSWORD_MODE_ENV,
    DEFAULT_PDF_RENDER_DPI,
    DEFAULT_PDF_RENDER_DPI_ENV,
    DEFAULT_PDF_RENDER_FORMAT_ENV,
    DEFAULT_PDF_TEXT_MODE_ENV,
    DEFAULT_PROCESSED_LABEL,
    DEFAULT_PROGRESS_FORMAT_ENV,
    DEFAULT_QUOTA_UNITS_PER_SECOND_ENV,
    DEFAULT_REQUEST_PROFILE_ENV,
    DEFAULT_REVIEW_LABEL,
    DEFAULT_SOFFICE_ENV,
    DEFAULT_TOKEN_ENV,
    DEFAULT_TOKEN_PATH,
    DEFAULT_TYPES_ENV,
    GMAIL_PUBLISHED_USER_QUOTA_UNITS_PER_SECOND,
    LEGACY_CONFIG_PATH,
    LEGACY_TOKEN_PATH,
    REQUEST_PROFILE_CONFIG,
    VALID_ATTACHMENT_TYPES,
    VALID_AUDIO_MODES,
    VALID_EMPTY_AFTER_REMOVAL_MODES,
    VALID_PDF_MODES,
    VALID_PDF_ORIGINAL_RETENTION,
    VALID_PDF_PASSWORD_FAILURE_ACTIONS,
    VALID_PDF_PASSWORD_MODES,
    VALID_PDF_RENDER_FORMATS,
    VALID_PDF_TEXT_MODES,
    VALID_PROGRESS_FORMATS,
    VALID_REQUEST_PROFILES,
)
from gmail_cleanup.models import AuditLabelSettings, ExtractionSettings, PlannedMessage


def die(message: str, code: int = 2) -> int:
    print(message, file=sys.stderr)
    return code


def log_progress(verbose: int, level: int, message: str) -> None:
    if verbose < level:
        return
    print(f"[gmail-cleanup] {message}", file=sys.stderr, flush=True)


def default_extraction_settings() -> ExtractionSettings:
    return ExtractionSettings(
        attachment_types=("image", "video"),
        before_year=None,
        min_message_bytes=0,
        min_part_bytes=0,
        pdf_mode="auto",
        pdf_original="keep",
        pdf_password_mode="skip",
        pdf_password_failure_action="skip",
        pdf_password_date_range=parse_year_range(DEFAULT_PDF_PASSWORD_DATE_RANGE),
        pdf_password_family_fail_limit=DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT,
        pdf_render_dpi=DEFAULT_PDF_RENDER_DPI,
        pdf_render_format="auto",
        pdf_text_mode="none",
        empty_after_removal="skip",
        audio_mode="copy",
        readable_folders=False,
        embedded_image_dir=None,
        soffice_path=None,
    )


def apply_preset_defaults(args: argparse.Namespace) -> None:
    preset = getattr(args, "preset", None)
    if preset is None:
        return
    defaults = ATTACHMENT_CLEANUP_PRESET_DEFAULTS.get(preset)
    if defaults is None:
        raise ValueError(f"Unsupported preset: {preset}")
    for name, value in defaults.items():
        if hasattr(args, name) and getattr(args, name) is None:
            setattr(args, name, value)


def resolve_query(explicit: str | None) -> str:
    if explicit is None or not explicit.strip():
        raise ValueError("Missing Gmail query. Pass --query or use a preset that supplies one.")
    return explicit.strip()


def build_extraction_settings(args: argparse.Namespace, config: dict[str, object], config_path: Path) -> ExtractionSettings:
    return ExtractionSettings(
        attachment_types=resolve_attachment_types(getattr(args, "types", None), config, config_path),
        before_year=resolve_before_year(getattr(args, "before_year", None), config, config_path),
        min_message_bytes=resolve_nonnegative_int_setting(
            "min_message_bytes",
            getattr(args, "min_message_bytes", None),
            DEFAULT_MIN_MESSAGE_BYTES_ENV,
            config,
            config_path,
        ),
        min_part_bytes=resolve_nonnegative_int_setting(
            "min_part_bytes",
            getattr(args, "min_part_bytes", None),
            DEFAULT_MIN_PART_BYTES_ENV,
            config,
            config_path,
        ),
        pdf_mode=resolve_pdf_mode(getattr(args, "pdf_mode", None), config, config_path),
        pdf_original=resolve_pdf_original(getattr(args, "pdf_original", None), config, config_path),
        pdf_password_mode=resolve_pdf_password_mode(getattr(args, "pdf_password_mode", None), config, config_path),
        pdf_password_failure_action=resolve_pdf_password_failure_action(
            getattr(args, "pdf_password_failure_action", None),
            config,
            config_path,
        ),
        pdf_password_date_range=resolve_pdf_password_date_range(getattr(args, "pdf_password_date_range", None), config, config_path),
        pdf_password_family_fail_limit=resolve_pdf_password_family_fail_limit(
            getattr(args, "pdf_password_family_fail_limit", None),
            getattr(args, "no_pdf_password_family_backoff", False),
            config,
            config_path,
        ),
        pdf_render_dpi=resolve_pdf_render_dpi(getattr(args, "pdf_render_dpi", None), config, config_path),
        pdf_render_format=resolve_pdf_render_format(getattr(args, "pdf_render_format", None), config, config_path),
        pdf_text_mode=resolve_pdf_text_mode(getattr(args, "pdf_text_mode", None), config, config_path),
        empty_after_removal=resolve_empty_after_removal(getattr(args, "empty_after_removal", None), config, config_path),
        audio_mode=resolve_audio_mode(getattr(args, "audio_mode", None), config, config_path),
        readable_folders=resolve_readable_folders(getattr(args, "readable_folders", False), config, config_path),
        embedded_image_dir=resolve_embedded_image_dir(getattr(args, "embedded_image_dir", None), config, config_path),
        soffice_path=resolve_soffice_path(getattr(args, "soffice", None), config, config_path),
    )


def format_message_label(plan: PlannedMessage) -> str:
    subject = plan.subject or "(no subject)"
    sender = plan.sender or "(unknown sender)"
    return f"{plan.message_id}: {subject} from {sender}"


def resolve_config_path(explicit: Path | None) -> Path:
    if explicit is not None:
        return explicit
    env_path = path_from_env(DEFAULT_CONFIG_ENV)
    if env_path is not None:
        return env_path
    if DEFAULT_CONFIG_PATH.exists() or not LEGACY_CONFIG_PATH.exists():
        return DEFAULT_CONFIG_PATH
    return LEGACY_CONFIG_PATH


def load_config(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    if tomllib is None:
        raise ValueError("TOML config files require Python 3.11 or newer.")
    with path.open("rb") as handle:
        data = tomllib.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid Gmail cleanup config in {path}: root must be a table")
    allowed_keys = {
        "backup_dir",
        "audit_labels",
        "audio_mode",
        "before_year",
        "credentials",
        "gmail_web_account",
        "gmail_user",
        "index_db",
        "label_processed",
        "label_review",
        "max_results",
        "min_message_bytes",
        "min_part_bytes",
        "pdf_mode",
        "pdf_original",
        "pdf_password_mode",
        "pdf_password_failure_action",
        "pdf_password_date_range",
        "pdf_password_family_fail_limit",
        "pdf_render_dpi",
        "pdf_render_format",
        "pdf_text_mode",
        "empty_after_removal",
        "embedded_image_dir",
        "request_profile",
        "quota_units_per_second",
        "progress_format",
        "readable_folders",
        "soffice",
        "token_cache",
        "types",
    }
    unknown = sorted(set(data) - allowed_keys)
    if unknown:
        raise ValueError(f"Invalid Gmail cleanup config {path}: unsupported key(s): {', '.join(unknown)}")
    return data


def config_string_value(config: dict[str, object], key: str, path: Path) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"Invalid Gmail cleanup config {path}: {key} must be a string")
    return value


def config_path_value(config: dict[str, object], key: str, path: Path) -> Path | None:
    value = config_string_value(config, key, path)
    if value is None:
        return None
    candidate = Path(value).expanduser()
    if candidate.is_absolute():
        return candidate
    return (path.parent / candidate).resolve()


def config_int_value(config: dict[str, object], key: str, path: Path) -> int | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, int):
        raise ValueError(f"Invalid Gmail cleanup config {path}: {key} must be an integer")
    return value


def config_float_value(config: dict[str, object], key: str, path: Path) -> float | None:
    value = config.get(key)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"Invalid Gmail cleanup config {path}: {key} must be a number")
    return float(value)


def config_bool_value(config: dict[str, object], key: str, path: Path) -> bool | None:
    value = config.get(key)
    if value is None:
        return None
    if not isinstance(value, bool):
        raise ValueError(f"Invalid Gmail cleanup config {path}: {key} must be true or false")
    return value


def env_int(name: str) -> int | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"${name} must be an integer, got: {value}") from exc


def env_float(name: str) -> float | None:
    value = os.environ.get(name)
    if value is None or value == "":
        return None
    try:
        return float(value)
    except ValueError as exc:
        raise ValueError(f"${name} must be a number, got: {value}") from exc


def resolve_backup_dir(explicit: Path | None, config: dict[str, object], config_path: Path) -> Path:
    path = explicit or path_from_env(DEFAULT_BACKUP_DIR_ENV) or config_path_value(config, "backup_dir", config_path)
    if path is None:
        raise ValueError(
            "Missing backup directory. Pass --backup-dir, set "
            f"${DEFAULT_BACKUP_DIR_ENV}, or add backup_dir to {config_path}."
        )
    return path


def resolve_embedded_image_dir(explicit: Path | None, config: dict[str, object], config_path: Path) -> Path | None:
    path = explicit or path_from_env(DEFAULT_EMBEDDED_IMAGE_DIR_ENV) or config_path_value(config, "embedded_image_dir", config_path)
    return path.expanduser() if path is not None else None


def resolve_soffice_path(explicit: str | None, config: dict[str, object], config_path: Path) -> str | None:
    value = explicit or os.environ.get(DEFAULT_SOFFICE_ENV) or config_string_value(config, "soffice", config_path)
    return value.strip() if isinstance(value, str) and value.strip() else None


def resolve_credentials_path(explicit: Path | None, config: dict[str, object], config_path: Path) -> Path:
    path = explicit or path_from_env(DEFAULT_CREDENTIALS_ENV) or config_path_value(config, "credentials", config_path)
    if path is None:
        raise ValueError(
            "Missing OAuth client secret path. "
            f"Pass --credentials, set ${DEFAULT_CREDENTIALS_ENV}, or add credentials to {config_path}."
        )
    if not path.is_file():
        raise ValueError(f"OAuth client secret JSON not found: {path}")
    return path


def resolve_token_cache_path(explicit: Path | None, config: dict[str, object], config_path: Path) -> Path:
    configured = explicit or path_from_env(DEFAULT_TOKEN_ENV) or config_path_value(config, "token_cache", config_path)
    if configured is not None:
        return configured
    if DEFAULT_TOKEN_PATH.exists() or not LEGACY_TOKEN_PATH.exists():
        return DEFAULT_TOKEN_PATH
    return LEGACY_TOKEN_PATH


def resolve_index_db_path(explicit: Path | None, config: dict[str, object], config_path: Path) -> Path:
    if explicit is not None:
        return explicit.expanduser()
    env_path = path_from_env(DEFAULT_INDEX_DB_ENV)
    if env_path is not None:
        return env_path
    configured = config_path_value(config, "index_db", config_path)
    if configured is not None:
        return configured
    return DEFAULT_INDEX_DB_PATH


def resolve_gmail_user(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = explicit or os.environ.get(DEFAULT_GMAIL_USER_ENV) or config_string_value(config, "gmail_user", config_path) or "me"
    return value.strip() or "me"


def resolve_gmail_web_account(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_GMAIL_WEB_ACCOUNT_ENV)
        or config_string_value(config, "gmail_web_account", config_path)
        or DEFAULT_GMAIL_WEB_ACCOUNT
    )
    return value.strip() or DEFAULT_GMAIL_WEB_ACCOUNT


def resolve_max_results(explicit: int | None, config: dict[str, object], config_path: Path) -> int:
    value = explicit if explicit is not None else env_int(DEFAULT_MAX_RESULTS_ENV)
    if value is None:
        value = config_int_value(config, "max_results", config_path)
    return value if value is not None else 50


def resolve_before_year(explicit: int | None, config: dict[str, object], config_path: Path) -> int | None:
    value = explicit if explicit is not None else env_int(DEFAULT_BEFORE_YEAR_ENV)
    if value is None:
        value = config_int_value(config, "before_year", config_path)
    if value is None:
        return None
    if value < 1:
        raise ValueError("--before-year must be a positive year")
    return value


def resolve_nonnegative_int_setting(
    key: str,
    explicit: int | None,
    env_name: str,
    config: dict[str, object],
    config_path: Path,
) -> int:
    value = explicit if explicit is not None else env_int(env_name)
    if value is None:
        value = config_int_value(config, key, config_path)
    if value is None:
        return 0
    if value < 0:
        cli_name = key.replace("_", "-")
        raise ValueError(f"--{cli_name} must be zero or greater")
    return value


def is_password_protected_pdf_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    markers = (
        "incorrect password",
        "password protected",
        "password-protected",
        "encrypted file",
        "file is encrypted",
    )
    return any(marker in message for marker in markers)


def config_string_sequence_value(config: dict[str, object], key: str, path: Path) -> str | None:
    value = config.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        return value
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return ",".join(value)
    raise ValueError(f"Invalid Gmail cleanup config {path}: {key} must be a string or list of strings")


def parse_attachment_types(value: str | None) -> tuple[str, ...]:
    if value is None:
        return ("image", "video")
    parts = tuple(token.strip().lower() for token in value.split(",") if token.strip())
    if not parts:
        raise ValueError("--types must include at least one attachment selector")
    invalid = sorted(set(parts) - set(VALID_ATTACHMENT_TYPES))
    if invalid:
        raise ValueError(f"Unsupported attachment selector(s): {', '.join(invalid)}")
    ordered: list[str] = []
    for part in parts:
        if part not in ordered:
            ordered.append(part)
    return tuple(ordered)


def resolve_attachment_types(explicit: str | None, config: dict[str, object], config_path: Path) -> tuple[str, ...]:
    value = explicit or os.environ.get(DEFAULT_TYPES_ENV) or config_string_sequence_value(config, "types", config_path)
    return parse_attachment_types(value)


def resolve_pdf_mode(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = explicit or os.environ.get(DEFAULT_PDF_MODE_ENV) or config_string_value(config, "pdf_mode", config_path) or "auto"
    if value not in VALID_PDF_MODES:
        raise ValueError(f"Unsupported PDF mode: {value}")
    return value


def resolve_pdf_original(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = explicit or os.environ.get(DEFAULT_PDF_ORIGINAL_ENV) or config_string_value(config, "pdf_original", config_path) or "keep"
    if value not in VALID_PDF_ORIGINAL_RETENTION:
        raise ValueError(f"Unsupported PDF original retention mode: {value}")
    return value


def resolve_pdf_password_mode(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_PDF_PASSWORD_MODE_ENV)
        or config_string_value(config, "pdf_password_mode", config_path)
        or "skip"
    )
    if value not in VALID_PDF_PASSWORD_MODES:
        raise ValueError(f"Unsupported PDF password mode: {value}")
    return value


def resolve_pdf_password_failure_action(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_PDF_PASSWORD_FAILURE_ACTION_ENV)
        or config_string_value(config, "pdf_password_failure_action", config_path)
        or "skip"
    )
    if value not in VALID_PDF_PASSWORD_FAILURE_ACTIONS:
        raise ValueError(f"Unsupported PDF password failure action: {value}")
    return value


def parse_year_range(value: str) -> tuple[int, int]:
    match = re.fullmatch(r"\s*(\d{4})\s*-\s*(\d{4})\s*", value)
    if match is None:
        raise ValueError(f"Invalid year range: {value!r}. Expected YYYY-YYYY.")
    start_year = int(match.group(1))
    end_year = int(match.group(2))
    if start_year > end_year:
        raise ValueError(f"Invalid year range: {value!r}. Start year must be <= end year.")
    return start_year, end_year


def resolve_pdf_password_date_range(explicit: str | None, config: dict[str, object], config_path: Path) -> tuple[int, int]:
    value = (
        explicit
        or os.environ.get(DEFAULT_PDF_PASSWORD_DATE_RANGE_ENV)
        or config_string_value(config, "pdf_password_date_range", config_path)
        or DEFAULT_PDF_PASSWORD_DATE_RANGE
    )
    return parse_year_range(value)


def resolve_pdf_password_family_fail_limit(
    explicit: int | None,
    disabled: bool,
    config: dict[str, object],
    config_path: Path,
) -> int:
    if disabled:
        return 0
    value = explicit if explicit is not None else env_int(DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT_ENV)
    if value is None:
        value = config_int_value(config, "pdf_password_family_fail_limit", config_path)
    if value is None:
        value = DEFAULT_PDF_PASSWORD_FAMILY_FAIL_LIMIT
    if value < 0:
        raise ValueError("--pdf-password-family-fail-limit must be 0 or greater")
    return value


def resolve_pdf_render_format(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = explicit or os.environ.get(DEFAULT_PDF_RENDER_FORMAT_ENV) or config_string_value(config, "pdf_render_format", config_path) or "auto"
    if value not in VALID_PDF_RENDER_FORMATS:
        raise ValueError(f"Unsupported PDF render format: {value}")
    return value


def resolve_pdf_render_dpi(explicit: int | None, config: dict[str, object], config_path: Path) -> int:
    value = explicit if explicit is not None else env_int(DEFAULT_PDF_RENDER_DPI_ENV)
    if value is None:
        value = config_int_value(config, "pdf_render_dpi", config_path)
    dpi = value if value is not None else DEFAULT_PDF_RENDER_DPI
    if dpi < 72 or dpi > 1200:
        raise ValueError("--pdf-render-dpi must be between 72 and 1200")
    return dpi


def resolve_pdf_text_mode(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_PDF_TEXT_MODE_ENV)
        or config_string_value(config, "pdf_text_mode", config_path)
        or "none"
    )
    if value not in VALID_PDF_TEXT_MODES:
        raise ValueError(f"Unsupported PDF text mode: {value}")
    return value


def resolve_audio_mode(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = explicit or os.environ.get(DEFAULT_AUDIO_MODE_ENV) or config_string_value(config, "audio_mode", config_path) or "copy"
    if value not in VALID_AUDIO_MODES:
        raise ValueError(f"Unsupported audio mode: {value}")
    return value


def resolve_empty_after_removal(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_EMPTY_AFTER_REMOVAL_ENV)
        or config_string_value(config, "empty_after_removal", config_path)
        or "skip"
    )
    if value not in VALID_EMPTY_AFTER_REMOVAL_MODES:
        raise ValueError(f"Unsupported empty-after-removal mode: {value}")
    return value


def resolve_request_profile(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_REQUEST_PROFILE_ENV)
        or config_string_value(config, "request_profile", config_path)
        or "moderate"
    )
    if value not in VALID_REQUEST_PROFILES:
        raise ValueError(f"Unsupported request profile: {value}")
    return value


def resolve_quota_units_per_second(
    explicit: float | None,
    config: dict[str, object],
    config_path: Path,
    request_profile: str,
) -> float:
    value = explicit if explicit is not None else env_float(DEFAULT_QUOTA_UNITS_PER_SECOND_ENV)
    if value is None:
        value = config_float_value(config, "quota_units_per_second", config_path)
    if value is None:
        value = float(REQUEST_PROFILE_CONFIG[request_profile]["quota_units_per_second"])
    if value <= 0:
        raise ValueError("--quota-units-per-second must be greater than 0")
    if value > GMAIL_PUBLISHED_USER_QUOTA_UNITS_PER_SECOND:
        raise ValueError(
            "--quota-units-per-second must not exceed Google's published per-user Gmail API limit "
            f"of {GMAIL_PUBLISHED_USER_QUOTA_UNITS_PER_SECOND:g}"
        )
    return value


def resolve_progress_format(explicit: str | None, config: dict[str, object], config_path: Path) -> str:
    value = (
        explicit
        or os.environ.get(DEFAULT_PROGRESS_FORMAT_ENV)
        or config_string_value(config, "progress_format", config_path)
        or "text"
    )
    if value not in VALID_PROGRESS_FORMATS:
        raise ValueError(f"Unsupported progress format: {value}")
    return value


def resolve_readable_folders(explicit: bool, config: dict[str, object], config_path: Path) -> bool:
    configured = config_bool_value(config, "readable_folders", config_path)
    return explicit or bool(configured)


def resolve_audit_label_settings(args: argparse.Namespace, config: dict[str, object], config_path: Path) -> AuditLabelSettings:
    use_defaults = bool(getattr(args, "audit_labels", False))
    configured_defaults = config_bool_value(config, "audit_labels", config_path)
    if configured_defaults is not None:
        use_defaults = use_defaults or configured_defaults
    processed = (
        getattr(args, "label_processed", None)
        or os.environ.get(DEFAULT_LABEL_PROCESSED_ENV)
        or config_string_value(config, "label_processed", config_path)
    )
    review = (
        getattr(args, "label_review", None)
        or os.environ.get(DEFAULT_LABEL_REVIEW_ENV)
        or config_string_value(config, "label_review", config_path)
    )
    if use_defaults:
        processed = processed or DEFAULT_PROCESSED_LABEL
        review = review or DEFAULT_REVIEW_LABEL
    return AuditLabelSettings(
        processed=processed.strip() if isinstance(processed, str) and processed.strip() else None,
        review=review.strip() if isinstance(review, str) and review.strip() else None,
    )


def path_from_env(name: str) -> Path | None:
    value = os.environ.get(name)
    return Path(value).expanduser() if value else None
