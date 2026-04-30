"""Tests for Tier-3 attested_reputation tool."""

from __future__ import annotations

import asyncio

from synpareia_trust_mcp.tools.attested_reputation import attested_reputation


def _run(coro):
    return asyncio.run(coro)


class TestAttestedReputationWithProviders:
    def test_queries_both_providers_when_configured(self, app_ctx_with_stubs) -> None:
        ctx, app = app_ctx_with_stubs
        result = _run(attested_reputation(identifier="alice", ctx=ctx))
        assert result["identifier"] == "alice"
        assert result["reputation_tier"] == 3
        assert result["assurance_tier"] == 2
        assert "synpareia" in result["providers_queried"]
        assert "moltrust" in result["providers_queried"]
        providers_in_signals = {s["provider"] for s in result["signals"]}
        assert "synpareia" in providers_in_signals
        assert "moltrust" in providers_in_signals

    def test_labels_signals_with_provider_attribution(self, app_ctx_with_stubs) -> None:
        ctx, app = app_ctx_with_stubs
        result = _run(attested_reputation(identifier="alice", ctx=ctx))
        # Every signal must have a provider and signal_type
        for signal in result["signals"]:
            assert signal["provider"] in {"synpareia", "moltrust"}
            assert "signal_type" in signal
            assert "value" in signal
            assert "confidence" in signal

    def test_not_found_returns_lookup_signals(self, app_ctx_with_stubs) -> None:
        ctx, app = app_ctx_with_stubs
        result = _run(attested_reputation(identifier="does-not-exist-xyz", ctx=ctx))
        # Both providers return not_found for unknown identifiers
        lookup_signals = [s for s in result["signals"] if s["signal_type"] == "lookup"]
        assert len(lookup_signals) >= 1
        assert all(s["value"] == "not_found" for s in lookup_signals)


class TestAttestedReputationPartialConfig:
    def test_only_synpareia_network_configured(self, app_ctx_with_stubs, monkeypatch) -> None:
        """If only synpareia network is configured, queries it alone."""
        ctx, app = app_ctx_with_stubs
        # Clear moltrust config
        from dataclasses import replace

        app.config = replace(app.config, moltrust_api_key=None)
        result = _run(attested_reputation(identifier="alice", ctx=ctx))
        assert result["providers_queried"] == ["synpareia"]

    def test_only_moltrust_configured(self, app_ctx_with_stubs) -> None:
        """If only MolTrust is configured, queries it alone."""
        ctx, app = app_ctx_with_stubs
        from dataclasses import replace

        app.config = replace(app.config, network_url=None)
        result = _run(attested_reputation(identifier="alice", ctx=ctx))
        assert result["providers_queried"] == ["moltrust"]


class TestAttestedReputationUnconfigured:
    def test_no_providers_returns_not_configured(self, app_ctx) -> None:
        ctx, app = app_ctx  # no network_url, no moltrust_api_key
        result = _run(attested_reputation(identifier="alice", ctx=ctx))
        assert result["providers_queried"] == []
        assert result["signals"] == []
        assert "SYNPAREIA_NETWORK_URL" in result["hint"]
        assert "SYNPAREIA_MOLTRUST_API_KEY" in result["hint"]
        # Graceful degradation — never raise, never 'error'
        assert "error" not in result


class TestAttestedReputationValidation:
    def test_rejects_empty_identifier(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(attested_reputation(identifier="", ctx=ctx))
        assert "error" in result

    def test_rejects_oversized_identifier(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(attested_reputation(identifier="x" * 500, ctx=ctx))
        assert "error" in result

    def test_rejects_control_characters(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(attested_reputation(identifier="alice\x00sneaky", ctx=ctx))
        assert "error" in result
