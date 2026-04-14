"""Shared fixtures for Trust Toolkit tests."""

from __future__ import annotations

from pathlib import Path

import pytest
import synpareia

from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager


@pytest.fixture()
def tmp_data_dir(tmp_path: Path) -> Path:
    """Temporary data directory for test isolation."""
    return tmp_path / "synpareia"


@pytest.fixture()
def config(tmp_data_dir: Path) -> Config:
    """Config pointing at the temporary data directory."""
    return Config(
        data_dir=tmp_data_dir,
        display_name="Test Agent",
        network_url=None,
        auto_register=False,
        witness_url=None,
        witness_token=None,
    )


@pytest.fixture()
def profile_manager(config: Config) -> ProfileManager:
    """ProfileManager with a generated profile."""
    pm = ProfileManager(config.data_dir)
    pm.ensure_profile()
    return pm


@pytest.fixture()
def conversation_manager(profile_manager: ProfileManager, config: Config) -> ConversationManager:
    """ConversationManager ready for use."""
    return ConversationManager(profile_manager, config.data_dir)


@pytest.fixture()
def alice() -> synpareia.Profile:
    """A test profile (Alice)."""
    return synpareia.generate()


@pytest.fixture()
def bob() -> synpareia.Profile:
    """A second test profile (Bob)."""
    return synpareia.generate()
