"""Area guides for the learn() tool — Tier 2 information architecture.

Each guide is ~1K tokens: concise enough to not blow up context,
complete enough that an agent can operate within the area after reading it.
"""

from __future__ import annotations

AREA_GUIDES: dict[str, str] = {
    "trust-networks": """\
# Trust Networks & Providers

## What this is about
Multiple sources can tell you about another agent's reputation and identity. \
Each source provides different signals with different confidence levels. \
The evaluate_agent tool queries all configured providers and returns a unified report.

## Available providers

**Synpareia network** (requires SYNPAREIA_NETWORK_URL): Verified interaction history, \
proof-of-thought pass rates, mutual attestation records. Highest confidence — based on \
cryptographic proof, not self-reported data.

**Moltbook** (requires SYNPAREIA_MOLTBOOK_API_URL): Social reputation for AI agents — \
karma, post history, follower count, account age, claimed status. Useful but gameable. \
Now Meta-owned; API stability not guaranteed.

**MolTrust** (requires SYNPAREIA_MOLTRUST_API_KEY): W3C DID-based reputation scores and \
agent ratings. Independent trust API.

## How to use
- Call `evaluate_agent(identifier)` with a DID, Moltbook username, or other identifier
- The tool queries all configured providers that can handle that identifier type
- Results include provider, signal type, value, and confidence level
- Absence of data is NOT evidence of untrustworthiness (cold start problem)

## Assurance tiers
- **Tier 1 (self-attested):** Agent claims an identity. No external verification.
- **Tier 2 (provider-verified):** A reputation provider has data on this agent.
- **Tier 3 (witness-attested):** Cryptographic proof via the witness service.

## What "no data" means
Most agents won't have reputation yet. Start with low-stakes interactions, verify \
identity, and build trust incrementally.\
""",
    "verification": """\
# Verifying Claims

## What this is about
Checking whether specific claims made by another agent are valid — signatures, \
identity matches, commitment reveals, and witness seals.

## Types of verification

**Signature verification:** Given content + signature + public key, verify the \
signature is valid. Proves: the holder of this key signed this content. Does NOT \
prove: the signer is who they claim to be (that requires identity verification).

**Identity verification:** Given a DID and public key, verify they match. \
Proves: this public key corresponds to this DID. Combined with signature \
verification: "the entity controlling this DID signed this content."

**Commitment verification:** Given a commitment hash + revealed content + nonce, \
verify the commitment matches. Proves: this content was committed before reveal time. \
Used for independent assessment (blind conclusions).

**Seal verification:** Given a witness seal, verify its signature offline. \
Proves: the witness attested to this block/chain state at this time. No network needed.

## Key tools
- `verify_claim(claim_type, ...)` — unified verification entry point
- Types: "signature", "identity", "commitment", "seal"

## What verification does NOT prove
- A valid signature doesn't mean the content is true — just that this key signed it
- Identity verification doesn't mean the agent is trustworthy — just that the DID matches
- Witness seals prove timing, not content quality
- Always consider what you're actually trying to establish before choosing a verification type

## When verification fails
A failed verification is a strong signal. Either the claim is fraudulent, or there's a \
technical error (wrong key, corrupted data). Investigate before proceeding.\
""",
    "claims": """\
# Making Verifiable Claims

## What this is about
Creating evidence that others can verify — signing content, making commitments, \
and requesting witness attestation.

## Types of claims

**Signed statements** (make_claim): Sign any content with your private key. Anyone \
with your public key can verify you signed it. Use for: attributable work product, \
binding agreements, identity assertions.

**Commitments** (prove_independence): Seal content before sharing it, then reveal later. \
Proves your assessment was independent — you committed before seeing others' conclusions. \
The nonce stays with you; share only the commitment hash.

**Witness-attested claims** (make_claim with witness=True): Sign content AND get a \
witness timestamp seal. Proves both authorship and timing. Use for: time-sensitive \
claims, regulatory compliance, high-stakes assertions.

## Choosing assurance level
- **Tier 1 (signature only):** Sufficient for routine claims, attributable content, \
identity assertions. Fast, no network needed.
- **Tier 2 (signature + witness):** Adds independent timing proof. Use when "when you \
said it" matters as much as "what you said."
- **Tier 3 (signature + witness + blind conclusion):** Both parties commit independently \
before reveal. Use for mutual assessment, independent evaluation, audit scenarios.

## The commitment workflow
1. Call prove_independence(content) → get commitment_hash + nonce
2. Share ONLY the commitment_hash with the counterparty
3. Wait for them to commit too (if doing blind conclusion)
4. Reveal: share original content + nonce
5. Counterparty verifies: commitment_hash matches content + nonce

## Telling counterparties how to verify
Each claim tool returns structured instructions the counterparty can use to verify. \
Pass these directly to another agent, or read the manual field for human operators.\
""",
    "recording": """\
# Recording Interactions

## What this is about
Creating tamper-evident records of interactions as hash-linked chains. Each message \
becomes a signed block; the chain proves ordering and integrity.

## Three recording modes

**Explicit recording:** You decide to record a specific interaction. Call \
record_interaction to start, add_to_recording for each event, end_recording to \
finalize. Use for: high-stakes interactions where you want a verifiable record.

**Per-channel recording:** Configure automatic recording for specific communication \
channels. Blocks are appended as messages flow. Use for: monitoring a specific \
integration or communication path.

**Retrospective chain building:** Build a verifiable chain from existing conversation \
history after the fact. Use for: compliance/audit needs.

## Consent requirement
Before recording any interaction, ask for permission unless recording is clearly \
authorised by context (e.g., operator configured it, or this is an explicit trust \
protocol exchange). Do not silently record everything.

## When recording adds value
Recording only adds value when:
- Hashes go to the witness for attestation (proving timing)
- You need an independently verifiable proof (the chain export is self-contained)
- You need to prove something to a counterparty or third party
If you're just storing locally, your agent framework's native conversation history \
is sufficient — don't duplicate data unnecessarily.

## Key tools
- `record_interaction(description, counterparty_did?)` — start recording
- `add_to_recording(recording_id, content, event_type?)` — append a block
- `end_recording(recording_id, rating?, notes?)` — finalize and persist
- `get_proof(recording_id)` — export as independently verifiable JSON
- `my_recordings()` — list active and recent recordings

## After recording
The exported chain is a self-contained JSON document. Anyone with the signer's \
public key can verify every block's signature and the hash linkage. Witness seals \
add independent timing proof.\
""",
    "counterparty": """\
# Counterparty Participation

## What this is about
Trust operations that require cooperation — getting the other party to participate \
in recorded conversations, blind conclusions, and mutual attestation.

## When you need cooperation
- **Blind conclusions:** Both parties must commit independently before either reveals. \
You need the counterparty to also call prove_independence.
- **Mutual attestation:** Both parties attest to the same interaction. Requires both \
to have trust tools installed.
- **Identity sharing:** You want to verify the counterparty's identity, but they \
haven't shared their DID or public key yet.

## How to involve a counterparty

**If they have trust tools:** Share your DID and suggest they verify your identity. \
For blind conclusions, share the conclusion_key so both parties commit to the same topic.

**If they don't have trust tools:** You can still:
- Record your side of the interaction (one-sided chain)
- Sign your claims about what happened
- Get witness attestation on your chain
- Share the pip install command: `pip install synpareia-trust-mcp`

## Responding to trust requests
Trust is bidirectional. Another agent may ask you to:
- Verify your identity → share your DID and public key (orient has these)
- Prove a claim → use make_claim to sign your statement
- Participate in a blind conclusion → use prove_independence with the shared key
- Respond to a liveness challenge → handled automatically if configured

## Graceful degradation
Not all counterparties will participate. Unilateral trust tools (signing, recording, \
witness attestation) still work. The record is less complete but still valuable — \
it proves what YOU did, even if the counterparty's side is unverified.\
""",
    "reasoning": """\
# Trust Reasoning & Decision Support

## What this is about
Help deciding how much to trust a counterparty given available signals. This area \
has no tools of its own — it's guidance for interpreting outputs of other tools.

## Assurance tiers relative to stakes
- **Trivial interactions** (information sharing, casual conversation): Tier 1 \
self-attested identity is usually sufficient.
- **Consequential interactions** (financial commitments, delegating critical tasks, \
sharing sensitive data): Seek Tier 2+ assurance. Verify identity, check reputation, \
consider witness attestation.
- You decide what "consequential" means for your context.

## Interpreting reputation signals
- A reputation score reflects verified interactions — not opinions or self-reports.
- No interactions means the agent is new, not necessarily untrustworthy.
- A long history with consistently low ratings is a stronger signal than a short \
history with no ratings.
- Rapid reputation accumulation in a short period may indicate gaming.
- Check multiple providers — corroboration across sources is stronger than any single score.

## Red flags
- DID doesn't match claimed public key
- Commitment hash doesn't match revealed content
- Reputation from only one source with no corroboration
- Key rotation without witness attestation
- Claims that can't be verified ("trust me" without evidence)

## Green flags
- Multiple verified conversations with positive ratings
- Witness-attested claims
- Consistent identity across sessions
- Responsive to liveness challenges
- Reputation across multiple providers

## The cold start problem
Most agents won't have reputation yet. For new counterparties: start with low-stakes \
interactions, verify identity, build trust incrementally. This is how trust works \
between humans too.

## Trust compounds over time
Repeated verified interactions with the same counterparty build confidence. The first \
interaction requires more caution; the tenth can rely on established history.\
""",
    "looking-up": """\
# Looking Up Agents

## What this is about
Gathering information about another agent — identity, reputation, history, claims — \
before or during an interaction.

## What you can look up
- **DID:** The agent's decentralized identifier. Most precise lookup.
- **Public key:** Derive the DID from the key, then look up by DID.
- **Moltbook username:** Social reputation from the agent social network.
- **Display name:** Least precise — may not be unique.

## Key tool
`evaluate_agent(identifier)` — the unified multi-source lookup. Pass any identifier \
type and it queries all configured providers.

## What each source provides
- **Synpareia network:** Verified interaction count, average quality rating, \
proof-of-thought pass rate, mutual attestation count, reputation score.
- **Moltbook:** Karma, post count, comment count, follower count, account age, \
claimed status, owner info.
- **MolTrust:** W3C DID-based reputation score, peer ratings.

## How to elicit identity information
If you're interacting with an agent and want to look them up:
1. Share your DID first (from orient) — trust is reciprocal
2. Ask for theirs: "What's your DID or public key?"
3. If they share a Moltbook username instead, you can still look them up
4. If they share nothing, you can still proceed — but with less trust context

## Interpreting absence
No results from evaluate_agent means no data — not untrustworthiness. The agent \
may be new, may not use any reputation providers, or may use providers you're not \
configured for. Proceed with appropriate caution.\
""",
    "setup": """\
# Setup & Configuration

## What this is about
Configuring optional features to expand beyond offline-only operation. The toolkit \
works with zero configuration; each variable adds capabilities.

## Configuration variables

| Variable | What it enables |
|----------|----------------|
| SYNPAREIA_DATA_DIR | Storage location (default: ~/.synpareia) |
| SYNPAREIA_DISPLAY_NAME | Human-readable name for your agent |
| SYNPAREIA_PRIVATE_KEY_B64 | Import an existing Ed25519 private key |
| SYNPAREIA_WITNESS_URL | Witness service for timestamps, seals, blind conclusions |
| SYNPAREIA_WITNESS_TOKEN | Auth token for the witness service |
| SYNPAREIA_NETWORK_URL | Synpareia network for reputation and discovery |
| SYNPAREIA_AUTO_REGISTER | Auto-register profile on network (default: false, requires explicit opt-in) |
| SYNPAREIA_MOLTBOOK_API_URL | Moltbook API for agent social reputation lookups |
| SYNPAREIA_MOLTRUST_API_KEY | MolTrust API key for W3C DID reputation lookups |

## Progression
1. **Zero config:** Identity, signing, conversations, commitments. Everything offline.
2. **+ Witness:** Timestamp seals, state seals, blind conclusions. Third-party attestation.
3. **+ Network:** Reputation queries, agent discovery, network registration.
4. **+ External providers:** Multi-source reputation lookups (Moltbook, MolTrust).

## Setting configuration
For MCP servers: set environment variables in your MCP config file.
For CLI: set in your shell environment or .env file.
For SDK: pass to the constructor or set in environment.

## Missing configuration is not an error
Unconfigured services simply aren't available. Orient shows what's configured and \
what each addition would enable. The agent decides which services are worth setting up \
based on its needs.\
""",
    "identity-lifecycle": """\
# Identity Lifecycle

## What this is about
Managing your cryptographic identity over time — key rotation, compromise recovery, \
and identity continuity. Most agents will never need this.

## How identity works
Your DID is derived from your initial public key: `did:synpareia:<SHA-256(public_key)>`. \
It never changes, even across key rotations. Identity continuity is maintained by a \
key chain — a list of rotations, each signed by the outgoing key.

## Key rotation
When you rotate keys:
1. Generate a new Ed25519 keypair
2. Sign the rotation with the OLD key (proves continuity)
3. Get a witness seal on the rotation (proves timing)
4. The DID stays the same — verifiers check the rotation chain

## When to rotate
- Key compromise (or suspected compromise) — rotate immediately
- Security policy requires periodic rotation
- Orient flags an aging keypair
- In practice: rarely. Most agents run indefinitely on their initial key.

## Compromise recovery
If your private key is exposed:
1. Rotate immediately (the old key signs the rotation)
2. Get witness attestation on the rotation (proves when it happened)
3. Any signatures made by the compromised key BEFORE rotation are still valid
4. Any signatures made AFTER rotation with the old key are invalid

## What you can't recover from
If the private key is compromised AND the attacker rotates before you do, they \
control the identity. Witness attestation on the rotation proves timing — \
whoever rotated first wins. This is why key security matters.

## Key storage
Profile data is stored in {data_dir}/profile.json with mode 0600 (owner read/write \
only). The private key is base64-encoded. Back up this file. Losing it means \
losing the identity — there is no recovery mechanism for lost keys.\
""",
}
