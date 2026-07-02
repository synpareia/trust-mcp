"""Round-trip contract tests — pipe each tool's response verbatim into its successor.

Motivated by LR-6: ``witness_seal_timestamp`` returned ``target_block_hash`` while
``witness_verify_seal``'s param is ``target_block_hash_hex``. FastMCP builds tool
argument models with pydantic ``extra="ignore"``, so piping the seal response verbatim
SILENTLY DROPPED the hash and verify returned a false ``{"valid": false}`` — the worst
error class for a trust tool. The existing witness tests missed it because they
hand-bridged the field (passed ``target_block_hash_hex`` from a separate variable)
instead of piping the actual response.

These tests simulate FastMCP's drop-unknown-keys behaviour via ``_pipe``: a consumer
tool only receives the keys it *declares*. If a producer's output field is named
differently from the successor's input param, the value is dropped and the round-trip
breaks. One test per output->successor pair on the trust paths.
"""

from __future__ import annotations

import asyncio
import hashlib
import inspect

import synpareia

from synpareia_trust_mcp.tools.recording import (
    recording_append,
    recording_end,
    recording_start,
)
from synpareia_trust_mcp.tools.witness import (
    witness_info,
    witness_seal_state,
    witness_seal_timestamp,
    witness_verify_seal,
)


def _run(coro):
    return asyncio.run(coro)


def _params(tool_fn) -> set[str]:
    """Input param names a tool declares — i.e. the keys FastMCP keeps, dropping the rest."""
    return {p for p in inspect.signature(tool_fn).parameters if p != "ctx"}


def _pipe(response: dict, consumer_fn) -> dict:
    """Simulate FastMCP ``extra="ignore"``: keep only keys the consumer declares."""
    return {k: v for k, v in response.items() if k in _params(consumer_fn)}


class TestWitnessSealRoundTrip:
    def test_timestamp_seal_verifies_when_response_piped_verbatim(self, app_ctx_with_witness):
        """LR-6 regression: a seal response piped straight into verify must verify true."""
        ctx, _ = app_ctx_with_witness
        block_hash_hex = hashlib.sha256(b"contract-timestamp").hexdigest()
        seal = _run(witness_seal_timestamp(block_hash_hex=block_hash_hex, ctx=ctx))
        assert "error" not in seal, seal
        info = _run(witness_info(ctx=ctx))
        # An agent pipes the seal response + witness_info verbatim into verify;
        # FastMCP keeps only the keys verify declares. Pre-0.6.2 the block hash
        # (named target_block_hash, not target_block_hash_hex) was dropped here.
        kwargs = {**_pipe(seal, witness_verify_seal), **_pipe(info, witness_verify_seal)}
        result = witness_verify_seal(ctx=ctx, **kwargs)
        assert result.get("valid") is True, result

    def test_state_seal_verifies_when_response_piped_verbatim(self, app_ctx_with_witness):
        ctx, _ = app_ctx_with_witness
        chain_head_hex = hashlib.sha256(b"contract-state").hexdigest()
        seal = _run(witness_seal_state(chain_id="chain-x", chain_head_hex=chain_head_hex, ctx=ctx))
        assert "error" not in seal, seal
        info = _run(witness_info(ctx=ctx))
        kwargs = {**_pipe(seal, witness_verify_seal), **_pipe(info, witness_verify_seal)}
        result = witness_verify_seal(ctx=ctx, **kwargs)
        assert result.get("valid") is True, result

    def test_verify_followup_params_are_complete_and_self_describing(self, app_ctx_with_witness):
        """A seal's verify_followup.params must verify on their own (incl. the witness key)."""
        ctx, _ = app_ctx_with_witness
        block_hash_hex = hashlib.sha256(b"contract-followup").hexdigest()
        seal = _run(witness_seal_timestamp(block_hash_hex=block_hash_hex, ctx=ctx))
        followup = seal["verify_followup"]
        assert followup["tool"] == "witness_verify_seal"
        params = followup["params"]
        # Self-describing: a third-party recipient needs no witness_info call.
        assert "witness_public_key_b64" in params
        # Every followup param is a real verify param — nothing is silently dropped.
        assert set(params) <= _params(witness_verify_seal)
        result = witness_verify_seal(ctx=ctx, **params)
        assert result.get("valid") is True, result

    def test_missing_target_reads_as_incomplete_not_invalid(self, app_ctx_with_witness):
        """A missing target must NOT surface as valid:false — that impugns honest evidence."""
        ctx, _ = app_ctx_with_witness
        block_hash_hex = hashlib.sha256(b"contract-missing").hexdigest()
        seal = _run(witness_seal_timestamp(block_hash_hex=block_hash_hex, ctx=ctx))
        info = _run(witness_info(ctx=ctx))
        # Deliberately omit the target hash entirely (agent forgot it).
        result = witness_verify_seal(
            ctx=ctx,
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
        )
        assert result.get("reason") == "incomplete_verification_input", result
        assert result.get("valid") is not False  # explicitly NOT a false "invalid"

    def test_state_seal_missing_target_reads_as_incomplete_not_invalid(self, app_ctx_with_witness):
        """State-seal mirror of the incomplete-input guard (parallel to the timestamp case)."""
        ctx, _ = app_ctx_with_witness
        chain_head_hex = hashlib.sha256(b"contract-state-missing").hexdigest()
        seal = _run(witness_seal_state(chain_id="chain-y", chain_head_hex=chain_head_hex, ctx=ctx))
        info = _run(witness_info(ctx=ctx))
        # Omit the chain target fields entirely — must read as incomplete, not invalid.
        result = witness_verify_seal(
            ctx=ctx,
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
        )
        assert result.get("reason") == "incomplete_verification_input", result
        assert result.get("valid") is not False

    def test_state_seal_verify_followup_round_trips(self, app_ctx_with_witness):
        """A state seal's verify_followup.params must verify on their own."""
        ctx, _ = app_ctx_with_witness
        chain_head_hex = hashlib.sha256(b"contract-state-followup").hexdigest()
        seal = _run(witness_seal_state(chain_id="chain-z", chain_head_hex=chain_head_hex, ctx=ctx))
        params = seal["verify_followup"]["params"]
        assert "witness_public_key_b64" in params
        assert set(params) <= _params(witness_verify_seal)
        result = witness_verify_seal(ctx=ctx, **params)
        assert result.get("valid") is True, result


class TestWitnessInfoContract:
    def test_witness_info_emits_verify_param_name(self, app_ctx_with_witness):
        ctx, _ = app_ctx_with_witness
        info = _run(witness_info(ctx=ctx))
        # witness_info -> witness_verify_seal: the key must be under verify's param name.
        assert "witness_public_key_b64" in info
        assert info["witness_public_key_b64"] == info["public_key_b64"]


class TestRecordingRoundTrip:
    def test_recording_start_echoes_input_param_name(self, app_ctx):
        ctx, _ = app_ctx
        did = synpareia.generate().id
        r = recording_start(description="round-trip", counterparty_did=did, ctx=ctx)
        # Output carries the same name as the input param (clarity + self re-reference).
        assert r.get("counterparty_did") == did

    def test_recording_end_pipes_into_state_seal(self, app_ctx):
        """recording_end -> witness_seal_state must pipe verbatim (chain_id + chain_head_hex)."""
        ctx, _ = app_ctx
        start = recording_start(description="seal-me", ctx=ctx)
        recording_append(recording_id=start["recording_id"], content="hello", ctx=ctx)
        end = recording_end(recording_id=start["recording_id"], ctx=ctx)
        piped = _pipe(end, witness_seal_state)
        # Both required state-seal inputs must survive the pipe.
        assert "chain_id" in piped, end
        assert "chain_head_hex" in piped, end
        assert piped["chain_head_hex"] == end["head_hash"]
