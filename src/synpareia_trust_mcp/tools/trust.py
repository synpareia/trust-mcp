"""evaluate_agent -- merged convenience entry point across all four tiers.

Per the four-tier reputation-evidence taxonomy
(docs/trust-capability.md §8, docs/explorations/counterparty-reputation.md):

- Tier 1 comes from the local journal (recall_counterparty internals).
- Tier 2 comes from media-platform adapters (check_media_signals internals).
- Tier 3 comes from attestation networks (attested_reputation internals).
- Tier 4 is a capability flag -- "can we run encode/decode with this
  counterparty?" -- not a lookup.

v0.4.0 introduces the (namespace, id) signature so the caller explicitly
disambiguates which context they are asking about. The old bare-string
``identifier=...`` form continues to work for one release with a
``deprecation`` flag on the response; it will be removed in v0.5.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.providers import (
    query_moltbook,
    query_moltrust,
    query_synpareia_network,
)

if TYPE_CHECKING:
    from synpareia_trust_mcp.journal import AgentRecord
    from synpareia_trust_mcp.providers import TrustSignal

_MAX_NAMESPACE_LEN = 64
_MAX_ID_LEN = 256

_MEDIA_NAMESPACES: set[str] = {
    "moltbook",
    "github",
    "twitter",
    "x",
    "discord",
    "slack",
    "email",
    "linkedin",
    "mastodon",
    "bluesky",
}


@mcp.tool()
async def evaluate_agent(
    ctx: Context,
    namespace: str | None = None,
    id: str | None = None,  # noqa: A002 -- matches the spec in counterparty-reputation.md
    identifier: str | None = None,
) -> dict[str, Any]:
    """Evaluate a counterparty across every configured tier.

    Pass `namespace` + `id` to route explicitly. `namespace` is the
    platform / context ("synpareia", "moltbook", "slack", "discord",
    "email", ...); `id` is the identifier within that namespace (a DID,
    handle, username, or local record id).

    The legacy ``identifier=...`` form still works for one release and
    emits a `deprecation` flag on the response. It will be removed in
    v0.5.

    Returns `{tier1, tier2, tier3, tier4_available, providers_queried,
    providers_skipped, summary}`. Every tier is a list; empty lists
    mean "no evidence at this tier" (never an error). An agent reads
    the structured result and decides how to weight each tier.
    """
    deprecation: str | None = None
    if namespace is None and id is None:
        if identifier is None:
            return {
                "error": (
                    "evaluate_agent requires (namespace, id). Example: "
                    "evaluate_agent(namespace='synpareia', id='did:synpareia:...')."
                ),
            }
        deprecation = (
            "evaluate_agent(identifier=...) is deprecated and will be removed "
            "in v0.5. Call evaluate_agent(namespace=..., id=...) instead."
        )
        namespace = _infer_namespace(identifier)
        id = identifier

    if not isinstance(namespace, str) or not namespace.strip():
        return {"error": "namespace must be a non-empty string"}
    if len(namespace) > _MAX_NAMESPACE_LEN:
        return {"error": f"namespace too long (max {_MAX_NAMESPACE_LEN})"}
    if _has_control_chars(namespace):
        return {"error": "namespace contains control characters"}
    if not isinstance(id, str) or not id.strip():
        return {"error": "id must be a non-empty string"}
    if len(id) > _MAX_ID_LEN:
        return {"error": f"id too long (max {_MAX_ID_LEN})"}
    if _has_control_chars(id):
        return {"error": "id contains control characters"}

    app: AppContext = ctx.request_context.lifespan_context
    config = app.config

    tier1 = _lookup_tier1(app, namespace, id)
    tier2_signals, tier2_provider = await _lookup_tier2(app, namespace, id)
    tier3_signals, tier3_providers = await _lookup_tier3(app, id)

    providers_queried: list[str] = []
    providers_skipped: list[dict[str, str]] = []

    if tier2_provider is not None:
        providers_queried.append(tier2_provider)
    elif namespace.lower() in _MEDIA_NAMESPACES and namespace.lower() == "moltbook":
        providers_skipped.append(
            {"name": "moltbook", "reason": "not configured (SYNPAREIA_MOLTBOOK_API_URL)"}
        )

    if "synpareia" in tier3_providers:
        providers_queried.append("synpareia")
    elif id.startswith("did:synpareia:") or namespace.lower() == "synpareia":
        providers_skipped.append(
            {"name": "synpareia", "reason": "not configured (SYNPAREIA_NETWORK_URL)"}
        )
    if "moltrust" in tier3_providers:
        providers_queried.append("moltrust")
    else:
        providers_skipped.append(
            {"name": "moltrust", "reason": "not configured (SYNPAREIA_MOLTRUST_API_KEY)"}
        )

    if namespace.lower() == "moltbook" and tier2_provider is None and not config.moltbook_api_url:
        # Already accounted for above; no double-skip.
        pass

    tier4_available = _tier4_available(namespace, id, tier1)

    tier2_dicts = [asdict(s) for s in tier2_signals]
    tier3_dicts = [asdict(s) for s in tier3_signals]

    result: dict[str, Any] = {
        "namespace": namespace,
        "id": id,
        "tier1": [r.to_dict() for r in tier1],
        "tier2": tier2_dicts,
        "tier3": tier3_dicts,
        "tier4_available": tier4_available,
        "providers_queried": providers_queried,
        "providers_skipped": providers_skipped,
        "summary": _summarize(
            namespace=namespace,
            id_=id,
            tier1=tier1,
            tier2=tier2_signals,
            tier3=tier3_signals,
            tier4_available=tier4_available,
            providers_queried=providers_queried,
            providers_skipped=providers_skipped,
        ),
    }
    if deprecation is not None:
        result["deprecation"] = deprecation
    return result


def _has_control_chars(text: str) -> bool:
    return any(ord(c) < 0x20 or ord(c) == 0x7F for c in text)


def _infer_namespace(identifier: str) -> str:
    if identifier.startswith("did:synpareia:"):
        return "synpareia"
    if identifier.startswith("local:"):
        return "local"
    return "unknown"


def _lookup_tier1(app: AppContext, namespace: str, id_: str) -> list[AgentRecord]:
    """Combine namespace_id lookup, direct id lookup, and display-name search."""
    matches: dict[str, AgentRecord] = {}

    direct = app.journal_store.get(id_)
    if direct is not None:
        matches[direct.identifier] = direct

    for record in app.journal_store.all():
        if record.namespace == namespace and record.namespace_id == id_:
            matches[record.identifier] = record

    for record in app.journal_store.find_by_name(id_):
        matches[record.identifier] = record

    return list(matches.values())


async def _lookup_tier2(
    app: AppContext, namespace: str, id_: str
) -> tuple[list[TrustSignal], str | None]:
    """Route Tier 2 by namespace. v1 only Moltbook has an adapter."""
    canonical = namespace.lower()
    if canonical == "moltbook":
        if not app.config.moltbook_api_url:
            return [], None
        signals = await query_moltbook(id_, app.config.moltbook_api_url)
        return signals, "moltbook"
    return [], None


async def _lookup_tier3(app: AppContext, id_: str) -> tuple[list[TrustSignal], list[str]]:
    """Query Tier 3 attestation providers regardless of namespace."""
    signals: list[TrustSignal] = []
    providers: list[str] = []
    config = app.config
    if config.network_url:
        providers.append("synpareia")
        signals.extend(await query_synpareia_network(id_, config.network_url))
    if config.moltrust_api_key:
        providers.append("moltrust")
        signals.extend(await query_moltrust(id_, config.moltrust_api_key))
    return signals, providers


def _tier4_available(namespace: str, id_: str, tier1: list[AgentRecord]) -> bool:
    """Tier 4 is possible whenever we have a synpareia DID for the counterparty.

    True if:
      - `id` itself looks like a synpareia DID, or
      - any matched Tier 1 record has a synpareia DID alias.
    """
    if id_.startswith("did:synpareia:"):
        return True
    for record in tier1:
        if any(alias.startswith("did:synpareia:") for alias in record.aliases):
            return True
    return False


def _summarize(
    *,
    namespace: str,
    id_: str,
    tier1: list[AgentRecord],
    tier2: list[TrustSignal],
    tier3: list[TrustSignal],
    tier4_available: bool,
    providers_queried: list[str],
    providers_skipped: list[dict[str, str]],
) -> str:
    parts: list[str] = []
    parts.append(f"Evaluated {namespace}:{id_} across four tiers.")

    tier_counts = []
    if tier1:
        tier_counts.append(f"tier1 records: {len(tier1)}")
    if tier2:
        tier_counts.append(f"tier2 signals: {len(tier2)}")
    if tier3:
        tier_counts.append(f"tier3 signals: {len(tier3)}")
    if tier_counts:
        parts.append(" / ".join(tier_counts) + ".")

    if tier4_available:
        parts.append("Tier 4 signing is available (synpareia DID detected).")

    if providers_skipped:
        details = "; ".join(f"{p['name']} ({p['reason']})" for p in providers_skipped)
        parts.append(f"Not configured: {details}.")

    if not providers_queried and not tier1:
        parts.append(
            "No evidence and no providers configured. Offline verify_claim "
            "still works without network access."
        )

    return " ".join(parts)
