"""MCP resources — read-only data surfaces for host integration."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.resource("synpareia://identity")
def identity_resource(ctx: Context[ServerSession, AppContext]) -> str:
    """Current synpareia identity: DID, public key, display name, registration status."""
    import base64

    app = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile
    return json.dumps(
        {
            "did": profile.id,
            "public_key_b64": base64.b64encode(profile.public_key).decode(),
            "display_name": app.config.display_name,
            "network_configured": app.config.network_url is not None,
            "network_registered": False,  # TODO: check registration status
        },
        indent=2,
    )


@mcp.resource("synpareia://conversations")
def conversations_resource(ctx: Context[ServerSession, AppContext]) -> str:
    """Active and recent conversations: IDs, counterparties, status."""
    app = ctx.request_context.lifespan_context
    active = app.conversation_manager.list_active()

    # Also list recent persisted conversations
    recent: list[dict] = []
    conv_dir = app.config.data_dir / "conversations"
    if conv_dir.exists():
        files = sorted(conv_dir.glob("conv_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[:20]:  # last 20
            recent.append(
                {
                    "conversation_id": f.stem,
                    "file": str(f),
                    "status": "completed",
                }
            )

    return json.dumps({"active": active, "recent": recent}, indent=2)
