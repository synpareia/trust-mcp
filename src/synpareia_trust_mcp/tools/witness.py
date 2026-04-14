"""Witness tools -- independent attestation via the synpareia witness service."""

from __future__ import annotations

import base64

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession

from synpareia_trust_mcp.app import AppContext, mcp


def _require_witness(app: AppContext) -> None:
    """Raise if witness is not configured."""
    if app.witness_client is None:
        msg = (
            "Witness service not configured. Set SYNPAREIA_WITNESS_URL "
            "(and optionally SYNPAREIA_WITNESS_TOKEN) to enable witness tools. "
            "Install with: pip install synpareia-trust-mcp[network]"
        )
        raise ValueError(msg)


@mcp.tool()
async def get_witness_info(ctx: Context[ServerSession, AppContext]) -> dict:
    """Get the witness service's identity — its DID and public key.

    The witness is an independent third party that provides cryptographic
    attestations. Use this to retrieve its public key for offline verification
    of seals it has issued.

    Requires SYNPAREIA_WITNESS_URL to be configured.
    """
    app = ctx.request_context.lifespan_context
    try:
        _require_witness(app)
        assert app.witness_client is not None
        info = await app.witness_client.get_witness_info()
        return {
            "witness_id": info.witness_id,
            "public_key_b64": info.public_key_b64,
            "public_key_hex": info.public_key_hex,
            "version": info.version,
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def request_timestamp_seal(
    block_hash_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Request the witness to timestamp a block, proving it existed at this moment.

    Provide the block's content_hash as a hex string. The witness signs the hash
    with its private key and returns a seal you can verify offline later.

    The seal is cryptographic proof that this block existed at the witnessed time,
    signed by an independent third party.
    """
    app = ctx.request_context.lifespan_context
    try:
        _require_witness(app)
        assert app.witness_client is not None
        profile = app.profile_manager.profile
        assert profile is not None

        block_hash = bytes.fromhex(block_hash_hex)
        seal = await app.witness_client.timestamp_seal(profile.id, block_hash)
        return {
            "seal_type": str(seal.seal_type),
            "witness_id": seal.witness_id,
            "sealed_at": seal.sealed_at.isoformat(),
            "target_block_hash": block_hash_hex,
            "witness_signature_b64": base64.b64encode(seal.witness_signature).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def request_state_seal(
    chain_id: str,
    chain_head_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Checkpoint a chain's current state with the witness.

    The witness signs the chain ID and head hash together, creating a
    cryptographic proof that the chain was in this exact state at the
    witnessed time. Useful for proving chain integrity at a point in time.
    """
    app = ctx.request_context.lifespan_context
    try:
        _require_witness(app)
        assert app.witness_client is not None
        profile = app.profile_manager.profile
        assert profile is not None

        chain_head = bytes.fromhex(chain_head_hex)
        seal = await app.witness_client.state_seal(profile.id, chain_id, chain_head)
        return {
            "seal_type": str(seal.seal_type),
            "witness_id": seal.witness_id,
            "sealed_at": seal.sealed_at.isoformat(),
            "target_chain_id": seal.target_chain_id,
            "target_chain_head": chain_head_hex,
            "witness_signature_b64": base64.b64encode(seal.witness_signature).decode(),
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
def verify_seal_offline(
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
    """Verify a witness seal without contacting the witness service. Works fully offline.

    Provide the seal fields and the witness's public key (from get_witness_info).
    This reconstructs the signing envelope and verifies the Ed25519 signature.

    For timestamp seals: provide target_block_hash_hex.
    For state seals: provide target_chain_id and target_chain_head_hex.
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
async def submit_blind_conclusion(
    conclusion_key: str,
    commitment_hash_hex: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Submit your commitment to a blind conclusion via the witness.

    A blind conclusion lets two parties independently commit to assessments
    before seeing each other's. The witness coordinates the exchange:

    1. Both parties seal their assessment locally (seal_commitment)
    2. Both submit the commitment hash here with the same conclusion_key
    3. When both have submitted, the witness reveals both commitment hashes
    4. Each party can then reveal and verify the other's commitment

    The conclusion_key is a shared identifier both parties agree on beforehand.
    """
    app = ctx.request_context.lifespan_context
    try:
        _require_witness(app)
        assert app.witness_client is not None
        profile = app.profile_manager.profile
        assert profile is not None

        commitment_hash = bytes.fromhex(commitment_hash_hex)
        status = await app.witness_client.submit_conclusion(
            conclusion_key, profile.id, commitment_hash
        )
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
async def get_blind_conclusion(
    conclusion_key: str,
    ctx: Context[ServerSession, AppContext],
) -> dict:
    """Check the status of a blind conclusion.

    Returns whether both parties have submitted, and if so, their commitment hashes.
    """
    app = ctx.request_context.lifespan_context
    try:
        _require_witness(app)
        assert app.witness_client is not None
        status = await app.witness_client.get_conclusion(conclusion_key)
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
