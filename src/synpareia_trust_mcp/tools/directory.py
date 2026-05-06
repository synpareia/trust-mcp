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
        WellKnownPublicationPolicy,
        build_agent_card,
        card_canonical_bytes,
        sign_agent_card,
    )

    HAS_PROFILE_SDK = True
except ImportError:  # pragma: no cover — SDK 0.5.0 not installed
    HAS_PROFILE_SDK = False

if TYPE_CHECKING:
    from synpareia_trust_mcp.app import AppContext

__all__ = [
    "delete_profile",
    "delete_profile_history",
    "disable_persistence",
    "enable_persistence",
    "get_profile",
    "publish_profile",
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
    policy block from a transport failure. Falls back to
    ``{"error": "<class>: <repr>"}`` for non-HTTP errors.
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
    return {"error": f"{type(exc).__name__}: {exc}"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _need_directory(app: AppContext) -> str:
    if not app.config.network_url:
        msg = (
            "directory operations require SYNPAREIA_NETWORK_URL to be configured. "
            "Set the env var to the synpareia service base URL (e.g. https://synpareia.example)"
        )
        raise RuntimeError(msg)
    return app.config.network_url


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
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
    )

    try:
        return await _publish_shape(app, shape)
    except Exception as exc:  # noqa: BLE001 — surface errors as structured tool output
        return {"error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def get_profile(did: str, ctx: Context) -> dict[str, Any]:
    """Fetch a counterparty's published agent card by DID.

    Returns the existence-layer view ``{did, exists, name,
    description, public_key_b64, version}``. Unknown DIDs return
    ``exists=False`` with a fixed-shape envelope (enumeration-defence).
    """
    if not HAS_PROFILE_SDK:
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

    app: AppContext = ctx.request_context.lifespan_context  # type: ignore[assignment]
    try:
        async with _build_profile_client(app) as client:
            return await client.get_existence(did=did)
    except Exception as exc:  # noqa: BLE001
        return {"error": f"{type(exc).__name__}: {exc}"}


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
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
        return {"error": f"{type(exc).__name__}: {exc}"}


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
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
        return {"error": f"{type(exc).__name__}: {exc}"}


@mcp.tool()
async def disable_persistence(ctx: Context) -> dict[str, Any]:
    """Withdraw the persistence opt-in and re-publish.

    Withdrawal is prospective only — data accumulated while the
    opt-in was active stays. After withdrawal, future erasure calls
    succeed. Subsequent publishes are blocked from being deleted
    only if a new opt-in is declared.
    """
    if not HAS_PROFILE_SDK:
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
        return {"error": f"{type(exc).__name__}: {exc}"}


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
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
        return {"error": "synpareia.profile not available — upgrade SDK to 0.5.0+"}

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
