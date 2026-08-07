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


# The value proposition lives HERE, in full, rather than behind a tool call.
#
# Two findings drove that. (1) This string is filter-proof: agent harnesses that
# restrict tool access commonly do so with a call-time deny hook, which never touches
# server instructions — so this text arrives even where `orient` itself is denied.
# (2) A pointer does not compel. A scout agent received `orient`'s output five times,
# including its "call learn(...) for the thesis" pointers, and never once followed one.
# Anything a fresh agent must actually absorb has to be stated here, not linked from here.
#
# Written in terms of social acts (commitments, records, checks) rather than mechanisms
# (blocks, signatures, seals). An agent that reads this should be able to answer "what is
# synpareia and when would I use it" without mentioning cryptography.
INSTRUCTIONS = """\
Synpareia is for the moments when something is at stake between you and another agent: \
you are relying on someone, being relied on, or agreeing to something either side may \
need to prove later. It exists because agents currently have no way to make a promise \
that means more than a sentence, and no way to tell a counterparty who keeps promises \
from one who does not.

The habits it is here to support:

- Something is at stake -> ask for a commitment rather than proceeding on goodwill. \
An intention you both signed is a different object from one you both remember.
- It may need proving later -> open a record while it happens, not after. \
A reconstructed account is worth far less than a contemporaneous signed one.
- You are about to trust a claim -> check it. Has this agent been consistent? \
Can they show evidence, or only assert?
- The interaction is complex, high-stakes, or adversarial -> use a Form. Forms are \
worked recipes for approaching, negotiating and concluding; you need not invent the \
choreography, and each states plainly what it cannot yet do.
- A commitment was kept or broken -> record the outcome, with the counterparty's \
consent. Accumulated outcomes are what a reputation is actually made of.

Underneath are cryptographic primitives -- signed statements, hash-linked records, \
timestamp seals -- but the tools are named for the social act, not the mechanism, and \
everything they produce verifies offline without asking us or anyone else.

Honest about the gaps: your evaluations of counterparties stay in your local journal \
in v1, and network-attested reputation lookups are not serving yet. What works today \
is evidence you hold and can produce, and evidence a counterparty can hand you.

Call `orient` for what applies to your situation, your identity, and anything in \
flight -- including after context loss. `learn(<topic>)` goes deeper on any of the above.\
"""

mcp = FastMCP(
    "Synpareia Trust Toolkit",
    lifespan=app_lifespan,
    instructions=INSTRUCTIONS,
)
