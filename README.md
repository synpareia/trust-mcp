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

17 tools across 7 areas. Start by calling `orient` — it summarises every area and points you to the relevant `learn` topic.

| Tool | What it does | Offline? |
|------|-------------|:-------:|
| `orient` | Discover all capabilities and which area fits your goal | Yes |
| `learn` | Get a focused guide for one area (usage, examples, pitfalls) | Yes |
| `make_claim` | Sign content with your private key — proves authorship | Yes |
| `verify_claim` | Verify another agent's signature, commitment, or identity claim | Yes |
| `prove_independence` | Commit to an assessment before seeing the other party's | Yes |
| `evaluate_agent` | Multi-provider trust evaluation (synpareia, Moltbook, MolTrust) | No |
| `recording_start` | Begin a verified interaction record | Yes |
| `recording_append` | Record a message or event | Yes |
| `recording_end` | Close and optionally rate | Yes |
| `recording_proof` | Export portable, verifiable proof | Yes |
| `recording_list` | List recordings (active and closed) | Yes |
| `witness_info` | Witness identity, public key, service URL | No |
| `witness_seal_timestamp` | Timestamp seal over a block hash | No |
| `witness_seal_state` | State seal over a chain head | No |
| `witness_verify_seal` | Offline verification of either seal type | Yes |
| `witness_submit_blind` | Submit a blind conclusion through the witness | No |
| `witness_get_blind` | Retrieve a prior blind conclusion | No |

14 of 17 tools work fully offline. The three network-touching tools (`evaluate_agent`, and the `witness_*` request tools) need a reachable provider or witness service.

### Upgrading from 0.2.0

The tool surface was reshaped in 0.3.0. `sign_content` → `make_claim`, `verify_signature` → `verify_claim`, `start_conversation`/`end_conversation` → `recording_start`/`recording_end`, and so on. See `CHANGELOG.md` for the full migration table — old names were removed outright, no shim.

## How It Works

The Trust Toolkit is built on [synpareia](https://pypi.org/project/synpareia/) — cryptographic primitives for AI agent identity. Your agent gets an Ed25519 keypair and a DID (Decentralized Identifier). Every signed statement is verifiable. Every conversation is hash-linked and tamper-evident.

**Identity is local.** Derived from your cryptographic keys, not from a server. Works offline, portable across platforms.

**Trust builds over time.** Each verified conversation adds to your agent's reputation. The more agents that participate, the more meaningful reputation becomes.

**Privacy by default.** Selective disclosure means your agent controls exactly what's visible, and to whom.

## Example Scenarios

### Verifying a counterparty

Your agent is about to delegate a task to another agent. First, check trust across every configured provider:

```
-> evaluate_agent(namespace="synpareia", id="did:synpareia:a1b2c3...")

tier1: (none — no prior contact in your local journal)
tier2: (namespace=synpareia has no Tier-2 adapter)
tier3:
  synpareia — reputation 0.92, 47 verified conversations, member since 2026-03
  moltrust  — score 4.6/5 across 18 ratings
tier4_available: true  (synpareia DID — encode_signed / decode_signed work)
```

### Making a provably independent assessment

Two agents need to rate a proposal independently:

```
-> prove_independence("Rating: 4/5 -- strong technical approach, weak go-to-market")

Committed. commitment_hash: 7f3a...  nonce_b64: cH/iD5Pm...
Share ONLY the hash. Keep the nonce secret until reveal.

[... other agent reveals their rating ...]

-> verify_claim(claim_type="commitment", commitment_hash="7f3a...",
                content="Rating: 4/5 -- strong technical approach, weak go-to-market",
                nonce_b64="cH/iD5Pm...")

Verified: content matches the sealed commitment.
The assessment was committed before being revealed.
```

### Recording an important interaction

```
-> recording_start("Task delegation negotiation with Agent Y")

Recording. Recording ID: rec_x7y8z9

[... interaction happens, recording_append for each exchange ...]

-> recording_end("rec_x7y8z9", rating=4, notes="Delivered on time, good quality")

Recording closed. 12 blocks, signed and hash-linked.

-> recording_proof("rec_x7y8z9")

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

## Data, storage, and privacy

The Trust Toolkit is **local-first**. Every file the toolkit creates lives under
`SYNPAREIA_DATA_DIR` (default `~/.synpareia`) on the machine running your agent;
nothing is sent off-machine unless you explicitly configure a network endpoint.

What's stored:

- **Profile** (`profile.json`, mode `0600`) — your agent's Ed25519 keypair and
  display name. The private key never leaves the file.
- **Conversation chains** (`conversations/<chain_id>/`) — your agent's signed
  records of conversations and claims, linked into a chain so any tampering is
  detectable.
- **Counterparty journal** (`counterparties.json`, mode `0600`) — your agent's
  notes about other agents you've encountered: their IDs, your evaluations,
  signed claims they've made to you. **This is your local log; entries are
  visible only to you and your agent.** Other agents do not see your journal.
  When you record an evaluation about a counterparty, that observation stays on
  your disk — there is no automatic upload, no shared reputation database, no
  cross-agent broadcast.
- **Recordings** (`recordings/<id>/`) — full message-by-message logs of
  conversations you explicitly asked the toolkit to record. Same locality
  guarantees.

What flows off-machine (only with explicit configuration):

- **Tier-2 platform queries** — if `SYNPAREIA_MOLTBOOK_API_URL` or other
  Tier-2 adapter URLs are set, `check_media_signals` calls those endpoints with
  the counterparty's handle. Otherwise, no network calls.
- **Tier-3 attestation queries** — if `SYNPAREIA_NETWORK_URL` or
  `SYNPAREIA_MOLTRUST_API_KEY` are set, `attested_reputation` queries those
  services. Otherwise, no network calls.
- **Witness service** — if `SYNPAREIA_WITNESS_URL` is set, the `witness_*`
  tools talk to that service to obtain timestamp seals. The witness only sees
  hashes and signatures, never your content. The current synpareia witness is
  sparse-witness (Position 4): it does not persist `requester_id`, so the
  attestation is not linkable to your identity beyond what you re-link
  yourself.

Subject-rights / GDPR notes (where the GDPR applies to your agent's
operations):

- All journal data lives on the data subject's own machine. Erasure is
  achieved by deleting the relevant record (`forget_counterparty` is on the
  v0.5 roadmap; today, edit `counterparties.json` directly).
- The toolkit imposes no retention period — observations persist until you
  delete them. If your operating environment requires a maximum retention,
  enforce it externally.
- The toolkit creates no shadow profiles: counterparties are recorded only
  when your agent explicitly calls `remember_counterparty`. There is no
  ambient observation.

This is not legal advice; review with counsel for your specific deployment.

## Built on

- [synpareia](https://pypi.org/project/synpareia/) — cryptographic primitives (Ed25519, SHA-256, hash-linked chains)
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol for AI tool integration

## License

Apache 2.0
