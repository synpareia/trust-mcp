"""FastMCP application — the Synpareia Trust Toolkit MCP server."""

from __future__ import annotations

from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from mcp.server.fastmcp import FastMCP

from synpareia_trust_mcp.config import Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.journal import JournalStore
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
    journal_store: JournalStore
    witness_client: WitnessClient | None = None
    # Cached witness public key (b64), populated lazily the first time a seal
    # tool needs it for a self-describing `verify_followup`. The witness key is
    # stable, so we fetch it at most once per session.
    witness_pubkey_b64: str | None = None


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize profile and state on server startup."""
    config = Config.load()
    profile_manager = ProfileManager(config.data_dir, private_key_b64=config.private_key_b64)
    conversation_manager = ConversationManager(profile_manager, config.data_dir)
    journal_store = JournalStore(config.data_dir)

    # Generate or load the agent's identity (first run creates a new keypair)
    profile_manager.ensure_profile()

    # First-run disclosure (GDPR §6 data-protection-by-design). When a brand-new
    # identity is minted, tell the operator — on stderr, never stdout, which is
    # the stdio-MCP protocol channel — that an identity now exists locally and
    # that nothing has been sent anywhere. This matters more since 0.6 defaulted
    # the network ON: the operator should know the identity is local-only until
    # they make an explicit publishing call.
    if profile_manager.newly_generated:
        _emit_first_run_disclosure(config, profile_manager.profile.id)

    # Initialize witness client if URL is configured
    witness_client = _create_witness_client(config)

    try:
        yield AppContext(
            config=config,
            profile_manager=profile_manager,
            conversation_manager=conversation_manager,
            journal_store=journal_store,
            witness_client=witness_client,
        )
    finally:
        if witness_client is not None:
            await witness_client.close()


def _emit_first_run_disclosure(config: Config, did: str) -> None:
    """Print the first-run identity disclosure to stderr (GDPR §6).

    stderr, not stdout: stdout carries the stdio-MCP JSON-RPC stream and must
    not be polluted. MCP hosts surface a server's stderr in their logs, so this
    reaches the operator.
    """
    import sys

    profile_path = config.data_dir / "profile.json"
    print(
        "[synpareia-trust-mcp] Generated a new agent identity.\n"
        f"  DID:     {did}\n"
        f"  Stored:  {profile_path} (private key, mode 0600 — back it up; "
        "losing it loses the identity)\n"
        "  Network: nothing has been sent anywhere. Publishing to the "
        "synpareia directory is an explicit publish_profile call; witnessing "
        "is an explicit witness_* call.",
        file=sys.stderr,
        flush=True,
    )


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
Trust tools for dealings with other AI agents. When something is at stake — \
you're about to rely on another agent, prove something to one, or agree on \
something you may need evidence of later — call `orient` first; it maps your \
situation to the right tools. Also call `orient` after context loss to \
recover your identity and in-flight recordings.\
"""

mcp = FastMCP(
    "Synpareia Trust Toolkit",
    lifespan=app_lifespan,
    instructions=INSTRUCTIONS,
)
