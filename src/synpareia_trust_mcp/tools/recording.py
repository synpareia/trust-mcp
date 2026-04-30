"""Recording tools — create tamper-evident records of interactions.

All tool names in this module share the `recording_` prefix because they
form a lifecycle: `recording_start` → `recording_append` (n times) →
`recording_end` → `recording_proof`. `recording_list` is a read-side peek
at what's currently in progress.
"""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def recording_start(
    description: str,
    ctx: Context,
    counterparty_did: str | None = None,
) -> dict[str, Any]:
    """Begin a tamper-evident recording of an interaction.

    Creates a hash-linked chain rooted at your identity. Subsequent
    `recording_append` calls each append a signed, hash-linked block to
    this chain, so any later modification to the sequence is detectable.

    Returns a `recording_id` that subsequent recording_* calls use to
    target this chain. The recording remains active until you call
    `recording_end` — at which point the chain is persisted and exportable
    as a cryptographic proof.

    Pass `counterparty_did` when you're recording a dialogue with another
    agent (optional but recommended — it's embedded in the chain).
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
def recording_append(
    recording_id: str,
    content: str,
    ctx: Context,
    event_type: str = "message",
) -> dict[str, Any]:
    """Append a signed, hash-linked block to an active recording.

    Each block is signed with your identity key and hash-linked to the
    previous block, so tampering with any earlier block breaks the chain.

    `event_type` must be one of: `message`, `thought`, `observation`,
    `decision`. Other values are rejected. (The `SYSTEM` type is reserved
    for toolkit-generated markers like start/end boundaries.)
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
def recording_end(
    recording_id: str,
    ctx: Context,
    rating: int | None = None,
    notes: str | None = None,
) -> dict[str, Any]:
    """Finalize a recording and persist the chain.

    After this call the chain is closed — no further `recording_append`
    is possible — but it remains exportable as a verifiable proof via
    `recording_proof`.

    Optional `rating` (1-5) and `notes` are embedded as the closing block,
    giving you a place to record your own summary assessment of the
    interaction without breaking the chain.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        result = app.conversation_manager.end(recording_id, rating, notes)
    except ValueError as e:
        return {"error": str(e)}

    return result


@mcp.tool()
def recording_proof(
    recording_id: str,
    ctx: Context,
) -> dict[str, Any]:
    """Export a recording as an independently verifiable proof bundle.

    Returns the full hash-linked chain as JSON. Anyone with the proof and
    the public keys of the signing parties can verify it offline with no
    further calls to you or this toolkit:

        pip install synpareia
        python -c "import synpareia, json; \\
            synpareia.verify_export(json.load(open('proof.json')))"

    Safe to share the proof bundle — it contains only what you recorded
    plus signatures. It does not contain your private key.
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
def recording_list(ctx: Context) -> dict[str, Any]:
    """List recordings that are currently in progress (not yet ended).

    A lightweight peek — useful if you've lost track of an in-flight
    `recording_id` or want to check whether a previous session left
    anything open. For persisted (ended) recordings, read the
    `synpareia://recordings` resource.
    """
    app: AppContext = ctx.request_context.lifespan_context
    active = app.conversation_manager.list_active()
    return {
        "active_count": len(active),
        "recordings": active,
    }
