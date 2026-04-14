"""FastMCP application — the Synpareia Trust Toolkit MCP server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager

try:
    from synpareia.witness.client import WitnessClient
except ImportError:
    WitnessClient = None  # type: ignore[assignment,misc]

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


@dataclass
class AppContext:
    """Shared state available to all tools via ctx.request_context.lifespan_context."""

    config: Config
    profile_manager: ProfileManager
    conversation_manager: ConversationManager
    witness_client: WitnessClient | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize profile and state on server startup."""
    config = Config.load()
    profile_manager = ProfileManager(config.data_dir)
    conversation_manager = ConversationManager(profile_manager, config.data_dir)

    # Generate or load the agent's identity (first run creates a new keypair)
    profile_manager.ensure_profile()

    # Initialize witness client if URL is configured
    witness_client = _create_witness_client(config)

    try:
        yield AppContext(
            config=config,
            profile_manager=profile_manager,
            conversation_manager=conversation_manager,
            witness_client=witness_client,
        )
    finally:
        if witness_client is not None:
            await witness_client.close()


def _create_witness_client(config: Config) -> WitnessClient | None:
    """Create a WitnessClient if the witness URL is configured and httpx is available."""
    if not config.witness_url:
        return None
    if WitnessClient is None:
        return None

    import httpx

    headers = {}
    if config.witness_token:
        headers["X-Access-Token"] = config.witness_token

    http_client = httpx.AsyncClient(
        base_url=config.witness_url,
        timeout=10.0,
        headers=headers,
    )
    client = WitnessClient.__new__(WitnessClient)
    client._base_url = config.witness_url
    client._client = http_client
    return client


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

Witness attestation (requires SYNPAREIA_WITNESS_URL):
- `get_witness_info` -- get the witness service's identity
- `request_timestamp_seal` -- get an independent timestamp on a block
- `request_state_seal` -- checkpoint a chain's state with the witness
- `verify_seal_offline` -- verify a seal without contacting the witness
- `submit_blind_conclusion` / `get_blind_conclusion` -- coordinate independent assessments

These tools are optional. Use them when trust and verification matter.\
"""

mcp = FastMCP(
    "Synpareia Trust Toolkit",
    lifespan=app_lifespan,
    instructions=INSTRUCTIONS,
)
