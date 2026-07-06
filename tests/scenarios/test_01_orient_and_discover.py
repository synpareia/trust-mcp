"""Scenario 01: Orient and discover capabilities from a cold start.

See scenarios/trust-toolkit/01-orient-and-discover.md for the aim,
steps, and success criteria.
"""

from __future__ import annotations

from synpareia_trust_mcp.tools.orient import AREAS_OF_CONCERN, learn, orient


class TestOrientAndDiscover:
    def test_orient_returns_all_capability_areas(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx)

        assert "areas_of_concern" in result
        returned_areas = {a["area"] for a in result["areas_of_concern"]}
        expected_areas = {a["area"] for a in AREAS_OF_CONCERN}
        assert returned_areas == expected_areas
        assert len(returned_areas) >= 9

    def test_orient_contains_identity_and_services(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx)

        assert "identity" in result
        assert result["identity"]["did"].startswith("did:synpareia:")
        assert result["identity"]["has_private_key"] is True
        assert "services" in result
        for service in ("witness", "network", "moltbook", "moltrust"):
            assert service in result["services"]
            assert "configured" in result["services"][service]

    def test_orient_with_no_providers_names_offline_capabilities(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx)

        offline = result["capabilities"]["offline"]
        assert any("signing" in c.lower() for c in offline)
        assert any("recording" in c.lower() for c in offline)
        # With zero providers, the network capabilities list should
        # not be empty — it should guide the user toward configuration.
        network = result["capabilities"]["network"]
        assert len(network) >= 1
        assert any("SYNPAREIA" in c for c in network)

    def test_every_area_accepted_by_learn(self, app_ctx) -> None:
        ctx, _ = app_ctx
        orient_out = orient(ctx)

        for area_entry in orient_out["areas_of_concern"]:
            area_name = area_entry["area"]
            guide_response = learn(area=area_name)
            assert "error" not in guide_response, (
                f"learn('{area_name}') returned an error; orient promises this area exists."
            )
            assert "guide" in guide_response

    def test_learn_rejects_unknown_area_with_help(self, app_ctx) -> None:
        result = learn(area="nonexistent-area")
        assert "error" in result
        assert "available_areas" in result
        assert len(result["available_areas"]) >= 9
        assert "orient" in result["hint"]

    def test_learn_guides_include_tool_names_and_examples(self, app_ctx) -> None:
        """An agent reading a guide should see concrete tools to call."""
        ctx, _ = app_ctx
        orient_out = orient(ctx)

        for area_entry in orient_out["areas_of_concern"]:
            guide = learn(area=area_entry["area"])["guide"]
            # The guide should be structured enough that an agent can act
            # on it — at minimum it should be a non-empty string or dict
            # and mention at least one tool name or configuration hint.
            assert guide, f"Empty guide for area '{area_entry['area']}'"

    def test_orient_surfaces_first_run_disclosure_on_fresh_identity(self, app_ctx) -> None:
        """A freshly-minted identity carries the GDPR §6 first-run notice
        ('nothing sent to the network'); a loaded one does not."""
        ctx, app = app_ctx
        # app_ctx generates a fresh profile, so newly_generated is True.
        assert app.profile_manager.newly_generated is True
        result = orient(ctx)
        first_run = result["identity"].get("first_run")
        assert first_run is not None
        assert first_run["new_identity"] is True
        # Durable-true: states the standing local-until-you-act property + the
        # opt-in nature of publishing/witnessing (must not go stale if the
        # agent publishes later in the same session).
        notice = first_run["notice"].lower()
        assert "locally" in notice
        assert "publish_profile" in notice
        assert "opt-in" in notice

        # Simulate a subsequent session (identity loaded, not minted).
        app.profile_manager.newly_generated = False
        assert "first_run" not in orient(ctx)["identity"]

    def test_orient_includes_next_steps(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx)
        assert "next_steps" in result
        assert isinstance(result["next_steps"], list)

    def test_orient_leads_with_start_here_situation_map(self, app_ctx) -> None:
        """Orient is called in the moment — the situation routing must come
        before the inventory (0.6.3 positioning; strategy review 2026-07-03)."""
        ctx, _ = app_ctx
        result = orient(ctx)
        assert "start_here" in result
        # First key in the return dict — the moment before the inventory.
        assert next(iter(result)) == "start_here"
        start_here = result["start_here"]
        assert isinstance(start_here, dict) and len(start_here) >= 5
        joined = " ".join(start_here.values()).lower()
        # Each of the three positioning verbs is reachable from the map.
        for tool in (
            "verify_claim",
            "evaluate_agent",
            "recording_start",
            "make_claim",
            "prove_independence",
            "publish_profile",
        ):
            assert tool in joined, f"start_here map doesn't route to {tool}"

    def test_under_the_hood_guide_names_only_real_sdk_symbols(self) -> None:
        """The learn('under-the-hood') tool->primitive map cites SDK symbols by
        name. If any drifts, an SDK-graduating agent gets routed to a
        nonexistent import. Pin every named symbol to a live import (the
        forms-coverage 'body claims vs SDK shapes' check, applied here).
        Review catch, PR #307 coverage perspective."""
        import importlib

        guide = learn(area="under-the-hood")["guide"]
        synpareia = importlib.import_module("synpareia")
        # Top-level symbols the guide names explicitly.
        for sym in (
            "sign",
            "verify",
            "from_public_key",
            "create_commitment",
            "verify_commitment",
            "Block",
            "Chain",
            "export_chain",
            "verify_export",
        ):
            assert sym in guide, f"guide no longer names {sym} — update this pin"
            assert hasattr(synpareia, sym), f"guide names synpareia.{sym} but it does not exist"
        # Submodule paths the guide names.
        assert hasattr(importlib.import_module("synpareia.hash"), "jcs_canonicalize")
        assert hasattr(importlib.import_module("synpareia.witness.client"), "WitnessClient")
        assert hasattr(importlib.import_module("synpareia.seal.verify"), "verify_seal")
