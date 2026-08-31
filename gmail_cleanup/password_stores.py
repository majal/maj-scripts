"""JSON-file-backed local stores for gmail-cleanup's PDF password learning:
recipe store (which cracking recipe worked for a sender/filename pattern),
secret store (the actual learned password, file-permission-locked 0600),
and per-family failure-count store used for backoff.

Extracted verbatim from the ``gmail-cleanup`` script as part of the
UNIX-philosophy/modularity split (see repo-template-standard.md item 10).
Depends only on the standard library plus gmail_cleanup.constants (already
extracted), so it moved as the eighth self-contained piece. No behavior
changes.
"""

from __future__ import annotations

import json
import os
import sys

from gmail_cleanup.constants import (
    PASSWORD_FAILURE_STORE_PATH,
    PASSWORD_RECIPE_STORE_PATH,
    PASSWORD_SECRET_STORE_PATH,
)


def load_password_recipe_store() -> dict[str, object]:
    if not PASSWORD_RECIPE_STORE_PATH.exists():
        return {}
    try:
        return json.loads(PASSWORD_RECIPE_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_password_recipe_store(store: dict[str, object]) -> None:
    PASSWORD_RECIPE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PASSWORD_RECIPE_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(store, sort_keys=True, indent=2), encoding="utf-8")
    temp_path.replace(PASSWORD_RECIPE_STORE_PATH)


def load_password_secret_store() -> dict[str, object]:
    if not PASSWORD_SECRET_STORE_PATH.exists():
        return {}
    try:
        return json.loads(PASSWORD_SECRET_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_password_secret_store(store: dict[str, object]) -> None:
    PASSWORD_SECRET_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PASSWORD_SECRET_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(store, sort_keys=True, indent=2), encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(temp_path, 0o600)
    temp_path.replace(PASSWORD_SECRET_STORE_PATH)
    if not sys.platform.startswith("win"):
        os.chmod(PASSWORD_SECRET_STORE_PATH, 0o600)


def load_password_failure_store() -> dict[str, object]:
    if not PASSWORD_FAILURE_STORE_PATH.exists():
        return {}
    try:
        return json.loads(PASSWORD_FAILURE_STORE_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def save_password_failure_store(store: dict[str, object]) -> None:
    PASSWORD_FAILURE_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    temp_path = PASSWORD_FAILURE_STORE_PATH.with_suffix(".tmp")
    temp_path.write_text(json.dumps(store, sort_keys=True, indent=2), encoding="utf-8")
    if not sys.platform.startswith("win"):
        os.chmod(temp_path, 0o600)
    temp_path.replace(PASSWORD_FAILURE_STORE_PATH)
    if not sys.platform.startswith("win"):
        os.chmod(PASSWORD_FAILURE_STORE_PATH, 0o600)
