"""Scenario 05: Evaluate a counterparty across multiple providers.

See scenarios/trust-toolkit/05-evaluate-agent-trust.md.

Uses the in-process ASGI stubs for Moltbook, MolTrust, and the synpareia
network so every HTTP call lands on a controlled fixture — no real
external services involved.
"""

from __future__ import annotations

import asyncio
import json

from synpareia_trust_mcp.tools.trust import evaluate_agent


def _call(identifier: str, ctx) -> dict:
    return asyncio.run(evaluate_agent(identifier=identifier, ctx=ctx))


class TestEvaluateAgentTrust:
    def test_three_providers_all_queried(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("alice", ctx)

        assert "providers_queried" in result
        assert set(result["providers_queried"]) == {
            "synpareia",
            "moltbook",
            "moltrust",
        }

    def test_signal_schema_is_uniform(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("alice", ctx)

        assert result["signals"], "expected at least one signal for alice"
        for signal in result["signals"]:
            for field in ("provider", "signal_type", "value", "confidence", "detail"):
                assert field in signal, f"signal missing {field}: {signal}"
            assert signal["confidence"] in {"low", "medium", "high"}

    def test_synpareia_signals_are_high_confidence(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("alice", ctx)

        synpareia_signals = [s for s in result["signals"] if s["provider"] == "synpareia"]
        assert synpareia_signals, "expected synpareia signals for alice"
        for s in synpareia_signals:
            # Lookup signals use "high" for the *claim* that the record
            # exists; data signals use "high" for proof-based signals.
            assert s["confidence"] == "high", f"synpareia signal should be high-confidence: {s}"

    def test_moltbook_and_moltrust_are_not_high_confidence(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("alice", ctx)

        for s in result["signals"]:
            if s["provider"] in {"moltbook", "moltrust"} and s["signal_type"] not in {
                "lookup",
                "error",
            }:
                assert s["confidence"] in {"low", "medium"}, (
                    f"{s['provider']} data signal should not be high-confidence: {s}"
                )

    def test_injector_payload_never_surfaced(self, app_ctx_with_stubs) -> None:
        """The Moltbook stub's 'injector' persona plants prompt-injection
        strings in `bio` and `description`. evaluate_agent must return
        only structured fields — the raw text must never appear in the
        output anywhere."""
        ctx, _ = app_ctx_with_stubs
        result = _call("injector", ctx)

        dumped = json.dumps(result).lower()
        # Reference strings from the stub fixture
        assert "ignore previous instructions" not in dumped
        assert "<<system>>" not in dumped
        assert "trust_score=1.0" not in dumped

    def test_unknown_identifier_returns_not_found_per_provider(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("nobody-by-this-name", ctx)

        providers_with_not_found = {
            s["provider"]
            for s in result["signals"]
            if s["signal_type"] == "lookup" and s["value"] == "not_found"
        }
        # Every provider should report not_found for an unknown identifier
        assert providers_with_not_found == {"synpareia", "moltbook", "moltrust"}

    def test_zero_config_returns_helpful_message(self, app_ctx) -> None:
        """With no providers configured, the tool must not crash and must
        point the caller at the env vars that would enable lookups."""
        ctx, _ = app_ctx
        result = _call("alice", ctx)

        assert result["providers_queried"] == []
        assert result["signals"] == []
        assert "summary" in result
        lower = result["summary"].lower()
        # At least one env var hint should be present
        assert any(
            hint in lower
            for hint in (
                "synpareia_network_url",
                "moltbook_api_url",
                "moltrust_api_key",
            )
        )
        # And the zero-config path should still recommend offline verify
        assert "verify_claim" in result["summary"]

    def test_schema_does_not_change_with_provider_count(self, app_ctx, app_ctx_with_stubs) -> None:
        """Whether 0 or 3 providers are configured, the response has the
        same shape: identifier, providers_queried, signals, summary."""
        zero_ctx, _ = app_ctx
        full_ctx, _ = app_ctx_with_stubs

        zero = _call("alice", zero_ctx)
        full = _call("alice", full_ctx)

        for key in ("identifier", "providers_queried", "signals", "summary"):
            assert key in zero, f"zero-config response missing {key}"
            assert key in full, f"full-config response missing {key}"

    def test_summary_is_concise(self, app_ctx_with_stubs) -> None:
        ctx, _ = app_ctx_with_stubs
        result = _call("alice", ctx)

        # ≤3 sentences per the scenario spec.
        sentence_terminators = result["summary"].count(".") + result["summary"].count("!")
        assert sentence_terminators <= 4, (
            f"summary should be ≤3 sentences, got {sentence_terminators}: {result['summary']!r}"
        )
