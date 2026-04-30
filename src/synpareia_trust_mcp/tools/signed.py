"""Tier-4 encode_signed / decode_signed -- per-message integration primitives.

Per the four-tier reputation-evidence taxonomy, Tier 4 is full integration:
both parties speak the synpareia protocol and every message becomes a
verifiable artifact. v1 ships these primitives so an agent can wrap
content manually before sending through any transport (Slack, Discord,
email, HTTP body, etc.) and unwrap incoming content after reading.

Envelope format (self-contained; no network lookup needed to verify):

    synpareia:v1:<base64url(json({
        payload: {
            v: 1,
            content: str,
            signer_did: str,     # did:synpareia:<SHA-256(pk) hex>
            public_key_b64: str, # Ed25519 public key, base64
            signed_at: str,      # ISO-8601 UTC
        },
        signature_b64: str,      # Ed25519 signature of jcs(payload)
    }))>

decode_signed returns a structured dict rather than raising. A non-
synpareia input passes through with `synpareia_validated=false` so
wrapper MCPs can route transparent content through the same call site.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

from mcp.server.fastmcp import Context
from synpareia import from_public_key
from synpareia.hash import jcs_canonicalize
from synpareia.signing import sign as ed25519_sign
from synpareia.signing import verify as ed25519_verify

from synpareia_trust_mcp.app import AppContext, mcp

# Mirrors `providers._ISO_DATE_PATTERN` — see ADV-052 (pentest 2026-04-30).
# Without this, a signer could put arbitrary text (control chars, multiline
# prompt-injection payloads) in `signed_at`, get a cryptographically valid
# envelope, and the verifier would still return `valid: True` with the free
# text reflected back to the calling agent. The Tier-2/3 pipeline already
# enforces the same shape on `created_at` via `providers._safe_iso_date`.
_ISO_DATE_PATTERN = re.compile(r"^[0-9T\-:.+Z ]{1,40}$")

SYNPAREIA_V1_PREFIX = "synpareia:v1:"
_MAX_CONTENT_BYTES = 64 * 1024
_MAX_ENVELOPE_BYTES = 128 * 1024


@mcp.tool()
def encode_signed(content: str, ctx: Context) -> dict[str, Any]:
    """Wrap `content` as a signed synpareia envelope (Tier 4).

    Produces a self-contained string that any recipient -- even one that
    has never seen your DID before -- can verify with `decode_signed` and
    the SDK. Drop the resulting string into any transport payload (Slack
    message body, email, HTTP response, MCP tool result) and the signature
    rides along.

    Returns `reputation_tier=4`, `assurance_tier=1` (self-attested; upgrade
    to Tier 3 by witnessing via `make_claim` with `assurance='witnessed'`).
    """
    if not isinstance(content, str):
        return {"error": "content must be a string"}
    if not content:
        return {"error": "content must not be empty"}
    encoded_content = content.encode("utf-8")
    if len(encoded_content) > _MAX_CONTENT_BYTES:
        return {"error": f"content too long (max {_MAX_CONTENT_BYTES} bytes)"}

    app: AppContext = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile
    if profile.private_key is None:
        return {"error": "profile has no private key; cannot sign"}

    payload = {
        "v": 1,
        "content": content,
        "signer_did": profile.id,
        "public_key_b64": base64.b64encode(profile.public_key).decode(),
        "signed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
    }
    canonical = jcs_canonicalize(payload)
    signature = ed25519_sign(profile.private_key, canonical)

    envelope = {
        "payload": payload,
        "signature_b64": base64.b64encode(signature).decode(),
    }
    envelope_bytes = json.dumps(envelope).encode("utf-8")
    encoded = SYNPAREIA_V1_PREFIX + base64.urlsafe_b64encode(envelope_bytes).decode()

    return {
        "ok": True,
        "encoded": encoded,
        "signer_did": profile.id,
        "signed_at": payload["signed_at"],
        "reputation_tier": 4,
        "assurance_tier": 1,
        "hint": (
            "Drop the `encoded` string into any transport payload. Recipients "
            "call decode_signed to verify. For witnessed assurance (Tier 3), "
            "use make_claim with assurance='witnessed' instead."
        ),
    }


@mcp.tool()
def decode_signed(encoded: str, ctx: Context) -> dict[str, Any]:  # noqa: ARG001
    """Unwrap a synpareia-signed envelope (Tier 4).

    Returns a structured dict -- never raises. Shape:
        {content, signer_did, valid, verified_at, synpareia_validated}

    `synpareia_validated=False` means the input was not a synpareia
    envelope; the content passes through unchanged so transparent wrappers
    can route untouched messages the same way. `synpareia_validated=True`
    with `valid=False` means the input *was* an envelope but signature or
    structure checks failed.
    """
    if not isinstance(encoded, str):
        return {"error": "encoded must be a string"}
    if len(encoded.encode("utf-8")) > _MAX_ENVELOPE_BYTES:
        return {"error": f"envelope too long (max {_MAX_ENVELOPE_BYTES} bytes)"}

    # Pass-through for anything that doesn't look like our envelope.
    if not encoded.startswith(SYNPAREIA_V1_PREFIX):
        return {
            "content": encoded,
            "signer_did": None,
            "valid": False,
            "verified_at": None,
            "synpareia_validated": False,
        }

    body = encoded[len(SYNPAREIA_V1_PREFIX) :]
    try:
        body_bytes = body.encode("ascii")
    except UnicodeEncodeError:
        return _invalid("non-ascii bytes in envelope body")
    padding = (-len(body_bytes)) % 4
    try:
        envelope_bytes = base64.b64decode(
            body_bytes + b"=" * padding,
            altchars=b"-_",
            validate=True,
        )
    except (binascii.Error, ValueError):
        return _invalid("malformed base64")

    try:
        envelope = json.loads(envelope_bytes)
    except json.JSONDecodeError:
        return _invalid("malformed JSON")

    if not isinstance(envelope, dict):
        return _invalid("envelope is not a JSON object")

    payload = envelope.get("payload")
    signature_b64 = envelope.get("signature_b64")
    if not isinstance(payload, dict) or not isinstance(signature_b64, str):
        return _invalid("missing payload or signature")

    if payload.get("v") != 1:
        return _invalid("unsupported envelope version")

    content = payload.get("content")
    signer_did = payload.get("signer_did")
    public_key_b64 = payload.get("public_key_b64")
    if (
        not isinstance(content, str)
        or not isinstance(signer_did, str)
        or not isinstance(public_key_b64, str)
    ):
        return _invalid("envelope fields missing or wrong type")

    try:
        public_key = base64.b64decode(public_key_b64, validate=True)
        signature = base64.b64decode(signature_b64, validate=True)
    except (binascii.Error, ValueError):
        return _invalid("malformed key or signature encoding")

    # Verify that signer_did matches SHA-256(public_key) -- i.e. the
    # envelope's claimed DID is the one derivable from the embedded key.
    # Without this check, a forger could keep the victim's DID string
    # but drop in their own key and re-sign.
    expected_did = "did:synpareia:" + hashlib.sha256(public_key).hexdigest()
    if expected_did != signer_did:
        return _invalid("signer_did does not match embedded public key")

    # Re-run the SDK's public-key → DID derivation as a double check.
    try:
        from_public_key(public_key)
    except Exception:
        return _invalid("invalid public key")

    canonical = jcs_canonicalize(payload)
    if not ed25519_verify(public_key, canonical, signature):
        return _invalid("signature verification failed")

    # ADV-052: validate `signed_at` against the same allowlist as Tier-2/3
    # `created_at`. A cryptographically-valid envelope with free-text
    # `signed_at` would otherwise echo arbitrary content (control chars,
    # multiline prompt-injection text) back to the calling agent under the
    # guise of trusted metadata. `encode_signed` always produces compliant
    # ISO strings; only an attacker-crafted payload reaches this branch.
    raw_signed_at = payload.get("signed_at")
    if not isinstance(raw_signed_at, str) or not _ISO_DATE_PATTERN.match(raw_signed_at):
        return _invalid("signed_at not ISO-8601 shaped")

    return {
        "content": content,
        "signer_did": signer_did,
        "valid": True,
        "verified_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "synpareia_validated": True,
        "signed_at": raw_signed_at,
    }


def _invalid(reason: str) -> dict[str, Any]:
    """Build a decode result representing a malformed / unverified envelope."""
    return {
        "content": None,
        "signer_did": None,
        "valid": False,
        "verified_at": None,
        "synpareia_validated": True,
        "reason": reason,
    }
