# Changelog

All notable changes to `synpareia-trust-mcp` will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
