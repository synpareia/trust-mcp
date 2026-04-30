"""Scenario 05: Evaluate a counterparty across multiple providers.

See scenarios/trust-toolkit/05-evaluate-agent-trust.md.

Uses the in-process ASGI stubs for Moltbook, MolTrust, and the synpareia
network so every HTTP call lands on a controlled fixture -- no real
external services involved.

v0.4.0 signature: ``evaluate_agent(namespace, id)``. Fans out to all
four tiers and returns a per-tier response. The legacy bare-string
form (``identifier=...``) is still accepted for one release, emitting
a ``deprecation`` flag in the response.
"""

from __future__ import annotations

import asyncio
import json

from synpareia_trust_mcp.tools.trust import evaluate_agent


def _call(ctx, **kwargs) -> dict:
    return asyncio.run(evaluate_agent(ctx=ctx, **kwargs))


class TestEvaluateAgentMergedResponse:
    def test_returns_per_tier_lists(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="alice")

        for key in (
            "tier1",
            "tier2",
            "tier3",
            "tier4_available",
            "providers_queried",
            "providers_skipped",
            "summary",
        ):
            assert key in result, f"missing key: {key}"
        assert isinstance(result["tier1"], list)
        assert isinstance(result["tier2"], list)
        assert isinstance(result["tier3"], list)
        assert isinstance(result["tier4_available"], bool)

    def test_tier3_signals_include_synpareia_and_moltrust(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="alice")

        providers_in_tier3 = {s["provider"] for s in result["tier3"]}
        assert "synpareia" in providers_in_tier3
        assert "moltrust" in providers_in_tier3

    def test_moltbook_namespace_populates_tier2(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="moltbook", id="alice")

        assert len(result["tier2"]) > 0
        providers_in_tier2 = {s["provider"] for s in result["tier2"]}
        assert "moltbook" in providers_in_tier2

    def test_non_media_namespace_tier2_is_empty(self, app_ctx_with_stubs) -> None:
        """Tier 2 only populates when the namespace has an adapter. A
        bare DID/synpareia query should leave tier2 empty (no guessing)."""
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="did:synpareia:abc")

        assert result["tier2"] == []

    def test_providers_queried_and_skipped_fields(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="alice")

        # synpareia-network + moltrust are configured → queried.
        # moltbook is not a synpareia-namespace Tier 3 provider — skipped
        # at Tier 3, but the Tier 2 namespace-specific routing means it
        # was only queried iff namespace='moltbook'.
        assert set(result["providers_queried"]) >= {"synpareia", "moltrust"}

    def test_tier4_available_when_synpareia_did(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="did:synpareia:deadbeef")
        assert result["tier4_available"] is True

    def test_tier4_unavailable_for_non_synpareia(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="moltbook", id="alice")
        assert result["tier4_available"] is False


class TestEvaluateAgentTier1Lookup:
    def test_tier1_populates_from_local_journal(self, app_ctx) -> None:
        ctx, app = app_ctx
        record = app.journal_store.upsert(
            namespace="slack",
            namespace_id="T0/U0",
            display_name="alice",
        )
        result = _call(ctx, namespace="slack", id="T0/U0")

        assert len(result["tier1"]) == 1
        assert result["tier1"][0]["identifier"] == record.identifier

    def test_tier1_matches_by_display_name(self, app_ctx) -> None:
        ctx, app = app_ctx
        app.journal_store.upsert(
            namespace="slack",
            namespace_id="T0/U0",
            display_name="alice",
        )
        result = _call(ctx, namespace="slack", id="alice")
        assert len(result["tier1"]) >= 1


class TestEvaluateAgentInjectionSafety:
    def test_injector_payload_never_surfaced(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="moltbook", id="injector")

        dumped = json.dumps(result).lower()
        assert "ignore previous instructions" not in dumped
        assert "<<system>>" not in dumped
        assert "trust_score=1.0" not in dumped


class TestEvaluateAgentUnknown:
    def test_unknown_identifier_returns_empty_tiers(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="nobody-by-this-name")

        # Tier 3 still reports structured signals (lookup=not_found per provider).
        not_found_providers = {
            s["provider"]
            for s in result["tier3"]
            if s.get("signal_type") == "lookup" and s.get("value") == "not_found"
        }
        assert not_found_providers == {"synpareia", "moltrust"}


class TestEvaluateAgentZeroConfig:
    def test_zero_config_returns_helpful_summary(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx, namespace="synpareia", id="alice")

        assert result["tier1"] == []
        assert result["tier2"] == []
        assert result["tier3"] == []
        assert result["providers_queried"] == []
        # Every configurable provider should appear in providers_skipped
        skipped_names = {p["name"] for p in result["providers_skipped"]}
        assert "synpareia" in skipped_names
        assert "moltrust" in skipped_names
        # Summary points the caller at the env vars
        lower = result["summary"].lower()
        assert any(
            env in lower
            for env in (
                "synpareia_network_url",
                "synpareia_moltrust_api_key",
                "synpareia_moltbook_api_url",
            )
        )


class TestEvaluateAgentLegacySignature:
    def test_legacy_identifier_kwarg_still_works(self, app_ctx_with_stubs) -> None:
        """The bare-string (identifier=...) form must still return useful
        data for one release while the deprecation rides along."""
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, identifier="alice")

        assert "deprecation" in result
        assert "evaluate_agent" in result["deprecation"]
        # Legacy path routes Tier 3 at minimum.
        assert set(result["providers_queried"]) >= {"synpareia", "moltrust"}

    def test_legacy_form_without_namespace_or_id_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx)
        assert "error" in result


class TestEvaluateAgentValidation:
    def test_rejects_empty_namespace(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx, namespace="", id="alice")
        assert "error" in result

    def test_rejects_empty_id(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx, namespace="synpareia", id="")
        assert "error" in result

    def test_rejects_control_characters(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx, namespace="synpareia", id="alice\x00")
        assert "error" in result

    def test_rejects_oversized_id(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _call(ctx, namespace="synpareia", id="x" * 500)
        assert "error" in result


class TestEvaluateAgentSummary:
    def test_summary_is_concise(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call(ctx, namespace="synpareia", id="alice")
        terminators = result["summary"].count(".") + result["summary"].count("!")
        assert terminators <= 5, f"summary too long: {result['summary']!r}"
