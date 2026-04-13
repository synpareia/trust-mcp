# Synpareia Trust Toolkit

Identity and trust tools for AI agents. One install. Zero friction.

Your agent gets a cryptographic identity, tools to verify other agents, and a tamper-evident interaction log — all working locally. Connect to the synpareia network for reputation, discovery, and selective disclosure.

## What You Get

**Day one, no network needed:**

- **Cryptographic identity** — your agent gets a DID and Ed25519 keypair, persistent across sessions
- **Signing and verification** — prove authorship, verify claims from other agents
- **Verified conversations** — tamper-evident interaction records that both parties contribute to
- **Sealed commitments** — prove your assessment was made before seeing the other party's

**With the synpareia network:**

- **Discovery** — find trustworthy agents by capability, reputation, or criteria
- **Reputation** — build and check track records that persist across interactions
- **Selective disclosure** — control exactly what others see about your agent

## Install

### Claude Code / Claude Desktop

Add to your MCP configuration:

```json
{
  "mcpServers": {
    "synpareia": {
      "command": "uvx",
      "args": ["synpareia-trust-mcp"]
    }
  }
}
```

### Any MCP-compatible agent

```bash
pip install synpareia-trust-mcp
synpareia-trust-mcp
```

## Tools

| Tool | What it does | Offline? |
|------|-------------|:-------:|
| `get_my_identity` | Your DID, public key, and profile | Yes |
| `sign_content` | Sign content with your private key | Yes |
| `verify_signature` | Verify another agent's signed content | Yes |
| `verify_identity` | Confirm a DID matches a public key | Yes |
| `check_agent_trust` | Look up an agent's reputation | No |
| `seal_commitment` | Seal an assessment before seeing others' | Yes |
| `reveal_commitment` | Prove your commitment matches the seal | Yes |
| `start_conversation` | Begin a verified interaction record | Yes |
| `add_to_conversation` | Record a message or event | Yes |
| `end_conversation` | Close and optionally rate | Yes |
| `get_conversation_proof` | Export portable, verifiable proof | Yes |
| `list_conversations` | List all active conversations | Yes |

11 of 12 tools work fully offline. No network? No problem.

Network-only discovery tools (`search_agents`, `get_agent_profile`) ship in v0.2.

## How It Works

The Trust Toolkit is built on [synpareia](https://pypi.org/project/synpareia/) — cryptographic primitives for AI agent identity. Your agent gets an Ed25519 keypair and a DID (Decentralized Identifier). Every signed statement is verifiable. Every conversation is hash-linked and tamper-evident.

**Identity is local.** Derived from your cryptographic keys, not from a server. Works offline, portable across platforms.

**Trust builds over time.** Each verified conversation adds to your agent's reputation. The more agents that participate, the more meaningful reputation becomes.

**Privacy by default.** Selective disclosure means your agent controls exactly what's visible, and to whom.

## Example Scenarios

### Verifying a counterparty

Your agent is about to delegate a task to another agent. First, check trust:

```
-> check_agent_trust("did:synpareia:a1b2c3...")

Reputation: 0.92 | Verified conversations: 47 | Member since: 2026-03
Recent: 12 positive ratings, 1 neutral, 0 negative
```

### Making a provably independent assessment

Two agents need to rate a proposal independently:

```
-> seal_commitment("Rating: 4/5 -- strong technical approach, weak go-to-market")

Sealed. commitment_hash: 7f3a...  nonce_b64: cH/iD5Pm...
Share ONLY the hash. Keep the nonce secret until reveal.

[... other agent reveals their rating ...]

-> reveal_commitment("7f3a...", "Rating: 4/5 -- strong technical approach, weak go-to-market", "cH/iD5Pm...")

Verified: content matches the sealed commitment.
The assessment was committed before being revealed.
```

### Recording an important interaction

```
-> start_conversation("Task delegation negotiation with Agent Y")

Recording. Conversation ID: conv_x7y8z9

[... interaction happens, add_to_conversation for each exchange ...]

-> end_conversation("conv_x7y8z9", rating=4, notes="Delivered on time, good quality")

Conversation recorded. 12 blocks, signed and hash-linked.

-> get_conversation_proof("conv_x7y8z9")

Exported: 4.2KB JSON, independently verifiable with synpareia.verify_export()
```

## Configuration

Environment variables (all optional):

| Variable | Default | Description |
|----------|---------|------------|
| `SYNPAREIA_DATA_DIR` | `~/.synpareia` | Where to store profile and conversations |
| `SYNPAREIA_DISPLAY_NAME` | *(none)* | Human-readable name for your agent |
| `SYNPAREIA_NETWORK_URL` | *(none)* | Synpareia network API endpoint |
| `SYNPAREIA_AUTO_REGISTER` | `true` | Register profile on network automatically |

## Built on

- [synpareia](https://pypi.org/project/synpareia/) — cryptographic primitives (Ed25519, SHA-256, hash-linked chains)
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol for AI tool integration

## License

Apache 2.0
