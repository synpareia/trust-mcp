"""Scenario 08: Zero-config install produces a usable trust toolkit.

See scenarios/trust-toolkit/08-zero-config-works.md.

With no env vars set, the toolkit must:
- Auto-generate a profile with 0600 permissions
- Offer every offline tool working
- Degrade every online tool gracefully with a helpful message
- Never require the agent to defensively guard against None responses
"""

from __future__ import annotations

import asyncio
import base64
import stat
from pathlib import Path

import synpareia

from synpareia_trust_mcp.tools.commitment import prove_independence
from synpareia_trust_mcp.tools.identity import make_claim, verify_claim
from synpareia_trust_mcp.tools.orient import learn, orient
from synpareia_trust_mcp.tools.recording import (
    recording_append,
    recording_end,
    recording_list,
    recording_proof,
    recording_start,
)
from synpareia_trust_mcp.tools.trust import evaluate_agent
from synpareia_trust_mcp.tools.witness import (
    witness_info,
    witness_seal_state,
    witness_seal_timestamp,
)


def _run(coro):
    return asyncio.run(coro)


class TestProfileAutoGeneration:
    def test_profile_file_created_with_0600_perms(self, app_ctx) -> None:
        _, app = app_ctx
        # Fixture calls ensure_profile() already; just assert the file
        profile_path = Path(app.config.data_dir) / "profile.json"
        assert profile_path.is_file()

        perms = stat.S_IMODE(profile_path.stat().st_mode)
        assert perms == 0o600, f"profile.json must be mode 0600, got {oct(perms)}"

    def test_profile_persists_across_manager_restarts(self, tmp_path) -> None:
        """Two ProfileManagers pointed at the same data_dir see the same DID."""
        from synpareia_trust_mcp.profile import ProfileManager

        data_dir = tmp_path / "data"
        pm1 = ProfileManager(data_dir)
        pm1.ensure_profile()
        did1 = pm1.profile.id

        pm2 = ProfileManager(data_dir)
        pm2.ensure_profile()
        did2 = pm2.profile.id

        assert did1 == did2, "DID must persist across restarts"


class TestOrientWithZeroConfig:
    def test_orient_reports_offline_only(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx=ctx)

        # Every service should be reported as unconfigured
        for service in ("witness", "network", "moltbook", "moltrust"):
            assert result["services"][service]["configured"] is False

        # Offline capabilities always present
        assert result["capabilities"]["offline"]

        # Next steps should mention at least one env var to set
        hint = " ".join(result["next_steps"]).upper()
        assert "SYNPAREIA_WITNESS_URL" in hint or "SYNPAREIA_NETWORK_URL" in hint

    def test_orient_lists_all_areas(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx=ctx)
        areas = [a["area"] for a in result["areas_of_concern"]]
        assert len(areas) >= 10

    def test_learn_works_offline(self, app_ctx) -> None:
        """learn() is pure-local — doesn't depend on any service."""
        result = learn(area="verification")
        assert "guide" in result


class TestOfflineToolsWork:
    def test_claim_roundtrip(self, app_ctx) -> None:
        ctx, _ = app_ctx
        claim = make_claim(content="I exist", ctx=ctx)
        verified = verify_claim(
            claim_type="signature",
            ctx=ctx,
            content=claim["content"],
            signature_b64=claim["signature_b64"],
            public_key_b64=claim["public_key_b64"],
        )
        assert verified["valid"] is True

    def test_commitment_roundtrip(self, app_ctx) -> None:
        ctx, _ = app_ctx
        sealed = prove_independence(content="assessment", ctx=ctx)
        verified = verify_claim(
            claim_type="commitment",
            ctx=ctx,
            commitment_hash=sealed["commitment_hash"],
            content="assessment",
            nonce_b64=sealed["nonce_b64"],
        )
        assert verified["valid"] is True

    def test_recording_lifecycle(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = recording_start(description="offline", ctx=ctx)
        rid = start["recording_id"]
        recording_append(recording_id=rid, content="m1", ctx=ctx)
        listing = recording_list(ctx=ctx)
        assert listing["active_count"] >= 1

        recording_end(recording_id=rid, ctx=ctx)
        proof = recording_proof(recording_id=rid, ctx=ctx)
        assert "error" not in proof

    def test_offline_verify_seal_works_without_witness_url(self, app_ctx) -> None:
        """witness_verify_seal must work even without a witness URL — it
        only needs the SDK primitives."""
        from synpareia_trust_mcp.tools.witness import witness_verify_seal

        ctx, _ = app_ctx
        witness_profile = synpareia.generate()
        block = synpareia.create_block(witness_profile, "message", b"x")
        seal = synpareia.seal.create_seal(
            witness_private_key=witness_profile.private_key,
            witness_id=witness_profile.id,
            seal_type=synpareia.types.SealType.TIMESTAMP,
            target_block_hash=block.content_hash,
        )

        result = witness_verify_seal(
            seal_type=str(seal.seal_type),
            witness_id=seal.witness_id,
            witness_signature_b64=base64.b64encode(seal.witness_signature).decode(),
            sealed_at=seal.sealed_at.isoformat(),
            witness_public_key_b64=base64.b64encode(witness_profile.public_key).decode(),
            target_block_hash_hex=block.content_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is True


class TestOnlineToolsDegradeGracefully:
    def test_evaluate_agent_hints_at_env_vars(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _run(evaluate_agent(identifier="alice", ctx=ctx))
        # Never None, always a structured dict
        assert isinstance(result, dict)
        assert result["providers_queried"] == []
        # summary should name the env vars
        summary = result["summary"]
        assert any(
            hint in summary
            for hint in (
                "SYNPAREIA_NETWORK_URL",
                "SYNPAREIA_MOLTBOOK_API_URL",
                "SYNPAREIA_MOLTRUST_API_KEY",
            )
        )
        # and mention the offline fallback
        assert "verify_claim" in summary

    def test_witness_info_hints_at_env_var(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _run(witness_info(ctx=ctx))
        assert "error" in result
        assert "SYNPAREIA_WITNESS_URL" in result["error"]

    def test_witness_seal_timestamp_hints_at_env_var(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _run(witness_seal_timestamp(block_hash_hex="ab" * 32, ctx=ctx))
        assert "error" in result
        assert "SYNPAREIA_WITNESS_URL" in result["error"]

    def test_witness_seal_state_hints_at_env_var(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _run(witness_seal_state(chain_id="c", chain_head_hex="ab" * 32, ctx=ctx))
        assert "error" in result
        assert "SYNPAREIA_WITNESS_URL" in result["error"]


class TestNoNullReturns:
    """Every tool returns a dict. No caller should ever have to guard
    against `None`."""

    def test_no_tool_returns_none(self, app_ctx) -> None:
        ctx, _ = app_ctx

        # A sampling across tool families — if these pass the pattern is
        # safe for the rest.
        calls = [
            make_claim(content="x", ctx=ctx),
            verify_claim(claim_type="signature", ctx=ctx),
            prove_independence(content="x", ctx=ctx),
            recording_start(description="x", ctx=ctx),
            recording_list(ctx=ctx),
            orient(ctx=ctx),
            learn(area="verification"),
            _run(evaluate_agent(identifier="x", ctx=ctx)),
            _run(witness_info(ctx=ctx)),
        ]
        for r in calls:
            assert r is not None
            assert isinstance(r, dict)
