"""Tests for signing and verification through the identity tools."""

from __future__ import annotations

import base64

import synpareia


class TestSignAndVerify:
    def test_sign_and_verify_roundtrip(self, alice: synpareia.Profile) -> None:
        content = b"I certify this proposal is sound"
        signature = synpareia.sign(alice.private_key, content)

        assert synpareia.verify(alice.public_key, content, signature)

    def test_wrong_key_rejects(self, alice: synpareia.Profile, bob: synpareia.Profile) -> None:
        content = b"Signed by Alice"
        signature = synpareia.sign(alice.private_key, content)

        # Bob's key should not verify Alice's signature
        assert not synpareia.verify(bob.public_key, content, signature)

    def test_tampered_content_rejects(self, alice: synpareia.Profile) -> None:
        content = b"Original content"
        signature = synpareia.sign(alice.private_key, content)

        assert not synpareia.verify(alice.public_key, b"Tampered content", signature)

    def test_did_derives_from_public_key(self, alice: synpareia.Profile) -> None:
        derived = synpareia.from_public_key(alice.public_key)
        assert derived.id == alice.id

    def test_wrong_key_wrong_did(self, alice: synpareia.Profile, bob: synpareia.Profile) -> None:
        derived = synpareia.from_public_key(bob.public_key)
        assert derived.id != alice.id

    def test_signature_is_deterministic(self, alice: synpareia.Profile) -> None:
        """Ed25519 signatures are deterministic for the same key+message."""
        content = b"Same message"
        sig1 = synpareia.sign(alice.private_key, content)
        sig2 = synpareia.sign(alice.private_key, content)
        assert sig1 == sig2


class TestBase64Encoding:
    """Test the base64 encode/decode patterns used by MCP tools."""

    def test_key_roundtrip(self, alice: synpareia.Profile) -> None:
        pk_b64 = base64.b64encode(alice.public_key).decode()
        pk_bytes = base64.b64decode(pk_b64)
        assert pk_bytes == alice.public_key

    def test_signature_roundtrip(self, alice: synpareia.Profile) -> None:
        sig = synpareia.sign(alice.private_key, b"test")
        sig_b64 = base64.b64encode(sig).decode()
        sig_bytes = base64.b64decode(sig_b64)
        assert sig_bytes == sig

    def test_full_mcp_flow(self, alice: synpareia.Profile) -> None:
        """Simulate the full sign_content -> verify_signature MCP flow."""
        content = "Hello from Agent A"
        content_bytes = content.encode()

        # sign_content tool output
        signature = synpareia.sign(alice.private_key, content_bytes)
        sig_b64 = base64.b64encode(signature).decode()
        pk_b64 = base64.b64encode(alice.public_key).decode()

        # verify_signature tool input (from the other agent)
        sig_back = base64.b64decode(sig_b64)
        pk_back = base64.b64decode(pk_b64)
        assert synpareia.verify(pk_back, content_bytes, sig_back)
