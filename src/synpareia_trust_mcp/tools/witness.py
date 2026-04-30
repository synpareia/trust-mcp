"""Witness tools — independent attestation via the synpareia witness service.

All tool names in this module share the `witness_` prefix because they
are all calls against the same external service. `witness_info` is a
read-side peek at the witness identity; the four `witness_seal_*` and
`witness_*_blind` tools each exchange data with the service.

All tools require `SYNPAREIA_WITNESS_URL` (and, for authenticated
deployments, `SYNPAREIA_WITNESS_TOKEN`). With witness unconfigured
these tools return a structured error rather than raising.
"""

from __future__ import annotations

import base64
import re
from typing import TYPE_CHECKING

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp

if TYPE_CHECKING:
    from synpareia import Profile
    from synpareia.witness import WitnessClient

_DID_PATTERN = re.compile(r"^did:synpareia:[0-9a-f]{64}$")
_VERSION_PATTERN = re.compile(r"^[A-Za-z0-9.\-+]{1,32}$")


def _require_witness(app: AppContext) -> WitnessClient:
    """Return the configured witness client, or raise if not configured.

    Returning the narrowed value (rather than asserting after the call)
    means callers don't need `assert app.witness_client is not None`
    afterwards — close-read 2026-04-30 flagged 6 such asserts as LOW
    defence-in-depth concerns (asserts vanish under `python -O`).
    """
    if app.witness_client is None:
        msg = (
            "Witness service not configured. Set SYNPAREIA_WITNESS_URL "
            "(and optionally SYNPAREIA_WITNESS_TOKEN) to enable witness tools. "
            "Install with: pip install synpareia-trust-mcp[network]"
        )
        raise ValueError(msg)
    return app.witness_client


def _require_profile(app: AppContext) -> Profile:
    """Return the loaded profile, or raise if not loaded."""
    profile = app.profile_manager.profile
    if profile is None:
        msg = "Profile not loaded — call orient first."
        raise ValueError(msg)
    return profile


def _safe_witness_id(val: object) -> str:
    """Return witness_id iff it is a well-formed did:synpareia DID.

    A malicious/MITM'd witness can return anything in this field; callers
    surface it to LLMs, so reject anything that isn't the expected shape
    rather than passing arbitrary strings through (ADV-012).
    """
    if isinstance(val, str) and _DID_PATTERN.match(val):
        return val
    return "did:invalid"


def _safe_witness_version(val: object) -> str:
    """Return version iff short and printable ASCII; else a neutral tag."""
    if isinstance(val, str) and _VERSION_PATTERN.match(val):
        return val
    return "unknown"


@mcp.tool()
async def witness_info(ctx: Context[ServerSession, AppContext]) -> dict:
    """Fetch the witness service's identity and public key.

    The witness is an independent third party that signs attestations
    (timestamp seals, state seals, blind conclusions). Retrieve its
    public key here once, then use it with `witness_verify_seal` to
    verify any seal it issues — fully offline, no further calls needed.

    Returns `witness_id` (a `did:synpareia:*` DID), `public_key_b64`,
    `public_key_hex`, and `version`. Requires `SYNPAREIA_WITNESS_URL`.
    """
    app = ctx.request_context.lifespan_context
    try:
        client = _require_witness(app)
        info = await client.get_witness_info()
        return {
            "witness_id": _safe_witness_id(info.witness_id),
            "public_key_b64": info.public_key_b64,
            "public_key_hex": info.public_key_hex,
            "version": _safe_witness_version(info.version),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def witness_seal_timestamp(
    block_hash_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Ask the witness to timestamp a block — proof it existed at this moment.

    Pass the block's content hash (hex). The witness signs the hash with
    its private key and returns a `SealPayload` you can verify offline
    later with `witness_verify_seal`.

    Use this to create evidence that a decision, claim, or observation
    predates some later event — a cryptographic "I knew this by T"
    signed by an independent third party, not by you.
    """
    app = ctx.request_context.lifespan_context
    try:
        client = _require_witness(app)

        block_hash = bytes.fromhex(block_hash_hex)
        seal = await client.timestamp_seal(block_hash)
        return {
            "seal_type": str(seal.seal_type),
            "witness_id": _safe_witness_id(seal.witness_id),
            "sealed_at": seal.sealed_at.isoformat(),
            "target_block_hash": block_hash_hex,
            "witness_signature_b64": base64.b64encode(seal.witness_signature).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def witness_seal_state(
    chain_id: str,
    chain_head_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Checkpoint a chain's current state with the witness.

    Pass the chain id and its current head hash (hex). The witness signs
    the pair together, creating proof that the chain was in this exact
    state at the witnessed time.

    Useful for proving that a chain has not been retconned: if anyone
    later claims "your chain never contained X", a state seal whose head
    commits to the block containing X refutes them.
    """
    app = ctx.request_context.lifespan_context
    try:
        client = _require_witness(app)

        chain_head = bytes.fromhex(chain_head_hex)
        seal = await client.state_seal(chain_id, chain_head)
        return {
            "seal_type": str(seal.seal_type),
            "witness_id": _safe_witness_id(seal.witness_id),
            "sealed_at": seal.sealed_at.isoformat(),
            "target_chain_id": seal.target_chain_id,
            "target_chain_head": chain_head_hex,
            "witness_signature_b64": base64.b64encode(seal.witness_signature).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def witness_verify_seal(
    seal_type: str,
    witness_id: str,
    witness_signature_b64: str,
    sealed_at: str,
    witness_public_key_b64: str,
    ctx: Context[ServerSession, AppContext],
    target_block_hash_hex: str | None = None,
    target_chain_id: str | None = None,
    target_chain_head_hex: str | None = None,
) -> dict:
    """Verify a witness seal offline — no calls to the witness service.

    Provide the seal fields (from `witness_seal_timestamp` or
    `witness_seal_state`) and the witness's public key (from
    `witness_info`, cached once). This reconstructs the signing envelope
    and checks the Ed25519 signature.

    For timestamp seals: pass `target_block_hash_hex`.
    For state seals: pass `target_chain_id` and `target_chain_head_hex`.

    Returns `valid: True/False`. This is the terminal verification step —
    anyone with the seal + the witness public key can run it independently.
    """
    from datetime import datetime

    from synpareia.seal import SealPayload
    from synpareia.seal.verify import verify_seal
    from synpareia.types import SealType

    try:
        witness_public_key = base64.b64decode(witness_public_key_b64)
        witness_signature = base64.b64decode(witness_signature_b64)

        target_block_hash = bytes.fromhex(target_block_hash_hex) if target_block_hash_hex else None
        target_chain_head = bytes.fromhex(target_chain_head_hex) if target_chain_head_hex else None

        seal = SealPayload(
            witness_id=witness_id,
            witness_signature=witness_signature,
            seal_type=SealType(seal_type),
            sealed_at=datetime.fromisoformat(sealed_at),
            target_block_hash=target_block_hash,
            target_chain_id=target_chain_id,
            target_chain_head=target_chain_head,
        )

        valid, error = verify_seal(seal, witness_public_key)
        return {
            "valid": valid,
            "seal_type": seal_type,
            "witness_id": witness_id,
            "error": error,
            "explanation": (
                "Seal signature is valid — the witness attested to this data."
                if valid
                else f"Seal verification failed: {error}"
            ),
        }
    except Exception as e:
        return {"valid": False, "error": str(e)}


@mcp.tool()
async def witness_submit_blind(
    conclusion_key: str,
    commitment_hash_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Submit your committed assessment to a blind conclusion exchange.

    A "blind conclusion" lets two parties independently commit to
    assessments (reviews, votes, estimates) before seeing each other's —
    evidence that neither party's answer was anchored by the other's.

    Flow:
    1. Both parties seal their assessment locally (`prove_independence`)
    2. Both call this tool with the same `conclusion_key` and their
       commitment hashes
    3. Once both have submitted, both commitments are revealed together
    4. Each party reveals their original content+nonce to prove their
       answer matches the hash they committed to

    `conclusion_key` is a shared identifier both parties agree on first
    (e.g., "dispute-42", a URL, or a hash of the question).
    """
    app = ctx.request_context.lifespan_context
    try:
        client = _require_witness(app)
        profile = _require_profile(app)

        commitment_hash = bytes.fromhex(commitment_hash_hex)
        status = await client.submit_conclusion(conclusion_key, profile.id, commitment_hash)
        result: dict = {
            "conclusion_key": status.conclusion_key,
            "status": status.status,
        }
        if status.status == "ready":
            result["party_a_commitment"] = status.party_a_commitment
            result["party_b_commitment"] = status.party_b_commitment
            result["message"] = (
                "Both parties have submitted. You can now exchange reveals. "
                "Use reveal_commitment with your original content and nonce to "
                "prove your assessment was independent."
            )
        elif status.status == "waiting":
            result["message"] = "Your commitment is recorded. Waiting for the other party."
        return result
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def witness_get_blind(
    conclusion_key: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Check the status of a blind conclusion exchange.

    Pair to `witness_submit_blind`. Returns whether both parties have
    submitted their commitments, and — once both have — the pair of
    commitment hashes so each party can verify the other's reveal.
    """
    app = ctx.request_context.lifespan_context
    try:
        client = _require_witness(app)
        status = await client.get_conclusion(conclusion_key)
        result: dict = {
            "conclusion_key": status.conclusion_key,
            "status": status.status,
        }
        if status.party_a_commitment:
            result["party_a_commitment"] = status.party_a_commitment
        if status.party_b_commitment:
            result["party_b_commitment"] = status.party_b_commitment
        return result
    except Exception as e:
        return {"error": str(e)}
