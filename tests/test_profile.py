"""Tests for profile management — generation, persistence, reload."""

from __future__ import annotations

import json
from pathlib import Path

import synpareia

from synpareia_trust_mcp.profile import ProfileManager


class TestProfileGeneration:
    def test_generates_profile_on_first_run(self, tmp_data_dir: Path) -> None:
        pm = ProfileManager(tmp_data_dir)
        profile = pm.ensure_profile()

        assert profile.id.startswith("did:synpareia:")
        assert len(profile.public_key) == 32
        assert profile.private_key is not None
        assert len(profile.private_key) == 32

    def test_creates_data_directory(self, tmp_data_dir: Path) -> None:
        assert not tmp_data_dir.exists()
        pm = ProfileManager(tmp_data_dir)
        pm.ensure_profile()
        assert tmp_data_dir.exists()

    def test_writes_profile_file(self, tmp_data_dir: Path) -> None:
        pm = ProfileManager(tmp_data_dir)
        pm.ensure_profile()

        profile_path = tmp_data_dir / "profile.json"
        assert profile_path.exists()

        data = json.loads(profile_path.read_text())
        assert "did" in data
        assert "public_key" in data
        assert "private_key" in data
        assert "created_at" in data

    def test_profile_file_has_restricted_permissions(self, tmp_data_dir: Path) -> None:
        pm = ProfileManager(tmp_data_dir)
        pm.ensure_profile()

        profile_path = tmp_data_dir / "profile.json"
        mode = profile_path.stat().st_mode & 0o777
        assert mode == 0o600, f"Expected 0600, got {oct(mode)}"


class TestProfilePersistence:
    def test_reloads_same_identity(self, tmp_data_dir: Path) -> None:
        pm1 = ProfileManager(tmp_data_dir)
        profile1 = pm1.ensure_profile()

        pm2 = ProfileManager(tmp_data_dir)
        profile2 = pm2.ensure_profile()

        assert profile1.id == profile2.id
        assert profile1.public_key == profile2.public_key
        assert profile1.private_key == profile2.private_key

    def test_does_not_overwrite_existing_profile(self, tmp_data_dir: Path) -> None:
        pm1 = ProfileManager(tmp_data_dir)
        pm1.ensure_profile()

        # Modify the file's mtime to verify it's not rewritten
        profile_path = tmp_data_dir / "profile.json"
        mtime1 = profile_path.stat().st_mtime

        pm2 = ProfileManager(tmp_data_dir)
        pm2.ensure_profile()

        mtime2 = profile_path.stat().st_mtime
        assert mtime1 == mtime2

    def test_reloaded_profile_can_sign(self, tmp_data_dir: Path) -> None:
        pm1 = ProfileManager(tmp_data_dir)
        pm1.ensure_profile()

        pm2 = ProfileManager(tmp_data_dir)
        profile2 = pm2.ensure_profile()

        # Sign with reloaded profile
        content = b"test message"
        signature = synpareia.sign(profile2.private_key, content)
        assert synpareia.verify(profile2.public_key, content, signature)


class TestProfileData:
    def test_get_profile_data_excludes_private_key(self, profile_manager: ProfileManager) -> None:
        data = profile_manager.get_profile_data()

        assert "did" in data
        assert "public_key_b64" in data
        assert "has_private_key" in data
        assert data["has_private_key"] is True
        assert "private_key" not in data

    def test_raises_before_ensure(self, tmp_data_dir: Path) -> None:
        pm = ProfileManager(tmp_data_dir)
        import pytest

        with pytest.raises(RuntimeError, match="not initialized"):
            _ = pm.profile
