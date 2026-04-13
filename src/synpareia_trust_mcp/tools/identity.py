"""Identity tools -- manage and present your cryptographic identity."""

from __future__ import annotations

import base64

import synpareia
from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def get_my_identity(ctx: Context[ServerSession, AppContext]) -> dict:
    """Get your synpareia identity: DID, public key, and profile metadata.

    Your DID (Decentralized Identifier) is your unique cryptographic identity.
    Share it with other agents so they can verify your signatures and look you up
    on the synpareia network.
    """
    app = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile
    return {
        "did": profile.id,
        "public_key_b64": base64.b64encode(profile.public_key).decode(),
        "display_name": app.config.display_name,
        "network_registered": False,  # TODO: check actual registration status
    }


@mcp.tool()
def sign_content(content: str, ctx: Context[ServerSession, AppContext]) -> dict:
    """Sign content with your private key, producing a verifiable statement.

    The recipient can verify this signature using your public key or DID,
    proving that you (and only you) authored this content. Use this for
    any claim you want to be cryptographically attributable to you.
    """
    app = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile

    assert profile.private_key is not None  # ProfileManager always has private key
    content_bytes = content.encode()
    signature = synpareia.sign(profile.private_key, content_bytes)

    return {
        "content": content,
        "signature_b64": base64.b64encode(signature).decode(),
        "signer_did": profile.id,
        "public_key_b64": base64.b64encode(profile.public_key).decode(),
    }


@mcp.tool()
def verify_signature(
    content: str,
    signature_b64: str,
    public_key_b64: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Verify that content was signed by the holder of a specific public key.

    Use this to confirm another agent actually authored a piece of content.
    You need their public key (from their get_my_identity output or a profile lookup).
    Works fully offline -- no network required.
    """
    try:
        content_bytes = content.encode()
        signature = base64.b64decode(signature_b64)
        public_key = base64.b64decode(public_key_b64)
        valid = synpareia.verify(public_key, content_bytes, signature)
    except Exception as e:
        return {"valid": False, "error": str(e)}

    signer_profile = synpareia.from_public_key(public_key)

    return {
        "valid": valid,
        "signer_did": signer_profile.id,
        "content_preview": content[:100] + ("..." if len(content) > 100 else ""),
    }
