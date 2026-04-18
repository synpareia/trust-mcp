"""Starlette stub for the Synpareia witness service.

Unlike moltbook/moltrust, the witness is one of our own services — the
testing strategy says it should be real (in-process ASGI transport). The
witness package itself is not installed in the trust-toolkit venv, so we
build a minimal reimplementation here that uses the SAME cryptographic
primitives (synpareia.seal.create_seal) so any offline verification path
that works against the real service also works against this stub.

Only the endpoints consumed by the trust-toolkit WitnessClient are
implemented. Liveness challenges and blind conclusions are stubs that
satisfy the HTTP contract but do not persist state across requests.

The stub's keypair is deterministic per-instance (generated at app
construction) so a single test can round-trip seal-sign → seal-verify
with the public key obtained via `get_witness_info`.
"""

from __future__ import annotations

import base64
import json
from typing import TYPE_CHECKING

import synpareia
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from synpareia.seal import create_seal
from synpareia.types import SealType

if TYPE_CHECKING:
    from starlette.requests import Request


def _seal_to_response(seal) -> dict:
    body = {
        "witness_id": seal.witness_id,
        "witness_signature_b64": base64.b64encode(seal.witness_signature).decode(),
        "seal_type": str(seal.seal_type),
        "sealed_at": seal.sealed_at.isoformat(),
    }
    if seal.target_block_hash is not None:
        body["target_block_hash"] = seal.target_block_hash.hex()
    if seal.target_chain_id is not None:
        body["target_chain_id"] = seal.target_chain_id
    if seal.target_chain_head is not None:
        body["target_chain_head"] = seal.target_chain_head.hex()
    return body


def make_witness_app(
    *,
    fail_mode: str | None = None,
    info_override: dict | None = None,
) -> Starlette:
    """Build a witness ASGI app with a fresh Ed25519 keypair.

    The keypair lives for the lifetime of the returned app. Tests that
    need a specific key should either call `get_witness_info` on the
    resulting client or mint their own via synpareia.generate() and
    inject the resulting profile into a different stub instance.

    fail_mode is reserved for adversarial tests:
        "500" — every POST returns 500
        "bad_signature" — seals are signed with the WRONG private key,
            so offline verification fails even though the issuance path
            succeeds (tests catch impersonation).

    info_override lets adversarial tests simulate a malicious/MITM'd
    witness that returns prompt-injection payloads in witness_id or
    version. The keys override the default info response verbatim.
    """
    witness_profile = synpareia.generate()

    # The "impersonator" profile is used only when fail_mode="bad_signature"
    # to simulate a witness whose advertised public key does not match
    # the private key it actually signs with.
    impersonator = synpareia.generate()

    def _signing_key() -> bytes:
        if fail_mode == "bad_signature":
            return impersonator.private_key
        return witness_profile.private_key

    async def get_info(request: Request) -> JSONResponse:
        body = {
            "witness_id": witness_profile.id,
            "public_key_hex": witness_profile.public_key.hex(),
            "public_key_b64": base64.b64encode(witness_profile.public_key).decode(),
            "version": "0.0-stub",
        }
        if info_override:
            body.update(info_override)
        return JSONResponse(body)

    async def timestamp_seal(request: Request) -> JSONResponse:
        if fail_mode == "500":
            return JSONResponse({"error": "server_error"}, status_code=500)
        body = json.loads(await request.body())
        block_hash = bytes.fromhex(body["block_hash"])
        seal = create_seal(
            witness_private_key=_signing_key(),
            witness_id=witness_profile.id,
            seal_type=SealType.TIMESTAMP,
            target_block_hash=block_hash,
        )
        return JSONResponse(_seal_to_response(seal))

    async def state_seal(request: Request) -> JSONResponse:
        if fail_mode == "500":
            return JSONResponse({"error": "server_error"}, status_code=500)
        body = json.loads(await request.body())
        chain_head = bytes.fromhex(body["chain_head"])
        seal = create_seal(
            witness_private_key=_signing_key(),
            witness_id=witness_profile.id,
            seal_type=SealType.STATE,
            target_chain_id=body["chain_id"],
            target_chain_head=chain_head,
        )
        return JSONResponse(_seal_to_response(seal))

    return Starlette(
        routes=[
            Route("/api/v1/witness", get_info, methods=["GET"]),
            Route("/api/v1/seals/timestamp", timestamp_seal, methods=["POST"]),
            Route("/api/v1/seals/state", state_seal, methods=["POST"]),
        ]
    )
