"""Integration tests — verify the MCP server boots and exposes tools/resources."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch


class TestMCPServerSetup:
    """Verify the MCP server imports, registers tools, and boots correctly."""

    def test_server_imports_cleanly(self) -> None:
        """The server module should import without errors."""
        import synpareia_trust_mcp.server  # noqa: F401

    def test_mcp_instance_exists(self) -> None:
        from synpareia_trust_mcp.server import mcp

        assert mcp is not None
        assert mcp.name == "Synpareia Trust Toolkit"

    def test_tools_registered(self) -> None:
        """All expected tools should be registered on the MCP instance."""
        from synpareia_trust_mcp.server import mcp

        tool_manager = mcp._tool_manager
        tool_names = set(tool_manager._tools.keys())

        expected_tools = {
            # Information architecture (Tier 1 & 2)
            "orient",
            "learn",
            # Claims and verification
            "make_claim",
            "verify_claim",
            # Trust evaluation
            "evaluate_agent",
            # Independence proofs
            "prove_independence",
            # Recording
            "recording_start",
            "recording_append",
            "recording_end",
            "recording_proof",
            "recording_list",
            # Witness
            "witness_info",
            "witness_seal_timestamp",
            "witness_seal_state",
            "witness_verify_seal",
            "witness_submit_blind",
            "witness_get_blind",
            # Profile directory (Phase 1g)
            "publish_profile",
            "get_profile",
            "update_profile_policy",
            "enable_persistence",
            "disable_persistence",
            "delete_profile_history",
            "delete_profile",
        }
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    def test_resources_registered_as_templates(self) -> None:
        """MCP resources with context params are registered as templates."""
        from synpareia_trust_mcp.server import mcp

        resource_manager = mcp._resource_manager
        template_uris = set(resource_manager._templates.keys())

        assert "synpareia://identity" in template_uris
        assert "synpareia://recordings" in template_uris

    def test_instructions_carry_the_thesis_not_just_a_pointer(self) -> None:
        """Server instructions must state the value proposition, not delegate it.

        This string is the one piece of framing that reaches a fresh agent
        unconditionally: harnesses that restrict tool access typically do so with a
        call-time deny hook, which leaves server instructions untouched. So it has to
        survive on its own — a scout agent received `orient`'s output five times,
        including its "call learn(...)" pointers, and followed none of them.

        The assertions below pin *properties*, not phrasing. The previous version of
        this test pinned the literal words "Trust tools", which made rewriting the
        framing look like a regression.
        """
        from synpareia_trust_mcp.server import mcp

        assert mcp.instructions is not None
        text = mcp.instructions
        lower = text.lower()

        # Still routes onward.
        assert "orient" in lower

        # States the social vocabulary the product is actually about. An agent reading
        # only this should be able to answer "what is synpareia and when would I use
        # it" without reaching for cryptography.
        for social_term in ("commitment", "record", "form", "at stake"):
            assert social_term in lower, f"instructions no longer mention {social_term!r}"

        # Guards against collapsing back to a one-line pointer. The pre-2026-07-30
        # version was ~300 chars and delegated everything to `orient`.
        assert len(text) > 800, (
            f"instructions are {len(text)} chars — too short to carry the thesis"
        )

        # Mechanisms may appear, but must not lead. The failure mode being prevented is
        # the surface introducing itself as primitives rather than as a purpose.
        assert "at stake" in lower[:400], "the opening should frame stakes, not mechanism"

    def test_tool_count(self) -> None:
        """Track the tool count to catch accidental additions/removals."""
        from synpareia_trust_mcp.server import mcp

        tool_count = len(mcp._tool_manager._tools)
        # 2 (orient/learn) + 2 (make_claim/verify_claim) + 1 (evaluate_agent)
        # + 1 (prove_independence) + 5 (recording) + 6 (witness)
        # + 5 (remember/recall/add_evaluation/find_evaluations/forget_counterparty)
        # + 1 (check_media_signals) + 1 (attested_reputation)
        # + 2 (encode_signed/decode_signed) = 26
        # + 7 (Phase 1g directory: publish_profile, get_profile,
        #     update_profile_policy, enable_persistence, disable_persistence,
        #     delete_profile_history, delete_profile) = 33
        # + 2 (A0/A1: set_reputation_consent, record_interaction) = 35
        # + 1 (A2: network_reputation) = 36
        #
        # NOTE this moves AGAINST the standing consolidation goal (33 -> ~28),
        # deliberately.
        # These two are the write path: `set_reputation_consent` makes an agent
        # recordable, `record_interaction` records. Consent can also be given by
        # co-signing each individual event, but that needs a live counterparty
        # transport we do not have yet — so TODAY the standing grant is the only
        # practical route, and without it a counterparty's write is refused.
        # Folding it into `update_profile_policy` was considered and rejected:
        # consent is not a policy tweak, and burying it in a general-purpose
        # updater is how an agent ends up never finding the one call that makes
        # them participate. Consolidation should happen around this tool, not
        # absorb it.
        #
        # `network_reputation` is the read half. Until it existed the write path
        # led nowhere an agent could look: events went in and no tool asked what
        # the network made of them. It is a separate tool from
        # `attested_reputation` (which fans out across external providers) on
        # purpose — this one is anchored on the caller's own position and serves
        # a collapsed pair, and merging the two would mean flattening that
        # distinction into an undifferentiated "reputation" surface.
        assert tool_count == 36, f"Expected 36 tools, got {tool_count}"


class TestMCPLifespan:
    """Test the lifespan context initialization."""

    def test_lifespan_creates_profile(self, tmp_path: str) -> None:
        """The lifespan should generate a profile in the data dir."""
        from synpareia_trust_mcp.app import AppContext, app_lifespan, mcp

        async def _run() -> None:
            env = {
                "SYNPAREIA_DATA_DIR": str(tmp_path),
                "SYNPAREIA_AUTO_REGISTER": "false",
            }
            with patch.dict(os.environ, env, clear=False):
                async with app_lifespan(mcp) as ctx:
                    assert isinstance(ctx, AppContext)
                    assert ctx.profile_manager.profile is not None
                    assert ctx.profile_manager.profile.id.startswith("did:synpareia:")

        asyncio.run(_run())


class TestEntryPoint:
    """Verify the package entry point is wired correctly."""

    def test_console_script_target_exists(self) -> None:
        """The main() function should exist and be callable."""
        from synpareia_trust_mcp.server import main

        assert callable(main)

    def test_package_metadata(self) -> None:
        """Package metadata should be accessible."""
        import synpareia_trust_mcp

        assert synpareia_trust_mcp.__version__ == "0.9.0"
