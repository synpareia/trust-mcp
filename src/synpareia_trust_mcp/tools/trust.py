"""Trust evaluation tools — multi-provider agent evaluation."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.providers import (
    TrustSignal,
    query_moltbook,
    query_moltrust,
    query_synpareia_network,
)


@mcp.tool()
async def evaluate_agent(
    identifier: str,
    ctx: Context,
) -> dict[str, Any]:
    """Look up trust and reputation for another agent across all configured providers.

    Pass a DID, Moltbook username, or other identifier.
    """
    app: AppContext = ctx.request_context.lifespan_context
    config = app.config

    all_signals: list[TrustSignal] = []
    providers_queried: list[str] = []

    # Query all configured providers
    if config.network_url:
        providers_queried.append("synpareia")
        signals = await query_synpareia_network(identifier, config.network_url)
        all_signals.extend(signals)

    if config.moltbook_api_url:
        providers_queried.append("moltbook")
        signals = await query_moltbook(identifier, config.moltbook_api_url)
        all_signals.extend(signals)

    if config.moltrust_api_key:
        providers_queried.append("moltrust")
        signals = await query_moltrust(identifier, config.moltrust_api_key)
        all_signals.extend(signals)

    if not providers_queried:
        return {
            "identifier": identifier,
            "providers_queried": [],
            "signals": [],
            "summary": (
                "No reputation providers configured. "
                "You can still verify specific claims offline using verify_claim. "
                "Set SYNPAREIA_NETWORK_URL, SYNPAREIA_MOLTBOOK_API_URL, or "
                "SYNPAREIA_MOLTRUST_API_KEY to enable reputation lookups."
            ),
        }

    return {
        "identifier": identifier,
        "providers_queried": providers_queried,
        "signals": [asdict(s) for s in all_signals],
        "summary": _summarize_signals(identifier, all_signals, providers_queried),
    }


def _summarize_signals(
    identifier: str,
    signals: list[TrustSignal],
    providers: list[str],
) -> str:
    """Generate a brief human-readable summary of trust signals."""
    errors = [s for s in signals if s.signal_type == "error"]
    not_found = [s for s in signals if s.signal_type == "lookup" and s.value == "not_found"]
    data_signals = [s for s in signals if s.signal_type not in ("error", "lookup")]

    parts = [f"Queried {len(providers)} provider(s): {', '.join(providers)}."]

    if not_found:
        not_found_providers = [s.provider for s in not_found]
        parts.append(f"Not found in: {', '.join(not_found_providers)}.")

    if errors:
        error_providers = [s.provider for s in errors]
        parts.append(f"Errors from: {', '.join(error_providers)}.")

    if data_signals:
        high_confidence = [s for s in data_signals if s.confidence == "high"]
        if high_confidence:
            parts.append(f"{len(high_confidence)} high-confidence signal(s) available.")
        else:
            parts.append(f"{len(data_signals)} signal(s) available (medium/low confidence).")
    elif not errors:
        parts.append(
            "No reputation data found. Agent may be new "
            "— absence is not evidence of untrustworthiness."
        )

    return " ".join(parts)
