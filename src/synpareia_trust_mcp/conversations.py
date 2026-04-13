"""Conversation state management — start, record, end, export."""

from __future__ import annotations

import base64
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import synpareia

from synpareia_trust_mcp.profile import ProfileManager


@dataclass
class ActiveConversation:
    """An in-progress verified conversation."""

    conversation_id: str
    chain: synpareia.Chain
    description: str
    counterparty: str | None
    started_at: datetime
    block_count: int = 0


class ConversationManager:
    """Manages conversation lifecycle: start, record, end, export."""

    def __init__(self, profile_manager: ProfileManager, data_dir: Path) -> None:
        self._pm = profile_manager
        self._data_dir = data_dir
        self._active: dict[str, ActiveConversation] = {}

    def start(
        self,
        description: str,
        counterparty: str | None = None,
    ) -> ActiveConversation:
        """Start a new verified conversation."""
        conversation_id = f"conv_{uuid.uuid4().hex[:12]}"
        chain = synpareia.create_chain(
            self._pm.profile,
            chain_type=synpareia.ChainType.SPHERE,
        )

        start_block = synpareia.create_block(
            self._pm.profile,
            type=synpareia.BlockType.SYSTEM,
            content=json.dumps(
                {
                    "event": "conversation_started",
                    "description": description,
                    "counterparty": counterparty,
                }
            ).encode(),
        )
        synpareia.append_block(chain, start_block)

        conv = ActiveConversation(
            conversation_id=conversation_id,
            chain=chain,
            description=description,
            counterparty=counterparty,
            started_at=datetime.now(UTC),
            block_count=1,
        )
        self._active[conversation_id] = conv
        return conv

    def add_message(
        self,
        conversation_id: str,
        content: str,
        block_type: str = "message",
        metadata: dict | None = None,
    ) -> int:
        """Add a block to an active conversation. Returns the new block count."""
        conv = self._get_active(conversation_id)
        block = synpareia.create_block(
            self._pm.profile,
            type=block_type,
            content=content.encode(),
            metadata=metadata,
        )
        synpareia.append_block(conv.chain, block)
        conv.block_count += 1
        return conv.block_count

    def end(
        self,
        conversation_id: str,
        rating: int | None = None,
        notes: str | None = None,
    ) -> dict:
        """End a conversation, persist it, and return summary."""
        conv = self._get_active(conversation_id)

        end_data: dict[str, object] = {"event": "conversation_ended"}
        if rating is not None:
            end_data["rating"] = rating
        if notes is not None:
            end_data["notes"] = notes

        end_block = synpareia.create_block(
            self._pm.profile,
            type=synpareia.BlockType.SYSTEM,
            content=json.dumps(end_data).encode(),
        )
        synpareia.append_block(conv.chain, end_block)
        conv.block_count += 1

        export = synpareia.export_chain(conv.chain)
        self._persist_conversation(conversation_id, export)
        del self._active[conversation_id]

        return {
            "conversation_id": conversation_id,
            "blocks": conv.block_count,
            "duration_seconds": (datetime.now(UTC) - conv.started_at).total_seconds(),
            "chain_id": conv.chain.id,
            "head_hash": export.get("head_hash", ""),
        }

    def export(self, conversation_id: str) -> dict:
        """Export an active conversation as verifiable JSON."""
        conv = self._get_active(conversation_id)
        return synpareia.export_chain(conv.chain)

    def seal_commitment(self, content: str) -> dict:
        """Create a sealed commitment. Returns the hash and nonce to the caller.

        Following the standard commit-reveal pattern (ENS, sealed-bid auctions),
        the caller holds the nonce. The server is stateless for commitments,
        which means they survive MCP server restarts (stdio servers are often
        spawned fresh per-connection).
        """
        commitment_block, nonce = synpareia.create_commitment_block(
            self._pm.profile,
            content=content.encode(),
        )
        assert commitment_block.content is not None  # commitment blocks always have content
        commitment_hash_hex = commitment_block.content.hex()

        return {
            "commitment_hash": commitment_hash_hex,
            "nonce_b64": base64.b64encode(nonce).decode(),
            "block_id": commitment_block.id,
            "instructions": (
                "Share ONLY the commitment_hash with the other party. "
                "Keep the nonce_b64 secret until reveal time. "
                "Call reveal_commitment with commitment_hash, original content, "
                "and nonce_b64 to prove your assessment was independent."
            ),
        }

    def reveal_commitment(
        self,
        commitment_hash_hex: str,
        original_content: str,
        nonce_b64: str,
    ) -> dict:
        """Reveal a previous commitment and verify it matches."""
        try:
            nonce = base64.b64decode(nonce_b64)
            commitment_bytes = bytes.fromhex(commitment_hash_hex)
            valid = synpareia.verify_commitment(
                commitment_bytes,
                original_content.encode(),
                nonce,
            )
        except Exception as e:
            return {"valid": False, "error": str(e)}

        return {
            "valid": valid,
            "commitment_hash": commitment_hash_hex,
            "content": original_content,
            "explanation": (
                "Verified: this content matches the sealed commitment. "
                "The assessment was committed before being revealed."
                if valid
                else "MISMATCH: the content does not match the commitment."
            ),
        }

    def list_active(self) -> list[dict]:
        """List all active conversations."""
        return [
            {
                "conversation_id": c.conversation_id,
                "description": c.description,
                "counterparty": c.counterparty,
                "started_at": c.started_at.isoformat(),
                "block_count": c.block_count,
            }
            for c in self._active.values()
        ]

    def _get_active(self, conversation_id: str) -> ActiveConversation:
        conv = self._active.get(conversation_id)
        if conv is None:
            active = list(self._active.keys()) or "(none)"
            msg = f"No active conversation '{conversation_id}'. Active: {active}"
            raise ValueError(msg)
        return conv

    def _persist_conversation(self, conversation_id: str, export: dict) -> None:
        conv_dir = self._data_dir / "conversations"
        conv_dir.mkdir(parents=True, exist_ok=True)
        path = conv_dir / f"{conversation_id}.json"
        path.write_text(json.dumps(export, indent=2))
