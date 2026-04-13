"""Tests for conversation lifecycle — start, record, end, export."""

from __future__ import annotations

import json

import pytest
import synpareia

from synpareia_trust_mcp.conversations import ConversationManager


class TestConversationLifecycle:
    def test_start_creates_conversation(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test conversation")

        assert conv.conversation_id.startswith("conv_")
        assert conv.description == "Test conversation"
        assert conv.counterparty is None
        assert conv.block_count == 1  # system start block

    def test_start_with_counterparty(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Negotiation", counterparty="did:synpareia:abc123")
        assert conv.counterparty == "did:synpareia:abc123"

    def test_add_message_increments_count(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test")
        assert conv.block_count == 1

        count = conversation_manager.add_message(conv.conversation_id, "Hello")
        assert count == 2

        count = conversation_manager.add_message(conv.conversation_id, "World")
        assert count == 3

    def test_add_message_custom_type(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test")
        count = conversation_manager.add_message(
            conv.conversation_id, "Thinking...", block_type="thought"
        )
        assert count == 2

    def test_end_returns_summary(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test")
        conversation_manager.add_message(conv.conversation_id, "Hello")
        conversation_manager.add_message(conv.conversation_id, "Goodbye")

        result = conversation_manager.end(conv.conversation_id, rating=4, notes="Good")

        assert result["conversation_id"] == conv.conversation_id
        assert result["blocks"] == 4  # start + 2 messages + end
        assert "chain_id" in result
        assert "head_hash" in result

    def test_end_persists_to_disk(self, conversation_manager: ConversationManager, config) -> None:
        conv = conversation_manager.start("Test")
        conversation_manager.end(conv.conversation_id)

        conv_dir = config.data_dir / "conversations"
        files = list(conv_dir.glob("conv_*.json"))
        assert len(files) == 1

        data = json.loads(files[0].read_text())
        assert "positions" in data
        assert "head_hash" in data

    def test_end_removes_from_active(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test")
        conversation_manager.end(conv.conversation_id)

        with pytest.raises(ValueError, match="No active conversation"):
            conversation_manager.add_message(conv.conversation_id, "Late message")

    def test_export_active_conversation(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Test")
        conversation_manager.add_message(conv.conversation_id, "Hello")

        export = conversation_manager.export(conv.conversation_id)

        assert "positions" in export
        assert len(export["positions"]) == 2  # start + message

    def test_list_active(self, conversation_manager: ConversationManager) -> None:
        conv1 = conversation_manager.start("Conv 1")
        conv2 = conversation_manager.start("Conv 2")

        active = conversation_manager.list_active()
        assert len(active) == 2

        ids = {c["conversation_id"] for c in active}
        assert conv1.conversation_id in ids
        assert conv2.conversation_id in ids

    def test_multiple_concurrent_conversations(
        self, conversation_manager: ConversationManager
    ) -> None:
        conv1 = conversation_manager.start("Conv 1")
        conv2 = conversation_manager.start("Conv 2")

        conversation_manager.add_message(conv1.conversation_id, "Message to conv 1")
        conversation_manager.add_message(conv2.conversation_id, "Message to conv 2")

        # End one, other should still be active
        conversation_manager.end(conv1.conversation_id)
        assert len(conversation_manager.list_active()) == 1

        # Can still add to conv2
        conversation_manager.add_message(conv2.conversation_id, "Another message")
        conversation_manager.end(conv2.conversation_id)
        assert len(conversation_manager.list_active()) == 0


class TestConversationErrors:
    def test_add_to_nonexistent_conversation(
        self, conversation_manager: ConversationManager
    ) -> None:
        with pytest.raises(ValueError, match="No active conversation"):
            conversation_manager.add_message("conv_doesnotexist", "Hello")

    def test_end_nonexistent_conversation(self, conversation_manager: ConversationManager) -> None:
        with pytest.raises(ValueError, match="No active conversation"):
            conversation_manager.end("conv_doesnotexist")

    def test_export_nonexistent_conversation(
        self, conversation_manager: ConversationManager
    ) -> None:
        with pytest.raises(ValueError, match="No active conversation"):
            conversation_manager.export("conv_doesnotexist")


class TestListActive:
    def test_list_empty(self, conversation_manager: ConversationManager) -> None:
        assert conversation_manager.list_active() == []

    def test_list_after_start(self, conversation_manager: ConversationManager) -> None:
        conversation_manager.start("Conv A")
        conversation_manager.start("Conv B")
        active = conversation_manager.list_active()
        assert len(active) == 2
        descriptions = {c["description"] for c in active}
        assert descriptions == {"Conv A", "Conv B"}

    def test_list_after_end(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Will end")
        conversation_manager.end(conv.conversation_id)
        assert conversation_manager.list_active() == []


class TestConversationVerification:
    def test_exported_chain_verifies(self, conversation_manager: ConversationManager) -> None:
        conv = conversation_manager.start("Verified test")
        conversation_manager.add_message(conv.conversation_id, "Message 1")
        conversation_manager.add_message(conv.conversation_id, "Message 2")

        export = conversation_manager.export(conv.conversation_id)
        valid, errors = synpareia.verify_export(export)
        assert valid, f"Chain should verify: {errors}"
