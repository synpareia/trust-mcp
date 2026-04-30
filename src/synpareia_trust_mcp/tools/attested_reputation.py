"""Tier-3 attested_reputation -- signed reputation from trust-provider networks.

Per the four-tier reputation-evidence taxonomy, Tier 3 is one-off network
attestation: cryptographic proof (or provider-signed statements) that an
identifier corresponds to a specific entity at a specific moment. This
tool fans out to the configured attestation providers (synpareia network,
MolTrust) and returns their signals with provider attribution.

v1 is query-only. Submission to the synpareia reputation network is
deferred to v2 pending witness Phase 2 (anonymous-credential identity
binding). Tier 3 reads are sufficient today: an agent can query what
others have attested without needing to attest back yet.

A Tier-3 reply is *not* proof that the counterparty authored any specific
message -- it proves "at time T, this identifier had these attested
signals". Bridging message-level binding is what Tier 4 provides via
`encode_signed` / `decode_signed`.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.providers import (
    TrustSignal,
    query_moltrust,
    query_synpareia_network,
)

_MAX_IDENTIFIER_LEN = 256


@mcp.tool()
async def attested_reputation(
    identifier: str,
    ctx: Context,
) -> dict[str, Any]:
    """Query signed reputation for a counterparty from attestation networks (Tier 3).

    `identifier` is a DID, provider-scoped ID, or opaque network handle.

    Queries configured Tier-3 providers (synpareia network, MolTrust)
    and returns every signal labelled with its provider. Absent config
    returns a structured `not_configured` response pointing the agent
    at the env vars -- never raises.

    Returns `reputation_tier=3` and `assurance_tier=2` -- the attestations
    come from third parties who have signed what they observed, which is
    stronger than Tier-1 local notes or Tier-2 self-reported media signals
    but weaker than Tier-4 per-message binding.
    """
    if not isinstance(identifier, str) or not identifier.strip():
        return {"error": "identifier must be a non-empty string"}
    if len(identifier) > _MAX_IDENTIFIER_LEN:
        return {"error": f"identifier too long (max {_MAX_IDENTIFIER_LEN})"}
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in identifier):
        return {"error": "identifier contains control characters"}

    app: AppContext = ctx.request_context.lifespan_context
    config = app.config

    all_signals: list[TrustSignal] = []
    providers_queried: list[str] = []

    if config.network_url:
        providers_queried.append("synpareia")
        all_signals.extend(await query_synpareia_network(identifier, config.network_url))

    if config.moltrust_api_key:
        providers_queried.append("moltrust")
        all_signals.extend(await query_moltrust(identifier, config.moltrust_api_key))

    base: dict[str, Any] = {
        "identifier": identifier,
        "reputation_tier": 3,
        "assurance_tier": 2,
        "providers_queried": providers_queried,
        "signals": [asdict(s) for s in all_signals],
    }

    if not providers_queried:
        base["hint"] = (
            "No Tier-3 providers configured. Set SYNPAREIA_NETWORK_URL for "
            "the synpareia reputation network or SYNPAREIA_MOLTRUST_API_KEY "
            "for MolTrust. Without them this tool returns no signals -- "
            "fall back to recall_counterparty (Tier 1) or check_media_signals "
            "(Tier 2)."
        )

    return base
