"""Tests for commit-reveal scheme — seal, reveal, stateless nonce handling."""

from __future__ import annotations

import base64
import os

from synpareia_trust_mcp.conversations import ConversationManager


class TestSealCommitment:
    def test_seal_returns_hash_and_nonce(self, conversation_manager: ConversationManager) -> None:
        result = conversation_manager.seal_commitment("My assessment: 4/5")

        assert "commitment_hash" in result
        assert "nonce_b64" in result
        assert "block_id" in result
        assert "instructions" in result

    def test_seal_hash_is_hex(self, conversation_manager: ConversationManager) -> None:
        result = conversation_manager.seal_commitment("Test content")
        # Should be valid hex
        bytes.fromhex(result["commitment_hash"])

    def test_seal_nonce_is_base64(self, conversation_manager: ConversationManager) -> None:
        result = conversation_manager.seal_commitment("Test content")
        nonce = base64.b64decode(result["nonce_b64"])
        assert len(nonce) == 32  # 32-byte random nonce

    def test_different_content_different_hash(
        self, conversation_manager: ConversationManager
    ) -> None:
        r1 = conversation_manager.seal_commitment("Assessment A")
        r2 = conversation_manager.seal_commitment("Assessment B")
        assert r1["commitment_hash"] != r2["commitment_hash"]

    def test_same_content_different_nonce(self, conversation_manager: ConversationManager) -> None:
        r1 = conversation_manager.seal_commitment("Same content")
        r2 = conversation_manager.seal_commitment("Same content")
        # Different random nonces produce different hashes
        assert r1["commitment_hash"] != r2["commitment_hash"]
        assert r1["nonce_b64"] != r2["nonce_b64"]


class TestRevealCommitment:
    def test_reveal_with_correct_content(self, conversation_manager: ConversationManager) -> None:
        seal = conversation_manager.seal_commitment("My rating: 5 stars")
        reveal = conversation_manager.reveal_commitment(
            seal["commitment_hash"], "My rating: 5 stars", seal["nonce_b64"]
        )

        assert reveal["valid"] is True
        assert reveal["content"] == "My rating: 5 stars"

    def test_reveal_with_tampered_content(self, conversation_manager: ConversationManager) -> None:
        seal = conversation_manager.seal_commitment("My rating: 5 stars")
        reveal = conversation_manager.reveal_commitment(
            seal["commitment_hash"], "TAMPERED: 1 star", seal["nonce_b64"]
        )

        assert reveal["valid"] is False

    def test_reveal_with_wrong_nonce(self, conversation_manager: ConversationManager) -> None:
        seal = conversation_manager.seal_commitment("Test content")
        wrong_nonce = base64.b64encode(os.urandom(32)).decode()

        reveal = conversation_manager.reveal_commitment(
            seal["commitment_hash"], "Test content", wrong_nonce
        )

        assert reveal["valid"] is False

    def test_reveal_with_invalid_hash(self, conversation_manager: ConversationManager) -> None:
        seal = conversation_manager.seal_commitment("Test")
        reveal = conversation_manager.reveal_commitment("not_valid_hex", "Test", seal["nonce_b64"])

        assert reveal["valid"] is False
        assert "error" in reveal

    def test_reveal_with_invalid_nonce(self, conversation_manager: ConversationManager) -> None:
        seal = conversation_manager.seal_commitment("Test")
        reveal = conversation_manager.reveal_commitment(
            seal["commitment_hash"], "Test", "not_valid_base64!!!"
        )

        assert reveal["valid"] is False
        assert "error" in reveal


class TestStatelessNonce:
    """Verify that commitments survive server restart (caller holds nonce)."""

    def test_reveal_works_with_fresh_manager(self, profile_manager, config) -> None:
        cm1 = ConversationManager(profile_manager, config.data_dir)
        seal = cm1.seal_commitment("Sealed before restart")

        # Simulate server restart — new ConversationManager, no shared state
        cm2 = ConversationManager(profile_manager, config.data_dir)
        reveal = cm2.reveal_commitment(
            seal["commitment_hash"],
            "Sealed before restart",
            seal["nonce_b64"],
        )

        assert reveal["valid"] is True

    def test_nonce_not_stored_on_server(self, conversation_manager: ConversationManager) -> None:
        """Verify the server has no _commitments dict (stateless approach)."""
        assert not hasattr(conversation_manager, "_commitments")
