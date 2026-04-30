"""Trust provider adapters for multi-source agent evaluation.

Each provider is a thin adapter that queries a specific reputation source
and returns structured signals. Providers return raw signals; the caller
(evaluate_agent tool) assembles them into a unified report.

IMPORTANT: Providers return structured numeric/categorical data only.
Never return raw text content from external sources — prompt injection risk.
Fields arriving from external providers are type-validated and length-capped
(see _safe_int / _safe_bool / _safe_str) before they are surfaced to callers.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

MAX_IDENTIFIER_LEN = 256
MAX_PROVIDER_RESPONSE_BYTES = 1_000_000
MAX_DATE_STR_LEN = 40

# ISO-8601 date / datetime charset: digits, dashes, colons, T, Z, ., +, space.
# This is intentionally strict — `created_at` is one of the fields the
# provider can easily stuff prompt-injection into (ADV-011), so only a
# date-shaped string is allowed through.
_ISO_DATE_PATTERN = re.compile(r"^[0-9T\-:.+Z ]{1,40}$")


@dataclass
class TrustSignal:
    """A single trust signal from a provider."""

    provider: str
    signal_type: str
    value: Any
    confidence: str  # "low", "medium", "high"
    detail: str


def _validate_identifier(identifier: str) -> str:
    """Validate and URL-quote an identifier for safe path interpolation.

    Rejects control characters, caps length, and percent-encodes every
    non-alphanumeric character (safe='') so that path-traversal attempts
    like `../../admin` or `..%2F..%2Fadmin` cannot escape the intended
    `/agents/{identifier}` route.
    """
    if not isinstance(identifier, str) or not identifier:
        msg = "identifier must be a non-empty string"
        raise ValueError(msg)
    if len(identifier) > MAX_IDENTIFIER_LEN:
        msg = f"identifier too long (max {MAX_IDENTIFIER_LEN})"
        raise ValueError(msg)
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in identifier):
        msg = "identifier contains control characters"
        raise ValueError(msg)
    return quote(identifier, safe="")


def _safe_int(val: Any, default: int = 0) -> int:
    """Coerce to int; fall back to default if not a real int.

    Booleans are rejected (isinstance(True, int) is True but they are not
    meaningful integers for karma/posts/etc.). Strings, dicts, lists and
    None all collapse to default.
    """
    if isinstance(val, bool):
        return default
    if isinstance(val, int):
        return val
    if isinstance(val, float) and val == val:  # reject NaN
        return int(val)
    return default


def _safe_bool(val: Any, default: bool = False) -> bool:
    """Coerce to bool only if the incoming value is literally a bool."""
    if isinstance(val, bool):
        return val
    return default


def _safe_iso_date(val: Any, default: str | None = None) -> str | None:
    """Return val only if it is an ISO-8601-ish date string.

    Strict allowlist of digits + date punctuation prevents prompt-injection
    payloads from reaching the caller under the guise of `created_at`
    (ADV-011).
    """
    if not isinstance(val, str):
        return default
    if not _ISO_DATE_PATTERN.match(val):
        return default
    return val


def _safe_number(val: Any) -> int | float | None:
    """Return val only if it's a finite int or float (not bool, NaN, or ±inf).

    Rejecting ±inf (ADV-054, pentest 2026-04-30): a hostile or compromised
    Tier-2/Tier-3 provider could otherwise return `Infinity` for a
    `reputation_score` or `average_rating` and the value would flow
    through to the caller as a high-confidence numeric trust signal.
    `math.isfinite` rejects both NaN and ±inf.
    """
    if isinstance(val, bool):
        return None
    if isinstance(val, int):
        return val
    if isinstance(val, float) and math.isfinite(val):
        return val
    return None


def _make_http_client(timeout: float = 10.0) -> httpx.AsyncClient:
    """Factory for the HTTP client used by provider queries.

    Kept as a module-level indirection so tests can monkeypatch it to
    route requests into in-process stubs (ASGI transport) instead of
    hitting real external services.
    """
    return httpx.AsyncClient(timeout=timeout)


async def _fetch_json(
    client: httpx.AsyncClient, url: str, **kwargs: Any
) -> tuple[int, dict | None]:
    """GET a URL and parse JSON, aborting if the response exceeds the size cap.

    Returns (status_code, data). data is None when status is 404 or when the
    body was too large / not decodable JSON — callers interpret those cases.
    Raises httpx.HTTPError on network / transport failures so the provider
    function can fall back to its "unavailable" signal.
    """
    import json

    async with client.stream("GET", url, **kwargs) as resp:
        if resp.status_code == 404:
            return resp.status_code, None
        resp.raise_for_status()
        body = bytearray()
        async for chunk in resp.aiter_bytes():
            body.extend(chunk)
            if len(body) > MAX_PROVIDER_RESPONSE_BYTES:
                raise httpx.HTTPError("response too large")
        try:
            parsed = json.loads(bytes(body))
        except json.JSONDecodeError as e:
            raise httpx.HTTPError(f"invalid JSON: {e.msg}") from e
        if not isinstance(parsed, dict):
            raise httpx.HTTPError("response is not a JSON object")
        return resp.status_code, parsed


async def query_moltbook(identifier: str, api_url: str) -> list[TrustSignal]:
    """Query Moltbook's verify-identity API for agent reputation.

    Returns structured data only: karma, post counts, follower count,
    account age, claimed status. Never raw content (injection risk).
    """
    try:
        safe_id = _validate_identifier(identifier)
    except ValueError as e:
        return [
            TrustSignal(
                provider="moltbook",
                signal_type="error",
                value="invalid_identifier",
                confidence="low",
                detail=str(e),
            )
        ]

    url = f"{api_url.rstrip('/')}/api/v1/agents/{safe_id}"
    signals: list[TrustSignal] = []

    try:
        async with _make_http_client() as client:
            status, data = await _fetch_json(client, url)
            if status == 404 or data is None:
                return [
                    TrustSignal(
                        provider="moltbook",
                        signal_type="lookup",
                        value="not_found",
                        confidence="high",
                        detail=f"No Moltbook agent found for '{identifier}'.",
                    )
                ]
    except httpx.HTTPError as e:
        return [
            TrustSignal(
                provider="moltbook",
                signal_type="error",
                value="unavailable",
                confidence="low",
                detail=f"Moltbook API error: {type(e).__name__}",
            )
        ]

    # Extract ONLY structured numeric/categorical fields, type-validated.
    signals.append(
        TrustSignal(
            provider="moltbook",
            signal_type="karma",
            value=_safe_int(data.get("karma"), 0),
            confidence="medium",
            detail="Moltbook karma score (social reputation, gameable).",
        )
    )
    signals.append(
        TrustSignal(
            provider="moltbook",
            signal_type="activity",
            value={
                "posts": _safe_int(data.get("posts"), 0),
                "comments": _safe_int(data.get("comments"), 0),
                "follower_count": _safe_int(data.get("follower_count"), 0),
            },
            confidence="medium",
            detail="Activity metrics from Moltbook.",
        )
    )
    signals.append(
        TrustSignal(
            provider="moltbook",
            signal_type="account_status",
            value={
                "is_claimed": _safe_bool(data.get("is_claimed"), False),
                "created_at": _safe_iso_date(data.get("created_at")),
            },
            confidence="medium",
            detail="Account claimed status and age.",
        )
    )

    return signals


async def query_moltrust(identifier: str, api_key: str) -> list[TrustSignal]:
    """Query MolTrust API for W3C DID-based reputation.

    Returns structured reputation scores only.
    """
    try:
        safe_id = _validate_identifier(identifier)
    except ValueError as e:
        return [
            TrustSignal(
                provider="moltrust",
                signal_type="error",
                value="invalid_identifier",
                confidence="low",
                detail=str(e),
            )
        ]

    signals: list[TrustSignal] = []

    try:
        async with _make_http_client() as client:
            status, data = await _fetch_json(
                client,
                f"https://api.moltrust.ch/v1/agents/{safe_id}/reputation",
                headers={"Authorization": f"Bearer {api_key}"},
            )
            if status == 404 or data is None:
                return [
                    TrustSignal(
                        provider="moltrust",
                        signal_type="lookup",
                        value="not_found",
                        confidence="high",
                        detail=f"No MolTrust record for '{identifier}'.",
                    )
                ]
    except httpx.HTTPError as e:
        return [
            TrustSignal(
                provider="moltrust",
                signal_type="error",
                value="unavailable",
                confidence="low",
                detail=f"MolTrust API error: {type(e).__name__}",
            )
        ]

    signals.append(
        TrustSignal(
            provider="moltrust",
            signal_type="reputation_score",
            value=_safe_number(data.get("reputation_score")),
            confidence="medium",
            detail="MolTrust W3C DID-based reputation score.",
        )
    )
    if "ratings_count" in data:
        signals.append(
            TrustSignal(
                provider="moltrust",
                signal_type="ratings",
                value={
                    "count": _safe_int(data.get("ratings_count"), 0),
                    "average": _safe_number(data.get("average_rating")),
                },
                confidence="medium",
                detail="Peer ratings from MolTrust network.",
            )
        )

    return signals


async def query_synpareia_network(identifier: str, network_url: str) -> list[TrustSignal]:
    """Query the synpareia network for verified interaction history.

    Returns the highest-confidence signals: based on cryptographic proof,
    not self-reported data.
    """
    try:
        safe_id = _validate_identifier(identifier)
    except ValueError as e:
        return [
            TrustSignal(
                provider="synpareia",
                signal_type="error",
                value="invalid_identifier",
                confidence="low",
                detail=str(e),
            )
        ]

    signals: list[TrustSignal] = []

    try:
        async with _make_http_client() as client:
            status, data = await _fetch_json(
                client,
                f"{network_url.rstrip('/')}/api/v1/agents/{safe_id}/reputation",
            )
            if status == 404 or data is None:
                return [
                    TrustSignal(
                        provider="synpareia",
                        signal_type="lookup",
                        value="not_found",
                        confidence="high",
                        detail=f"No synpareia network record for '{identifier}'.",
                    )
                ]
    except httpx.HTTPError as e:
        return [
            TrustSignal(
                provider="synpareia",
                signal_type="error",
                value="unavailable",
                confidence="low",
                detail=f"Synpareia network error: {type(e).__name__}",
            )
        ]

    signals.append(
        TrustSignal(
            provider="synpareia",
            signal_type="verified_interactions",
            value={
                "count": _safe_int(data.get("interaction_count"), 0),
                "average_quality": _safe_number(data.get("average_quality")),
                "proof_of_thought_pass_rate": _safe_number(data.get("pot_pass_rate")),
            },
            confidence="high",
            detail="Verified interaction history with cryptographic proof.",
        )
    )
    if "reputation_score" in data:
        signals.append(
            TrustSignal(
                provider="synpareia",
                signal_type="reputation_score",
                value=_safe_number(data.get("reputation_score")),
                confidence="high",
                detail="Synpareia network reputation score (EigenTrust-based).",
            )
        )

    return signals
