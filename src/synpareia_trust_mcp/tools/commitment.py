"""Independence proof tools — commit-then-reveal for provably independent assessment."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def prove_independence(content: str, ctx: Context) -> dict[str, Any]:
    """Seal your assessment before seeing others'.

    Share ONLY commitment_hash. Keep nonce_b64 secret until reveal.
    Verify with verify_claim(claim_type='commitment', ...).
    """
    app: AppContext = ctx.request_context.lifespan_context
    result = app.conversation_manager.seal_commitment(content)
    # Update instructions to reference new tool names
    result["instructions"] = (
        "Share ONLY the commitment_hash with the other party. "
        "Keep the nonce_b64 secret until reveal time. "
        "To verify: verify_claim(claim_type='commitment', commitment_hash=..., "
        "content=..., nonce_b64=...)."
    )
    return result
