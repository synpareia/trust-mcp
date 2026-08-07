"""Tests for the shared filesystem durability helpers (fsutil)."""

from __future__ import annotations

from pathlib import Path

from synpareia_trust_mcp.fsutil import atomic_write_bytes, quarantine_corrupt_file


class TestAtomicWriteBytes:
    def test_writes_payload_with_0600_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_bytes(target, b"hello")
        assert target.read_bytes() == b"hello"
        assert (target.stat().st_mode & 0o777) == 0o600

    def test_overwrites_an_existing_file(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        target.write_bytes(b"old")
        atomic_write_bytes(target, b"new")
        assert target.read_bytes() == b"new"

    def test_leaves_no_temp_file_behind(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_bytes(target, b"x")
        assert list(tmp_path.glob("*.tmp")) == []

    def test_clears_a_stale_temp_from_a_prior_crash(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        # Simulate a crash that left a temp file (O_EXCL would otherwise fail on it).
        (tmp_path / "data.json.tmp").write_bytes(b"stale")
        atomic_write_bytes(target, b"fresh")
        assert target.read_bytes() == b"fresh"
        assert list(tmp_path.glob("*.tmp")) == []

    def test_honours_a_custom_mode(self, tmp_path: Path) -> None:
        target = tmp_path / "data.json"
        atomic_write_bytes(target, b"x", mode=0o640)
        assert (target.stat().st_mode & 0o777) == 0o640


class TestQuarantineCorruptFile:
    def test_moves_the_file_aside_and_returns_the_backup(self, tmp_path: Path) -> None:
        target = tmp_path / "counterparties.json"
        target.write_text("corrupt {{{")

        backup = quarantine_corrupt_file(target)

        assert backup is not None
        assert backup.name.startswith("counterparties.json.corrupt-")
        assert backup.read_text() == "corrupt {{{"
        assert not target.exists()  # moved, not copied

    def test_returns_none_when_the_file_is_missing(self, tmp_path: Path) -> None:
        # A best-effort move of a non-existent file fails softly (caller still proceeds).
        assert quarantine_corrupt_file(tmp_path / "gone.json") is None
