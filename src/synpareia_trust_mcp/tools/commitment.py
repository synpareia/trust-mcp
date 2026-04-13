"""Commitment tools -- seal and reveal provably independent assessments."""

from __future__ import annotations

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def seal_commitment(content: str, ctx: Context[ServerSession, AppContext]) -> dict:
    """Seal your assessment or decision before seeing the other party's.

    Creates a cryptographic commitment: a hash that proves you committed to
    specific content at this point in time.

    IMPORTANT: The response includes both a commitment_hash and a nonce_b64.
    Share ONLY the commitment_hash with the other party. Keep the nonce_b64
    secret until you're ready to reveal.

    Call reveal_commitment later with the commitment_hash, your original content,
    and the nonce_b64 to prove your assessment was independent.
    """
    app = ctx.request_context.lifespan_context
    return app.conversation_manager.seal_commitment(content)


@mcp.tool()
def reveal_commitment(
    commitment_hash: str,
    original_content: str,
    nonce_b64: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Reveal a previous commitment and prove it matches the sealed hash.

    Provide all three values from your earlier seal_commitment call:
    - commitment_hash: the hash you shared with the other party
    - original_content: the exact content you sealed
    - nonce_b64: the secret nonce from the seal response

    Returns verification proof that the content matches the commitment.
    The other party can independently verify using the synpareia SDK.
    """
    app = ctx.request_context.lifespan_context
    return app.conversation_manager.reveal_commitment(
        commitment_hash,
        original_content,
        nonce_b64,
    )
