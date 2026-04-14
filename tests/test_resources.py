"""Tests for MCP resources."""

from __future__ import annotations

import json
from pathlib import Path

from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager
from synpareia_trust_mcp.resources import conversations_resource, identity_resource


class FakeLifespan:
    """Minimal stand-in for the lifespan context."""

    def __init__(self, config: Config, pm: ProfileManager, cm: ConversationManager) -> None:
        self.config = config
        self.profile_manager = pm
        self.conversation_manager = cm


class FakeRequestContext:
    def __init__(self, lifespan: FakeLifespan) -> None:
        self.lifespan_context = lifespan


class FakeContext:
    """Minimal stand-in for mcp Context."""

    def __init__(self, lifespan: FakeLifespan) -> None:
        self.request_context = FakeRequestContext(lifespan)


class TestIdentityResource:
    def test_returns_valid_json(
        self,
        config: Config,
        profile_manager: ProfileManager,
        conversation_manager: ConversationManager,
    ) -> None:
        ctx = FakeContext(FakeLifespan(config, profile_manager, conversation_manager))
        result = identity_resource(ctx)  # type: ignore[arg-type]
        data = json.loads(result)

        assert "did" in data
        assert data["did"].startswith("did:synpareia:")
        assert "public_key_b64" in data
        assert data["display_name"] == "Test Agent"
        assert data["network_configured"] is False

    def test_network_configured_when_url_set(
        self, profile_manager: ProfileManager, tmp_data_dir: Path
    ) -> None:
        config = Config(
            data_dir=tmp_data_dir,
            display_name=None,
            network_url="https://api.example.com",
            auto_register=True,
            witness_url=None,
            witness_token=None,
        )
        cm = ConversationManager(profile_manager, config.data_dir)
        ctx = FakeContext(FakeLifespan(config, profile_manager, cm))
        result = identity_resource(ctx)  # type: ignore[arg-type]
        data = json.loads(result)
        assert data["network_configured"] is True


class TestConversationsResource:
    def test_empty_when_no_conversations(
        self,
        config: Config,
        profile_manager: ProfileManager,
        conversation_manager: ConversationManager,
    ) -> None:
        ctx = FakeContext(FakeLifespan(config, profile_manager, conversation_manager))
        result = conversations_resource(ctx)  # type: ignore[arg-type]
        data = json.loads(result)

        assert data["active"] == []
        assert data["recent"] == []

    def test_shows_active_conversation(
        self,
        config: Config,
        profile_manager: ProfileManager,
        conversation_manager: ConversationManager,
    ) -> None:
        conversation_manager.start("Test conversation")
        ctx = FakeContext(FakeLifespan(config, profile_manager, conversation_manager))
        result = conversations_resource(ctx)  # type: ignore[arg-type]
        data = json.loads(result)

        assert len(data["active"]) == 1
        assert data["active"][0]["description"] == "Test conversation"

    def test_shows_recent_completed(
        self,
        config: Config,
        profile_manager: ProfileManager,
        conversation_manager: ConversationManager,
    ) -> None:
        conv = conversation_manager.start("Completed conv")
        conversation_manager.end(conv.conversation_id)

        ctx = FakeContext(FakeLifespan(config, profile_manager, conversation_manager))
        result = conversations_resource(ctx)  # type: ignore[arg-type]
        data = json.loads(result)

        assert len(data["active"]) == 0
        assert len(data["recent"]) == 1
        assert data["recent"][0]["status"] == "completed"
