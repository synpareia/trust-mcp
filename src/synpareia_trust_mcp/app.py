"""FastMCP application — the Synpareia Trust Toolkit MCP server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class AppContext:
    """Shared state available to all tools via ctx.request_context.lifespan_context."""

    config: Config
    profile_manager: ProfileManager
    conversation_manager: ConversationManager


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize profile and state on server startup."""
    config = Config.load()
    profile_manager = ProfileManager(config.data_dir)
    conversation_manager = ConversationManager(profile_manager, config.data_dir)

    # Generate or load the agent's identity (first run creates a new keypair)
    profile_manager.ensure_profile()

    yield AppContext(
        config=config,
        profile_manager=profile_manager,
        conversation_manager=conversation_manager,
    )


INSTRUCTIONS = """\
You have the Synpareia Trust Toolkit installed, giving you a verifiable \
cryptographic identity and trust tools for agent interactions.

Your identity:
- You have a DID (Decentralized Identifier) and Ed25519 keypair
- Use `get_my_identity` to see your credentials
- Use `sign_content` to create verifiable signed statements

When interacting with other agents:
- `check_agent_trust` -- look up their reputation (requires network)
- `verify_signature` -- verify their signed claims
- `start_conversation` -- record important interactions as tamper-evident chains
- `seal_commitment` / `reveal_commitment` -- prove assessments were independent

These tools are optional. Use them when trust and verification matter.\
"""

mcp = FastMCP(
    "Synpareia Trust Toolkit",
    lifespan=app_lifespan,
    instructions=INSTRUCTIONS,
)
