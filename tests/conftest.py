"""Shared fixtures for Trust Toolkit tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import synpareia

from synpareia_trust_mcp.app import AppContext
from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager

pytest_plugins = ["tests.stubs.fixtures"]


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
        private_key_b64=None,
        network_url=None,
        auto_register=False,
        witness_url=None,
        witness_token=None,
        moltbook_api_url=None,
        moltrust_api_key=None,
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


def _make_ctx(app: AppContext) -> Any:
    """Build a fake FastMCP Context wrapping an AppContext.

    Tools dereference `ctx.request_context.lifespan_context` — we only
    need that attribute chain to exist for direct tool invocation.
    """
    return SimpleNamespace(
        request_context=SimpleNamespace(lifespan_context=app),
    )


@pytest.fixture()
def app_ctx(
    profile_manager: ProfileManager,
    conversation_manager: ConversationManager,
    config: Config,
):
    """Direct-invocation harness for MCP tools.

    Returns (ctx, app_context) where ctx is a fake FastMCP Context that
    tools can consume exactly as they would in a live server session.
    """
    app = AppContext(
        config=config,
        profile_manager=profile_manager,
        conversation_manager=conversation_manager,
        witness_client=None,
    )
    return _make_ctx(app), app


@pytest.fixture()
def app_ctx_with_stubs(
    profile_manager: ProfileManager,
    conversation_manager: ConversationManager,
    config_with_stubs: Config,
):
    """Same as app_ctx but with providers configured against in-process
    stubs (Moltbook, MolTrust, synpareia-network)."""
    # profile_manager and conversation_manager depend on `config` (not
    # `config_with_stubs`), but the data_dir they use is independent of
    # provider URLs — those are only consumed by providers.py. Rebuild
    # the conversation manager so it shares the new data_dir.
    pm = ProfileManager(
        config_with_stubs.data_dir,
        private_key_b64=config_with_stubs.private_key_b64,
    )
    pm.ensure_profile()
    cm = ConversationManager(pm, config_with_stubs.data_dir)
    app = AppContext(
        config=config_with_stubs,
        profile_manager=pm,
        conversation_manager=cm,
        witness_client=None,
    )
    return _make_ctx(app), app


@pytest.fixture()
def app_ctx_with_witness(
    profile_manager: ProfileManager,
    conversation_manager: ConversationManager,
    config: Config,
    witness_client,
):
    """app_ctx that has a live in-process witness client attached."""
    from dataclasses import replace

    config_with_witness = replace(config, witness_url="http://witness.test")
    app = AppContext(
        config=config_with_witness,
        profile_manager=profile_manager,
        conversation_manager=conversation_manager,
        witness_client=witness_client,
    )
    return _make_ctx(app), app
