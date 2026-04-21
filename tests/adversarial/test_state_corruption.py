"""Regression tests for state-corruption exploits (ADV-019).

Locks in that event_type on add_to_recording is enum-restricted — the
toolkit's internal SYSTEM marker type cannot be forged by the caller."""

from __future__ import annotations

from synpareia_trust_mcp.tools.recording import (
    add_to_recording,
    record_interaction,
)


class TestReservedEventType:
    """ADV-019 — add_to_recording only accepts a small known set of
    event types. SYSTEM (used for conversation_started/conversation_ended
    markers) is reserved."""

    def test_system_event_type_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="real", ctx=ctx)
        rid = start["recording_id"]

        for forged in ("system", "SYSTEM", "conversation_ended", "conversation_started"):
            result = add_to_recording(
                recording_id=rid, content="forged", event_type=forged, ctx=ctx
            )
            assert result.get("error"), f"forged event_type {forged!r} was accepted without error"
            assert "event_type" in result["error"] or "invalid" in result["error"].lower()

    def test_random_event_type_rejected(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="real", ctx=ctx)
        rid = start["recording_id"]

        result = add_to_recording(
            recording_id=rid,
            content="payload",
            event_type="arbitrary_marker",
            ctx=ctx,
        )
        assert result.get("error")

    def test_allowed_event_types_accepted(self, app_ctx) -> None:
        ctx, _ = app_ctx
        start = record_interaction(description="real", ctx=ctx)
        rid = start["recording_id"]

        for allowed in ("message", "thought", "observation", "decision"):
            result = add_to_recording(
                recording_id=rid,
                content=f"hello-{allowed}",
                event_type=allowed,
                ctx=ctx,
            )
            assert result.get("recorded") is True, f"{allowed} rejected: {result}"
