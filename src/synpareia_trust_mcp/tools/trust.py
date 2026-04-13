"""Trust evaluation tools -- check reputation and verify identities."""

from __future__ import annotations

import base64

import synpareia
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def check_agent_trust(
    agent_did: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Look up trust and reputation information for another agent.

    Queries the synpareia network for this agent's reputation score,
    conversation history summary, and verification status. Requires
    network connectivity (SYNPAREIA_NETWORK_URL must be configured).

    If the network is not available, you can still verify specific claims
    using verify_signature and verify_identity.
    """
    app = ctx.request_context.lifespan_context

    if not app.config.network_url:
        return {
            "agent_did": agent_did,
            "available": False,
            "message": (
                "Network not configured. Set SYNPAREIA_NETWORK_URL to enable "
                "trust lookups. You can still verify signatures directly using "
                "verify_signature and verify_identity."
            ),
        }

    # TODO: implement network API call when service endpoints exist
    return {
        "agent_did": agent_did,
        "available": False,
        "message": (
            "Network reputation lookups will be available when the synpareia "
            "network service is deployed. For now, use verify_signature to "
            "verify specific claims, and start_conversation to build a "
            "verifiable interaction record."
        ),
    }


@mcp.tool()
def verify_identity(
    agent_did: str,
    public_key_b64: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Verify that a DID matches a public key. Works fully offline.

    If an agent claims to be did:synpareia:abc123 and provides a public key,
    this confirms whether that key actually derives that DID. A mismatch means
    the agent may be impersonating someone else.
    """
    try:
        public_key = base64.b64decode(public_key_b64)
        derived = synpareia.from_public_key(public_key)
        matches = derived.id == agent_did
    except Exception as e:
        return {"valid": False, "error": str(e)}

    return {
        "valid": matches,
        "claimed_did": agent_did,
        "derived_did": derived.id,
        "explanation": (
            "The public key correctly derives this DID. Identity confirmed."
            if matches
            else (
                "MISMATCH: the public key does not derive the claimed DID. "
                "This agent may be impersonating someone else."
            )
        ),
    }
