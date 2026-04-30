"""Tier-2 check_media_signals — media-platform reputation signals.

Per the four-tier reputation-evidence taxonomy, Tier 2 covers signals
provided by third-party media/identity platforms (Moltbook, GitHub,
Twitter, email-verification providers, etc.). These are self-reported
by their platform — the agent should treat them as directional hints,
not authoritative claims.

v1 ships a single hardcoded adapter (Moltbook). Additional namespaces
return a structured `no_adapter` response with guidance rather than
raising, so agent UX remains graceful when querying unsupported
platforms. Future v2 work introduces a plugin model; the exploration
decision #5 deferred that until the provider ecosystem justifies it.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.providers import query_moltbook

_KNOWN_NAMESPACES: dict[str, str] = {
    "moltbook": "moltbook",
    "github": "github",
    "twitter": "twitter",
    "x": "twitter",
    "discord": "discord",
    "slack": "slack",
    "email": "email",
    "linkedin": "linkedin",
    "mastodon": "mastodon",
    "bluesky": "bluesky",
}

_MAX_NAMESPACE_LEN = 64
_MAX_HANDLE_LEN = 256


@mcp.tool()
async def check_media_signals(
    namespace: str,
    handle: str,
    ctx: Context,
) -> dict[str, Any]:
    """Query media-platform reputation signals for a counterparty (Tier 2).

    `namespace` is the platform (`moltbook`, `github`, `twitter`, etc.).
    `handle` is the counterparty's identifier on that platform.

    v1 ships with the Moltbook adapter. Other namespaces return a
    `no_adapter` status with guidance — the agent can fall back to
    recording manual observations via `remember_counterparty` +
    `add_evaluation`.

    Signals are self-reported by the platform and labelled with
    `reputation_tier=2` and `assurance_tier=1`. Treat them as
    directional, not authoritative.
    """
    if not isinstance(namespace, str) or not namespace.strip():
        return {"error": "namespace must be a non-empty string"}
    if len(namespace) > _MAX_NAMESPACE_LEN:
        return {"error": f"namespace too long (max {_MAX_NAMESPACE_LEN})"}
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in namespace):
        # Without this, control bytes (NUL, ANSI escapes, DEL) would echo
        # back into the response `hint` and `namespace` fields, which the
        # calling agent reads as part of its prompt — ADV-002-class
        # reflected injection. Sibling tools (attested_reputation,
        # evaluate_agent) already enforce this; check_media_signals
        # didn't until pentest 2026-04-30 / ADV-051.
        return {"error": "namespace contains control characters"}
    if not isinstance(handle, str) or not handle.strip():
        return {"error": "handle must be a non-empty string"}
    if len(handle) > _MAX_HANDLE_LEN:
        return {"error": f"handle too long (max {_MAX_HANDLE_LEN})"}
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in handle):
        return {"error": "handle contains control characters"}

    app: AppContext = ctx.request_context.lifespan_context
    normalised = namespace.lower().strip()
    canonical = _KNOWN_NAMESPACES.get(normalised, normalised)

    base = {
        "namespace": namespace,
        "handle": handle,
        "reputation_tier": 2,
        "assurance_tier": 1,
    }

    if canonical == "moltbook":
        if not app.config.moltbook_api_url:
            return {
                **base,
                "provider_status": "not_configured",
                "signals": [],
                "hint": (
                    "Set SYNPAREIA_MOLTBOOK_API_URL to enable Moltbook lookups. "
                    "Without config the tool returns no signals — this is a Tier-2 "
                    "miss, not an error."
                ),
            }
        signals = await query_moltbook(handle, app.config.moltbook_api_url)
        return {
            **base,
            "provider_status": "queried",
            "signals": [asdict(s) for s in signals],
        }

    return {
        **base,
        "provider_status": "no_adapter",
        "signals": [],
        "hint": (
            f"v1 does not ship a Tier-2 adapter for '{namespace}'. Record "
            "what you know manually via remember_counterparty and "
            "add_evaluation — your notes are Tier-1 but durable."
        ),
    }
