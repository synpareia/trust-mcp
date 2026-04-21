"""Regression tests for filesystem permission exploits (ADV-020).

The agent's Ed25519 private key lives in profile.json. Any window where
the file is world-readable lets a local attacker loop-read and win a
TOCTOU race. The file must be created atomically with 0o600 from the
outset — no later chmod."""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

from synpareia_trust_mcp.profile import ProfileManager

if TYPE_CHECKING:
    import pytest


def _mode(path: Path) -> int:
    return os.stat(path).st_mode & 0o777


class TestProfileFilePermissions:
    """ADV-020 — profile.json is never world-readable, even transiently."""

    def test_profile_json_is_0o600(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "synpareia"
        pm = ProfileManager(data_dir)
        pm.ensure_profile()

        profile_path = data_dir / "profile.json"
        assert profile_path.is_file()
        assert _mode(profile_path) == 0o600, (
            f"profile.json has mode {oct(_mode(profile_path))}, expected 0o600"
        )

    def test_data_dir_is_0o700(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "synpareia"
        pm = ProfileManager(data_dir)
        pm.ensure_profile()

        mode = _mode(data_dir)
        # On systems where the umask or FS prevents 0o700, we at least
        # require that group and other have NO permissions.
        assert mode & 0o077 == 0, (
            f"data_dir has mode {oct(mode)}, must not be group/world accessible"
        )

    def test_conversation_files_not_world_readable(self, tmp_path: Path) -> None:
        """Companion to ADV-020 — persisted conversations also contained
        sensitive data (recorded messages, counterparties). They must not
        be 0o664 on a shared host."""
        from synpareia_trust_mcp.conversations import ConversationManager

        data_dir = tmp_path / "synpareia"
        pm = ProfileManager(data_dir)
        pm.ensure_profile()
        cm = ConversationManager(pm, data_dir)

        conv = cm.start("test", counterparty="did:example:bob")
        cm.add_message(conv.conversation_id, "hello", block_type="message")
        cm.end(conv.conversation_id)

        conv_files = list((data_dir / "conversations").glob("conv_*.json"))
        assert len(conv_files) == 1
        mode = _mode(conv_files[0])
        assert mode & 0o077 == 0, (
            f"conversation file has mode {oct(mode)}, must not be group/world accessible"
        )

    def test_rewrite_does_not_open_permissive_window(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Overwriting an existing profile.json must never leave it world-
        readable mid-write. We check this by hooking open() to observe the
        mode passed on creation."""
        data_dir = tmp_path / "synpareia"
        data_dir.mkdir()

        # Seed an existing profile
        pm = ProfileManager(data_dir)
        pm.ensure_profile()

        observed_modes: list[int] = []
        real_open = os.open
        target = str(data_dir / "profile.json")

        def recording_open(*args, **kwargs):  # type: ignore[no-untyped-def]
            if args and str(args[0]) == target and len(args) >= 3:
                observed_modes.append(args[2])
            return real_open(*args, **kwargs)

        monkeypatch.setattr(os, "open", recording_open)

        # Force a re-save via a fresh ProfileManager + explicit private key
        import base64

        import synpareia

        existing = pm.profile
        assert existing.private_key is not None
        pk_b64 = base64.b64encode(existing.private_key).decode()

        pm2 = ProfileManager(data_dir, private_key_b64=pk_b64)
        pm2.ensure_profile()

        assert observed_modes, "no open() call observed — test wiring issue"
        for m in observed_modes:
            assert m == 0o600, f"profile.json created with permissive mode {oct(m)}"

        # Reload should still work (sanity)
        pm3 = ProfileManager(data_dir)
        pm3.ensure_profile()
        assert pm3.profile.id == existing.id

        del synpareia  # silence linter
