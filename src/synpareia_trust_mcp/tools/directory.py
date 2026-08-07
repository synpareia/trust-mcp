"""Profile-directory tools — Trust MCP 0.5.0 (Phase 1g).

Wires the Phase 1d/1e directory routes through the SDK's
``synpareia.profile.ProfileClient``. Tools provide the operator's
self-service surface (publish, update policy, enable/disable
persistence opt-in, erase) plus a counterparty-fetch helper
(``get_profile``).

**State on disk.** The Trust MCP persists ``data_dir/published_card.json``
after a successful publish so subsequent ``update_profile_policy``
calls can rebuild from the last published shape and re-sign without
re-asking for fields the operator already declared. The published-
card cache is read-only otherwise; operators see what the directory
returned.

**Identity binding.** Every authenticated route (publish, delete*)
signs the HTTP request with the operator's Ed25519 private key
(from ``ProfileManager``); the directory verifies the signature
against the DID's current controlling key per the rotation chain.
The operator never sends their private key over the wire.

**Witness anchor.** When ``SYNPAREIA_WITNESS_URL`` is configured at
the *main service*, the directory anchors the card-hash itself
(see ``services.witness_anchor`` in the main service). The Trust
MCP's existing witness wiring is independent: agents can request
their *own* timestamp seal via ``request_witness_anchor``. Both
paths leak only the hash.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003 — runtime function-arg annotation
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import mcp

try:
    from synpareia.profile import (
        FirstContactFee,
        PersistenceOptIn,
        ProfileClient,
        ReputationConsent,
        WellKnownPublicationPolicy,
        build_agent_card,
        card_canonical_bytes,
        sign_agent_card,
    )

    HAS_PROFILE_SDK = True
except ImportError:  # pragma: no cover — profile SDK below the declared floor
    HAS_PROFILE_SDK = False

if TYPE_CHECKING:
    from synpareia_trust_mcp.app import AppContext

# Kept equal to the `synpareia` floor in this package's pyproject.toml by
# `tests/test_sdk_floor_message.py`, which parses the declared requirement and
# compares. It is not derived at runtime: the whole point of this message is to
# be correct when the SDK import *failed*, so it cannot read anything out of the
# SDK, and reading our own dist metadata fails the same way for an editable or
# source checkout. A constant plus a test that binds it is the honest shape.
#
# Eight call sites said "0.5.0+" and a ninth said "0.7.0+" before this. The floor
# had moved to 0.7.0, so those eight told an operator on 0.6.x to upgrade to a
# version they already exceeded — while the actual failure was that `directory.py`
# imports `ReputationConsent`, which 0.6.x does not export.
MIN_PROFILE_SDK_VERSION = "0.7.0"


def _profile_sdk_unavailable() -> dict[str, Any]:
    """Degradation payload for tools that need the profile SDK.

    Returns a fresh dict per call: these go back to MCP clients as tool
    results, and a shared module-level dict would let one caller's mutation
    reach every later caller.
    """
    return {
        "error": (f"synpareia.profile not available — upgrade SDK to {MIN_PROFILE_SDK_VERSION}+")
    }


_HTTP_FORBIDDEN = 403
#: Retry-aid memo cap. Not an audit log — the directory's ledger is the durable
#: record, so entries are only useful until a send has succeeded.
_EVENT_MEMO_MAX = 500

__all__ = [
    "delete_profile",
    "delete_profile_history",
    "disable_persistence",
    "enable_persistence",
    "get_profile",
    "network_reputation",
    "publish_profile",
    "record_interaction",
    "set_reputation_consent",
    "update_profile_policy",
]


_PUBLISHED_CARD_FILE = "published_card.json"


# ---------------------------------------------------------------------------
# Local card-shape cache (no network)
# ---------------------------------------------------------------------------


def _published_card_path(data_dir: Path) -> Path:
    return data_dir / _PUBLISHED_CARD_FILE


def _load_cached_card(data_dir: Path) -> dict[str, Any] | None:
    path = _published_card_path(data_dir)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def _save_cached_card(data_dir: Path, card_shape: dict[str, Any]) -> None:
    path = _published_card_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(card_shape, indent=2, sort_keys=True), encoding="utf-8")


def _mark_cached_card_tombstoned(data_dir: Path, *, reason: str | None) -> None:
    """Annotate the on-disk cached card as tombstoned.

    The cache file stays for inspection (the docstring on
    ``delete_profile`` promises this), but ``orient`` reads the
    tombstone fields to surface ``directory.published == False``
    after a full delete. Callers that want a fully-clean slate
    can remove ``published_card.json`` manually.
    """
    cached = _load_cached_card(data_dir)
    if cached is None:
        return
    cached["tombstoned_at"] = datetime.now(UTC).isoformat()
    cached["tombstoned_reason"] = reason
    _save_cached_card(data_dir, cached)


def _structured_error(exc: BaseException) -> dict[str, Any]:
    """Translate an exception from a ``ProfileClient`` call into a
    JSON-serialisable tool-output dict.

    Preserves the directory's structured 4xx body (notably the
    ``{detail, code, scope}`` envelope returned for the
    ``persistence_opt_in`` 403) so MCP callers can distinguish a
    policy block from a transport failure. Transport failures
    (connect/timeout — most often an opted-out or unreachable
    network) become a ``{error, reason: "network_unreachable", hint}``
    envelope so agents get guidance instead of a raw ``ConnectError``.
    Falls back to ``{"error": "<class>: <repr>"}`` for anything else.
    """
    import httpx

    if isinstance(exc, httpx.HTTPStatusError):
        out: dict[str, Any] = {
            "error": f"directory returned HTTP {exc.response.status_code}",
            "status_code": exc.response.status_code,
        }
        try:
            body = exc.response.json()
        except (ValueError, json.JSONDecodeError):
            body = None
        if isinstance(body, dict):
            # FastAPI nests structured errors under "detail"; also
            # accept top-level shapes for forward compatibility.
            detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
            if isinstance(detail, dict):
                if "code" in detail:
                    out["code"] = detail["code"]
                if "scope" in detail:
                    out["scope"] = detail["scope"]
                if "detail" in detail and detail["detail"] != out["error"]:
                    out["detail"] = detail["detail"]
            elif isinstance(body.get("detail"), str):
                out["detail"] = body["detail"]
        return out
    if isinstance(exc, httpx.TransportError):
        # ConnectError / ConnectTimeout / ReadTimeout / network failures.
        # In practice the dominant cause is an opted-out or unreachable
        # network (offline / isolated), so surface that as guidance rather
        # than a raw "ConnectError: All connection attempts failed" the
        # caller has to decode. Distinct from a directory HTTP error above.
        return {
            "error": "could not reach the synpareia network",
            "reason": "network_unreachable",
            "hint": (
                "The directory could not be reached. If you're offline or "
                "network-isolated this is expected — set SYNPAREIA_NETWORK_URL='off' "
                "to work fully locally. Otherwise check connectivity and retry; a "
                "cold-started service can take a few seconds to answer its first request."
            ),
        }
    return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _event_time_memo_path(data_dir: Path) -> Path:
    return data_dir / "event_times.json"


def _stable_event_time(data_dir: Path, block_id: str, now: datetime) -> datetime:
    """Return the timestamp this ``block_id`` was FIRST sent with.

    Without this the tool has no idempotency whatsoever, while documenting that
    it does. ``created_at`` binds into the signing envelope, so the directory
    derives a different event hash from every call — a retry after a network
    timeout records a SECOND interaction on a live shared graph and re-applies
    the valence. A stable ``block_id`` alone does not help, because the
    timestamp beside it is what varies.

    So the first send for a given id wins and is remembered; every later send
    with that id rebuilds a byte-identical envelope and the directory's own
    event-level dedup fires. Memo failures are non-fatal — a lost memo degrades
    to the old behaviour (a new event), which is the same risk as not having the
    file, and is strictly better than refusing to record anything.
    """
    path = _event_time_memo_path(data_dir)
    try:
        memo: dict[str, str] = json.loads(path.read_text())
    except (OSError, ValueError):
        memo = {}

    if (seen := memo.get(block_id)) is not None:
        try:
            return datetime.fromisoformat(seen)
        except ValueError:
            pass  # corrupt entry — fall through and re-stamp

    memo[block_id] = now.isoformat()
    # Bounded: this is a retry aid, not an audit log. The directory's ledger is
    # the durable record; keeping every id forever would grow without limit for
    # no benefit once a send has succeeded.
    if len(memo) > _EVENT_MEMO_MAX:
        for stale in sorted(memo, key=lambda k: memo[k])[: len(memo) - _EVENT_MEMO_MAX]:
            del memo[stale]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(memo))
    except OSError:
        pass  # see docstring: non-fatal
    return now


def _consent_aware_error(exc: BaseException, *, counterparty_did: str) -> dict[str, Any]:
    """Turn an ingest failure into something an agent can act on.

    A 403 here is NOT a malformed request. It means the counterparty has not
    granted standing consent to be recorded on this channel, and the remedy is to
    ask them — not to retry, not to change the payload, not to escalate. Reported
    as a generic HTTP error it looks identical to a bug in the caller, and an
    agent would burn retries on something that will never succeed.

    Everything else falls through to the shared structured-error handler, which
    already distinguishes transport from status failures.
    """
    import httpx

    if not isinstance(exc, httpx.HTTPStatusError) or exc.response.status_code != _HTTP_FORBIDDEN:
        return _structured_error(exc)

    detail: dict[str, Any] = {}
    try:
        body = exc.response.json()
        detail = body.get("detail", body) if isinstance(body, dict) else {}
    except ValueError:
        detail = {}

    # Branch on the CODE, not on 403 alone. The service's access gate also
    # answers 403, with a bare {"detail": "Forbidden"} — under a legitimate
    # re-gate this handler would otherwise tell the agent that a named third
    # party had refused consent, which is a confident, specific, false statement
    # about someone else. A wrong explanation is worse than a generic one.
    if not (isinstance(detail, dict) and detail.get("code") == "consent_missing"):
        return _structured_error(exc)

    return {
        "error": (
            f"{counterparty_did} has not consented to being recorded on this "
            "channel, so the network refused the event."
        ),
        "code": "counterparty_has_not_consented",
        "counterparty_did": counterparty_did,
        # Echoed rather than paraphrased: the service names WHICH subject and
        # WHICH channel, and a multi-party event can fail on a party that is
        # not the one the caller was thinking about.
        "server_detail": detail,
        "remedy": (
            "Nothing is wrong with your request and retrying will not help. "
            "The counterparty must call set_reputation_consent themselves; "
            "consent cannot be granted on their behalf."
        ),
    }


DIRECTORY_NOT_CONFIGURED = (
    "directory operations require SYNPAREIA_NETWORK_URL to be configured. "
    "Set the env var to the synpareia service base URL (e.g. https://synpareia.example)"
)


def _need_directory(app: AppContext) -> str:
    """Return the directory base URL, or RAISE if it is not configured.

    Note the contract: this never returns ``None``. Callers that want a
    structured error instead of an exception must test
    ``app.config.network_url`` themselves — see ``_directory_error``.
    ``record_interaction`` used to write ``if (missing := _need_directory(app))
    is not None: return {"error": missing}``, which is always true on the
    success path, so the tool returned the directory URL in an ``error`` field
    and never made a request. No test called the tool, so 608 of them passed
    with it dead.
    """
    if not app.config.network_url:
        raise RuntimeError(DIRECTORY_NOT_CONFIGURED)
    return app.config.network_url


def _directory_error(app: AppContext) -> dict[str, Any] | None:
    """``None`` when the directory is configured, else the error payload.

    The return-``None``-on-success shape is what a ``walrus is not None``
    guard actually expects, so the two read the same way round.
    """
    if not app.config.network_url:
        return {"error": DIRECTORY_NOT_CONFIGURED}
    return None


def _build_profile_client(app: AppContext) -> ProfileClient:
    base_url = _need_directory(app)
    # The Trust MCP doesn't yet track a directory access token
    # separately from the witness one. The pre-launch deployment
    # carries the same X-Access-Token across both surfaces, so we
    # forward SYNPAREIA_WITNESS_TOKEN when set; agents that
    # configure only one of these get correct behaviour either
    # way (the directory rejects the request if the token is
    # wrong, and the existing 401 surfaces structurally).
    # Phase 2 may add a dedicated SYNPAREIA_DIRECTORY_TOKEN.
    return ProfileClient(base_url, access_token=app.config.witness_token or None)


def _make_card_shape(  # noqa: PLR0913 — many policy fields by design
    *,
    name: str,
    description: str | None,
    provider: str | None,
    url: str | None,
    version: str,
    skills: list[str],
    role_tag: str | None,
    first_contact_fee_credits: int | None,
    accepted_payment_rails: list[str],
    well_known_a2a_fields: list[str] | None,
    persistence_scope: list[str] | None,
    persistence_opted_in_at: str | None,
    accept_attestations: list[str] | None = None,
    accept_delivery: list[str] | None = None,
) -> dict[str, Any]:
    """Pack tool kwargs into a serialisable card shape.

    Returned dict is the on-disk cache + the input to
    ``_card_from_shape`` for re-signing on policy updates.
    """
    return {
        "a2a": {
            "name": name,
            "description": description,
            "provider": provider,
            "url": url,
            "version": version,
            "skills": list(skills),
        },
        "synpareia": {
            "role_tag": role_tag,
            "first_contact_fee_credits": first_contact_fee_credits,
            "accepted_payment_rails": list(accepted_payment_rails),
            "well_known_a2a_fields": (
                list(well_known_a2a_fields) if well_known_a2a_fields is not None else None
            ),
            "persistence_scope": (
                list(persistence_scope) if persistence_scope is not None else None
            ),
            "persistence_opted_in_at": persistence_opted_in_at,
            "accept_attestations": (
                list(accept_attestations) if accept_attestations is not None else None
            ),
            "accept_delivery": (list(accept_delivery) if accept_delivery is not None else None),
        },
    }


def _card_from_shape(profile, shape: dict[str, Any]):  # type: ignore[no-untyped-def]
    """Build an ``AgentCard`` from a cached shape + a Profile."""
    a2a = shape["a2a"]
    syn = shape["synpareia"]

    fcc = (
        FirstContactFee(credits=int(syn["first_contact_fee_credits"]))
        if syn.get("first_contact_fee_credits") is not None
        else None
    )
    persistence = None
    if syn.get("persistence_scope") is not None and syn.get("persistence_opted_in_at"):
        persistence = PersistenceOptIn(
            opted_in_at=syn["persistence_opted_in_at"],
            scope=list(syn["persistence_scope"]),
        )
    well_known = None
    if syn.get("well_known_a2a_fields") is not None:
        well_known = WellKnownPublicationPolicy(
            a2a_standard_fields=list(syn["well_known_a2a_fields"])
        )
    # A grant block is emitted only when at least one axis was actually set.
    # `None` on both means "the operator never spoke about consent", which must
    # serialise as NO block — an empty block would read as a deliberate
    # opt-out they never made.
    consent = None
    if syn.get("accept_attestations") is not None or syn.get("accept_delivery") is not None:
        consent = ReputationConsent(
            accept_attestations=list(syn.get("accept_attestations") or []),
            accept_delivery=list(syn.get("accept_delivery") or []),
        )

    return build_agent_card(
        profile,
        name=a2a.get("name", ""),
        description=a2a.get("description"),
        provider=a2a.get("provider"),
        url=a2a.get("url"),
        version=a2a.get("version", "1.0"),
        skills=a2a.get("skills") or [],
        role_tag=syn.get("role_tag"),
        first_contact_fee=fcc,
        persistence=persistence,
        accepted_payment_rails=syn.get("accepted_payment_rails") or [],
        well_known_publication=well_known,
        reputation_consent=consent,
    )


async def _publish_shape(app: AppContext, shape: dict[str, Any]) -> dict[str, Any]:
    """Sign + publish a card shape; cache it on success. Returns the
    directory's response (``{did, version, card_hash_hex}``)."""
    profile = app.profile_manager.profile
    if profile.private_key is None:
        msg = "no private key available; cannot sign card for publish"
        raise RuntimeError(msg)

    card = _card_from_shape(profile, shape)
    signed_bytes = card_canonical_bytes(card)
    signature = sign_agent_card(signed_bytes, profile.private_key)

    async with _build_profile_client(app) as client:
        result = await client.publish(
            did=profile.id,
            signed_bytes=signed_bytes,
            signature=signature,
            public_key=profile.public_key,
            private_key=profile.private_key,
        )

    _save_cached_card(app.config.data_dir, shape)
    return result


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def publish_profile(
    name: str,
    ctx: Context,
    *,
    description: str | None = None,
    provider: str | None = None,
    url: str | None = None,
    version: str = "1.0",
    skills: list[str] | None = None,
    role_tag: str | None = None,
    first_contact_fee_credits: int | None = None,
    accepted_payment_rails: list[str] | None = None,
    well_known_a2a_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Build, sign, and publish your agent card to the directory.

    Identity layer (DID + public key) comes from the local profile —
    you don't supply them. Other fields are operator-controlled.
    Returns ``{did, version, card_hash_hex}`` from the directory.

    Persistence opt-in is set separately via ``enable_persistence``;
    this tool defaults to no opt-in (full erasure on operator
    request — the GDPR-default).

    Requires ``SYNPAREIA_NETWORK_URL`` to be set.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]

    # Preserve any prior persistence opt-in so a bare publish_profile
    # call doesn't accidentally retract a valid opt-in commitment.
    cached = _load_cached_card(app.config.data_dir) or {}
    cached_syn = cached.get("synpareia") or {}

    shape = _make_card_shape(
        name=name,
        description=description,
        provider=provider,
        url=url,
        version=version,
        skills=skills or [],
        role_tag=role_tag,
        first_contact_fee_credits=first_contact_fee_credits,
        accepted_payment_rails=accepted_payment_rails or [],
        well_known_a2a_fields=well_known_a2a_fields,
        persistence_scope=cached_syn.get("persistence_scope"),
        persistence_opted_in_at=cached_syn.get("persistence_opted_in_at"),
        # Carried forward for the same reason as persistence, and more sharply:
        # silently dropping these would RETRACT a consent grant counterparties
        # are relying on to record events about this agent, turning their next
        # write into a 403 with no visible cause. Consent is changed by
        # `set_reputation_consent`, never as a side effect of republishing a card.
        accept_attestations=cached_syn.get("accept_attestations"),
        accept_delivery=cached_syn.get("accept_delivery"),
    )

    try:
        return await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001 — surface errors as structured tool output
        return _structured_error(exc)


@mcp.tool()
async def get_profile(did: str, ctx: Context) -> dict[str, Any]:
    """Fetch a counterparty's published agent card by DID.

    Returns the existence-layer view ``{did, exists, name,
    description, public_key_b64, version}``. Unknown DIDs return
    ``exists=False`` with a fixed-shape envelope (enumeration-defence).
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    try:
        async with _build_profile_client(app) as client:
            return await client.get_existence(did=did)
    except Exception as exc:  # noqa: BLE001
        return _structured_error(exc)


@mcp.tool()
async def update_profile_policy(
    ctx: Context,
    *,
    name: str | None = None,
    description: str | None = None,
    provider: str | None = None,
    url: str | None = None,
    skills: list[str] | None = None,
    role_tag: str | None = None,
    first_contact_fee_credits: int | None = None,
    accepted_payment_rails: list[str] | None = None,
    well_known_a2a_fields: list[str] | None = None,
) -> dict[str, Any]:
    """Update one or more card fields and re-publish.

    Loads the last-published card from disk, applies the supplied
    overrides, signs, publishes. Fields not supplied are preserved.
    Persistence opt-in is preserved across updates — withdraw it
    explicitly via ``disable_persistence``.

    Returns ``{did, version, card_hash_hex}`` of the new version.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    cached = _load_cached_card(app.config.data_dir)
    if cached is None:
        return {
            "error": (
                "no published card on disk — call publish_profile() first to "
                "establish the operator's baseline"
            )
        }

    a2a = dict(cached["a2a"])
    syn = dict(cached["synpareia"])
    if name is not None:
        a2a["name"] = name
    if description is not None:
        a2a["description"] = description
    if provider is not None:
        a2a["provider"] = provider
    if url is not None:
        a2a["url"] = url
    if skills is not None:
        a2a["skills"] = list(skills)
    if role_tag is not None:
        syn["role_tag"] = role_tag
    if first_contact_fee_credits is not None:
        syn["first_contact_fee_credits"] = first_contact_fee_credits
    if accepted_payment_rails is not None:
        syn["accepted_payment_rails"] = list(accepted_payment_rails)
    if well_known_a2a_fields is not None:
        syn["well_known_a2a_fields"] = list(well_known_a2a_fields)

    shape = {"a2a": a2a, "synpareia": syn}
    try:
        return await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001
        return _structured_error(exc)


@mcp.tool()
async def record_interaction(
    counterparty_did: str,
    ctx: Context,
    *,
    magnitude: float = 0.5,
    valence: float | None = None,
    shareable: bool = False,
    event_id: str | None = None,
) -> dict[str, Any]:
    """Record that you dealt with another agent, and optionally how it went.

    This writes to the shared network, not your local journal. Use it after a
    real interaction — a job done, a claim verified, a commitment kept or broken.

    **This tool records no content.** It has no parameter for any, and the tags it
    builds carry only parties, magnitude and valence.

    That now holds at the network level too, not just for this tool. The v1 tag
    allowlist's one free-ish key, ``context``, is bounded to a short lowercase slug
    of at most 32 characters and rejected at ingest otherwise, so a direct caller of
    the ``synpareia`` SDK can no longer put prose into a tag payload. (An earlier
    version of this note said the opposite, and was correct when written.)

    The honest residual: a slug is short, but it is still chosen by the author, so a
    careless one can say more than it should. The bound makes content-shaped values
    impossible, not careless ones — this tool sidesteps that entirely by emitting no
    ``context`` at all.

    - ``magnitude`` (0..1) — how substantial the dealing was. Drives how much this
      edge counts, not which way.
    - ``valence`` (-1..1) — how it went. Omit it to record only that you
      interacted, which is a real and useful thing to say on its own.
    - ``shareable`` — your half of a two-sided decision. False (default) means
      the record stays visible to the two of you. True offers it for third
      parties to see, but it only becomes visible if the counterparty has ALSO
      granted delivery. Neither of you can publish the other unilaterally.
    - ``event_id`` — supply your own to make retries safe. The same id records
      once; a new id records again. Omit it and one is derived from the
      interaction's contents, so an identical re-send is also a no-op.

    **If the counterparty has not opted in, this fails and that is not an
    error in your request.** Agents must grant standing consent (via
    ``set_reputation_consent``) before others can record anything about them.
    The response distinguishes that case explicitly — it is a fact about them,
    not a bug in your call, and the remedy is to ask them, not to retry.

    Requires ``SYNPAREIA_NETWORK_URL`` and a published identity.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    if (unconfigured := _directory_error(app)) is not None:
        return unconfigured

    from synpareia.hash import jcs_canonicalize
    from synpareia.topology import build_interaction_tags, build_topology_event

    profile = app.profile_manager.profile
    if profile.private_key is None:
        return {"error": "local identity has no private key — cannot sign an event"}
    if counterparty_did == profile.id:
        return {
            "error": "cannot record an interaction with yourself",
            "code": "self_interaction",
        }

    try:
        tags = build_interaction_tags(
            parties=[profile.id, counterparty_did],
            magnitude=magnitude,
            valence=valence,
        )
    except ValueError as exc:
        return {"error": str(exc), "code": "invalid_arguments"}

    # The default id is derived from the interaction's CONTENT only — no clock.
    # Mixing the current time in (an earlier version used the date) makes the id
    # itself drift across a midnight boundary, so the one thing meant to make a
    # retry safe becomes another source of divergence.
    block_id = event_id or "evt_" + hashlib.sha256(jcs_canonicalize(tags)).hexdigest()[:24]
    created_at = _stable_event_time(app.config.data_dir, block_id, datetime.now(UTC))

    envelope = build_topology_event(
        author_did=profile.id,
        author_private_key=profile.private_key,
        tags=tags,
        created_at=created_at,
        block_id=block_id,
        deliverable=shareable,
    )

    try:
        async with _build_profile_client(app) as client:
            result = await client.submit_event(envelope=envelope, private_key=profile.private_key)
    except Exception as exc:  # noqa: BLE001 — surface errors as structured tool output
        return _consent_aware_error(exc, counterparty_did=counterparty_did)

    return {
        **result,
        "counterparty_did": counterparty_did,
        # `idempotent` is easy to skim past, and skimming past it means treating a
        # retry as a second interaction. Say what happened in words.
        "effect": (
            "already recorded — this is the same event, not a second interaction"
            if result.get("idempotent")
            else "recorded"
        ),
        "shared": (
            "offered for third parties to see, if the counterparty has also granted delivery"
            if shareable
            else "visible only to the two of you"
        ),
    }


@mcp.tool()
async def network_reputation(counterparty_did: str, ctx: Context) -> dict[str, Any]:
    """Ask the network what it can tell **you** about another agent.

    The other half of ``record_interaction``. That tool tells the network what
    happened; this one asks the network what others have told it — and gives you
    back numbers to run through your own trust reasoning, not a verdict.

    You get two, and they are read together:

    - ``magnitude`` (-1..1) — how the reports lean. Negative is poor.
    - ``confidence`` (0..) — how much dealing backs that lean. It is an
      accumulated weight, **not** a probability: 0.5 does not mean "50% sure",
      and there is no ceiling.

    **Check ``confidence`` first.** At ``0.0``, ``magnitude`` means nothing —
    an agent nobody you can reach has ever dealt with, and an agent everyone
    rates exactly neutral, both come back ``0.0``. Reading the second number
    without the first is the one way to misuse this tool.

    **The answer is yours specifically.** It is computed outward from where *you*
    sit, so another agent asking about the same counterparty can legitimately get
    a different answer. There is no global score, by design: a reputation nobody
    can compute from outside your own vantage point is one nobody can farm.

    You get no names. Not who reported, not through whom it reached you, not how
    many hops away. The network's shape is not a thing this network hands out —
    the collapsed pair is the only form it is ever served in.

    **Advisory.** Nothing here ranks, thresholds or decides. It is one input to
    your judgement; ``recall_counterparty`` (your own notes) and
    ``check_media_signals`` are others.

    An unknown agent comes back ``confidence: 0.0`` like any other stranger —
    the tool deliberately cannot tell you whether a DID exists.

    Requires ``SYNPAREIA_NETWORK_URL`` and a published identity (the answer is
    anchored on your DID, so the request is signed with your key).
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    if (unconfigured := _directory_error(app)) is not None:
        return unconfigured

    profile = app.profile_manager.profile
    if profile.private_key is None:
        return {"error": "local identity has no private key — cannot sign a reputation read"}
    if counterparty_did == profile.id:
        # Not merely unsupported: the anchored walk runs outward from you, so
        # "what does the network think of me" is a different question with a
        # different answer, not a degenerate case of this one.
        return {
            "error": "cannot ask the network about yourself from your own vantage point",
            "code": "self_reputation",
        }

    try:
        async with _build_profile_client(app) as client:
            result = await client.get_reputation(
                subject_did=counterparty_did,
                asker_did=profile.id,
                private_key=profile.private_key,
            )
    except Exception as exc:  # noqa: BLE001 — surface errors as structured tool output
        return _structured_error(exc)

    confidence = float(result.get("confidence", 0.0))
    return {
        **result,
        # Say in words what the numbers mean together, because the failure mode
        # is reading `magnitude` alone. An agent that skims gets the same warning
        # as one that reads the schema.
        "reading": (
            "nothing visible to you backs this agent — ignore `magnitude` entirely; "
            "this is not a bad report, it is no report"
            if confidence == 0.0
            else (
                f"backed by {confidence:.3g} of weighted dealing, as reachable from you. "
                "Advisory only — run it through your own trust reasoning"
            )
        ),
    }


@mcp.tool()
async def set_reputation_consent(
    ctx: Context,
    *,
    accept_attestations: list[str] | None = None,
    accept_delivery: list[str] | None = None,
) -> dict[str, Any]:
    """Declare which channels others may record — and serve — events about you on.

    **Without this, you are un-recordable.** The network refuses any event whose
    data-subject has not consented: a counterparty trying to attest something
    about you gets a hard rejection, not a quiet skip. Publishing a card is not
    consent; this is.

    Two independent axes, because they are two different decisions:

    - ``accept_attestations`` — *may-record*. Channels others may record events
      about you on without your per-event signature. Nothing lands without this.
    - ``accept_delivery`` — *may-serve*. Channels on which events about you may be
      counted into a stranger's reputation view of you. Without it, accepted
      events stay visible only to the parties involved.

    Granting record-without-deliver is a real and useful middle state:
    counterparties build a private picture, strangers read nothing. Granting
    deliver-without-record does nothing — there is nothing to serve.

    Common channels: ``"interaction"`` (you and another agent dealt with each
    other) and ``"valence"`` (their assessment of how it went). Names are
    free-form; unknown ones are simply never matched.

    Withdrawal is **prospective**: removing a channel stops future un-co-signed
    recording, and does not erase what was already recorded under a valid grant.
    Use the erasure tools for that.

    Omitting an argument leaves that axis unchanged. Pass ``[]`` to revoke one
    explicitly — the two are different requests and are treated differently.

    Requires a previously-published card on disk.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    cached = _load_cached_card(app.config.data_dir)
    if cached is None:
        return {
            "error": (
                "no published card on disk — call publish_profile() first, then set consent on it"
            )
        }

    syn = dict(cached["synpareia"])
    # None = "don't touch this axis"; [] = "revoke this axis". Collapsing the two
    # would make an omitted argument silently revoke a standing grant, which is
    # the one mistake this tool must not make.
    if accept_attestations is not None:
        syn["accept_attestations"] = list(accept_attestations)
    if accept_delivery is not None:
        syn["accept_delivery"] = list(accept_delivery)
    shape = {"a2a": dict(cached["a2a"]), "synpareia": syn}

    try:
        published = await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001 — surface errors as structured tool output
        return _structured_error(exc)

    granted_record = syn.get("accept_attestations") or []
    granted_deliver = syn.get("accept_delivery") or []
    return {
        **published,
        "accept_attestations": granted_record,
        "accept_delivery": granted_deliver,
        # State the CONSEQUENCE, not just the field values. An agent reading
        # `{"accept_attestations": []}` has to know the whole consent model to
        # realise it means "nobody can attest anything about me".
        "effect": (
            "no one can record events about you without your per-event signature"
            if not granted_record
            else (
                f"others may record events about you on {sorted(granted_record)}; "
                + (
                    "those events stay visible only to the parties involved (no may-deliver grant)"
                    if not granted_deliver
                    else f"and may be served to third parties on {sorted(granted_deliver)}"
                )
            )
        ),
    }


@mcp.tool()
async def enable_persistence(scope: list[str], ctx: Context) -> dict[str, Any]:
    """Opt into non-erasure persistence and re-publish.

    ``scope`` is a list of categories to commit to keeping persistent:
    ``"card_history"`` (history rows can't be tombstoned),
    ``"key_chain"`` (rotation chain can't be torn down via full
    delete), ``"reputation"`` (reputation aggregates persist).

    The opt-in is recorded with the current timestamp and re-published
    in the next card. Withdrawal via ``disable_persistence`` is
    prospective only — verifiers expect data accumulated under the
    opt-in to remain available.

    Requires a previously-published card on disk.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    cached = _load_cached_card(app.config.data_dir)
    if cached is None:
        return {
            "error": (
                "no published card on disk — call publish_profile() first before "
                "opting into persistence"
            )
        }

    valid_scopes = {"card_history", "key_chain", "reputation"}
    invalid = [s for s in scope if s not in valid_scopes]
    if invalid:
        valid_sorted = sorted(valid_scopes)
        return {
            "error": (f"invalid scope values: {invalid!r}; expected subset of {valid_sorted!r}")
        }

    a2a = dict(cached["a2a"])
    syn = dict(cached["synpareia"])
    syn["persistence_scope"] = list(scope)
    syn["persistence_opted_in_at"] = datetime.now(UTC).isoformat()
    shape = {"a2a": a2a, "synpareia": syn}

    try:
        return await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001
        return _structured_error(exc)


@mcp.tool()
async def disable_persistence(ctx: Context) -> dict[str, Any]:
    """Withdraw the persistence opt-in and re-publish.

    Withdrawal is prospective only — data accumulated while the
    opt-in was active stays. After withdrawal, future erasure calls
    succeed. Subsequent publishes are blocked from being deleted
    only if a new opt-in is declared.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    cached = _load_cached_card(app.config.data_dir)
    if cached is None:
        return {"error": "no published card on disk"}

    a2a = dict(cached["a2a"])
    syn = dict(cached["synpareia"])
    syn["persistence_scope"] = None
    syn["persistence_opted_in_at"] = None
    shape = {"a2a": a2a, "synpareia": syn}

    try:
        return await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001
        return _structured_error(exc)


@mcp.tool()
async def delete_profile_history(
    version: int, ctx: Context, *, reason: str | None = None
) -> dict[str, Any]:
    """Tombstone a single card-version row in the operator's history.

    Returns ``{ok: True}`` on success or a structured error. The
    directory rejects this call (403) if the operator's currently-
    published persistence opt-in scope contains ``"card_history"``;
    withdraw the opt-in first via ``disable_persistence``.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    profile = app.profile_manager.profile
    if profile.private_key is None:
        return {"error": "no private key available; cannot authenticate erasure"}

    try:
        async with _build_profile_client(app) as client:
            await client.delete_history_version(
                did=profile.id,
                version=version,
                public_key=profile.public_key,
                private_key=profile.private_key,
                reason=reason,
            )
        return {"ok": True, "did": profile.id, "version": version}
    except Exception as exc:  # noqa: BLE001 — translate to structured tool output
        return _structured_error(exc)


@mcp.tool()
async def delete_profile(ctx: Context, *, reason: str | None = None) -> dict[str, Any]:
    """Cascade-tombstone every history row for the operator's profile.

    Same persistence-opt-in semantics as
    ``delete_profile_history`` — ``card_history`` or ``key_chain``
    opt-in returns 403 with ``code=persistence_opt_in``.

    Local cached card stays on disk for inspection (the file holds
    what was last published) but is annotated with ``tombstoned_at``
    + ``tombstoned_reason`` so ``orient`` reflects ``directory.published
    == False`` after this call. Operators wanting a fully-clean
    slate can remove ``published_card.json`` manually.
    """
    if not HAS_PROFILE_SDK:
        return _profile_sdk_unavailable()

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    profile = app.profile_manager.profile
    if profile.private_key is None:
        return {"error": "no private key available; cannot authenticate erasure"}

    try:
        async with _build_profile_client(app) as client:
            await client.delete_profile(
                did=profile.id,
                public_key=profile.public_key,
                private_key=profile.private_key,
                reason=reason,
            )
        _mark_cached_card_tombstoned(app.config.data_dir, reason=reason)
        return {"ok": True, "did": profile.id}
    except Exception as exc:  # noqa: BLE001 — translate to structured tool output
        return _structured_error(exc)
