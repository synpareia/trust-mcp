"""Recording tools — create tamper-evident records of interactions."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def record_interaction(
    description: str,
    ctx: Context,
    counterparty_did: str | None = None,
) -> dict[str, Any]:
    """Start recording an interaction as a tamper-evident hash-linked chain.

    Returns a recording_id for subsequent calls.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        conv = app.conversation_manager.start(description, counterparty_did)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "recording_id": conv.conversation_id,
        "chain_id": conv.chain.id,
        "description": description,
        "counterparty": counterparty_did,
        "started_at": conv.started_at.isoformat(),
        "status": "recording",
    }


@mcp.tool()
def add_to_recording(
    recording_id: str,
    content: str,
    ctx: Context,
    event_type: str = "message",
) -> dict[str, Any]:
    """Append a signed, hash-linked block to an active recording.

    Types: message, thought, observation, decision. Other values are
    rejected — the SYSTEM type is reserved for toolkit markers.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        count = app.conversation_manager.add_message(
            recording_id,
            content,
            block_type=event_type,
        )
    except ValueError as e:
        return {"error": str(e)}

    return {
        "recording_id": recording_id,
        "block_number": count,
        "event_type": event_type,
        "recorded": True,
    }


@mcp.tool()
def end_recording(
    recording_id: str,
    ctx: Context,
    rating: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Finalize a recording and persist as a verifiable chain. Optional rating (1-5) and notes."""
    app: AppContext = ctx.request_context.lifespan_context
    try:
        result = app.conversation_manager.end(recording_id, rating, notes)
    except ValueError as e:
        return {"error": str(e)}

    return result


@mcp.tool()
def get_proof(
    recording_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Export a recording as independently verifiable JSON.

    Anyone can verify with: synpareia.verify_export(proof)
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        export = app.conversation_manager.export(recording_id)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "recording_id": recording_id,
        "proof": export,
        "verification": {
            "command": "synpareia.verify_export(proof)",
            "manual": (
                "pip install synpareia && python -c "
                '"import synpareia, json; '
                "synpareia.verify_export(json.load(open('proof.json')))\""
            ),
        },
    }


@mcp.tool()
def my_recordings(ctx: Context) -> dict[str, Any]:
    """List active recordings being tracked."""
    app: AppContext = ctx.request_context.lifespan_context
    active = app.conversation_manager.list_active()
    return {
        "active_count": len(active),
        "recordings": active,
    }
