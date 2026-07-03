"""Tests for witness tools — seal verification, error handling, config integration."""

from __future__ import annotations

import base64

import synpareia
from synpareia.seal import SealPayload, create_seal
from synpareia.types import SealType

from synpareia_trust_mcp.app import AppContext, _create_witness_client
from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.journal import JournalStore
from synpareia_trust_mcp.profile import ProfileManager
from synpareia_trust_mcp.tools.witness import (
    _require_witness,
    witness_verify_seal,
)


class TestRequireWitness:
    def test_raises_when_no_client(self, profile_manager: ProfileManager, config: Config) -> None:
        app = AppContext(
            config=config,
            profile_manager=profile_manager,
            conversation_manager=ConversationManager(profile_manager, config.data_dir),
            journal_store=JournalStore(config.data_dir),
            witness_client=None,
        )
        import pytest

        with pytest.raises(ValueError, match="Witness service is disabled by configuration"):
            _require_witness(app)

    def test_passes_with_client(self, profile_manager: ProfileManager, config: Config) -> None:
        """Should not raise when witness_client is set (use a sentinel object)."""

        class FakeClient:
            pass

        app = AppContext(
            config=config,
            profile_manager=profile_manager,
            conversation_manager=ConversationManager(profile_manager, config.data_dir),
            journal_store=JournalStore(config.data_dir),
            witness_client=FakeClient(),  # type: ignore[arg-type]
        )
        _require_witness(app)  # Should not raise


class TestCreateWitnessClient:
    def test_returns_none_without_url(self, config: Config) -> None:
        assert _create_witness_client(config) is None

    def test_creates_client_with_url(self, tmp_data_dir) -> None:
        config = Config(
            data_dir=tmp_data_dir,
            display_name=None,
            private_key_b64=None,
            network_url=None,
            auto_register=False,
            witness_url="https://witness.example.com",
            witness_token=None,
            moltbook_api_url=None,
            moltrust_api_key=None,
        )
        client = _create_witness_client(config)
        assert client is not None
        assert client._base_url == "https://witness.example.com"

    def test_creates_client_with_token(self, tmp_data_dir) -> None:
        config = Config(
            data_dir=tmp_data_dir,
            display_name=None,
            private_key_b64=None,
            network_url=None,
            auto_register=False,
            witness_url="https://witness.example.com",
            witness_token="my-secret-token",
            moltbook_api_url=None,
            moltrust_api_key=None,
        )
        client = _create_witness_client(config)
        assert client is not None
        # The httpx client should have the token in default headers
        assert client._client.headers.get("X-Access-Token") == "my-secret-token"


class TestVerifySealOffline:
    """Test offline seal verification — no network needed."""

    def _make_seal(self) -> tuple[SealPayload, bytes, bytes]:
        """Create a valid seal for testing."""
        witness_profile = synpareia.generate()
        block = synpareia.create_block(synpareia.generate(), "message", "test content")

        seal = create_seal(
            witness_private_key=witness_profile.private_key,
            witness_id=witness_profile.id,
            seal_type=SealType.TIMESTAMP,
            target_block_hash=block.content_hash,
        )
        return seal, witness_profile.public_key, block.content_hash

    def test_valid_seal_passes(self) -> None:
        seal, public_key, block_hash = self._make_seal()

        # Call the tool function directly (without MCP context)
        # We need to bypass the ctx parameter — call the underlying logic
        from synpareia.seal.verify import verify_seal

        valid, error = verify_seal(seal, public_key)
        assert valid
        assert error is None

    # These call the REAL witness_verify_seal tool (not a copy) so the tests track
    # shipping behaviour — the divergent hand-copy that used to live here is exactly
    # the seam LR-6 slipped through (it hand-bridged target_block_hash_hex). The
    # tool is offline, so app_ctx (witness_client=None) is a sufficient context.

    def test_verify_seal_offline_valid(self, app_ctx) -> None:
        ctx, _ = app_ctx
        seal, public_key, block_hash = self._make_seal()
        result = witness_verify_seal(
            seal_type=str(seal.seal_type),
            witness_id=seal.witness_id,
            witness_signature_b64=base64.b64encode(seal.witness_signature).decode(),
            sealed_at=seal.sealed_at.isoformat(),
            witness_public_key_b64=base64.b64encode(public_key).decode(),
            target_block_hash_hex=block_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is True

    def test_verify_seal_offline_wrong_key(self, app_ctx) -> None:
        ctx, _ = app_ctx
        seal, _, block_hash = self._make_seal()
        wrong_key = synpareia.generate().public_key
        result = witness_verify_seal(
            seal_type=str(seal.seal_type),
            witness_id=seal.witness_id,
            witness_signature_b64=base64.b64encode(seal.witness_signature).decode(),
            sealed_at=seal.sealed_at.isoformat(),
            witness_public_key_b64=base64.b64encode(wrong_key).decode(),
            target_block_hash_hex=block_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is False

    def test_verify_seal_offline_tampered_timestamp(self, app_ctx) -> None:
        ctx, _ = app_ctx
        seal, public_key, block_hash = self._make_seal()
        result = witness_verify_seal(
            seal_type=str(seal.seal_type),
            witness_id=seal.witness_id,
            witness_signature_b64=base64.b64encode(seal.witness_signature).decode(),
            sealed_at="2099-01-01T00:00:00+00:00",  # tampered
            witness_public_key_b64=base64.b64encode(public_key).decode(),
            target_block_hash_hex=block_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is False

    def test_verify_seal_offline_invalid_inputs(self, app_ctx) -> None:
        ctx, _ = app_ctx
        # Malformed sig/key WITH a target present, so we reach the crypto path
        # (a missing target is a separate, structured incomplete-input case — see
        # test_roundtrip_contracts.py::test_missing_target_reads_as_incomplete_not_invalid).
        result = witness_verify_seal(
            seal_type="timestamp",
            witness_id="did:synpareia:fake",
            witness_signature_b64="not-valid-base64!!!",
            sealed_at="2026-01-01T00:00:00+00:00",
            witness_public_key_b64="also-not-valid!!!",
            target_block_hash_hex="ab" * 32,
            ctx=ctx,
        )
        assert result["valid"] is False
        assert "error" in result
