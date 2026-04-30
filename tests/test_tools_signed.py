"""Tests for Tier-4 encode_signed / decode_signed primitives."""

from __future__ import annotations

import json

from synpareia_trust_mcp.tools.signed import (
    SYNPAREIA_V1_PREFIX,
    decode_signed,
    encode_signed,
)


class TestEncodeSigned:
    def test_returns_prefixed_string(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = encode_signed(content="hello world", ctx=ctx)
        assert result["ok"] is True
        assert result["encoded"].startswith(SYNPAREIA_V1_PREFIX)
        assert result["signer_did"] == app.profile_manager.profile.id

    def test_reports_reputation_and_assurance_tiers(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = encode_signed(content="hello", ctx=ctx)
        assert result["reputation_tier"] == 4
        # Assurance is self-attested until witnessed
        assert result["assurance_tier"] == 1

    def test_rejects_empty_content(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = encode_signed(content="", ctx=ctx)
        assert "error" in result

    def test_rejects_oversized_content(self, app_ctx) -> None:
        ctx, app = app_ctx
        # 128KB payload — well over the 64KB cap
        result = encode_signed(content="a" * (128 * 1024), ctx=ctx)
        assert "error" in result

    def test_rejects_non_string_content(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = encode_signed(content=12345, ctx=ctx)  # type: ignore[arg-type]
        assert "error" in result


class TestDecodeSigned:
    def test_roundtrip_verifies(self, app_ctx) -> None:
        ctx, app = app_ctx
        encoded = encode_signed(content="the quick brown fox", ctx=ctx)["encoded"]
        result = decode_signed(encoded=encoded, ctx=ctx)
        assert result["synpareia_validated"] is True
        assert result["valid"] is True
        assert result["content"] == "the quick brown fox"
        assert result["signer_did"] == app.profile_manager.profile.id
        assert result["verified_at"] is not None

    def test_plain_string_passes_through_not_validated(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = decode_signed(encoded="hello from slack", ctx=ctx)
        assert result["synpareia_validated"] is False
        assert result["valid"] is False
        assert result["content"] == "hello from slack"
        assert result["signer_did"] is None

    def test_tampered_content_fails_verification(self, app_ctx) -> None:
        import base64

        ctx, app = app_ctx
        encoded = encode_signed(content="original", ctx=ctx)["encoded"]
        # Peel the prefix + base64, tamper content, re-encode
        body = encoded[len(SYNPAREIA_V1_PREFIX) :]
        decoded_json = json.loads(base64.urlsafe_b64decode(body))
        decoded_json["payload"]["content"] = "tampered"
        tampered = (
            SYNPAREIA_V1_PREFIX
            + base64.urlsafe_b64encode(json.dumps(decoded_json).encode()).decode()
        )
        result = decode_signed(encoded=tampered, ctx=ctx)
        assert result["synpareia_validated"] is True
        assert result["valid"] is False

    def test_malformed_base64_after_prefix(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = decode_signed(encoded=SYNPAREIA_V1_PREFIX + "!!!not-base64!!!", ctx=ctx)
        assert result["synpareia_validated"] is True
        assert result["valid"] is False

    def test_mismatched_did_and_public_key_fails(self, app_ctx) -> None:
        """A forger who drops in a new public key but keeps the victim's DID
        must not pass verification."""
        import base64

        import synpareia

        ctx, app = app_ctx
        encoded = encode_signed(content="hello", ctx=ctx)["encoded"]
        body = encoded[len(SYNPAREIA_V1_PREFIX) :]
        decoded_json = json.loads(base64.urlsafe_b64decode(body))
        # Swap in a different pubkey while keeping the victim's DID
        attacker = synpareia.generate()
        decoded_json["payload"]["public_key_b64"] = base64.b64encode(attacker.public_key).decode()
        forged = (
            SYNPAREIA_V1_PREFIX
            + base64.urlsafe_b64encode(json.dumps(decoded_json).encode()).decode()
        )
        result = decode_signed(encoded=forged, ctx=ctx)
        assert result["synpareia_validated"] is True
        assert result["valid"] is False

    def test_rejects_non_string_input(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = decode_signed(encoded=12345, ctx=ctx)  # type: ignore[arg-type]
        assert "error" in result

    def test_rejects_oversized_envelope(self, app_ctx) -> None:
        ctx, app = app_ctx
        # 256KB envelope — over cap
        huge = SYNPAREIA_V1_PREFIX + "a" * (256 * 1024)
        result = decode_signed(encoded=huge, ctx=ctx)
        assert "error" in result


class TestCrossAgentRoundtrip:
    def test_alice_encodes_bob_decodes(self, app_ctx, tmp_path) -> None:
        """Bob (a fresh AppContext with a distinct profile) can decode
        Alice's signed envelope.

        The envelope is self-contained: decoder does not need to share state
        with the encoder. signer_did comes from the envelope, not from Bob's
        profile.
        """
        from types import SimpleNamespace

        from synpareia_trust_mcp.app import AppContext
        from synpareia_trust_mcp.config import Config
        from synpareia_trust_mcp.conversations import ConversationManager
        from synpareia_trust_mcp.journal import JournalStore
        from synpareia_trust_mcp.profile import ProfileManager

        alice_ctx, alice_app = app_ctx
        # Build Bob from scratch in a fresh data dir so his key is distinct.
        bob_dir = tmp_path / "bob-synpareia"
        bob_config = Config(
            data_dir=bob_dir,
            display_name="Bob",
            private_key_b64=None,
            network_url=None,
            auto_register=False,
            witness_url=None,
            witness_token=None,
            moltbook_api_url=None,
            moltrust_api_key=None,
        )
        bob_pm = ProfileManager(bob_dir)
        bob_pm.ensure_profile()
        bob_cm = ConversationManager(bob_pm, bob_dir)
        bob_js = JournalStore(bob_dir)
        bob_app = AppContext(
            config=bob_config,
            profile_manager=bob_pm,
            conversation_manager=bob_cm,
            journal_store=bob_js,
            witness_client=None,
        )
        bob_ctx = SimpleNamespace(
            request_context=SimpleNamespace(lifespan_context=bob_app),
        )
        assert alice_app.profile_manager.profile.id != bob_app.profile_manager.profile.id

        encoded = encode_signed(content="hi bob, it's alice", ctx=alice_ctx)["encoded"]
        result = decode_signed(encoded=encoded, ctx=bob_ctx)
        assert result["valid"] is True
        assert result["signer_did"] == alice_app.profile_manager.profile.id
        assert result["content"] == "hi bob, it's alice"
