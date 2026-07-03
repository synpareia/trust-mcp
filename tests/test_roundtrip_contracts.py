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
import base64
import hashlib
import inspect

import synpareia

from synpareia_trust_mcp.tools.identity import verify_claim
from synpareia_trust_mcp.tools.recall import remember_counterparty
from synpareia_trust_mcp.tools.recording import (
    recording_append,
    recording_end,
    recording_start,
)
from synpareia_trust_mcp.tools.trust import evaluate_agent
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


class TestTask40DeferredPipes:
    """The three mismatches the 0.6.2 32-tool audit flagged as 'needs design' and
    deferred to task #40. Each is now resolved and pinned here.
    """

    def test_identity_block_pipes_into_verify_claim_via_did_alias(self, app_ctx):
        """Producers (orient/whoami/publish/directory) emit the DID under `did`;
        verify_claim(identity) expected only `agent_did`. #3 adds `did` as an alias
        so an identity block pipes straight in."""
        ctx, _ = app_ctx
        prof = synpareia.generate()
        # Shape of orient's identity block (extra keys get dropped by the pipe).
        identity = {
            "did": prof.id,
            "public_key_b64": base64.b64encode(prof.public_key).decode(),
            "display_name": "dropped-by-pipe",
            "has_private_key": True,
        }
        piped = _pipe(identity, verify_claim)
        # The alias field must survive FastMCP's drop-unknown (it did not pre-fix).
        assert "did" in piped, piped
        assert "public_key_b64" in piped, piped
        result = verify_claim(claim_type="identity", ctx=ctx, **piped)
        assert result.get("valid") is True, result

    def test_remember_counterparty_record_pipes_into_evaluate_agent(self, app_ctx):
        """remember_counterparty emits `namespace` + `namespace_id`; evaluate_agent
        expected `namespace` + `id`. #2 adds `namespace_id` as an alias for `id` so a
        Tier-1 record pipes straight in without renaming."""
        ctx, _ = app_ctx
        did = synpareia.generate().id
        record = remember_counterparty(
            namespace="synpareia", namespace_id=did, display_name="Peer", ctx=ctx
        )
        assert "error" not in record, record
        piped = _pipe(record, evaluate_agent)
        assert "namespace" in piped and "namespace_id" in piped, record
        result = _run(evaluate_agent(ctx=ctx, **piped))
        # Routing must succeed: namespace_id bound to id, so NOT the missing-args error.
        assert "requires (namespace, id)" not in (result.get("error") or ""), result
        # And it evaluated the intended namespace (not an inferred/legacy fallback).
        assert result.get("error") is None, result

    def test_blind_party_commitment_verifies_via_verify_claim(self, app_ctx):
        """#1 was a field-name/instruction gap, NOT a scheme incompatibility: the
        `party_a_commitment` / `party_b_commitment` a blind conclusion echoes back is a
        verify_claim-compatible commitment_hash (it is literally the hash each party
        sealed locally and submitted). Pin that it verifies, so the instruction fix
        (point at verify_claim, not the phantom `reveal_commitment` tool) is grounded."""
        ctx, _ = app_ctx
        app = ctx.request_context.lifespan_context
        content = "my independent assessment"
        seal = app.conversation_manager.seal_commitment(content)
        # Simulate what witness_get_blind / witness_submit_blind echoes back.
        blind_result = {"party_a_commitment": seal["commitment_hash"]}
        result = verify_claim(
            claim_type="commitment",
            ctx=ctx,
            commitment_hash=blind_result["party_a_commitment"],
            content=content,
            nonce_b64=seal["nonce_b64"],
        )
        assert result.get("valid") is True, result
