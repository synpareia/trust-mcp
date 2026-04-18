"""Regression tests for resource-exhaustion exploits (ADV-014, ADV-015, ADV-016).

Locks in the input-size and response-size caps that prevent a single
caller (or hostile provider) from exhausting memory or disk.
"""

from __future__ import annotations

import asyncio

import httpx
from starlette.applications import Starlette
from starlette.responses import Response
from starlette.routing import Route

from synpareia_trust_mcp import providers
from synpareia_trust_mcp.tools.recording import (
    add_to_recording,
    end_recording,
    record_interaction,
)


class TestInputSizeLimits:
    """ADV-014 — description/counterparty_did/notes/content are capped."""

    def test_oversize_description_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = record_interaction(description="x" * 10_000, ctx=ctx)
        assert result.get("error"), "oversize description was accepted"
        assert "description" in result["error"].lower()

    def test_oversize_counterparty_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = record_interaction(
            description="fine",
            counterparty_did="did:x:" + "a" * 1_000,
            ctx=ctx,
        )
        assert result.get("error"), "oversize counterparty_did was accepted"

    def test_oversize_content_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="fine", ctx=ctx)
        rid = start["recording_id"]

        # 128 KB content — above the 64 KB cap
        result = add_to_recording(recording_id=rid, content="x" * 131_072, ctx=ctx)
        assert result.get("error"), "oversize content was accepted"

    def test_oversize_notes_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="fine", ctx=ctx)
        rid = start["recording_id"]

        result = end_recording(recording_id=rid, notes="x" * 10_000, ctx=ctx)
        assert result.get("error"), "oversize notes was accepted"

    def test_normal_sizes_still_work(self, app_ctx) -> None:
        """Caps must not break the normal path — a 500-char description
        and 1 KB content should still round-trip."""
        ctx, _ = app_ctx
        start = record_interaction(description="x" * 500, ctx=ctx)
        assert "error" not in start

        added = add_to_recording(
            recording_id=start["recording_id"],
            content="y" * 1024,
            ctx=ctx,
        )
        assert added.get("recorded") is True


class TestActiveRecordingCap:
    """ADV-015 — _active dict is capped; stale entries are evicted."""

    def test_active_cap_blocks_runaway_allocation(self, app_ctx) -> None:
        ctx, _ = app_ctx

        # Open 100 recordings — this is the cap
        opened = 0
        for i in range(100):
            r = record_interaction(description=f"run-{i}", ctx=ctx)
            if "error" in r:
                break
            opened += 1

        assert opened == 100, f"only opened {opened}/100 before error"

        # 101st call must be rejected
        overflow = record_interaction(description="overflow", ctx=ctx)
        assert overflow.get("error"), "exceeded 100 active recordings without error"
        assert "too many" in overflow["error"].lower()

    def test_stale_recordings_evicted_on_new_start(self, app_ctx) -> None:
        """Old active recordings (>24h) are dropped when a new start arrives,
        freeing up slots under the cap."""
        from datetime import UTC, datetime, timedelta

        ctx, app = app_ctx

        # Open one; then manually age its started_at
        r = record_interaction(description="ancient", ctx=ctx)
        rid = r["recording_id"]
        stale = app.conversation_manager._active[rid]
        stale.started_at = datetime.now(UTC) - timedelta(days=2)

        # Now fill to the cap; old one should be evicted first
        for i in range(100):
            result = record_interaction(description=f"fresh-{i}", ctx=ctx)
            assert "error" not in result, f"failed at fresh-{i}: {result}"

        # The stale recording is gone
        assert rid not in app.conversation_manager._active


class TestProviderResponseCap:
    """ADV-016 — provider HTTP responses above 1 MB are aborted."""

    def test_oversize_response_triggers_unavailable(self, monkeypatch) -> None:
        from synpareia_trust_mcp.providers import query_moltbook

        async def huge(request):
            # 2 MB body — 2x the cap
            return Response(content=b"{" + b'"x":1,' * 200_000 + b'"end":1}', status_code=200)

        app = Starlette(
            routes=[Route("/api/v1/agents/{identifier}", huge, methods=["GET"])],
        )

        def _make_client(timeout: float = 10.0) -> httpx.AsyncClient:
            return httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://moltbook.test",
                timeout=timeout,
            )

        monkeypatch.setattr(providers, "_make_http_client", _make_client)

        result = asyncio.run(query_moltbook("whatever", "http://moltbook.test"))
        # Oversize body collapses to the 'unavailable' signal, not a crash
        assert len(result) == 1
        assert result[0].signal_type == "error"
        assert result[0].value == "unavailable"
