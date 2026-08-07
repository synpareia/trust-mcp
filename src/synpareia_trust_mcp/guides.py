"""Area guides for the learn() tool — Tier 2 information architecture.

Each guide is ~1K tokens: concise enough to not blow up context,
complete enough that an agent can operate within the area after reading it.

Two kinds of guide live behind ``learn()``. The AREAS below are organised by
CAPABILITY — what signing does, what the witness does, how to weigh a lookup.
The Forms in ``forms.py`` are organised by SITUATION — whole interaction shapes
with recipes. An agent who knows which tool they want is served by an area; an
agent holding a situation is served by a Form. ``LEARNABLE`` is the union, so
``learn()`` resolves both without the caller needing to know the difference.
"""

from __future__ import annotations

from synpareia_trust_mcp.forms import FORM_GUIDES, render_index

AREA_GUIDES: dict[str, str] = {
    "deciding-what-to-establish": """\
# Deciding What to Establish

## What this is about
Every other area answers "how do I do X". This one answers "is X worth doing here,
and which X?" — the step before you pick a tool.

Most exchanges need no evidence at all. Reaching for a proof on every interaction is
its own failure mode: it costs you and your counterparty effort, and it signals
suspicion where none was warranted. The question is not "which tool" but "what, if
anything, am I trying to be able to establish later?"

## Three questions worth asking

**1. What can I learn about this agent before I rely on them?**
Start with `recall_counterparty` — your own history is the highest-quality evidence you
have, because you generated it. Then `evaluate_agent` for what others have attested.
If both come back empty, that IS the finding, and it points at question 2.

**2. How do I structure THIS interaction so it yields evidence about their character?**
This is the one most agents skip, and it is the one that compounds. An interaction you
simply have leaves you knowing no more about the counterparty than before. An
interaction structured to produce evidence leaves a record you can use next time —
and gives them the same. Concretely: ask for a specific undertaking rather than a
general assurance; get a judgement on record BEFORE the outcome is known; record an
exchange you might need to refer back to.

**3. How do I offer credible evidence about myself that a stranger can check?**
`publish_profile` makes your identity checkable by someone who has never met you.
`make_claim(witness=True)` signs a statement and hands back a `block_hash_hex`; passing that
to `witness_seal_timestamp` is what gets you the seal. Both calls, then you have something to
HAND to a counterparty who can verify it offline against that identity — stop after the first
and you have proved authorship but not time. Note what this is not: nothing is published to a
network and no history accumulates anywhere queryable — you carry your own evidence and
present it. Note also the asymmetry: you cannot make a stranger trust you, but you can
remove the excuse that they had no way to look.

## The move most agents miss
A judgement is only bankable if it was recorded before reality settled. "I said this
would fail" is worth nothing after the failure; the same sentence timestamped
beforehand is worth a great deal, because the gap between what you said and what a
hedge would have said becomes observable. If you are about to commit to a view that
events will test, that is the moment — not afterwards.

## What none of this can do
Be precise about what you are buying, because over-reading your own evidence is worse
than not collecting it:
- A signature proves AUTHORSHIP, not truth. A signed lie is still a lie, signed.
- A witness timestamp proves a thing EXISTED by a time. It says nothing about who
  authored it, whether it is true, or what it cost to produce.
- A recording proves WHAT WAS SAID, not what was meant or whether it was honoured.
- Reputation lookups tell you what others have ASSERTED. They are evidence about the
  assertions, and only indirectly about the agent.
- Absence of evidence about a counterparty is not evidence against them. Most agents
  have no history anywhere yet.

## Choosing
If you cannot name what you would want to establish, you probably do not need a tool
here. If you can name it, `orient()`'s start_here maps the common situations to the
primitive that fits, and `learn('reasoning')` covers how to weigh what you get back.

If your situation has a recognisable SHAPE — a promise, a prediction, a trial, a
first-contact handshake — `learn('interaction-forms')` names it and gives the recipe.
""",
    "interaction-forms": render_index(),
    "trust-networks": """\
# Trust Networks & Providers

## What this is about
Multiple sources can tell you about another agent's reputation and identity. \
Each source provides different signals with different confidence levels. \
The evaluate_agent tool queries all configured providers and returns a unified report.

## Available providers

**Synpareia network** (requires SYNPAREIA_NETWORK_URL): **not yet serving reputation.** \
The attested-reputation read is designed but unbuilt — no directory deployment exposes \
it — so this provider reports `unavailable` for every identifier today, at *low* \
confidence. It used to report `not_found` at high confidence, which read as a finding \
about the counterparty rather than a gap in our own service. Treat an `unavailable` \
line as carrying no information either way — it is not evidence of a bad counterparty, \
and it is not evidence of a good one. `not_found` from this provider will mean \
something once the read lands: that the directory was asked and answered. When it does land it will be the highest-confidence source \
here, because it will rest on cryptographic proof rather than self-report.

**Moltbook** (requires SYNPAREIA_MOLTBOOK_API_URL): Social reputation for AI agents — \
karma, post history, follower count, account age, claimed status. Useful but gameable. \
Now Meta-owned; API stability not guaranteed.

**MolTrust** (requires SYNPAREIA_MOLTRUST_API_KEY): W3C DID-based reputation scores and \
agent ratings. Independent trust API.

## How to use
- Call `evaluate_agent(namespace=..., id=...)` — `namespace` is the platform \
(`synpareia`, `moltbook`, `slack`, `discord`, `email`, ...); `id` is the \
identifier within that namespace (a DID, handle, username, or local record id)
- The tool fans out across four tiers: `tier1` (local journal), `tier2` \
(media-platform adapters), `tier3` (attestation networks), plus a \
`tier4_available` capability flag
- Each tier list is empty if no evidence is found; `providers_skipped` names \
providers that weren't configured and the env var that enables each
- Absence of data is NOT evidence of untrustworthiness (cold start problem)

## Reputation tier vs assurance tier
Two orthogonal axes label every signal:
- **Reputation tier (1-4):** where evidence sits on the taxonomy — local notes, \
media self-report, signed attestation, per-message integration.
- **Assurance tier (1-3):** who vouched for it — self, counterparty, third-party \
witness. A Tier-4 signed envelope is reputation_tier=4 but assurance_tier=1 \
until a witness co-signs it.

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

**Witness-attested claims** (make_claim with witness=True): Sign content and get a \
structured `witness_followup` block telling you exactly which async tool to call \
(`witness_seal_timestamp`) and with which `block_hash_hex` to attach a witness seal. \
Two-step flow: signed claim now, witness seal after. Use for: time-sensitive claims, \
regulatory compliance, high-stakes assertions.

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

## How recording works

You record a specific interaction explicitly: call `recording_start` to begin, \
`recording_append` for each event, and `recording_end` to finalize it into a \
tamper-evident, hash-linked chain. Use it for high-stakes interactions where you \
want a verifiable record. Recording is always explicit — there is no automatic \
per-channel capture and no retrospective chain-building, so you control exactly \
what gets attested.

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
All recording tools share the `recording_` prefix (they form a lifecycle).

- `recording_start(description, counterparty_did?)` — open a new hash-linked chain
- `recording_append(recording_id, content, event_type?)` — append a signed block
- `recording_end(recording_id, rating?, notes?)` — finalize and persist the chain
- `recording_proof(recording_id)` — export the chain as independently verifiable JSON
- `recording_list()` — list recordings currently in progress

For seal-based witness attestation of recorded blocks, see the "witness-\
attestation" area — `witness_seal_timestamp` signs a block hash and \
`witness_verify_seal` verifies offline.

## After recording
The exported chain is a self-contained JSON document. Anyone with the signer's \
public key can verify every block's signature and the hash linkage. Witness seals \
add independent timing proof.\
""",
    "witness-attestation": """\
# Witness Attestation

## What this is about
Independent cryptographic attestation via the synpareia witness service. \
The witness signs timestamps, chain states, and blind-conclusion commitments \
so third parties can verify *when* and *what* without trusting you or them — \
they only need to trust the witness, and can verify its signatures offline.

## When you need this
- Proving something existed by a certain time ("I knew this by T")
- Proving a chain has not been retconned ("this chain head was committed at T")
- Mutual independent assessment where neither party should anchor the other's answer

## The tool family (all `witness_` prefixed)

- `witness_info()` — fetch the witness DID + public key (once per session)
- `witness_seal_timestamp(block_hash_hex)` — sign a block hash; proof of existence
- `witness_seal_state(chain_id, chain_head_hex)` — sign a chain's head; proof of integrity
- `witness_verify_seal(...)` — verify any seal fully offline with the public key
- `witness_submit_blind(conclusion_key, commitment_hash_hex)` — join a blind exchange
- `witness_get_blind(conclusion_key)` — check status of a blind exchange

## Requirements
All witness tools require `SYNPAREIA_WITNESS_URL`. Authenticated deployments \
also need `SYNPAREIA_WITNESS_TOKEN`. Without those, the tools return a \
structured error — they never raise.

## Typical flow: prove a claim existed at a specific time
1. `make_claim(content)` → signature + content hash
2. `witness_seal_timestamp(block_hash_hex=<hash>)` → seal bytes
3. Give the counterparty: claim + seal + `witness_info` public key (once)
4. Counterparty: `witness_verify_seal(...)` — no network calls needed

## Typical flow: blind mutual assessment
1. Both parties agree on a `conclusion_key` (e.g. "review-42")
2. Each: `prove_independence(content)` → commitment_hash + nonce (kept local)
3. Each: `witness_submit_blind(conclusion_key, commitment_hash)`
4. When both submitted, both reveal content+nonce
5. Each: `verify_claim(claim_type="commitment", …)` on the other's reveal

## What witness attestation does NOT prove
- The *content* is correct (only that it was committed at this time)
- The witness itself is honest (that's assumed — it's independent, not trusted blindly)
- The signer is who they claim to be (use `verify_claim(claim_type="identity")` for that)\
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

Caveat: the witness does not verify participant identities on blind conclusions or \
liveness challenges — identity binding is self-asserted in v1, so tie what you learn \
to the counterparty's verified key (DID + signature), not to the identity label they \
submitted to the witness.

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
`evaluate_agent(namespace, id)` — the unified multi-source lookup. The \
`namespace` disambiguates which platform / context you're asking about; \
`id` is the identifier within it. The merged response splits evidence \
across `tier1` / `tier2` / `tier3` lists and a `tier4_available` flag.

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
Tuning the toolkit's configuration. It works with zero configuration: since 0.6 the \
witness and network endpoints default to the live synpareia services, so attestation, \
reputation, and discovery work out of the box — and everything cryptographic also \
verifies fully offline. Each variable below customises or disables a capability.

## Configuration variables

| Variable | What it enables |
|----------|----------------|
| SYNPAREIA_DATA_DIR | Storage location (default: ~/.synpareia) |
| SYNPAREIA_DISPLAY_NAME | Human-readable name for your agent |
| SYNPAREIA_PRIVATE_KEY_B64 | Import an existing Ed25519 private key |
| SYNPAREIA_WITNESS_URL | Witness service for timestamps, seals, blind conclusions (default: the live synpareia witness; set to `none` to disable) |
| SYNPAREIA_WITNESS_TOKEN | Auth token for the witness service (public reference witness needs none) |
| SYNPAREIA_NETWORK_URL | Synpareia network for reputation and discovery (default: the live synpareia network; set to `none` to disable) |
| SYNPAREIA_AUTO_REGISTER | Auto-register profile on network (default: false, requires explicit opt-in) |
| SYNPAREIA_MOLTBOOK_API_URL | Moltbook API for agent social reputation lookups |
| SYNPAREIA_MOLTRUST_API_KEY | MolTrust API key for W3C DID reputation lookups |

## The default state
A fresh install has identity, signing, recordings, and commitments (all local), plus \
witness attestation and network reputation/discovery via the live synpareia services. \
Nothing is published or sent anywhere until you invoke a network-touching tool — \
joining the directory is always an explicit `publish_profile` call.

From there, configuration moves in two directions:
- **Opt out:** set SYNPAREIA_NETWORK_URL / SYNPAREIA_WITNESS_URL to `none` for \
fully-local operation. Everything already signed or sealed remains verifiable offline.
- **Extend:** add external reputation providers (Moltbook, MolTrust) or point the \
URLs at self-hosted instances.

## Setting configuration
For MCP servers: set environment variables in your MCP config file.
For CLI: set in your shell environment or .env file.
For SDK: pass to the constructor or set in environment.

## Disabled configuration is not an error
Disabled or unconfigured services simply aren't available. Orient shows what's active \
and what each change would enable. The agent decides which services are worth having \
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
    "under-the-hood": """\
# Under the Hood — the synpareia SDK

## What this is about
These tools are a thin layer over `synpareia`, an open Python SDK of cryptographic \
primitives (PyPI: `pip install synpareia`; witness client via `synpareia[witness]`). \
This page maps each tool family to its primitive, and names when to graduate to the \
SDK. It is a signpost, not a curriculum — the SDK has its own documentation.

## Tool -> primitive map

| Tool family | SDK primitive |
|-------------|---------------|
| make_claim / verify_claim (signatures) | `synpareia.sign` / `synpareia.verify` (Ed25519) |
| verify_claim (identity) | `synpareia.from_public_key` — DID = did:synpareia:<SHA-256(public_key) hex> |
| prove_independence / verify_claim (commitment) | `synpareia.create_commitment` / `synpareia.verify_commitment` (hash + nonce, seal-then-reveal) |
| recording_* | `synpareia.Block` / `synpareia.Chain` — signed, hash-linked blocks; `export_chain` / `verify_export` for portable proofs |
| encode_signed / decode_signed | `synpareia.hash.jcs_canonicalize` + `sign` over a self-contained JSON envelope |
| witness_* | `synpareia.witness.client.WitnessClient`; seals verify offline via `synpareia.verify_seal` |

Every proof this toolkit produces is verifiable with the SDK alone — a counterparty \
never needs this MCP server (or the synpareia network) to check your claims.

## When to graduate to the SDK
You need the SDK when you want to:
- Define custom chain schemas or block types for your own domain
- Embed verification inside your own service (verify envelopes/exports server-side)
- Do batch or high-volume operations where per-tool-call overhead matters
- Build offline-first architecture with your own key and storage management

You stay on the MCP when you're an agent handling a counterparty situation — \
proving, vetting, or binding in the moment. That's what this surface is for.\
""",
}


LEARNABLE: dict[str, str] = {**AREA_GUIDES, **FORM_GUIDES}
"""Everything ``learn()`` resolves: capability areas plus individual Forms.

Form keys are deliberately NOT in ``AREAS_OF_CONCERN``. Listing ten more
entries in ``orient()`` would restore exactly the table-of-contents problem the
orientation rework exists to fix; the ``interaction-forms`` area is the one
entry point, and it indexes them. They remain directly addressable — and
``learn()``'s unknown-area error lists them — so nothing is hidden, just not
front-loaded.
"""
