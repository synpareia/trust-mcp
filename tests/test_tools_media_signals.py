"""Tests for Tier-2 check_media_signals tool."""

from __future__ import annotations

import asyncio

from synpareia_trust_mcp.tools.media_signals import check_media_signals


def _run(coro):
    return asyncio.run(coro)


class TestCheckMediaSignalsMoltbook:
    def test_queries_moltbook_for_moltbook_namespace(self, app_ctx_with_stubs) -> None:
        ctx, app = app_ctx_with_stubs
        result = _run(check_media_signals(namespace="moltbook", handle="alice", ctx=ctx))
        assert result["namespace"] == "moltbook"
        assert result["handle"] == "alice"
        assert result["reputation_tier"] == 2
        assert result["provider_status"] == "queried"
        signal_types = {s["signal_type"] for s in result["signals"]}
        assert "karma" in signal_types
        assert "activity" in signal_types

    def test_moltbook_not_found_returns_lookup_signal(self, app_ctx_with_stubs) -> None:
        ctx, app = app_ctx_with_stubs
        result = _run(
            check_media_signals(namespace="moltbook", handle="does-not-exist-123", ctx=ctx)
        )
        assert result["provider_status"] == "queried"
        signal_types = {s["signal_type"] for s in result["signals"]}
        assert "lookup" in signal_types


class TestCheckMediaSignalsUnconfigured:
    def test_moltbook_without_config_returns_not_configured(self, app_ctx) -> None:
        ctx, app = app_ctx  # no moltbook_api_url set
        result = _run(check_media_signals(namespace="moltbook", handle="alice", ctx=ctx))
        assert result["provider_status"] == "not_configured"
        assert result["signals"] == []
        assert "SYNPAREIA_MOLTBOOK_API_URL" in result["hint"]


class TestCheckMediaSignalsUnsupported:
    def test_unknown_namespace_returns_no_adapter(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(check_media_signals(namespace="linkedin", handle="alice", ctx=ctx))
        assert result["provider_status"] == "no_adapter"
        assert result["signals"] == []
        assert "linkedin" in result["hint"]

    def test_known_but_unimplemented_namespace(self, app_ctx) -> None:
        """GitHub is conceptually Tier 2 but v1 ships with only Moltbook.

        The tool should explicitly acknowledge the namespace and point the
        agent at the workaround (use recall_counterparty + add_evaluation
        to record what they know manually).
        """
        ctx, app = app_ctx
        result = _run(check_media_signals(namespace="github", handle="alice", ctx=ctx))
        assert result["provider_status"] == "no_adapter"


class TestCheckMediaSignalsValidation:
    def test_rejects_empty_namespace(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(check_media_signals(namespace="", handle="alice", ctx=ctx))
        assert "error" in result

    def test_rejects_empty_handle(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = _run(check_media_signals(namespace="moltbook", handle="", ctx=ctx))
        assert "error" in result
