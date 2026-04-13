"""Conversation tools -- record, verify, and export agent interactions."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def start_conversation(
    description: str,
    ctx: Context[ServerSession, AppContext],
    counterparty_did: str | None = None,
) -> dict:
    """Begin recording an interaction as a verified synpareia Conversation.

    Creates a tamper-evident, hash-linked chain of events that both parties
    can contribute to. Use this for important interactions where you want a
    verifiable record of what was said, by whom, and when.

    Returns a conversation_id to use with add_to_conversation, end_conversation,
    and get_conversation_proof.
    """
    app = ctx.request_context.lifespan_context
    conv = app.conversation_manager.start(description, counterparty_did)

    return {
        "conversation_id": conv.conversation_id,
        "chain_id": conv.chain.id,
        "description": description,
        "counterparty": counterparty_did,
        "started_at": conv.started_at.isoformat(),
        "status": "recording",
    }


@mcp.tool()
def add_to_conversation(
    conversation_id: str,
    content: str,
    ctx: Context[ServerSession, AppContext],
    event_type: str = "message",
) -> dict:
    """Record a message or event in an active conversation.

    Each entry is signed with your private key, hashed, and linked to the
    previous entry — creating a tamper-evident chain.

    event_type can be: message, thought, observation, decision, or any custom type.
    """
    app = ctx.request_context.lifespan_context
    try:
        count = app.conversation_manager.add_message(
            conversation_id,
            content,
            block_type=event_type,
        )
    except ValueError as e:
        return {"error": str(e)}

    return {
        "conversation_id": conversation_id,
        "block_number": count,
        "event_type": event_type,
        "recorded": True,
    }


@mcp.tool()
def end_conversation(
    conversation_id: str,
    ctx: Context[ServerSession, AppContext],
    rating: int | None = None,
    notes: str | None = None,
) -> dict:
    """End a verified conversation and persist the record.

    Optionally provide a rating (1-5) and notes. The full conversation is
    exported as a verifiable chain and saved locally. If connected to the
    synpareia network, the conversation summary contributes to reputation.
    """
    app = ctx.request_context.lifespan_context
    try:
        result = app.conversation_manager.end(conversation_id, rating, notes)
    except ValueError as e:
        return {"error": str(e)}

    return result


@mcp.tool()
def get_conversation_proof(
    conversation_id: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Export an active conversation as portable, independently verifiable JSON.

    The proof contains all blocks, signatures, and hash links. Anyone with this
    JSON can verify the conversation's integrity using the synpareia SDK:

        import synpareia
        valid, errors = synpareia.verify_export(proof_json)
    """
    app = ctx.request_context.lifespan_context
    try:
        export = app.conversation_manager.export(conversation_id)
    except ValueError as e:
        return {"error": str(e)}

    return {
        "conversation_id": conversation_id,
        "proof": export,
        "verification_command": "synpareia.verify_export(proof)",
    }


@mcp.tool()
def list_conversations(ctx: Context[ServerSession, AppContext]) -> dict:
    """List all active conversations being recorded.

    Shows conversation IDs, descriptions, counterparties, and block counts
    for all currently active conversations. Use the conversation_id from
    the results with add_to_conversation, end_conversation, or
    get_conversation_proof.
    """
    app = ctx.request_context.lifespan_context
    active = app.conversation_manager.list_active()
    return {
        "active_count": len(active),
        "conversations": active,
    }
