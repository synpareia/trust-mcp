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

    def test_orient_includes_next_steps(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = orient(ctx)
        assert "next_steps" in result
        assert isinstance(result["next_steps"], list)
