# Changelog

All notable changes to `synpareia-trust-mcp` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

## [0.6.1] - 2026-07-01

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

## [0.4.0] - 2026-04-23

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
  release and attaches a `deprecation` flag to the response. **It will
  be removed in v0.5.** Migrate by passing explicit `namespace` + `id`:

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

## [0.2.0] - 2026-04-16

Witness service integration — timestamp seals, state seals, blind conclusions, liveness challenges.

### Added

- `get_witness_info` — witness identity, public key, service URL
- `request_timestamp_seal` — request a signed attestation that a block-hash existed at a given time
- `request_state_seal` — request a signed attestation over a chain head
- `verify_seal_offline` — offline verification of either seal type using the witness public key
- `submit_blind_conclusion` / `get_blind_conclusion` — witness-mediated blind conclusion flow
- Configuration via `SYNPAREIA_WITNESS_URL`, `SYNPAREIA_WITNESS_ACCESS_TOKEN`

## [0.1.0] - 2026-04-12

Initial release. 12 tools covering identity, signing, commitments, verified conversations.

### Added

- **Identity:** `get_my_identity`, `verify_identity`
- **Signing:** `sign_content`, `verify_signature`
- **Trust:** `check_agent_trust`
- **Commitments:** `seal_commitment`, `reveal_commitment`
- **Conversations:** `start_conversation`, `add_to_conversation`, `end_conversation`, `get_conversation_proof`, `list_conversations`
- Persistent local profile storage (`~/.synpareia/profile.json`, mode 0600)
- MCP server entry point (`synpareia-trust-mcp` via `pyproject.toml [project.scripts]`)
