"""MCP resources — read-only data surfaces for host integration."""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.resource("synpareia://identity")
def identity_resource(ctx: Context) -> str:
    """Current synpareia identity: DID, public key, display name, configuration status."""
    import base64

    app: AppContext = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile
    return json.dumps(
        {
            "did": profile.id,
            "public_key_b64": base64.b64encode(profile.public_key).decode(),
            "display_name": app.config.display_name,
            "network_configured": app.config.network_url is not None,
            "witness_configured": app.config.witness_url is not None,
        },
        indent=2,
    )


@mcp.resource("synpareia://recordings")
def recordings_resource(ctx: Context) -> str:
    """Active and recent interaction recordings: IDs, counterparties, status."""
    app: AppContext = ctx.request_context.lifespan_context
    active = app.conversation_manager.list_active()

    recent: list[dict] = []
    conv_dir = app.config.data_dir / "conversations"
    if conv_dir.exists():
        files = sorted(conv_dir.glob("conv_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
        for f in files[:20]:
            # Intentionally drop the filesystem path — callers have the
            # recording_id and can retrieve contents via get_proof (ADV-017).
            recent.append(
                {
                    "recording_id": f.stem,
                    "status": "completed",
                }
            )

    return json.dumps({"active": active, "recent": recent}, indent=2)
