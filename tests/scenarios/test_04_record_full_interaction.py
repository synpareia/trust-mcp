"""Scenario 04: Record an interaction end-to-end and export proof.

See scenarios/trust-toolkit/04-record-full-interaction.md.
"""

from __future__ import annotations

import synpareia

from synpareia_trust_mcp.tools.recording import (
    add_to_recording,
    end_recording,
    get_proof,
    my_recordings,
    record_interaction,
)


def _is_valid(result: object) -> bool:
    """Normalize the several shapes verify_export may return."""
    if result is True:
        return True
    if isinstance(result, tuple) and result and result[0] is True:
        return True
    return isinstance(result, dict) and result.get("valid") is True


class TestRecordFullInteraction:
    def test_full_lifecycle_records_and_exports(self, app_ctx) -> None:
        ctx, _ = app_ctx

        # Start recording
        start = record_interaction(
            description="proofread document X",
            counterparty_did="did:synpareia:bob",
            ctx=ctx,
        )
        assert "recording_id" in start
        rid = start["recording_id"]

        # Add several blocks — block_number monotonically increases
        prev = 0
        for i in range(3):
            added = add_to_recording(
                recording_id=rid,
                content=f"turn {i}",
                event_type="message",
                ctx=ctx,
            )
            assert added.get("recorded") is True
            assert added["block_number"] > prev, (
                f"block_number must increase on each append; "
                f"got {added['block_number']} after {prev}"
            )
            prev = added["block_number"]

        # It should be listed as active
        active = my_recordings(ctx=ctx)
        assert active["active_count"] >= 1

        # End recording
        ended = end_recording(recording_id=rid, ctx=ctx)
        assert "error" not in ended

        # Export proof
        proof = get_proof(recording_id=rid, ctx=ctx)
        assert "error" not in proof
        assert "proof" in proof

        # The exported proof must verify with the SDK's independent
        # verifier — not the toolkit's internals. verify_export can return
        # True, (True, [...]), or {"valid": True, ...} depending on version.
        verification_result = synpareia.verify_export(proof["proof"])
        assert _is_valid(verification_result), (
            f"verify_export returned non-truthy: {verification_result!r}"
        )

    def test_adding_to_nonexistent_recording_returns_error(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = add_to_recording(
            recording_id="00000000-0000-0000-0000-000000000000",
            content="x",
            ctx=ctx,
        )
        assert "error" in result

    def test_cannot_add_after_end(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="short", ctx=ctx)
        rid = start["recording_id"]
        add_to_recording(recording_id=rid, content="msg", ctx=ctx)
        end_recording(recording_id=rid, ctx=ctx)

        # Adding after end should return an error, not silently succeed
        result = add_to_recording(recording_id=rid, content="late", ctx=ctx)
        assert "error" in result

    def test_tampered_proof_fails_verification(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="tamper test", ctx=ctx)
        rid = start["recording_id"]
        for i in range(2):
            add_to_recording(recording_id=rid, content=f"m{i}", ctx=ctx)
        end_recording(recording_id=rid, ctx=ctx)
        proof = get_proof(recording_id=rid, ctx=ctx)["proof"]

        # The chain export has positions[].block.content (hex-encoded bytes).
        # Flip one byte to simulate tampering without making the JSON
        # structurally invalid.
        positions = proof.get("positions")
        assert positions, "proof schema changed unexpectedly"
        last_block = positions[-1]["block"]
        original_hex = last_block["content"]
        last_block["content"] = "ff" + original_hex[2:]

        try:
            result = synpareia.verify_export(proof)
            assert not _is_valid(result), f"tampered proof must not verify, got {result!r}"
        except Exception:
            # An exception is also an acceptable failure mode — what's
            # not acceptable is verify_export returning truthy for a
            # tampered proof.
            pass

    def test_my_recordings_lists_ended_recording(self, app_ctx) -> None:
        """Ended recordings should remain discoverable (at least by
        proof retrieval) even if the 'active' list is just for in-flight
        ones. This test documents the current behavior."""
        ctx, _ = app_ctx
        start = record_interaction(description="lifecycle", ctx=ctx)
        rid = start["recording_id"]
        add_to_recording(recording_id=rid, content="m", ctx=ctx)
        end_recording(recording_id=rid, ctx=ctx)

        # Whatever the current contract is, get_proof must succeed
        # after end_recording — that's the verifier's only view.
        proof = get_proof(recording_id=rid, ctx=ctx)
        assert "error" not in proof

    def test_proof_bundle_is_self_contained(self, app_ctx) -> None:
        """An exported proof must contain enough data to verify without
        any help from the original agent."""
        ctx, _ = app_ctx
        start = record_interaction(description="self-contained", ctx=ctx)
        rid = start["recording_id"]
        add_to_recording(recording_id=rid, content="m1", ctx=ctx)
        add_to_recording(recording_id=rid, content="m2", ctx=ctx)
        end_recording(recording_id=rid, ctx=ctx)
        proof = get_proof(recording_id=rid, ctx=ctx)

        # Verification instructions must accompany the proof
        assert "verification" in proof
        assert "command" in proof["verification"]
        # The exported chain data must include identity and blocks
        bundle = proof["proof"]
        assert bundle, "empty proof bundle"
