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
            "Witness service is disabled by configuration (SYNPAREIA_WITNESS_URL). "
            "Re-enable it (and optionally set SYNPAREIA_WITNESS_TOKEN) to use "
            "witness tools. Install with: pip install synpareia-trust-mcp[network]"
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


async def _cached_witness_pubkey_b64(app: AppContext, client: WitnessClient) -> str | None:
    """Witness public key (b64), fetched + cached once per session (best-effort).

    Used to make seal responses self-describing: the `verify_followup` block
    embeds the pubkey so a third-party recipient can run `witness_verify_seal`
    fully offline, with no separate `witness_info` round-trip. Returns None if
    the fetch fails — the seal itself already succeeded, so a followup without
    the key still degrades gracefully (the recipient can fetch it via
    `witness_info`).

    Cache lifetime is the session. That can't go stale in practice: the witness
    signing key is a hard non-rotation invariant (CLAUDE.md §0 — never rotated
    without a full key-rotation redesign), so the pubkey is stable for the process.
    """
    if app.witness_pubkey_b64 is None:
        try:
            info = await client.get_witness_info()
            app.witness_pubkey_b64 = info.public_key_b64
        except Exception:
            return None
    return app.witness_pubkey_b64


def _verify_followup(
    *,
    seal_type: str,
    witness_id: str,
    witness_signature_b64: str,
    sealed_at: str,
    witness_public_key_b64: str | None,
    target_block_hash_hex: str | None = None,
    target_chain_id: str | None = None,
    target_chain_head_hex: str | None = None,
) -> dict:
    """Self-describing hand-off block mirroring make_claim's ``witness_followup``.

    Gives the exact ``witness_verify_seal`` params for this seal so a recipient
    can verify it verbatim — no field-name guesswork (LR-6). Includes the
    witness public key when available so verification needs no witness call.
    """
    params: dict[str, str] = {
        "seal_type": seal_type,
        "witness_id": witness_id,
        "witness_signature_b64": witness_signature_b64,
        "sealed_at": sealed_at,
    }
    if target_block_hash_hex is not None:
        params["target_block_hash_hex"] = target_block_hash_hex
    if target_chain_id is not None:
        params["target_chain_id"] = target_chain_id
    if target_chain_head_hex is not None:
        params["target_chain_head_hex"] = target_chain_head_hex
    if witness_public_key_b64 is not None:
        params["witness_public_key_b64"] = witness_public_key_b64
        message = (
            "Pass these params straight to witness_verify_seal to check this seal "
            "offline — no witness call needed. Anyone you forward this seal to can "
            "verify it independently with the included witness_public_key_b64."
        )
    else:
        message = (
            "Pass these params to witness_verify_seal, plus witness_public_key_b64 "
            "from witness_info (the witness was unreachable to embed it here)."
        )
    return {"tool": "witness_verify_seal", "params": params, "message": message}


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
        app.witness_pubkey_b64 = info.public_key_b64
        return {
            "witness_id": _safe_witness_id(info.witness_id),
            "public_key_b64": info.public_key_b64,
            # Alias under witness_verify_seal's exact param name (0.6.2, LR-6) so the
            # witness_info -> witness_verify_seal hop pipes verbatim.
            "witness_public_key_b64": info.public_key_b64,
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
        seal_type = str(seal.seal_type)
        witness_id = _safe_witness_id(seal.witness_id)
        sealed_at = seal.sealed_at.isoformat()
        signature_b64 = base64.b64encode(seal.witness_signature).decode()
        pubkey_b64 = await _cached_witness_pubkey_b64(app, client)
        return {
            "seal_type": seal_type,
            "witness_id": witness_id,
            "sealed_at": sealed_at,
            # Canonical name — matches witness_verify_seal's param exactly (0.6.2, LR-6).
            "target_block_hash_hex": block_hash_hex,
            # Deprecated alias (pre-0.6.2 name); verify still accepts it. Kept one
            # release for back-compat, will be dropped in a future major.
            "target_block_hash": block_hash_hex,
            "witness_signature_b64": signature_b64,
            "verify_followup": _verify_followup(
                seal_type=seal_type,
                witness_id=witness_id,
                witness_signature_b64=signature_b64,
                sealed_at=sealed_at,
                witness_public_key_b64=pubkey_b64,
                target_block_hash_hex=block_hash_hex,
            ),
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
        seal_type = str(seal.seal_type)
        witness_id = _safe_witness_id(seal.witness_id)
        sealed_at = seal.sealed_at.isoformat()
        signature_b64 = base64.b64encode(seal.witness_signature).decode()
        pubkey_b64 = await _cached_witness_pubkey_b64(app, client)
        return {
            "seal_type": seal_type,
            "witness_id": witness_id,
            "sealed_at": sealed_at,
            "target_chain_id": seal.target_chain_id,
            # Canonical name — matches witness_verify_seal's param exactly (0.6.2, LR-6).
            "target_chain_head_hex": chain_head_hex,
            # Deprecated alias (pre-0.6.2 name); verify still accepts it.
            "target_chain_head": chain_head_hex,
            "witness_signature_b64": signature_b64,
            "verify_followup": _verify_followup(
                seal_type=seal_type,
                witness_id=witness_id,
                witness_signature_b64=signature_b64,
                sealed_at=sealed_at,
                witness_public_key_b64=pubkey_b64,
                target_chain_id=seal.target_chain_id,
                target_chain_head_hex=chain_head_hex,
            ),
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
    target_block_hash: str | None = None,
    target_chain_head: str | None = None,
) -> dict:
    """Verify a witness seal offline — no calls to the witness service.

    Easiest call: feed the fields from a `witness_seal_timestamp` /
    `witness_seal_state` response straight in — its `verify_followup.params`
    already lists exactly what to pass, including the witness public key.
    This reconstructs the signing envelope and checks the Ed25519 signature.

    For timestamp seals: pass `target_block_hash_hex`.
    For state seals: pass `target_chain_id` and `target_chain_head_hex`.
    The pre-0.6.2 seal-response field names (`target_block_hash`,
    `target_chain_head`) are accepted as aliases, so a seal response piped
    in verbatim verifies correctly.

    Returns `valid: True/False`. If the fields needed to rebuild the envelope
    are missing, returns a structured `incomplete_verification_input` error —
    NOT `valid: false` — because a missing target means the request was
    under-specified, not that the seal is forged.
    """
    from datetime import datetime

    from synpareia.seal import SealPayload
    from synpareia.seal.verify import verify_seal
    from synpareia.types import SealType

    # Accept the seal-response field names verbatim (LR-6): coalesce the
    # pre-0.6.2 aliases onto the canonical hex params. FastMCP drops unknown
    # keys silently, so without declaring these a verbatim seal response would
    # lose its target and verify against an empty envelope -> false "invalid".
    target_block_hash_hex = target_block_hash_hex or target_block_hash
    target_chain_head_hex = target_chain_head_hex or target_chain_head

    # Distinguish "you didn't give me the target" from "the signature is bad".
    # Returning valid:false for a missing target would wrongly impugn honest
    # evidence — the worst error class for a trust tool (LR-6).
    seal_type_lc = seal_type.lower() if isinstance(seal_type, str) else ""
    if seal_type_lc == "timestamp" and not target_block_hash_hex:
        return {
            "error": "cannot verify: timestamp seal has no target_block_hash_hex",
            "reason": "incomplete_verification_input",
            "hint": (
                "A timestamp seal is verified against the block hash it sealed. Pass "
                "target_block_hash_hex — or feed the seal response's verify_followup.params."
            ),
        }
    if seal_type_lc == "state" and (not target_chain_id or not target_chain_head_hex):
        return {
            "error": "cannot verify: state seal missing target_chain_id / target_chain_head_hex",
            "reason": "incomplete_verification_input",
            "hint": (
                "A state seal is verified against (target_chain_id, target_chain_head_hex). "
                "Pass both — or feed the seal response's verify_followup.params."
            ),
        }

    try:
        witness_public_key = base64.b64decode(witness_public_key_b64)
        witness_signature = base64.b64decode(witness_signature_b64)

        target_block_hash_bytes = (
            bytes.fromhex(target_block_hash_hex) if target_block_hash_hex else None
        )
        target_chain_head_bytes = (
            bytes.fromhex(target_chain_head_hex) if target_chain_head_hex else None
        )

        seal = SealPayload(
            witness_id=witness_id,
            witness_signature=witness_signature,
            seal_type=SealType(seal_type),
            sealed_at=datetime.fromisoformat(sealed_at),
            target_block_hash=target_block_hash_bytes,
            target_chain_id=target_chain_id,
            target_chain_head=target_chain_head_bytes,
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

    Note: the witness does not verify the requester identity submitted
    with a commitment — identity binding is the caller's self-asserted
    claim in v1 (until Phase-2 anonymous credentials), so verify the
    counterparty's reveal against their known key, not the slot label.
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
                "Both parties have submitted. Exchange reveals now: send the other "
                "party your original content + nonce_b64, and verify theirs with "
                "verify_claim(claim_type='commitment', commitment_hash=<their "
                "party_a_commitment or party_b_commitment>, content=<their revealed "
                "content>, nonce_b64=<their revealed nonce>). A valid result proves "
                "their assessment was committed before either of you revealed."
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

    Note: party identities on a conclusion are self-asserted in v1 —
    the witness does not verify who occupies each slot.
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
