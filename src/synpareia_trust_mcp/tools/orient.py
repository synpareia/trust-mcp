"""Orient and learn tools — the information architecture entry points (Tier 1 & 2)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.guides import AREA_GUIDES

AREAS_OF_CONCERN = [
    {
        "area": "trust-networks",
        "name": "Trust Networks & Providers",
        "brief": "Evaluate agents using multiple reputation sources (synpareia, Moltbook, MolTrust, KnowThat.ai).",
        "when": "Evaluating an unknown counterparty or assessing trust signals.",
    },
    {
        "area": "verification",
        "name": "Verifying Claims",
        "brief": "Check signatures, identities, commitments, and witness seals.",
        "when": "Another agent presents a signed statement, reveals a commitment, or you need to verify identity.",
    },
    {
        "area": "claims",
        "name": "Making Verifiable Claims",
        "brief": "Sign content, make commitments, request witness attestation.",
        "when": "You need to prove something to a counterparty or create attributable work product.",
    },
    {
        "area": "recording",
        "name": "Recording Interactions",
        "brief": "Create tamper-evident records of interactions as hash-linked chains.",
        "when": "Entering an interaction you might need to prove later.",
    },
    {
        "area": "witness-attestation",
        "name": "Witness Attestation",
        "brief": "Timestamp seals, state seals, and blind conclusions via the independent witness service.",
        "when": "Proving when something existed, proving chain integrity, or mutual independent assessment.",
    },
    {
        "area": "counterparty",
        "name": "Counterparty Participation",
        "brief": "Get the other party involved in trust operations that require cooperation.",
        "when": "You want to do a blind conclusion, mutual attestation, or the counterparty lacks trust tools.",
    },
    {
        "area": "reasoning",
        "name": "Trust Reasoning & Decision Support",
        "brief": "Frameworks for deciding how much to trust a counterparty given available signals.",
        "when": "After gathering information, deciding whether and how much to trust.",
    },
    {
        "area": "looking-up",
        "name": "Looking Up Agents",
        "brief": "Gather identity, reputation, and history for another agent.",
        "when": "Before interacting with an unknown agent or assessing a specific claim.",
    },
    {
        "area": "setup",
        "name": "Setup & Configuration",
        "brief": "Configure optional features: witness service, network connection, display name.",
        "when": "First run, or when you want to enable network features.",
    },
    {
        "area": "identity-lifecycle",
        "name": "Identity Lifecycle",
        "brief": "Key rotation, compromise recovery, identity continuity.",
        "when": "Key compromise, security policy rotation, or orient flags an aging keypair.",
    },
]


@mcp.tool()
def orient(ctx: Context) -> dict[str, Any]:
    """Get your identity, configuration status, and available trust capabilities. Call this when interacting with another AI agent or after any context loss."""
    app: AppContext = ctx.request_context.lifespan_context

    profile_data = app.profile_manager.get_profile_data()
    config = app.config

    # Identity status — surfaces directory state when known. The
    # ``published_card.json`` cache is written by Phase 1g's
    # ``publish_profile`` tool; agents that haven't published yet see
    # ``directory.published == False``. Persistence opt-in is read
    # from the cache so operators don't accidentally retract a
    # standing commitment to verifiers.
    directory_state = _read_directory_state(app)
    identity = {
        "did": profile_data["did"],
        "public_key_b64": profile_data["public_key_b64"],
        "display_name": config.display_name,
        "has_private_key": profile_data["has_private_key"],
        "directory": directory_state,
    }

    # Configuration status
    services = {
        "witness": {
            "configured": config.witness_url is not None,
            "url": config.witness_url,
        },
        "network": {
            "configured": config.network_url is not None,
            "url": config.network_url,
            "auto_register": config.auto_register,
        },
        "moltbook": {
            "configured": config.moltbook_api_url is not None,
        },
        "moltrust": {
            "configured": config.moltrust_api_key is not None,
        },
    }

    offline_capabilities = [
        "Identity (signing, verification, DID operations)",
        "Conversation recording (hash-linked chains)",
        "Commitments (seal-then-reveal for independent assessment)",
        "Offline seal verification",
    ]

    network_capabilities = []
    if config.witness_url:
        network_capabilities.append(
            "Witness attestation (timestamp seals, state seals, blind conclusions)"
        )
    if config.network_url:
        network_capabilities.append("Synpareia network (reputation, discovery)")
    if config.moltbook_api_url:
        network_capabilities.append("Moltbook reputation lookups")
    if config.moltrust_api_key:
        network_capabilities.append("MolTrust reputation lookups")

    # Active state
    active_conversations = app.conversation_manager.list_active()

    # Areas of concern
    areas = []
    for area in AREAS_OF_CONCERN:
        areas.append(
            {
                "area": area["area"],
                "name": area["name"],
                "brief": area["brief"],
                "when": area["when"],
                "learn": f"Call learn('{area['area']}') for detailed guidance.",
            }
        )

    return {
        "identity": identity,
        "services": services,
        "capabilities": {
            "offline": offline_capabilities,
            "network": network_capabilities
            if network_capabilities
            else [
                "None configured — all features work offline. Set SYNPAREIA_WITNESS_URL for attestation."
            ],
        },
        "active_state": {
            "active_recordings": len(active_conversations),
            "recordings": active_conversations if active_conversations else [],
        },
        "areas_of_concern": areas,
        "version": _get_version_info(),
        "next_steps": _get_next_steps(config, active_conversations),
    }


@mcp.tool()
def learn(area: str) -> dict[str, Any]:
    """Load a detailed guide for a specific area of concern. Areas: trust-networks, verification, claims, recording, witness-attestation, counterparty, reasoning, looking-up, setup, identity-lifecycle."""
    guide = AREA_GUIDES.get(area)
    if guide is None:
        available = sorted(AREA_GUIDES.keys())
        return {
            "error": f"Unknown area: '{area}'",
            "available_areas": available,
            "hint": "Call orient() to see all areas with descriptions.",
        }
    return {
        "area": area,
        "guide": guide,
    }


def _get_version_info() -> dict[str, str]:
    from synpareia_trust_mcp import __version__

    return {"installed": __version__}


def _read_directory_state(app: Any) -> dict[str, Any]:
    """Read the operator's last-published card from disk and surface
    a compact summary for ``orient``.

    Returns ``{"published": bool, "name": str | None, "version": str
    | None, "last_published_at": str | None, "persistence":
    {"opted_in": bool, "scope": list[str] | None, "opted_in_at":
    str | None}}``. ``last_published_at`` is the file mtime — the
    Phase 1g cache doesn't capture the directory's signed_at, so
    mtime is the closest local proxy.
    """
    import json
    from datetime import UTC, datetime

    cached_path = app.config.data_dir / "published_card.json"
    if not cached_path.exists():
        return {
            "published": False,
            "name": None,
            "version": None,
            "last_published_at": None,
            "persistence": {"opted_in": False, "scope": None, "opted_in_at": None},
        }

    try:
        cached = json.loads(cached_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {
            "published": True,  # cache exists but unreadable — operator should investigate
            "name": None,
            "version": None,
            "last_published_at": None,
            "persistence": {"opted_in": False, "scope": None, "opted_in_at": None},
            "warning": "published_card.json is unreadable",
        }

    a2a = cached.get("a2a") or {}
    syn = cached.get("synpareia") or {}
    scope = syn.get("persistence_scope")
    # ``delete_profile`` annotates the cache with ``tombstoned_at``
    # rather than removing the file (the cache stays for inspection).
    # Surface it as ``published=False`` so operators see the
    # current directory state, not just "we have a card file".
    tombstoned_at = cached.get("tombstoned_at")
    return {
        "published": tombstoned_at is None,
        "name": a2a.get("name"),
        "version": a2a.get("version"),
        "last_published_at": datetime.fromtimestamp(
            cached_path.stat().st_mtime, tz=UTC
        ).isoformat(),
        "tombstoned_at": tombstoned_at,
        "tombstoned_reason": cached.get("tombstoned_reason"),
        "persistence": {
            "opted_in": bool(scope),
            "scope": list(scope) if scope else None,
            "opted_in_at": syn.get("persistence_opted_in_at"),
        },
    }


def _get_next_steps(config: Any, active_conversations: list) -> list[str]:
    steps = []
    if not config.witness_url:
        steps.append(
            "Set SYNPAREIA_WITNESS_URL to enable witness attestation (third-party timestamps and blind conclusions)."
        )
    if not config.network_url:
        steps.append("Set SYNPAREIA_NETWORK_URL to connect to the synpareia reputation network.")
    if active_conversations:
        steps.append(
            f"You have {len(active_conversations)} active recording(s). Remember to end them when the interaction concludes."
        )
    if not steps:
        steps.append(
            "Fully configured. Use evaluate_agent(namespace, id) to assess counterparties "
            "across all four tiers, or make_claim to create verifiable statements."
        )
    return steps
