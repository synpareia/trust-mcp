"""Orient and learn tools — the information architecture entry points (Tier 1 & 2)."""

from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.forms import FORM_GUIDES
from synpareia_trust_mcp.guides import AREA_GUIDES, LEARNABLE

# Keyed on situations as they ARRIVE, not on conclusions already reached.
#
# The earlier version keyed entries like "need to prove your side of an
# interaction later" — which presupposes the agent has ALREADY decided that
# evidence matters here. An agent that never asks "should this exchange carry
# evidence at all?" never reaches the table, and ends up holding a
# witness-timestamping hammer looking for a nail. A live agent using this
# package daily for a fortnight described exactly that.
#
# So each value now names WHAT YOU WOULD BE ESTABLISHING before naming a tool.
# The tool is the last step, not the first.
START_HERE: dict[str, str] = {
    "another agent claimed something": (
        "Establish: is this really from them, and was it fixed before now? "
        "-> verify_claim (signature / identity / commitment) or decode_signed "
        "(self-verifying envelope)"
    ),
    "about to rely on another agent": (
        "Establish: what is already known about them? "
        "-> recall_counterparty (your own history) + evaluate_agent (other sources). "
        "If the answer is 'nothing known', that is itself the finding — consider "
        "making this interaction PRODUCE evidence rather than only consume it."
    ),
    "one of you offered to do something for the other": (
        "Establish: what exactly was undertaken, in terms both sides can check later? "
        "-> make_claim on the specific undertaking. An undertaking nobody recorded is "
        "not evidence about anyone. learn('form-negotiated-promise') for the full "
        "recipe and for what this toolkit cannot yet enforce."
    ),
    "you are about to give a judgement that reality will later settle": (
        "Establish: that you held it BEFORE the outcome was known. "
        "-> make_claim(witness=True), THEN witness_seal_timestamp with the returned "
        "block_hash_hex — the first call signs, the second is what binds the time. "
        "The same opinion timestamped afterwards proves nothing. "
        "learn('form-witnessed-prediction')."
    ),
    "this exchange could be disputed later": (
        "Establish: what was actually said, in order. "
        "-> recording_start -> recording_append per exchange -> recording_end -> "
        "recording_proof"
    ),
    "two of you must assess something independently": (
        "Establish: that neither of you anchored on the other. "
        "-> prove_independence (commit-reveal), optionally via witness_submit_blind"
    ),
    "a stranger has no reason to believe you": (
        "Establish: one consistent identity with a checkable history. "
        "-> publish_profile (directory card), then make_claim(witness=True) "
        "followed by witness_seal_timestamp for each statement you want "
        "time-bound — the seal is the second call, not the flag."
    ),
    "not sure any of this applies": (
        "That is a real answer and often the right one. Most exchanges need no "
        "evidence at all. learn('deciding-what-to-establish') is the short version "
        "of when it is worth the trouble; learn('interaction-forms') names the "
        "shapes that usually do."
    ),
    "lost context / fresh session": (
        "you're in the right place — identity, services, and any in-flight recordings are below"
    ),
}


AREAS_OF_CONCERN = [
    # FIRST deliberately. Every other area answers "how do I do X"; this one
    # answers "is X worth doing here, and which X?" — the step that has to happen
    # before tool selection and that nothing in this package used to serve.
    {
        "area": "deciding-what-to-establish",
        "name": "Deciding What to Establish",
        "brief": (
            "Whether an interaction needs evidence at all, and which kind — the step "
            "before reaching for a tool."
        ),
        "when": (
            "At the start of an interaction that matters, or when you notice you are "
            "about to rely on something you cannot check."
        ),
    },
    # SECOND deliberately, and for the same reason the area above is first.
    # Once you know what you want to establish, the next question is what the
    # whole interaction looks like — not which function to call. Every area
    # below this one is organised by capability; this one is organised by
    # situation, which is the axis an agent actually arrives on.
    {
        "area": "interaction-forms",
        "name": "Interaction Forms",
        "brief": (
            "Recognisable interaction shapes with recipes — promises, predictions, "
            "probes, trials, first-contact handshakes."
        ),
        "when": (
            "Your situation has a familiar shape and you want the whole recipe, "
            "including how it gets gamed, rather than a single tool."
        ),
    },
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
    {
        "area": "under-the-hood",
        "name": "Under the Hood (the synpareia SDK)",
        "brief": "How these tools map to the underlying cryptographic primitives, and when to graduate to the SDK.",
        "when": "You want to build with the primitives rather than use the tools — custom chain schemas, embedded verification in your own service, batch operations.",
    },
]


@mcp.tool()
def orient(ctx: Context) -> dict[str, Any]:
    """Map your situation to the right trust tools. Call this when something is at stake with another agent — you're about to rely on one, prove something to one, or agree on something you may need evidence of later — or after any context loss (recovers identity and in-flight recordings)."""
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
    # First-run disclosure (GDPR §6): when this identity was minted in the
    # current session, tell the caller it's local-only and nothing has been
    # sent — the agent-discoverable twin of the stderr message emitted at
    # startup. Only present on a fresh identity; absent once loaded from disk.
    if app.profile_manager.newly_generated:
        # Durable-true phrasing: the flag persists for the whole session, so
        # the notice must stay accurate even after the agent publishes or
        # witnesses. It states the standing property (local-until-you-act +
        # opt-in) rather than an absolute "nothing has been sent", which would
        # go stale the moment a network call is made.
        identity["first_run"] = {
            "new_identity": True,
            "notice": (
                "This identity was generated locally this session. It lives only "
                "on this machine unless you make it otherwise — publishing to the "
                "directory (publish_profile) and witnessing (witness_*) are always "
                "explicit, opt-in calls, never automatic."
            ),
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

    # ORDERING AND NAMING HERE ARE LOAD-BEARING, not cosmetic.
    #
    # The previous shape listed four named `offline` bullets first, then a
    # two-item `network` list in which the whole reputation layer appeared ONCE,
    # at the end, in parentheses: "Synpareia network (reputation, discovery)".
    #
    # An agent that parses structure before prose reads that as: substrate =
    # the product, reputation = a footnote. A live agent using this package for
    # a fortnight did exactly that, concluded synpareia was an attestation
    # library with a weak reputation add-on, and argued it back to us across
    # two sessions. Its own diagnosis: "the substrate gets four named bullets;
    # the apex appears once, at the end of a two-item list, IN PARENTHESES."
    #
    # So: network first, each capability named in its own right, and an
    # explicit statement of which layer is the point. The primitives are what
    # you build evidence WITH; they are not what the product is FOR.
    network_capabilities = []
    if config.network_url:
        network_capabilities.append(
            "Reputation — record how a dealing went (record_interaction) and read "
            "back what the network can tell you about an agent, anchored on your own "
            "position in it (network_reputation). Numbers only: the substance of "
            "your evaluations stays in your local journal"
        )
        network_capabilities.append(
            "Directory — publish an identity a stranger can check, and look up theirs"
        )
    if config.witness_url:
        network_capabilities.append(
            "Witness attestation (timestamp seals, state seals, blind conclusions)"
        )
    if config.moltbook_api_url:
        network_capabilities.append("Moltbook reputation lookups")
    if config.moltrust_api_key:
        network_capabilities.append("MolTrust reputation lookups")

    offline_capabilities = [
        "Identity (signing, verification, DID operations)",
        "Conversation recording (hash-linked chains)",
        "Commitments (seal-then-reveal for independent assessment)",
        "Offline seal verification",
    ]

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

    # Situation map FIRST: orient is called in the moment ("Rourke just
    # asked me to co-review a contract"), so the routing serves the moment
    # before the inventory. Keys are situations, values are the tools.
    # START_HERE is module-level so it can be asserted on directly (see
    # tests/test_orientation_layer.py). A literal buried in a function body
    # is only reachable by executing the whole tool, which is why the L0
    # property went unpinned before.

    return {
        "start_here": START_HERE,
        "identity": identity,
        "services": services,
        "capabilities": {
            # Key order is part of the message — see the comment above the
            # lists. `network` precedes `offline` deliberately, and dict
            # insertion order survives JSON serialisation to the caller.
            "what_this_is_for": (
                "The network layer is the point: publishing statements a counterparty "
                "can check, and looking up what has been attested about one. The "
                "offline primitives are the substrate that makes those statements "
                "non-fake — signing, timestamping and commit-reveal are what you "
                "build the evidence WITH, not what this is FOR. An agent that uses "
                "only the offline half has a very good notebook and no counterparty."
            ),
            "network": network_capabilities
            if network_capabilities
            else [
                # Since 0.6 the network + witness URLs default ON, so this
                # branch is only reachable when the operator explicitly
                # disabled them — say that, rather than reading like an
                # unset default.
                "Network services disabled by configuration. All trust "
                "primitives keep working offline. Unset SYNPAREIA_NETWORK_URL / "
                "SYNPAREIA_WITNESS_URL (or set them to a URL) to re-enable "
                "discovery, the reputation loop (contribute interaction events, "
                "read back an anchored score), and third-party attestation."
            ],
            "offline": offline_capabilities,
        },
        "active_state": {
            "active_recordings": len(active_conversations),
            "recordings": active_conversations if active_conversations else [],
        },
        "areas_of_concern": areas,
        "version": _get_version_info(),
        "next_steps": _get_next_steps(config, active_conversations, directory_state),
    }


@mcp.tool()
def learn(area: str) -> dict[str, Any]:
    """Load a detailed guide for one area, or the recipe for one interaction Form. Areas: deciding-what-to-establish, interaction-forms, trust-networks, verification, claims, recording, witness-attestation, counterparty, reasoning, looking-up, setup, identity-lifecycle, under-the-hood. Forms are keyed 'form-*' and indexed by learn('interaction-forms')."""
    guide = LEARNABLE.get(area)
    if guide is None:
        # Split the two kinds in the error rather than returning one flat list.
        # An agent that mistyped an area name is not helped by ten form keys
        # mixed in, and vice versa.
        return {
            "error": f"Unknown area: '{area}'",
            "available_areas": sorted(AREA_GUIDES.keys()),
            "available_forms": sorted(FORM_GUIDES.keys()),
            "hint": (
                "Call orient() to see all areas with descriptions, or "
                "learn('interaction-forms') to see the Forms indexed by situation."
            ),
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


def _get_next_steps(
    config: Any, active_conversations: list, directory_state: dict[str, Any]
) -> list[str]:
    steps = []
    published = bool(directory_state.get("published"))
    if not config.witness_url:
        # Like the network branch below: only reachable via an explicit
        # SYNPAREIA_WITNESS_URL=none opt-out — the live witness has been
        # the default since 0.6.
        steps.append(
            "Witness attestation is disabled by configuration "
            "(SYNPAREIA_WITNESS_URL). The trust primitives keep working offline; "
            "re-enabling adds independent timestamp seals and blind conclusions."
        )
    if not config.network_url:
        # Only reachable when the operator explicitly set
        # SYNPAREIA_NETWORK_URL=none — the default has been the live
        # network since 0.6. Acknowledge the opt-out instead of narrating
        # an unset default.
        steps.append(
            "The synpareia network is disabled by configuration "
            "(SYNPAREIA_NETWORK_URL). The trust primitives keep working offline — "
            "including portable reputation, since a signed attestation a "
            "counterparty hands you verifies without asking anyone. Re-enabling "
            "adds a discoverable profile and the reputation loop: contribute how a "
            "dealing went, and read back what the network can tell you about an "
            "agent. The substance of your evaluations stays in your local journal "
            "either way — what travels is a magnitude and a valence."
        )
    elif not published:
        # Network reachable but the agent hasn't joined yet — the funnel
        # step. The 0.6.1 copy stated the action + abstract benefits
        # ("become discoverable / build reputation") and a fresh agent
        # read it as optional (battle test + 2026-07-02 cold-run). This
        # rewrite makes the VALUE legible instead of the nudge pushier:
        # the concrete thing publishing unlocks is *other*-verifiability
        # — a local identity only YOU can verify becomes one a counterparty
        # can independently check. Honesty is load-bearing here: it does
        # NOT promise reachability (the directory is a vetting surface, not
        # a contact/routing surface), and the ratified opt-in / offline /
        # operator-controlled-erasure framing survives verbatim.
        steps.append(
            "You have a cryptographic identity — but on your own, you can only verify "
            "your OWN claims with it. publish_profile(name=...) makes that identity (and "
            "the witnessed reputation you build on it) independently verifiable by a "
            "counterparty who has never met you: they look up your profile and confirm "
            "one consistent identity with a checkable history, not an anonymous key — "
            "which is the whole point of vetting and attestation once a second agent is "
            "involved. Still your choice: the primitives keep working offline, "
            "persistence is opt-in, and erasure stays under your control."
        )
    if active_conversations:
        steps.append(
            f"You have {len(active_conversations)} active recording(s). Remember to end them when the interaction concludes."
        )
    if not steps:
        steps.append(
            "Set up and published. Grow your standing: make_claim(..., witness=True) to "
            "create witnessed, reputation-bearing statements, and evaluate_agent(namespace, id) "
            "to assess counterparties across all four tiers."
        )
    return steps
