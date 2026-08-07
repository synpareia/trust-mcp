"""Filesystem durability helpers shared by the local stores (journal + profile).

Both `counterparties.json` (journal) and `profile.json` (keypair/DID) are
single-file stores that must survive a crash mid-write and never exist with a
wider-than-0o600 mode. This module centralises the two mechanics they share:

* `atomic_write_bytes` — temp-file + `os.replace` write, so a crash leaves the
  intact old file or the intact new one, never a truncated one.
* `quarantine_corrupt_file` — move a whole-file-corrupt store aside before a
  rewrite would overwrite (and permanently lose) it.
"""

from __future__ import annotations

import contextlib
import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def atomic_write_bytes(path: Path, payload: bytes, *, mode: int = 0o600) -> None:
    """Write ``payload`` to ``path`` atomically with ``mode`` permissions.

    Writes to a sibling temp file — opened ``O_EXCL`` with ``mode``, so it never
    exists with a wider mode (closes the chmod-after-create TOCTOU, ADV-020) —
    then ``os.replace``s it over ``path``. Because the rename is atomic, a crash
    leaves either the intact old file or the intact new file, never a truncated
    one. A stale temp file from a prior crash is cleared first (the next write is
    self-healing).
    """
    tmp = path.with_name(path.name + ".tmp")
    tmp.unlink(missing_ok=True)
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, mode)
    with os.fdopen(fd, "wb") as f:
        f.write(payload)
    os.replace(tmp, path)
    # O_CREAT's mode is masked by umask, so re-assert the exact mode (belt-and-suspenders).
    with contextlib.suppress(OSError):
        path.chmod(mode)


def quarantine_corrupt_file(path: Path) -> Path | None:
    """Move a corrupt file aside to ``{name}.corrupt-<timestamp>`` (best-effort).

    Returns the backup path, or ``None`` if the move failed. The point is to
    PRESERVE data before a rewrite would destroy it — never to crash the caller
    over a failed preservation, so a failed move is swallowed and reported via
    the return value. Mirrors the ``profile.json`` auto-recover quarantine so the
    two stores behave consistently on corruption.
    """
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%fZ")
    backup = path.with_name(f"{path.name}.corrupt-{stamp}")
    try:
        path.rename(backup)
    except OSError:
        return None
    return backup
