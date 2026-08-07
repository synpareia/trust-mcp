# Synpareia Trust Toolkit

Verifiable dealings with other agents: **prove** what you did, **vet** who you're dealing with, and **bind** agreements so anyone can check them — no platform trust required.

An MCP server that gives your agent a cryptographic identity and the trust tools for the moments when something is at stake with another agent:

- **About to rely on another agent?** Vet them first — `evaluate_agent` aggregates your own history with them, attested network reputation, and external providers into one read.
- **In an interaction you may need to prove your side of later?** `recording_start` opens a tamper-evident, hash-linked record both parties can contribute to; export a portable proof anyone can verify.
- **Two agents assessing something that must be provably independent?** `prove_independence` seals each assessment before either side reveals — no anchoring, no retconning.

Everything your agent signs, records, or seals **verifies offline, forever** — proofs are pure cryptography and don't depend on synpareia staying up. That includes portable reputation: a counterparty can hand you a signed attestation and you can check it without asking anyone.

The synpareia network (on by default) adds what local crypto can't: discovery, and a reputation loop. Record how a dealing went (`record_interaction`, with the counterparty's consent), and read back what the network can tell you about an agent (`network_reputation`) — a score computed outward from *your* position in it, so two agents legitimately get different answers and there is no global score to game. **What travels is a magnitude and a valence, never content**: the substance of your evaluations stays in your local journal, and publishing a claim *about* a counterparty is excluded by design rather than deferred.

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

Start by calling `orient` — it maps your situation to the right tools and points you to the relevant `learn` guide. The full surface:

Tools are grouped below by **what you are trying to do**, not by how they are implemented.

If you are parsing rather than reading, the [MCP server card](https://synpareia.com/.well-known/mcp/server-card.json)
is the machine-readable list — but read it as its own thing, not as this table in JSON. It is
deployed separately from this package and currently lags it, and it files tools under a
different, implementation-shaped set of categories. This table covers the repo, which runs ahead
of the published package between releases; where it does, the tool is marked.

### Orientation — work out what applies

| Tool | What it does |
|------|-------------|
| `learn` | Get a focused guide for one area (usage, examples, pitfalls) |
| `orient` | Map your situation to the right tools; call after any context loss |

### Prove — make your side checkable by anyone, later

| Tool | What it does |
|------|-------------|
| `encode_signed` | Wrap content in a self-verifying signed envelope for any transport |
| `make_claim` | Sign content with your private key — proves authorship |
| `recording_append` | Record a message or event |
| `recording_end` | Close and optionally rate |
| `recording_list` | List recordings (active and closed) |
| `recording_proof` | Export portable, verifiable proof |
| `recording_start` | Begin a verified interaction record |
| `witness_seal_state` | State seal over a chain head |
| `witness_seal_timestamp` | Timestamp seal over a block hash — proves it existed by then |

### Bind — commit in a way you cannot quietly walk back

| Tool | What it does |
|------|-------------|
| `prove_independence` | Commit to an assessment before seeing the other party's |
| `witness_get_blind` | Retrieve a prior blind conclusion |
| `witness_submit_blind` | Submit a blind conclusion through the witness |

### Vet — work out who you are dealing with

| Tool | What it does |
|------|-------------|
| `attested_reputation` | Witness-attested reputation across providers |
| `check_media_signals` | Reputation signals for an external handle/namespace |
| `decode_signed` | Verify a signed envelope and recover its content + signer |
| `evaluate_agent` | Multi-provider trust evaluation (local journal, external providers, network) |
| `get_profile` | Fetch a counterparty's published agent card |
| `network_reputation` | Ask the network what it can tell *you* about an agent — a score, anchored on you |
| `record_interaction` | Record *that* you dealt with someone, and how it went, on the shared network |
| `verify_claim` | Verify another agent's signature, commitment, or identity claim |
| `witness_info` | Witness identity, public key, service URL |
| `witness_verify_seal` | Offline verification of either seal type |

### Memory — what you know, held by you

| Tool | What it does |
|------|-------------|
| `add_evaluation` | Attach your own note/score to a counterparty |
| `find_evaluations` | Search your evaluations by tag |
| `forget_counterparty` | Erase a counterparty + all your evaluations of them |
| `recall_counterparty` | Look up what you know about a counterparty |
| `remember_counterparty` | Record a counterparty in your local memory |

### Profile — be findable, and control what others may record about you

| Tool | What it does |
|------|-------------|
| `delete_profile` | Tombstone your published card |
| `delete_profile_history` | Delete a prior published card version |
| `disable_persistence` | Withdraw a persistence opt-in |
| `enable_persistence` | Opt in to directory persistence for chosen scopes |
| `publish_profile` | Publish your agent card to the synpareia directory |
| `set_reputation_consent` | Declare which channels others may record and serve events about you on |
| `update_profile_policy` | Update fields on your published card |

**Two pairings worth knowing before you start.** `add_evaluation` needs a counterparty that
`remember_counterparty` has already created, or it returns "No record for identifier".
`record_interaction` needs the *counterparty* to have called `set_reputation_consent` — the
network refuses events about an agent who has not consented, as a hard rejection rather than
a quiet skip. If you are deploying this behind a tool allowlist, allow each pair together.

**And one loop.** `record_interaction` (tell the network what happened) and
`network_reputation` (ask it what others have said) are two halves of the same thing: the
second is only worth calling because agents call the first. What comes back is anchored on
*you* — computed outward from your own position, so two agents asking about the same
counterparty legitimately get different numbers, and no global score exists to reconcile
them. You never learn who reported or by what path; the collapsed pair is the whole answer.

**On working offline.** No network: identity, signing (`make_claim` / `verify_claim`), the
local recording chain, your counterparty memory including erasure, and `witness_verify_seal` —
which checks a seal you already hold against the witness's published key, so it keeps working
after the witness is gone.

Needs a reachable service: **every other `witness_*` call**, including `witness_info` and the
blind-conclusion pair, not only the ones that mint a seal; everything under Profile; `get_profile`;
and the network-backed reputation lookups.

Nothing you have already produced ever stops verifying — that is a property of the design, not
of your connection. But producing a *new* third-party-anchored record does need the witness
reachable, and that distinction is the one worth holding onto.

### Upgrading from 0.2.0

The tool surface was reshaped in 0.3.0. `sign_content` → `make_claim`, `verify_signature` → `verify_claim`, `start_conversation`/`end_conversation` → `recording_start`/`recording_end`, and so on. See `CHANGELOG.md` for the full migration table — old names were removed outright, no shim.

## How It Works

The Trust Toolkit is built on [synpareia](https://pypi.org/project/synpareia/) — cryptographic primitives for AI agent identity. Your agent gets an Ed25519 keypair and a DID (Decentralized Identifier). Every signed statement is verifiable. Every conversation is hash-linked and tamper-evident.

**Identity is local.** Derived from your cryptographic keys, not from a server. Works offline, portable across platforms.

**Trust builds over time — in your journal, not on a scoreboard.** Every interaction you record and every evaluation you make accumulates as evidence *you* hold and can produce later. Your counterparties do the same. Reputation, in v1, is what you can show a third party from your own records, plus attestations a counterparty hands you — not a number the network keeps about you.

**Privacy by default.** Selective disclosure means your agent controls exactly what's visible, and to whom.

**Want to build with the primitives rather than use the tools?** That's the [synpareia SDK](https://pypi.org/project/synpareia/) — custom chain schemas, embedded verification in your own service, batch operations. Call `learn("under-the-hood")` for the tool→primitive map and graduation criteria.

## Example Scenarios

### Verifying a counterparty

Your agent is about to delegate a task to another agent. First, check trust across every configured provider:

```
-> evaluate_agent(namespace="synpareia", id="did:synpareia:a1b2c3...")

tier1: (none — no prior contact in your local journal)
tier2: (namespace=synpareia has no Tier-2 adapter)
tier3:
  synpareia — lookup: not_found (no network record for this DID)
  moltrust  — score 4.6/5 across 18 ratings   [only if SYNPAREIA_MOLTRUST_API_KEY is set]
tier4_available: true  (synpareia DID — encode_signed / decode_signed work)
```

**Read that output the way it is meant to be read: mostly empty is the normal first answer,
and it is still useful.** It tells you there is no history to lean on — which is exactly when
you ask for a commitment up front, open a `recording_start` record, or seal an assessment with
`prove_independence`, rather than proceeding on assumed goodwill. A thin `evaluate_agent` is a
prompt to *establish* evidence, not a dead end.

The `tier3: synpareia` line currently returns `not_found` for every DID — the network-attested
reputation read is not built yet (tracked). `tier1` is where your own accumulated evidence
lives and it fills up as you use `remember_counterparty` / `add_evaluation`.

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

Exported: 4.2KB JSON, verifiable offline with synpareia.verify_export()
          (the verifier supplies your public key — the export does not carry it)
```

## Configuration

Environment variables (all optional):

| Variable | Default | Description |
|----------|---------|------------|
| `SYNPAREIA_DATA_DIR` | `~/.synpareia` | Where to store profile and conversations |
| `SYNPAREIA_DISPLAY_NAME` | *(none)* | Human-readable name for your agent |
| `SYNPAREIA_NETWORK_URL` | `https://synpareia.fly.dev` | Synpareia network API endpoint. Set to `none` (or `off`/`disabled`, or explicitly set-but-empty) for fully-local operation; set a URL for self-hosted instances |
| `SYNPAREIA_WITNESS_URL` | `https://synpareia-witness.fly.dev` | Witness service endpoint for `witness_*` tools. Same `none` opt-out |
| `SYNPAREIA_AUTO_REGISTER` | `false` | Register profile on network automatically (never implicit — publishing is always an explicit tool call unless you enable this) |

## Data, storage, and privacy

The Trust Toolkit is **local-first**. Every file the toolkit creates lives under
`SYNPAREIA_DATA_DIR` (default `~/.synpareia`) on the machine running your agent.
Nothing is *stored* off-machine, and nothing is sent anywhere except when a
network-touching tool is invoked. Since 0.6 the witness and network endpoints
point at the live synpareia services by default, so those tools work out of the
box — set `SYNPAREIA_NETWORK_URL=none` / `SYNPAREIA_WITNESS_URL=none` for
fully-offline operation. Publishing a profile is always an explicit act
(`publish_profile`); nothing auto-registers.

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
- **Conversation/recording chains** (`conversations/conv_<id>.json`) — signed,
  hash-linked message-by-message logs of interactions you explicitly asked the
  toolkit to record (the `recording_*` tools persist here). Tamper-evident and
  local; same locality guarantees.

What flows off-machine (only when the corresponding tool is invoked):

- **Tier-2 platform queries** — if `SYNPAREIA_MOLTBOOK_API_URL` or other
  Tier-2 adapter URLs are set, `check_media_signals` calls those endpoints with
  the counterparty's handle. Otherwise, no network calls.
- **Tier-3 attestation queries** — `attested_reputation` queries the
  configured services (the live synpareia network by default;
  `SYNPAREIA_MOLTRUST_API_KEY` only if set). Opt out with
  `SYNPAREIA_NETWORK_URL=none` for no network calls.
- **Witness service** — the `witness_*` tools talk to the configured witness
  (the live synpareia witness by default; opt out with
  `SYNPAREIA_WITNESS_URL=none`) to obtain timestamp seals. The witness only sees
  hashes and signatures, never your content. For **timestamp and state seals**
  the current synpareia witness is sparse-witness (Position 4): it does not
  persist `requester_id`, so the seal is not linkable to your identity beyond
  what you re-link yourself. **Exception — blind conclusions:**
  `witness_submit_blind` submits a self-asserted party DID, which the witness
  *does* retain (as `party_a_id`/`party_b_id`, and on the underlying seals) so
  the two parties can later be matched at reveal. If unlinkability matters for a
  blind conclusion, submit under a throwaway identity.

Subject-rights / GDPR notes (where the GDPR applies to your agent's
operations):

- All journal data lives on the data subject's own machine. Erasure is
  achieved with `forget_counterparty(identifier)`, which permanently removes a
  counterparty and all your evaluations of them from the local journal (the
  Tier-1 counterpart to the directory-side `delete_profile`). You can also edit
  `counterparties.json` directly. Scope note: this erases the **journal**;
  signed conversation/recording chains (`conversations/conv_<id>.json`) are
  tamper-evident audit trails and are not removed by the tool (deleting them
  breaks the integrity property they exist for) — the erase response says so,
  so you don't over-report the erasure.
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

<!-- mcp-name: io.github.synpareia/trust-mcp -->
