"""Claim and verification tools — make verifiable claims, verify others' claims."""

from __future__ import annotations

import base64
from typing import Any

import synpareia
from mcp.server.fastmcp import Context
from synpareia.hash import content_hash_hex

from synpareia_trust_mcp.app import AppContext, mcp


@mcp.tool()
def make_claim(
    content: str,
    ctx: Context,
    witness: bool = False,
) -> dict[str, Any]:
    """Sign content with your private key, creating a verifiable claim.

    The result always contains the signature and the verification
    instructions a third party needs.

    If ``witness=True``, the result additionally carries a
    ``witness_followup`` block telling you how to attach a witness
    timestamp seal — ``witness_seal_timestamp`` is a separate async
    tool, so the seal isn't bundled into this synchronous call. Pass
    the pre-computed ``block_hash_hex`` from this result straight to
    that tool and it will sign and return the seal.
    """
    app: AppContext = ctx.request_context.lifespan_context
    profile = app.profile_manager.profile

    assert profile.private_key is not None
    content_bytes = content.encode()
    signature = synpareia.sign(profile.private_key, content_bytes)
    # Use the SDK's canonical content-hash helper so trust-mcp and
    # downstream witness/recording paths agree on the digest by
    # construction.
    block_hash = content_hash_hex(content)

    result: dict[str, Any] = {
        "content": content,
        "signature_b64": base64.b64encode(signature).decode(),
        "signer_did": profile.id,
        "public_key_b64": base64.b64encode(profile.public_key).decode(),
        "block_hash_hex": block_hash,
        "verification_instructions": {
            "tool": "verify_claim",
            "params": {
                "claim_type": "signature",
                "content": content,
                "signature_b64": base64.b64encode(signature).decode(),
                "public_key_b64": base64.b64encode(profile.public_key).decode(),
            },
            "message": f"Verify this claim was signed by {profile.id}.",
            "manual": (
                "pip install synpareia && python -c "
                '"import synpareia; '
                f"print(synpareia.verify(bytes.fromhex('{profile.public_key.hex()}'), "
                f"b'{content[:50]}...', "
                f"bytes.fromhex('{signature.hex()}')))\"",
            ),
        },
    }

    if witness and app.witness_client is not None:
        result["witness_followup"] = {
            "tool": "witness_seal_timestamp",
            "params": {"block_hash_hex": block_hash},
            "message": (
                "Pass block_hash_hex to witness_seal_timestamp. The result "
                "includes witness_id, sealed_at, and witness_signature_b64 "
                "you can attach alongside this claim. Recipients verify the "
                "seal offline against the witness's published public key."
            ),
        }
    elif witness:
        result["witness_followup"] = {
            "tool": None,
            "message": (
                "Witness not configured. Claim is signed but not witness-attested. "
                "Set SYNPAREIA_WITNESS_URL (and optionally SYNPAREIA_WITNESS_TOKEN) "
                "to enable witness seals."
            ),
        }

    return result


@mcp.tool()
def verify_claim(
    claim_type: str,
    ctx: Context,
    content: str | None = None,
    signature_b64: str | None = None,
    public_key_b64: str | None = None,
    agent_did: str | None = None,
    commitment_hash: str | None = None,
    nonce_b64: str | None = None,
) -> dict[str, Any]:
    """Verify a claim.

    Types: 'signature' (content+sig+key), 'identity' (did+key),
    'commitment' (hash+content+nonce).
    """
    if claim_type == "signature":
        return _verify_signature(content, signature_b64, public_key_b64)
    elif claim_type == "identity":
        return _verify_identity(agent_did, public_key_b64)
    elif claim_type == "commitment":
        return _verify_commitment(commitment_hash, content, nonce_b64)
    else:
        return {
            "valid": False,
            "error": (
                f"Unknown claim_type: '{claim_type}'. Use 'signature', 'identity', or 'commitment'."
            ),
        }


def _verify_signature(
    content: str | None,
    signature_b64: str | None,
    public_key_b64: str | None,
) -> dict[str, Any]:
    if not all([content, signature_b64, public_key_b64]):
        return {
            "valid": False,
            "error": "Signature verification requires: content, signature_b64, public_key_b64.",
        }
    try:
        content_bytes = content.encode()  # type: ignore[union-attr]
        signature = base64.b64decode(signature_b64)  # type: ignore[arg-type]
        public_key = base64.b64decode(public_key_b64)  # type: ignore[arg-type]
        valid = synpareia.verify(public_key, content_bytes, signature)
        # Derive the signer DID inside the try block so a malformed
        # public key (now rejected early by from_public_key) returns a
        # structured error rather than crashing the caller.
        signer_profile = synpareia.from_public_key(public_key)
    except Exception as e:
        return {"valid": False, "error": str(e)}

    return {
        "valid": valid,
        "claim_type": "signature",
        "signer_did": signer_profile.id,
        "explanation": (
            "Signature verified. This content was signed by the holder of this key."
            if valid
            else "INVALID signature. The content, signature, or key does not match."
        ),
    }


def _verify_identity(
    agent_did: str | None,
    public_key_b64: str | None,
) -> dict[str, Any]:
    if not all([agent_did, public_key_b64]):
        return {
            "valid": False,
            "error": "Identity verification requires: agent_did, public_key_b64.",
        }
    try:
        public_key = base64.b64decode(public_key_b64)  # type: ignore[arg-type]
        derived = synpareia.from_public_key(public_key)
        matches = derived.id == agent_did
    except Exception as e:
        return {"valid": False, "error": str(e)}

    return {
        "valid": matches,
        "claim_type": "identity",
        "claimed_did": agent_did,
        "derived_did": derived.id,
        "explanation": (
            "Identity confirmed. The public key correctly derives this DID."
            if matches
            else "MISMATCH: the public key does not derive the claimed DID. "
            "This agent may be impersonating someone else."
        ),
    }


def _verify_commitment(
    commitment_hash: str | None,
    content: str | None,
    nonce_b64: str | None,
) -> dict[str, Any]:
    if not all([commitment_hash, content, nonce_b64]):
        return {
            "valid": False,
            "error": "Commitment verification requires: commitment_hash, content, nonce_b64.",
        }
    try:
        nonce = base64.b64decode(nonce_b64)  # type: ignore[arg-type]
        commitment_bytes = bytes.fromhex(commitment_hash)  # type: ignore[arg-type]
        valid = synpareia.verify_commitment(
            commitment_bytes,
            content.encode(),  # type: ignore[union-attr]
            nonce,
        )
    except Exception as e:
        return {"valid": False, "error": str(e)}

    return {
        "valid": valid,
        "claim_type": "commitment",
        "explanation": (
            "Commitment verified. This content matches the sealed commitment "
            "— the assessment was independent."
            if valid
            else "MISMATCH: the content does not match the commitment."
        ),
    }
