"""Scenario 03: Prove an assessment was independent.

See scenarios/trust-toolkit/03-prove-independence.md.

The tool surface uses a nonce (random bytes held by the committer) rather
than a context string to bind the commitment; the scenario's "context"
from the markdown maps to the nonce in code.
"""

from __future__ import annotations

import base64

from synpareia_trust_mcp.tools.commitment import prove_independence
from synpareia_trust_mcp.tools.identity import verify_claim


class TestProveIndependence:
    def test_commitment_and_reveal_roundtrip(self, app_ctx) -> None:
        ctx, _ = app_ctx
        content = "My independent assessment: 7/10"

        # Step 1: seal the assessment before seeing others'
        sealed = prove_independence(content=content, ctx=ctx)
        assert "commitment_hash" in sealed
        assert "nonce_b64" in sealed

        # Step 2: reveal and verify
        verified = verify_claim(
            claim_type="commitment",
            ctx=ctx,
            commitment_hash=sealed["commitment_hash"],
            content=content,
            nonce_b64=sealed["nonce_b64"],
        )
        assert verified["valid"] is True

    def test_altered_content_at_reveal_fails(self, app_ctx) -> None:
        ctx, _ = app_ctx
        sealed = prove_independence(content="original assessment", ctx=ctx)

        verified = verify_claim(
            claim_type="commitment",
            ctx=ctx,
            commitment_hash=sealed["commitment_hash"],
            content="different assessment, trying to cheat",
            nonce_b64=sealed["nonce_b64"],
        )
        assert verified["valid"] is False

    def test_wrong_nonce_fails(self, app_ctx) -> None:
        ctx, _ = app_ctx
        sealed = prove_independence(content="assessment", ctx=ctx)
        bogus_nonce = base64.b64encode(b"\x00" * 32).decode()

        verified = verify_claim(
            claim_type="commitment",
            ctx=ctx,
            commitment_hash=sealed["commitment_hash"],
            content="assessment",
            nonce_b64=bogus_nonce,
        )
        assert verified["valid"] is False

    def test_different_contents_produce_different_hashes(self, app_ctx) -> None:
        ctx, _ = app_ctx
        s1 = prove_independence(content="assessment A", ctx=ctx)
        s2 = prove_independence(content="assessment B", ctx=ctx)
        assert s1["commitment_hash"] != s2["commitment_hash"]

    def test_same_content_different_nonce_produces_different_hash(self, app_ctx) -> None:
        """Fresh nonces prevent rainbow-table precomputation of common
        short assessments."""
        ctx, _ = app_ctx
        s1 = prove_independence(content="same content", ctx=ctx)
        s2 = prove_independence(content="same content", ctx=ctx)
        # Different nonces → different commitments → no enumeration attack
        # works across committers even if they commit identical content.
        assert s1["nonce_b64"] != s2["nonce_b64"]
        assert s1["commitment_hash"] != s2["commitment_hash"]

    def test_output_instructs_caller_on_what_to_share(self, app_ctx) -> None:
        ctx, _ = app_ctx
        sealed = prove_independence(content="x", ctx=ctx)
        assert "instructions" in sealed
        instructions = sealed["instructions"].lower()
        assert "commitment_hash" in instructions
        assert "nonce" in instructions
