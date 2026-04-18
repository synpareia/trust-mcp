"""Scenario 02: Make a claim, have someone else verify it.

See scenarios/trust-toolkit/02-make-and-verify-claim.md.
"""

from __future__ import annotations

import base64

from synpareia_trust_mcp.tools.identity import make_claim, verify_claim


class TestMakeAndVerifyClaim:
    def test_claim_contains_all_fields_verifier_needs(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = make_claim(content="I reviewed document X", ctx=ctx)

        for field in ("content", "signature_b64", "signer_did", "public_key_b64"):
            assert field in result, f"missing field {field}"
        assert result["signer_did"].startswith("did:synpareia:")
        # The verification_instructions block tells the caller how to
        # verify — it must reference verify_claim with the right params.
        assert result["verification_instructions"]["tool"] == "verify_claim"
        params = result["verification_instructions"]["params"]
        assert params["claim_type"] == "signature"

    def test_valid_roundtrip_different_verifier(self, app_ctx) -> None:
        """The hallmark test: Bob verifies Alice using only her outputs."""
        ctx, _ = app_ctx
        alice_claim = make_claim(content="Alice reviewed doc X", ctx=ctx)

        # Bob — a third party — has only the public outputs.
        result = verify_claim(
            claim_type="signature",
            ctx=ctx,
            content=alice_claim["content"],
            signature_b64=alice_claim["signature_b64"],
            public_key_b64=alice_claim["public_key_b64"],
        )
        assert result["valid"] is True
        assert result["signer_did"] == alice_claim["signer_did"]

    def test_tampered_content_fails(self, app_ctx) -> None:
        ctx, _ = app_ctx
        claim = make_claim(content="original content", ctx=ctx)

        result = verify_claim(
            claim_type="signature",
            ctx=ctx,
            content="altered content",
            signature_b64=claim["signature_b64"],
            public_key_b64=claim["public_key_b64"],
        )
        assert result["valid"] is False

    def test_wrong_key_fails(self, app_ctx) -> None:
        import synpareia

        ctx, _ = app_ctx
        claim = make_claim(content="content", ctx=ctx)

        bob = synpareia.generate()
        bob_pubkey_b64 = base64.b64encode(bob.public_key).decode()

        result = verify_claim(
            claim_type="signature",
            ctx=ctx,
            content=claim["content"],
            signature_b64=claim["signature_b64"],
            public_key_b64=bob_pubkey_b64,
        )
        assert result["valid"] is False

    def test_malformed_base64_returns_structured_error(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = verify_claim(
            claim_type="signature",
            ctx=ctx,
            content="hello",
            signature_b64="!!!not base64!!!",
            public_key_b64="!!!also not!!!",
        )
        assert result["valid"] is False
        assert "error" in result

    def test_missing_required_params_returns_error(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = verify_claim(claim_type="signature", ctx=ctx)
        assert result["valid"] is False
        assert "error" in result
        # Error should name which fields are missing
        err = result["error"].lower()
        assert "signature" in err or "content" in err

    def test_unknown_claim_type_returns_error_with_valid_options(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = verify_claim(claim_type="telepathy", ctx=ctx)
        assert result["valid"] is False
        assert "error" in result
        # Should mention valid options
        for valid_type in ("signature", "identity", "commitment"):
            assert valid_type in result["error"]
