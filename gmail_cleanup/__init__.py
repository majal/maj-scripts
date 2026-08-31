"""Support package for the ``gmail-cleanup`` CLI.

This package holds pieces of ``gmail-cleanup`` (the executable script at the
repo root) that have been split out into focused, single-purpose modules.
The top-level script remains the actual CLI entrypoint and imports from this
package; nothing here is meant to be run directly.
"""

from __future__ import annotations
