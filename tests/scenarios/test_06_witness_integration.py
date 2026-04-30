"""Scenario 06: Witness-sealed claim, verified offline by a third party.

See scenarios/trust-toolkit/06-witness-integration.md.

Uses an in-process witness stub that performs real Ed25519 signing —
so offline verification exercises the same cryptographic path as a
production witness.
"""

from __future__ import annotations

import asyncio
import base64

import synpareia

from synpareia_trust_mcp.tools.witness import (
    witness_info,
    witness_seal_state,
    witness_seal_timestamp,
    witness_verify_seal,
)


def _run(coro):
    return asyncio.run(coro)


class TestWitnessInfo:
    def test_returns_witness_id_and_public_key(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness
        info = _run(witness_info(ctx=ctx))

        assert "error" not in info, info
        assert info["witness_id"].startswith("did:synpareia:")
        # Public key must be valid Ed25519 (32 bytes once decoded)
        decoded = base64.b64decode(info["public_key_b64"])
        assert len(decoded) == 32
        # And must match the hex form
        assert bytes.fromhex(info["public_key_hex"]) == decoded

    def test_error_when_no_witness_configured(self, app_ctx) -> None:
        ctx, _ = app_ctx
        info = _run(witness_info(ctx=ctx))
        assert "error" in info
        # Error must name the env var to set, not leak a stack trace
        assert "SYNPAREIA_WITNESS_URL" in info["error"]


class TestTimestampSealRoundtrip:
    def test_seal_is_verifiable_offline(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness

        # Create a block; hash it; request a seal for the content hash.
        profile = synpareia.generate()
        block = synpareia.create_block(profile, type="message", content=b"claim X")
        block_hash_hex = block.content_hash.hex()

        seal = _run(witness_seal_timestamp(block_hash_hex=block_hash_hex, ctx=ctx))
        assert "error" not in seal, seal

        info = _run(witness_info(ctx=ctx))

        # Verify with only the public outputs — no witness network call.
        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
            target_block_hash_hex=block_hash_hex,
            ctx=ctx,
        )
        assert result["valid"] is True, result
        assert "valid" in result["explanation"].lower()

    def test_tampered_timestamp_fails(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness
        profile = synpareia.generate()
        block = synpareia.create_block(profile, type="message", content=b"x")
        seal = _run(witness_seal_timestamp(block_hash_hex=block.content_hash.hex(), ctx=ctx))
        info = _run(witness_info(ctx=ctx))

        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at="2099-01-01T00:00:00+00:00",
            witness_public_key_b64=info["public_key_b64"],
            target_block_hash_hex=block.content_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is False

    def test_tampered_target_hash_fails(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness
        profile = synpareia.generate()
        block = synpareia.create_block(profile, type="message", content=b"x")
        seal = _run(witness_seal_timestamp(block_hash_hex=block.content_hash.hex(), ctx=ctx))
        info = _run(witness_info(ctx=ctx))

        # Flip the first byte of the target hash
        tampered = "ff" + block.content_hash.hex()[2:]
        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
            target_block_hash_hex=tampered,
            ctx=ctx,
        )
        assert result["valid"] is False

    def test_wrong_public_key_fails(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness
        profile = synpareia.generate()
        block = synpareia.create_block(profile, type="message", content=b"x")
        seal = _run(witness_seal_timestamp(block_hash_hex=block.content_hash.hex(), ctx=ctx))

        imposter_pubkey = synpareia.generate().public_key
        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=base64.b64encode(imposter_pubkey).decode(),
            target_block_hash_hex=block.content_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is False

    def test_tampered_signature_fails(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness
        profile = synpareia.generate()
        block = synpareia.create_block(profile, type="message", content=b"x")
        seal = _run(witness_seal_timestamp(block_hash_hex=block.content_hash.hex(), ctx=ctx))
        info = _run(witness_info(ctx=ctx))

        # Flip a byte in the signature
        sig_bytes = base64.b64decode(seal["witness_signature_b64"])
        mutated = bytes([sig_bytes[0] ^ 0x01]) + sig_bytes[1:]
        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=base64.b64encode(mutated).decode(),
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
            target_block_hash_hex=block.content_hash.hex(),
            ctx=ctx,
        )
        assert result["valid"] is False


class TestStateSealRoundtrip:
    def test_state_seal_roundtrip(self, app_ctx_with_witness) -> None:
        ctx, _ = app_ctx_with_witness

        profile = synpareia.generate()
        chain = synpareia.create_chain(profile, policy=synpareia.templates.cop(profile))
        block = synpareia.create_block(profile, type="message", content=b"hi")
        synpareia.append_block(chain, block)
        export = synpareia.export_chain(chain)

        seal = _run(
            witness_seal_state(
                chain_id=chain.id,
                chain_head_hex=export["head_hash"],
                ctx=ctx,
            )
        )
        assert "error" not in seal, seal

        info = _run(witness_info(ctx=ctx))

        result = witness_verify_seal(
            seal_type=seal["seal_type"],
            witness_id=seal["witness_id"],
            witness_signature_b64=seal["witness_signature_b64"],
            sealed_at=seal["sealed_at"],
            witness_public_key_b64=info["public_key_b64"],
            target_chain_id=chain.id,
            target_chain_head_hex=export["head_hash"],
            ctx=ctx,
        )
        assert result["valid"] is True


class TestZeroConfigWitness:
    def test_request_seal_without_witness_configured(self, app_ctx) -> None:
        ctx, _ = app_ctx
        result = _run(witness_seal_timestamp(block_hash_hex="ab" * 32, ctx=ctx))
        assert "error" in result
        # No stack trace leakage — must be a friendly diagnostic
        assert "SYNPAREIA_WITNESS_URL" in result["error"]
