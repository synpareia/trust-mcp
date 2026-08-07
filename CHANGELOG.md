# Changelog

All notable changes to `synpareia-trust-mcp` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0] - 2026-08-07

### Added

- **`record_interaction`** — record that you dealt with another agent, and
  optionally how it went. Writes to the shared network, not the local journal.

  The failure mode is the point. A counterparty who has not granted standing
  consent produces a 403, and reported as a generic HTTP error that is
  indistinguishable from a bug in the caller — so an agent burns retries on
  something that can never succeed. The tool returns
  `code: counterparty_has_not_consented` with the server's own subject/channel
  detail echoed rather than paraphrased (a multi-party event can fail on a party
  the caller wasn't thinking about) and states plainly that retrying will not
  help and consent cannot be granted on someone's behalf.

  `shareable=False` by default, and the response says which of the two states you
  got in words. So does `idempotent`: a re-sent event returns 201 having applied
  nothing, and skimming past that flag means counting a retry as a second
  interaction.

- **`set_reputation_consent`** — declare which channels others may record, and
  serve, events about you on. Without a grant an agent is *un-recordable*: the
  network refuses any event whose data-subject has not consented, so a
  counterparty attempting to attest something gets a hard rejection rather than a
  quiet skip. Publishing a card is not consent; this tool is.

  Two independent arguments, `accept_attestations` (may-record) and
  `accept_delivery` (may-serve). Omitting one leaves that axis unchanged; passing
  `[]` revokes it — collapsing those two would make an omitted argument silently
  retract a standing grant. `publish_profile` now carries both forward for the
  same reason, so republishing a card cannot drop consent as a side effect.

  The response states the *consequence* alongside the field values, because
  `{"accept_attestations": []}` requires knowing the whole consent model to read
  as "nobody can attest anything about me".

  Added deliberately against the standing consolidation target: this is the call
  that makes an agent participate at all, and burying it inside a general-purpose
  policy updater is how it never gets found.

  (This entry used to end "Tool count 33 → 34". It was written when this was the
  release's only new tool and was never revisited when `record_interaction` landed
  above it — the real figure for the release is **33 → 36**, stated once rather than
  per-entry, because a running total inside one tool's bullet goes stale the moment a
  second tool joins the same release. It has now gone stale twice: the corrected
  "33 → 35" was written before `network_reputation` landed below. `make
  check-tool-count` derives the live count from the registry and catches neither,
  because the CHANGELOG sits in its exemption list. See task #230.)

- **`network_reputation`** — ask the network what it can tell *you* about another
  agent. The read half of the loop `record_interaction` opens.

  Until this tool, contributing was the only thing an agent could do: events went
  in, the directory computed a personalised aggregate from them, and no surface
  served it. An agent had no reason to record anything, because nothing could
  read it back.

  Returns `magnitude` (-1..1, how the reports lean) and `confidence` (how much
  dealing backs that lean). `confidence` is an accumulated weight, **not a
  probability** — unbounded above, and `0.0` means no visible report at all, at
  which point `magnitude` must be ignored rather than read as neutral. The
  response carries a plain-language `reading` saying exactly that, because the
  numbers alone are indistinguishable from a genuinely middling agent.

  The answer is **anchored on the caller**. It is computed outward from the
  asker's own position, so two agents asking about the same counterparty
  legitimately get different numbers and no global score exists. Nothing about
  who reported, or through whom it reached you, is disclosed — the collapsed pair
  is the only shape the network's structure is ever served in. Advisory: nothing
  here ranks, thresholds or decides.

  Kept separate from `attested_reputation` on purpose. That tool fans out across
  external providers and returns labelled signals; this one is a single anchored
  aggregate from our own network. Merging them would flatten the distinction
  between "somebody signed a claim about them" and "this is what the graph looks
  like from where you stand".

- **`learn('interaction-forms')` — recipes for whole interactions, not just
  tools.** Ten named interaction shapes (witnessed prediction, precommitment,
  no-injection opener, probe, trial period, calibration audit, negotiated
  promise, spirit-vs-letter, counterfactual witness, escrow), each addressable
  as `learn('form-<name>')` and indexed by the situation it belongs to. Every
  area guide until now was organised by CAPABILITY — what signing does, what
  the witness does. These are organised by SITUATION, which is the axis an
  agent actually arrives on. Distilled from the Manual of Forms; `docs/` does
  not ship in the wheel, so they are inlined.
- **Each Form states what this package cannot yet deliver.** The Manual runs
  ahead of the toolkit in four specific ways — no co-signing tool, no
  `derivative_signal_policy`, no transport for the claim itself, no stake
  primitive — and every Form names which of them bite it. Three Forms
  are marked "shape only": documented so the shape is recognisable, not so it
  can be run here. A recipe that reads as complete while its load-bearing phase
  is missing would be a worse defect than an overclaim in prose, because an
  agent discovers it mid-interaction.
- **`learn('deciding-what-to-establish')`** — the step before tool selection:
  whether an interaction needs evidence at all, and which kind. Listed first
  in `orient()`, with an explicit off-ramp for "most exchanges need none of
  this". `orient()`'s `start_here` now names what you would be ESTABLISHING
  before naming a tool.

### Changed

- **Floor bump: `synpareia[witness,profile]>=0.7.0`** (was `>=0.6.0`). `directory.py`
  imports `ReputationConsent`, which 0.6.x does not export. That import sits inside
  the `try/except ImportError` that sets `HAS_PROFILE_SDK`, so resolving 0.6.x did
  **not** raise — it silently disabled the entire directory tool group. A too-low
  floor fails this way quietly rather than loudly, which is why the number moved
  rather than the guard.

  Release ordering: `synpareia 0.7.0` must be published to PyPI **and indexed**
  before this package is synced, or the public repo's CI cannot resolve the
  dependency. The monorepo gate cannot see this — `[tool.uv.sources]` resolves
  `synpareia` from `../sdk` as an editable install.

- **`orient()`'s capability block leads with the network layer.** It previously
  listed four named `offline` capabilities first, then a two-item `network`
  list in which the entire reputation layer appeared once, at the end, in
  parentheses — `"Synpareia network (reputation, discovery)"`. An agent that
  parses structure before prose reads that as "substrate is the product,
  reputation is a footnote", and one did: a live agent used this package for a
  fortnight, concluded synpareia was an attestation library with a weak
  reputation add-on, and argued it back to us. Reputation and Directory are now
  named capabilities in their own right, `network` precedes `offline`, and a
  `what_this_is_for` line states which layer is the point and which is the
  substrate. Pinned by tests, including one that rejects a parenthetical
  mention.

### Fixed

- **Eight degradation messages named a version that was never the floor.** Every
  profile-SDK-dependent directory tool returns a message when `synpareia.profile`
  is unimportable. Eight of the nine said "upgrade SDK to 0.5.0+" and the ninth said
  "0.7.0+", while the declared floor had moved to 0.7.0 — so an operator on 0.6.x
  was told to upgrade to a version they already exceeded, and the real cause (a
  missing `ReputationConsent` export) went unnamed.

  The sentence now derives from a single `MIN_PROFILE_SDK_VERSION` constant, and
  `tests/test_sdk_floor_message.py` binds that constant to the floor declared in
  `pyproject.toml` — so bumping the floor without updating the message fails the
  suite. Nine hand-maintained copies of one number is the defect; the test is what
  stops a tenth.

- **Tier-3 no longer reports a finding it never made.** `attested_reputation`'s
  synpareia provider requests `GET /api/v1/agents/{id}/reputation`. No directory
  deployment serves that route — it is defined by no router; the nearest real route,
  `/api/v1/verify/{profile_id}`, sits behind `ENABLE_LEGACY_SURFACES` and is off in
  production; and the v2 surface has no reputation read at all. Verified live: both v1
  paths 404 while `/api/v2/profiles/{did}` returns 200.

  Every call therefore 404'd, and the provider turned that into
  `value="not_found", confidence="high"` with the detail *"No synpareia network record
  for '<id>'."* — a positive claim about the counterparty, asserted at the highest
  confidence the tool offers, derived from a request nothing answers. An asking agent
  could not distinguish it from a considered "we looked and there is nothing", which is
  the entire value of a tier-3 read.

  It now reports `value="unavailable", confidence="low"`, saying plainly that no
  reputation endpoint is deployed and that this is **not** a statement about the
  counterparty. `not_found` remains reachable, at high confidence, when the service
  actually answers with an affirmative absence (`exists: false` — the fixed-shape
  convention the directory's own v2 endpoint already uses, where an unknown DID is a
  200 rather than a 404).

  The guide text already said this in prose — "carries no information either way" —
  while the machine-readable signal said the opposite. Only the prose was honest, and
  agents read the signal.

  **Why no test caught it:** `tests/stubs/synpareia_network.py` *implements* the
  requested route, so the suite verified the parser against a server that does not
  exist. The oracle was derived from the subject. Two existing tests asserted the
  false behaviour outright and are corrected here; the new
  `tests/test_synpareia_tier3_honesty.py` stubs a directory that behaves like the real
  one — 404 on the reputation path — and asserts the property that matters to a caller:
  that "nothing was looked at" is distinguishable from "we looked and found nothing".

- **`mcp` is now constrained to `>=1.28.1,<2` — this repairs a broken install.**
  (The floor is a security floor as well as a compatibility one; see **Security** below.)

  `mcp` 2.0.0 (2026-07-28) moved `mcp.server.fastmcp`. Because 0.8.0 declared
  `mcp[cli]>=1.0` with no upper bound, a fresh `pip install synpareia-trust-mcp`
  resolved to 2.0.0 and raised `ModuleNotFoundError: No module named
  'mcp.server.fastmcp'` before the server could start. Installs from
  2026-07-28T13:45Z (when `mcp` 2.0.0 was published) onward are affected; earlier
  ones resolved `mcp` 1.x and are fine.

  **If you are on 0.8.0, upgrade to 0.9.0.** This release carries the bound, so
  `pip install --upgrade synpareia-trust-mcp` is the remedy. A published wheel's
  metadata cannot be amended, so 0.8.0 stays broken on a fresh install permanently —
  an install-time upper-bound pin was only ever a stopgap for the days when no fixed
  release existed. No code or API change is involved; 0.8.0's own code is fine
  against `mcp` 1.x.

  The bound is deliberate rather than precautionary and stays until the server is
  ported to the `mcp` 2.x API.

- **`add_evaluation` on an unknown counterparty now returns a recovery, and
  the recovery is one that works.** It previously returned only
  `"No record for identifier 'x'"`. The prerequisite was documented — in the
  docstring, which an agent reaching the error has already read past — and this
  dead-ended the one reputation workflow a live agent attempted. Two failure
  shapes are now distinguished: no record at all (→ call
  `remember_counterparty`, then use the `identifier` from its response), and
  the far likelier one, passing a **display name** where an identifier is
  required. Records are keyed by an opaque `local:<uuid>`, and a display name
  never resolves to the record displaying it, so the naive retry failed
  identically a second time. The error now names the identifier(s) that work.
  Identifier resolution itself is unchanged — matching display names would make
  lookup ambiguous when two counterparties share a name, which is a design call
  (tracked separately), not a bugfix.

- **The guidance now says that witness timestamping is TWO calls.**
  `make_claim(witness=True)` signs and returns a `witness_followup`
  instruction; it does not obtain a seal. An agent stopping there holds proof
  of authorship and no proof of time — precisely the property the calibration
  and precommitment shapes exist to establish. Two places previously said
  otherwise: the `deciding-what-to-establish` guide claimed the flag "produces
  a sealed claim", and `orient()`'s `a stranger has no reason to believe you`
  entry named the flag alone. Both corrected. Every agent-facing string that
  mentions `witness=True` — all ten Forms, all thirteen area guides, every
  `start_here` entry, and the Forms index — is now checked for the second
  call, and the breadth of that check is itself asserted.
- **Every surface now describes the reputation loop that actually exists.**
  Nine agent-facing strings — the `GAP_NO_CLAIM_TRANSPORT` paragraph (quoted by
  six Forms), three Forms' own wording, the Forms index, and three `orient()`
  capability lines — said "reputation is read-only in v1". That stopped being
  true when `record_interaction` shipped and is now false twice over.

  **Two tests were pinning the falsehood in place.** One required the literal
  phrase "read-only in v1" in the Forms index; the other asserted `orient()`'s
  reputation capability still said "read-only". Both were written honestly, to
  stop an overclaim, and both aged into guards holding an UNDERclaim. They are
  inverted rather than deleted — the phrase must now be ABSENT from every
  surface, and the capability line must name both `record_interaction` and
  `network_reputation`, because a line mentioning only lookups is how the old
  wording comes back.

  The residual constraint is real and is now stated as what it is: the substance
  of a claim about a counterparty cannot be published, **by design and not
  pending a release**. A magnitude and a valence travel; the text does not. The
  new gap paragraph is asserted to name both halves, so the correction cannot
  swap one misleading surface for its opposite.

- **Whole-file journal corruption no longer silently loses your local
  records.** An undecodable or wrong-shaped `counterparties.json` used to read
  as empty, and the next write would then overwrite the (recoverable) file with
  a fresh list — silent total data loss (pentest INFO-2). It is now moved aside
  to `counterparties.json.corrupt-<timestamp>` before the store starts empty, so
  an operator can recover it. If the move itself can't happen (a read-only fs),
  the store now **refuses** (`JournalCorruptError`) rather than proceed to a
  state where the next write would overwrite the unpreserved file. Per-row
  malformed handling (0.7.x) is unchanged.
- **`profile.json` is now written atomically** (temp file + rename), closing a
  durability gap where a crash mid-rewrite could truncate or empty the file and
  lose the persisted keypair + DID. No behaviour change on the happy path.

### Security

- **The `mcp` floor moved from `>=1.0` to `>=1.28.1`, which is a security floor and
  not only the compatibility bound described under Fixed.** `mcp` 1.27.0 carries
  PYSEC-2026-3481 and PYSEC-2026-3482 (fixed in 1.27.2) and PYSEC-2026-3483 (fixed in
  1.28.1). **None is reachable in this package's stdio-only configuration** — they
  require SSE/StreamableHTTP, the deprecated `websocket_server`, or experimental
  `enable_tasks`, none of which the trust MCP enables. Our own lockfile was
  nonetheless pinning 1.27.0, so an install resolving from it inherited all three.
  Upgrading to 0.9.0 raises the floor past them.

  (The `python-multipart`, `pyjwt` and `idna` floors alongside it are unchanged from
  0.8.0 and are not part of this release.)

### Internal

- Extracted the shared `atomic_write_bytes` / `quarantine_corrupt_file` helpers
  (`fsutil`) used by both the journal and profile stores; removed a vestigial
  `_record_to_dict` passthrough and de-duplicated the identifier-match predicate
  (`_matches`) across the read and mutate paths. No tool-contract change.

## [0.8.0] - 2026-07-14

### Removed

- **BREAKING: removed the deprecated `evaluate_agent(identifier=...)` legacy
  parameter** (deprecated since 0.4.0, two releases past its promised removal
  window). Call `evaluate_agent(namespace=..., id=...)` — or pipe a Tier-1
  record straight in via `namespace_id=...` — instead. The `deprecation` flag
  the legacy form emitted on the response is gone with it.

  | Old                                              | New                                                             |
  | ------------------------------------------------ | --------------------------------------------------------------- |
  | `evaluate_agent("alice")`                        | `evaluate_agent(namespace="moltbook", id="alice")`              |
  | `evaluate_agent("did:synpareia:a1b2c3")`         | `evaluate_agent(namespace="synpareia", id="did:synpareia:a1b2c3")` |
  | `evaluate_agent("T0ABC/U0123")` *(Slack)*        | `evaluate_agent(namespace="slack", id="T0ABC/U0123")`           |

### Security

- Bumped the transitive `click` pin (pulled via `mcp[cli]`/`uvicorn`) from
  8.3.2 to 8.4.2 in `uv.lock` to clear **CVE-2026-7246** (command injection in
  `click.edit()`, ≤8.3.2; fixed in 8.3.3). Not reachable from this server — we
  never call `click.edit()` — and the published wheel is unaffected (click is
  not a declared dependency, so a fresh install already resolves the fixed
  line). This only tidies the committed dev/CI lockfile so the public repo does
  not carry a flagged pin.

## [0.7.0] - 2026-07-06

Privacy-completion release: makes the data-protection posture the prove/vet/bind
copy already promises actually true in the product. Closes the two GDPR §6 gaps
the 0.6.3 publish-gate `legal` perspective surfaced (both amplified by
network-on-by-default). Adds one tool (33 total) — backward-compatible; minor
bump.

### Added

- **`forget_counterparty(identifier)`** — first-class Tier-1 erasure. Permanently
  removes a counterparty record and *all* your evaluations of them from the local
  **journal**; the local-data counterpart to the directory-side `delete_profile`.
  Idempotent (forgetting an absent identifier returns `forgotten: false`, no
  error). This is the concrete mechanism behind "erasure stays under your
  control" **for the counterparty journal** (GDPR Art. 17, on the data subject's
  own machine) — previously the README could only point agents at hand-editing
  `counterparties.json`. Scope is deliberately the journal: signed
  conversation/recording chains (`conversations/conv_<id>.json`) are
  tamper-evident audit trails and are not erased by this tool (the response says
  so), preserving the audit-integrity-vs-erasure trade the data-protection design
  already names.
- **First-run identity disclosure (GDPR §6).** When the server mints a brand-new
  identity, it now discloses — on stderr (never stdout, the stdio-MCP protocol
  channel) — the DID, the on-disk location, and that *nothing has been sent
  anywhere* (publishing and witnessing are always explicit calls). `orient` also
  carries an `identity.first_run` notice for the session in which the identity
  was created. This matters more since 0.6 defaulted the network ON: the operator
  should know a fresh identity is local-only until they make an explicit call.

## [0.6.3] - 2026-07-03

Positioning + copy release ahead of the MCP-marketplace listings, and the first
release to carry the post-0.6.2 round-trip and copy fixes (#301, #305) that
landed on `master` after 0.6.2 shipped. Still no *behaviour* change to any
cryptographic or network operation; the 32-tool set is unchanged, and the two
parameters added in #301 are backward-compatible aliases (old field names still
work).

### Fixed

- **Closed the three round-trip name mismatches that 0.6.2 listed as deferred
  (#301, task #40a).** `verify_claim` now accepts `did` as an alias for
  `agent_did`, and `evaluate_agent` accepts `namespace_id` as an alias for `id`,
  so an identity/lookup block pipes straight in without renaming fields. The
  `witness_submit_blind` / `seal_commitment` instructions were also redirected
  from a phantom `reveal_commitment` (never a registered tool) to the real
  `verify_claim(claim_type='commitment', ...)`. Added round-trip contract tests.
- **Corrected four agent-facing references to things that don't exist (#305).**
  `encode_signed`'s witnessed-assurance hint (`assurance='witnessed'` →
  `make_claim(content, witness=True)`); dead `learn("disambiguation")` pointers
  in the counterparty tools; fictional "per-channel recording" / "retrospective
  chain building" modes in the recording guide; and a stale `forget_counterparty`
  "v0.5 roadmap" note in the README.

### Changed

- **Positioning: prove / vet / bind.** All discovery and in-context copy now
  leads with the situations the toolkit is for — *prove what you did, vet who
  you're dealing with, bind agreements so anyone can check them* — instead of
  a primitive catalogue. Rewritten: README opening, `pyproject` description,
  server `INSTRUCTIONS` (now stakes-triggered, not "when interacting with
  another AI agent"), and the `orient` docstring.
- **`orient` now returns a `start_here` situation map first** — seven
  common situations ("another agent claimed something", "about to rely on
  another agent", …) each mapped to the tools that handle them. The inventory
  (identity, services, capabilities, areas) follows.
- **Offline copy reconciled with network-on defaults (since 0.6).** Offline
  verification is now framed as a guarantee ("everything verifies offline,
  forever"), not the value proposition. The `setup` guide's "Progression"
  ladder (zero-config → +witness → +network) is replaced by the actual
  default state (live services on, nothing published implicitly) plus the
  two real directions: opt out (`none`) or extend/self-host. `orient`'s
  no-network fallback and next-steps texts now acknowledge an explicit
  opt-out instead of narrating an unset default.
- **Network-join funnel copy (unpublished + network on):** names the concrete
  value — a counterparty who has never met you can independently verify your
  identity and witnessed history — while keeping the ratified honesty framing
  (offline keeps working, persistence opt-in, erasure under your control, no
  reachability promise).

### Added

- **`learn("under-the-hood")`** — the MCP↔SDK boundary signpost: a tool
  family → SDK primitive map (`make_claim` → `synpareia.sign`,
  `recording_*` → `Block`/`Chain`, `witness_*` → `WitnessClient`, …) and
  graduation criteria for when to build on the `synpareia` SDK directly.
  Also listed as an `orient` area of concern.

## [0.6.2] - 2026-07-02

Round-trip symmetry + truthful metadata, ahead of the MCP-marketplace listings
(launch-review LR-6/7/13). No breaking changes — old field/param names still work.

### Fixed

- **Seal → verify no longer returns a false "seal invalid" (LR-6).**
  `witness_seal_timestamp` returned the target under `target_block_hash` while
  `witness_verify_seal`'s param was `target_block_hash_hex` (same for
  `witness_seal_state` / `target_chain_head`). FastMCP's arg model is pydantic
  `extra="ignore"`, so piping a seal response verbatim silently dropped the
  target and verify rebuilt an empty envelope → `{"valid": false}` — wrongly
  impugning a cryptographically sound seal. Now:
  - seal responses expose the canonical `target_block_hash_hex` /
    `target_chain_head_hex` (old names kept as aliases);
  - `witness_verify_seal` accepts both names;
  - a missing target returns a structured `incomplete_verification_input` error
    (with a hint) instead of `valid: false` — "you under-specified the request"
    is not "the seal is forged".
- **`recording_end` → `witness_seal_state` and `witness_info` → `witness_verify_seal`
  now pipe verbatim** — `recording_end` also emits `chain_head_hex`, `witness_info`
  also emits `witness_public_key_b64`.
- **`recording_start`** now echoes `counterparty_did` (matching its input param;
  `counterparty` kept as an alias).
- Bumped transitive **`pydantic-settings` 2.13.1 → 2.14.2** (GHSA-4xgf-cpjx-pc3j).

### Added

- **Self-describing seals.** `witness_seal_timestamp` / `witness_seal_state`
  responses include a `verify_followup` block (mirroring `make_claim`'s
  `witness_followup`) with the exact `witness_verify_seal` params — including the
  witness public key — so a seal is verifiable by a third-party recipient with no
  witness call and no field-name guesswork.
- **Round-trip contract tests** (`tests/test_roundtrip_contracts.py`): every
  output→successor pair is verified by piping the literal response into the
  successor under FastMCP's drop-unknown-keys semantics. These fail on pre-0.6.2
  code and would have caught LR-6.
- `[project.urls]` now includes `Issues` and `Changelog` (LR-7).

### Known / deferred (tracked)

- Three lower-severity name mismatches remain, deferred because they are not clean
  verbatim pipes (need small design calls): blind `party_*_commitment` →
  `verify_claim.commitment_hash`, `remember_counterparty.namespace_id` →
  `evaluate_agent.id`, and `verify_claim.agent_did` (no producer emits `agent_did`).

## [0.6.1] - 2026-07-02

Funnel + error-ergonomics polish surfaced by the pre-marketplace
fresh-agent battle test (`docs/explorations/pre-marketplace-battletest.md`).
A cold agent understood the offline primitives but treated joining the
synpareia network as "optional," and a network failure surfaced as a raw
`ConnectError`. No API changes — copy + error-shape only.

### Changed

- **`orient` funnels toward the network.** `next_steps` now presents
  publishing a profile / joining synpareia as the natural next step when
  the network is configured but the agent hasn't published yet (framed
  honestly: erasure stays operator-controlled, persistence opt-in). The
  "no network configured" hint and the `capabilities.network` fallback
  now name discovery + portable reputation, not just witness attestation.

### Fixed

- **Structured errors on network failure.** `_structured_error` now maps
  `httpx.TransportError` (connect/timeout — most often an opted-out or
  unreachable network) to a `{error, reason: "network_unreachable", hint}`
  envelope instead of a raw `ConnectError: All connection attempts failed`.
  `publish_profile`, `get_profile`, `update_profile_policy`, and the
  other network tools now route their catch-all through the helper, so
  they all get the structured HTTP-4xx body and the transport hint.

## [0.6.0] - 2026-06-10

Live-by-default release (audit D-12b / launch hit-list 1.6): a fresh
install now finds the deployed synpareia services without any env-var
setup. Minor bump under the pre-1.0 SemVer caveat — the default-URL
change is a behaviour change for existing installs that relied on the
old local-only default, documented loudly below with the opt-out.
Pairs with `synpareia` SDK 0.6.0 on PyPI (publish ordering: the SDK
must be indexed first; see the floor bump under Changed).

### Changed

- **BEHAVIOUR CHANGE — network and witness URLs now default to the
  live services.** `SYNPAREIA_NETWORK_URL` defaults to
  `https://synpareia.fly.dev` and `SYNPAREIA_WITNESS_URL` to
  `https://synpareia-witness.fly.dev` (both previously defaulted to
  `None`, i.e. local-only, so a fresh install never found the deployed
  network). **How to opt out:** set the env var to `none`, `off`,
  `disabled`, or the empty string (case-insensitive) to disable the
  feature entirely (fully local); set any other value to point at a
  self-hosted or staging instance. `SYNPAREIA_AUTO_REGISTER` remains
  `false`: nothing is published to the directory unless you explicitly
  call a publishing tool.
- **NOTE FOR TEST SUITES AND CI:** if your test suite exercises
  network-touching tools (directory, witness, reputation) without
  opting out, it will now reach the **production** services. Set
  `SYNPAREIA_NETWORK_URL=none` and `SYNPAREIA_WITNESS_URL=none` in your
  test environment (this repo does it with a suite-wide autouse
  fixture), or block sockets outright with `pytest-socket`. This is not
  hypothetical: during development of this change, an unguarded test
  suite published a test profile to the production directory.
- **Floor bump: `synpareia[witness,profile]>=0.6.0`** (was `>=0.5.0`).
  Picks up the SDK's `verify_block` fail-closed fix and the RFC 8785
  canonicalization swap — see the SDK 0.6.0 CHANGELOG for the breaking
  notes (`verify_block` unsigned-pass removal; ints outside ±2^53 now
  raise; floats now signable).
- `README.md` privacy section rewritten honestly for the new posture
  (storage stays local-first; network-touching tools reach the live
  services unless opted out), and the `SYNPAREIA_AUTO_REGISTER` doc row
  corrected (docs said `true`; the code default has always been
  `false`).

### Notes

- **Honesty note on witness identity binding (audit D-9):** the witness
  service does not verify the requester identity submitted with blind
  conclusions or liveness challenges — identity binding is the caller's
  self-asserted claim in v1, until Phase-2 anonymous credentials land.
  The witness tool docstrings and guides now say so explicitly. No
  behaviour change.

## [0.5.1] - 2026-05-12

Defensive security floor on a transitive dependency. No code changes,
no new tools, no behavioural change from 0.5.0.

### Security

- Add `python-multipart>=0.0.27` to the runtime dependency floor.
  CVE-2026-42561 affects `python-multipart<0.0.27` (pulled in
  transitively via `mcp`). The trust-toolkit's published MCP server
  uses stdio transport and does not itself invoke multipart parsing,
  so the vulnerability is not reachable on the toolkit's own surface;
  the floor is defence-in-depth for downstream operators who might
  enable HTTP transports on top of `mcp`.

## [0.5.0] - 2026-05-06

Phase 1 of the funnel-implementation-roadmap. Wires the new SDK 0.5.0
profile-directory surface into the MCP, taking the tool count from 25
to 32. Pairs with `synpareia 0.5.0` on PyPI; the floor declared in
`pyproject.toml` ensures consumers re-resolve appropriately.

### Added

- **Profile directory tools** (7 new): `publish_profile` (build + sign
  + publish your agent card to the directory), `get_profile(did)`
  (counterparty existence-layer fetch), `update_profile_policy`
  (rebuild + re-sign + re-publish, preserving unspecified fields and
  the persistence opt-in across updates), `enable_persistence(scope)`
  / `disable_persistence()` (opt-in/out helpers for `card_history`,
  `key_chain`, `reputation`), `delete_profile_history(version)` and
  `delete_profile()` (sigauth-protected erasure).
- **`orient` now surfaces directory state** under
  `identity.directory.{published, name, version, last_published_at,
  persistence}` so a fresh agent's first call tells it whether it has
  a published profile and what's in it.
- **`SYNPAREIA_NETWORK_URL` env var** as the directory base URL (also
  used by the synpareia-reputation provider).
- **On-disk cache** at `data_dir/published_card.json` records the last-
  published shape so `update_profile_policy` only changes what's
  specified (true to its name). `delete_profile` annotates the cache
  with `tombstoned_at` so `orient` reports `published=False` post-
  delete.
- New `tools/directory.py` module wrapping the SDK 0.5.0 `ProfileClient`
  / `SyncProfileClient` consumer-side surface.
- 9 new tests for the directory tools + 2 regression tests on the
  Copilot-review fix-up (access-token forwarding, structured-error
  envelope preservation, tombstone-aware orient).

### Changed

- Floor on `synpareia[witness,profile]>=0.5.0` (was `>=0.4.0`).
- `expected_tools` list synced to 32.
- Network-backed tools return structured `not_configured` errors that
  name the specific env var when their dependency is missing — replaces
  free-text error strings so wrapper MCPs can route on the error code.

### Security

- Sigauth flow on all mutating directory operations (publish, update,
  delete) via the SDK's RFC 9421 wrapper. Read operations
  (`get_profile`) are unauthenticated by design (existence-layer).

## [0.4.1] - 2026-05-01

Patch release driven by dojo-run findings. Surfaced by sonnet's run on
the fresh-discovery scenario (`dojo/findings/runs-2-thru-5.md` in the
monorepo) — the 0.4.0 `make_claim(witness=True)` docstring promised a
witness seal but the implementation just added a vague hint string,
forcing agents to compute the SHA-256 of the content themselves before
calling `witness_seal_timestamp`.

> **Migration note for 0.4.0 callers reading `witness_note`:** the
> `witness_note` string field is replaced by the structured
> `witness_followup` dict. Pre-1.0 patch releases may carry breaking
> field renames; if you were reading `result["witness_note"]`, switch
> to `result["witness_followup"]["message"]` (with the same human-
> readable purpose) or use the new `tool` and `params` keys to drive
> the witness seal call programmatically.

### Changed

- `make_claim` now always returns `block_hash_hex` (SHA-256 of the
  signed content as hex). Recipients and the agent itself need a
  canonical digest to refer to the claim; pre-computing it removes
  the manual hashing dojo observed agents doing.
- `make_claim(witness=True)` now returns a structured `witness_followup`
  block (`{tool, params: {block_hash_hex}, message}`) replacing the
  earlier `witness_note` string. The block tells the agent exactly
  which tool to call (`witness_seal_timestamp`) and with which
  argument — no manual hash computation, no docstring/behaviour
  mismatch. When witness isn't configured, `tool` is `None` and the
  message points at the env vars to set.
- `make_claim` docstring is rewritten to be honest about the two-step
  flow: signed claim from this synchronous tool, witness seal from a
  separate async one. The hash returned bridges them cleanly.

### Added

- Four new tests in `test_02_make_and_verify_claim.py` pinning the new
  fields: `block_hash_hex` always present and matches SHA-256 of
  content; `witness_followup` absent when `witness=False`; configured
  vs unconfigured witness paths each return the right shape.

## [0.4.0] - 2026-04-30

Four-tier reputation-evidence taxonomy ships as the v1 tool surface. The
taxonomy distinguishes where evidence sits on two orthogonal axes:
**reputation tier** (1 local journal → 2 media → 3 attestation network →
4 per-message integration) and **assurance tier** (1 self-attested → 2
counterparty-attested → 3 witness-attested).

`evaluate_agent` becomes the merged convenience entry point across all
four tiers, now signed as `(namespace, id)`. See
`docs/explorations/counterparty-reputation.md` and `docs/trust-capability.md`
for the full rationale (including CJEU *EDPS v SRB* and the Position 4
sparse-witness ratification).

### Added

- **Tier 1 counterparty journal** — local, offline, always available:
  - `remember_counterparty` — upsert by `(namespace, namespace_id)`,
    display-name history, free-form `custom_fields` (no hard schema).
  - `recall_counterparty` — read-only lookup by identifier, DID alias,
    or display name (case-insensitive, historical matches included).
  - `add_evaluation` — attach free-text note with optional `tags` and
    `score` to any record.
  - `find_evaluations` — search evaluations across all records by tag.
- **Tier 2 media signals** (`check_media_signals(namespace, handle)`) —
  platform-level reputation signals. v1 ships the Moltbook adapter;
  other namespaces return a structured `no_adapter` response with
  guidance.
- **Tier 3 attested reputation** (`attested_reputation(identifier)`) —
  query-only fan-out to configured attestation providers (synpareia
  network, MolTrust). Reports `reputation_tier=3`, `assurance_tier=2`.
  Submission to the synpareia reputation network is deferred to v2
  pending witness Phase 2 (anonymous-credential identity binding).
- **Tier 4 per-message primitives** — `encode_signed(content)` /
  `decode_signed(string)`. Self-contained Ed25519-signed envelopes
  that can ride any transport (Slack, Discord, email, HTTP). Decoder
  is pass-through for non-synpareia input: returns the raw string with
  `synpareia_validated=false` so wrapper MCPs can route transparent
  content through the same call site.

### Changed

- **Breaking:** `evaluate_agent` signature is now `(namespace, id)` and
  returns a per-tier merged response:

  ```
  {
    namespace, id,
    tier1: [local records...],
    tier2: [media signals...],
    tier3: [attestation signals...],
    tier4_available: bool,
    providers_queried: [...],
    providers_skipped: [{name, reason}...],
    summary,
  }
  ```

  The legacy `evaluate_agent(identifier=...)` form still works for one
  release and attaches a `deprecation` flag to the response. **It was
  removed in 0.8.0.** Migrate by passing explicit `namespace` + `id`:

  | Old                                              | New                                                             |
  | ------------------------------------------------ | --------------------------------------------------------------- |
  | `evaluate_agent("alice")`                        | `evaluate_agent(namespace="moltbook", id="alice")`              |
  | `evaluate_agent("did:synpareia:a1b2c3")`         | `evaluate_agent(namespace="synpareia", id="did:synpareia:a1b2c3")` |
  | `evaluate_agent("T0ABC/U0123")` *(Slack)*        | `evaluate_agent(namespace="slack", id="T0ABC/U0123")`           |

- Tool count: 17 → 25 (added 8 tools across the four-tier taxonomy; no
  tools removed). Full list visible via `orient`.

### Security

- Tier-4 signed envelopes cryptographically bind `signer_did` to the
  embedded public key (DID = SHA-256 of pubkey). A forger who swaps in
  their own key while keeping the victim's DID is rejected at decode.
- ADV-011-class input validation (length caps, control-character
  rejection) applied to every new tool surface: `namespace` (≤64),
  `id` / `identifier` (≤256), envelope (≤128 KB), content (≤64 KB).
- Legacy-compat path in `evaluate_agent` infers the namespace from the
  identifier shape (`did:synpareia:` → `synpareia`, `local:` → `local`,
  else `unknown`) — it never routes unknown identifiers to a Tier-2
  adapter by accident.

### Fixed (2026-04-30 publish-gate pentest pass)

- **ADV-050 (LOW):** Evaluation text validator now rejects DEL (0x7F) for
  consistency with every other validator in `journal.py`.
- **ADV-051 (MEDIUM):** `check_media_signals(namespace, handle)` now
  validates control characters in both fields. Without this, NUL/DEL/ANSI
  bytes from external counterparty data could echo back into the calling
  agent's prompt via the response `hint` field.
- **ADV-052 (MEDIUM):** `decode_signed` now validates `payload.signed_at`
  against the same ISO-8601 allowlist as Tier-2/3 `created_at`. A
  cryptographically-valid envelope with free-text `signed_at` (control
  chars, multiline prompt-injection) is rejected as `valid: False`.
- **ADV-053 (MEDIUM):** Evaluation `score` now requires
  `math.isfinite(score)` — ±inf is rejected. Defence in depth:
  `JournalStore._save` writes with `allow_nan=False` so the journal file
  is RFC-7159 valid even if a future code path bypasses validation.
- **ADV-054 (MEDIUM):** `providers._safe_number` now requires
  `math.isfinite(val)`. A hostile/compromised Tier-2/Tier-3 provider can
  no longer inject ±inf into the trust signal pipeline.
- **ADV-055 (MEDIUM):** `JournalStore` enforces per-record list cardinality
  caps (32 display_names, 16 aliases, 1024 evaluations, 64 custom_fields).
  Previously unbounded; one rotating-display-name counterparty could
  inflate the journal file without limit, blocking every other tool call.
- **ADV-056 (LOW):** Documented the proxy-blind rate-limit key in
  `witness/src/witness/rate_limit.py` (no behavioural change in v0.4.0;
  fix lands when witness flips to multi-tenant or removes the access
  gate).

### Fixed (2026-04-30 close-read pass)

- `_require_witness` and `_require_profile` helpers now return the
  narrowed value rather than raising-and-letting-mypy-narrow-via-assert,
  eliminating 6 `assert` statements that vanish under `python -O`.
- `journal.py` module docstring no longer references a non-existent
  `merge_records(a, b)` operation; v0.4 supports the `add_did` alias path
  with a v0.5 follow-up planned for first-class merge.

## [0.3.0] - 2026-04-21

Tool surface reshape around a tiered information architecture (orient → learn → act). Trust evaluation is now multi-provider. Naming is unified (noun-verb grouping: `recording_*`, `witness_*`). **This is a breaking release.** Existing MCP configurations using 0.2.0 tool names will stop working on upgrade — see the migration table below.

### Added

- `orient` — tiered overview of all 9 capability areas, entry point for fresh agents
- `learn` — per-area guide content, follow-up from `orient`
- `evaluate_agent` — multi-provider trust evaluation (synpareia, Moltbook, MolTrust), returns structured `TrustSignal` per provider via the adapter pattern in `providers.py`
- `prove_independence` — dedicated commit-before-reveal primitive, distinct from generic signing
- Area guides (`guides.py`) covering identity, claims, independence, recording, witness, trust evaluation, configuration, troubleshooting

### Changed

- **Breaking:** SDK dependency bumped to `synpareia[witness]>=0.3.0` — requires the new chain-policy-aware SDK and carries the breaking witness seal signature change (no more `requester_id` on public seal requests)
- **Breaking:** 12+ MCP tools renamed, consolidated, or removed. Migration table:

  | 0.2.0 tool                 | 0.3.0 equivalent                               |
  | -------------------------- | ---------------------------------------------- |
  | `get_my_identity`          | `orient` (profile surfaced in output)          |
  | `sign_content`             | `make_claim`                                   |
  | `verify_signature`         | `verify_claim`                                 |
  | `verify_identity`          | `verify_claim` (identity claim type)           |
  | `check_agent_trust`        | `evaluate_agent` (multi-provider)              |
  | `seal_commitment`          | `prove_independence`                           |
  | `reveal_commitment`        | `verify_claim` (commitment claim type)         |
  | `start_conversation`       | `recording_start`                              |
  | `add_to_conversation`      | `recording_append`                             |
  | `end_conversation`         | `recording_end`                                |
  | `get_conversation_proof`   | `recording_proof`                              |
  | `list_conversations`       | `recording_list`                               |
  | `get_witness_info`         | `witness_info`                                 |
  | `request_timestamp_seal`   | `witness_seal_timestamp`                       |
  | `request_state_seal`       | `witness_seal_state`                           |
  | `verify_seal_offline`      | `witness_verify_seal`                          |
  | `submit_blind_conclusion`  | `witness_submit_blind`                         |
  | `get_blind_conclusion`     | `witness_get_blind`                            |

  There is no shim layer — old names were removed outright. Any agent config referencing the old names must be updated in lockstep with the upgrade.

### Removed

- `trust-toolkit/src/synpareia_trust_mcp/tools/conversation.py` module (consolidated into `recording.py` with the new names)
- Standalone `get_my_identity` — the profile is now part of `orient`'s output

### Security

- Recording roundtrip verified end-to-end via `synpareia.verify_export` with the 0.3.0 policy-aware chain — tamper detection now covers the POLICY genesis block in addition to content blocks
- Witness seal requests no longer send `requester_id` (sparse-witness construction, ratifies Position 4 of the counterparty-reputation exploration)

## [0.2.0] - 2026-04-14

Witness service integration — timestamp seals, state seals, blind conclusions, liveness challenges.

### Added

- `get_witness_info` — witness identity, public key, service URL
- `request_timestamp_seal` — request a signed attestation that a block-hash existed at a given time
- `request_state_seal` — request a signed attestation over a chain head
- `verify_seal_offline` — offline verification of either seal type using the witness public key
- `submit_blind_conclusion` / `get_blind_conclusion` — witness-mediated blind conclusion flow
- Configuration via `SYNPAREIA_WITNESS_URL`, `SYNPAREIA_WITNESS_ACCESS_TOKEN`

## [0.1.0] - 2026-04-14

Initial release. 12 tools covering identity, signing, commitments, verified conversations.

### Added

- **Identity:** `get_my_identity`, `verify_identity`
- **Signing:** `sign_content`, `verify_signature`
- **Trust:** `check_agent_trust`
- **Commitments:** `seal_commitment`, `reveal_commitment`
- **Conversations:** `start_conversation`, `add_to_conversation`, `end_conversation`, `get_conversation_proof`, `list_conversations`
- Persistent local profile storage (`~/.synpareia/profile.json`, mode 0600)
- MCP server entry point (`synpareia-trust-mcp` via `pyproject.toml [project.scripts]`)
