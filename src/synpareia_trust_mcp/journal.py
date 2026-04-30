"""Counterparty journal — Tier 1 local records per the four-tier taxonomy.

See `docs/explorations/counterparty-reputation.md` and `docs/trust-capability.md`
for the capability design. This module is the backing store for
`recall_counterparty`, `add_evaluation`, and the Tier 1 leg of
`evaluate_agent`.

Storage is a single JSON file per data_dir (typical: ~/.synpareia/counterparties.json),
written with 0o600 permissions and atomic replace. That is enough for a
single-process MCP server; a multi-process or networked store is post-v1.

Key identity model (per decision #2, alias + lazy-merge):
- Primary key is `identifier`. On first contact with a counterparty we assign
  a random local ID (`local:<uuid4>`). The primary key never changes thereafter.
- DIDs and other portable identifiers are recorded as `aliases`. Lookups by
  alias resolve to the same primary record.
- If two local records later turn out to resolve to the same DID (e.g. both
  counterparties sign challenges with the same key), the caller is expected
  to leave the duplicate intact and add the DID alias to the canonical record
  via `add_did(...)` — we do not auto-merge, per the design's "explicit agent
  confirmation" rule. A first-class `merge_records(a, b)` operation is a
  v0.5 follow-up; for v0.4 the alias path is the supported workaround.
"""

from __future__ import annotations

import contextlib
import json
import math
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

MAX_NAMESPACE_LEN = 64
MAX_IDENTIFIER_LEN = 256
MAX_DISPLAY_NAME_LEN = 256
MAX_CUSTOM_FIELD_KEY_LEN = 64
MAX_CUSTOM_FIELD_VALUE_LEN = 1024
MAX_EVALUATION_TEXT_LEN = 8192
MAX_TAG_LEN = 64
MAX_TAGS_PER_EVALUATION = 16

# Per-record list cardinality caps (ADV-055, pentest 2026-04-30).
# The journal is "load-all-on-read, write-all-on-save"; a counterparty whose
# rotating display name fills these unbounded would inflate every subsequent
# operation linearly. Caps below are generous for legitimate use and bound
# the worst-case file size at low-MB scale.
MAX_DISPLAY_NAMES_PER_RECORD = 32
MAX_ALIASES_PER_RECORD = 16
MAX_EVALUATIONS_PER_RECORD = 1024
MAX_CUSTOM_FIELDS_PER_RECORD = 64
MAX_INTERACTIONS_PER_RECORD = 1024
MAX_SIGNED_CLAIMS_PER_RECORD = 256


class RecordNotFoundError(LookupError):
    """Raised when an operation targets a record that does not exist."""


@dataclass
class Evaluation:
    """An agent-written note on a counterparty (decision #4)."""

    text: str
    tags: list[str] = field(default_factory=list)
    score: float | None = None
    created_at: str = ""


@dataclass
class AgentRecord:
    """A Tier 1 local record of one counterparty.

    Schema follows `counterparty-reputation.md#data-model`. Fields beyond
    display_names + namespace_id are free-form (decision #3); we impose no
    hard schema on `custom_fields` but reject injection shapes via validation.
    """

    identifier: str
    namespace: str
    namespace_id: str | None
    display_names: list[str]
    custom_fields: dict[str, Any]
    interactions: list[dict[str, Any]]
    evaluations: list[Evaluation]
    signed_claims: list[dict[str, Any]]
    aliases: list[str]
    first_seen_at: str
    last_seen_at: str
    tier_max: int

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["evaluations"] = [asdict(e) for e in self.evaluations]
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRecord:
        evals = [Evaluation(**e) for e in data.get("evaluations", [])]
        return cls(
            identifier=data["identifier"],
            namespace=data["namespace"],
            namespace_id=data.get("namespace_id"),
            display_names=list(data.get("display_names", [])),
            custom_fields=dict(data.get("custom_fields", {})),
            interactions=list(data.get("interactions", [])),
            evaluations=evals,
            signed_claims=list(data.get("signed_claims", [])),
            aliases=list(data.get("aliases", [])),
            first_seen_at=data["first_seen_at"],
            last_seen_at=data["last_seen_at"],
            tier_max=int(data.get("tier_max", 1)),
        )


class JournalStore:
    """Single-file journal of AgentRecords.

    v1 is deliberately simple: load-all-on-read, write-all-on-save,
    atomic replace, 0o600 permissions. A per-record sharded store or
    an embedded database is deferred until the record count justifies it.
    """

    FILENAME = "counterparties.json"

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._path = data_dir / self.FILENAME

    def upsert(
        self,
        namespace: str,
        namespace_id: str | None,
        display_name: str,
        custom_fields: dict[str, Any] | None = None,
    ) -> AgentRecord:
        """Create a record or update an existing one (matched by namespace + namespace_id).

        Display names accumulate into a history list (current name is last).
        `custom_fields` merge into the existing dict.
        """
        _validate_namespace(namespace)
        _validate_display_name(display_name)
        if namespace_id is not None:
            _validate_namespace_id(namespace_id)
        merged_fields = _validate_custom_fields(custom_fields or {})

        records = self._load()
        now = _utcnow_iso()

        existing = _find_by_namespace_id(records, namespace, namespace_id)
        if existing is not None:
            if display_name not in existing.display_names:
                if len(existing.display_names) >= MAX_DISPLAY_NAMES_PER_RECORD:
                    msg = f"display_names cap reached (max {MAX_DISPLAY_NAMES_PER_RECORD})"
                    raise ValueError(msg)
                existing.display_names.append(display_name)
            # Cap custom_fields cardinality after merge.
            merged_total = {**existing.custom_fields, **merged_fields}
            if len(merged_total) > MAX_CUSTOM_FIELDS_PER_RECORD:
                msg = f"custom_fields cap reached (max {MAX_CUSTOM_FIELDS_PER_RECORD})"
                raise ValueError(msg)
            existing.custom_fields.update(merged_fields)
            existing.last_seen_at = now
            self._save(records)
            return existing

        record = AgentRecord(
            identifier=f"local:{uuid.uuid4()}",
            namespace=namespace,
            namespace_id=namespace_id,
            display_names=[display_name],
            custom_fields=merged_fields,
            interactions=[],
            evaluations=[],
            signed_claims=[],
            aliases=[],
            first_seen_at=now,
            last_seen_at=now,
            tier_max=1,
        )
        records.append(record)
        self._save(records)
        return record

    def get(self, identifier: str) -> AgentRecord | None:
        """Fetch by primary identifier or any alias. Returns None if missing."""
        for record in self._load():
            if record.identifier == identifier or identifier in record.aliases:
                return record
        return None

    def find_by_name(self, name: str) -> list[AgentRecord]:
        """Case-insensitive match across current + historical display names."""
        needle = name.lower()
        matches: list[AgentRecord] = []
        for record in self._load():
            if any(needle == dn.lower() for dn in record.display_names):
                matches.append(record)
        return matches

    def add_did(self, identifier: str, did: str) -> AgentRecord:
        """Record a DID as an alias on an existing local record.

        Lifts `tier_max` to at least 3: the caller is expected to have
        performed a signed-challenge verification before calling this.
        """
        records = self._load()
        record = _find_by_identifier(records, identifier)
        if record is None:
            msg = f"No record for identifier {identifier!r}"
            raise RecordNotFoundError(msg)
        if did not in record.aliases:
            if len(record.aliases) >= MAX_ALIASES_PER_RECORD:
                msg = f"aliases cap reached (max {MAX_ALIASES_PER_RECORD})"
                raise ValueError(msg)
            record.aliases.append(did)
        if record.tier_max < 3:
            record.tier_max = 3
        record.last_seen_at = _utcnow_iso()
        self._save(records)
        return record

    def add_evaluation(
        self,
        identifier: str,
        text: str,
        tags: list[str] | None = None,
        score: float | None = None,
    ) -> Evaluation:
        _validate_evaluation(text, tags or [], score)
        records = self._load()
        record = _find_by_identifier(records, identifier)
        if record is None:
            msg = f"No record for identifier {identifier!r}"
            raise RecordNotFoundError(msg)
        if len(record.evaluations) >= MAX_EVALUATIONS_PER_RECORD:
            msg = f"evaluations cap reached (max {MAX_EVALUATIONS_PER_RECORD})"
            raise ValueError(msg)
        evaluation = Evaluation(
            text=text,
            tags=list(tags or []),
            score=score,
            created_at=_utcnow_iso(),
        )
        record.evaluations.append(evaluation)
        record.last_seen_at = evaluation.created_at
        self._save(records)
        return evaluation

    def find_evaluations(self, tag: str) -> list[dict[str, Any]]:
        """Return every evaluation with this tag, annotated with its record id."""
        results: list[dict[str, Any]] = []
        for record in self._load():
            for evaluation in record.evaluations:
                if tag in evaluation.tags:
                    results.append(
                        {
                            "record_identifier": record.identifier,
                            "record_display_names": list(record.display_names),
                            "evaluation": evaluation,
                        }
                    )
        return results

    def all(self) -> list[AgentRecord]:
        return self._load()

    def _load(self) -> list[AgentRecord]:
        if not self._path.exists():
            return []
        try:
            data = json.loads(self._path.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            return []
        return [AgentRecord.from_dict(item) for item in data]

    def _save(self, records: list[AgentRecord]) -> None:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            self._data_dir.chmod(0o700)

        # `allow_nan=False` ensures we never write the non-RFC-7159 literals
        # `NaN`, `Infinity`, `-Infinity` to disk — defence in depth against
        # a future code path that bypasses `_validate_evaluation`.
        payload = json.dumps(
            [r.to_dict() for r in records],
            indent=2,
            sort_keys=False,
            allow_nan=False,
        ).encode()

        tmp = self._path.with_suffix(".json.tmp")
        if tmp.exists():
            tmp.unlink()
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)
        os.replace(tmp, self._path)
        with contextlib.suppress(OSError):
            self._path.chmod(0o600)


def _find_by_identifier(records: list[AgentRecord], identifier: str) -> AgentRecord | None:
    for r in records:
        if r.identifier == identifier or identifier in r.aliases:
            return r
    return None


def _find_by_namespace_id(
    records: list[AgentRecord], namespace: str, namespace_id: str | None
) -> AgentRecord | None:
    if namespace_id is None:
        return None
    for r in records:
        if r.namespace == namespace and r.namespace_id == namespace_id:
            return r
    return None


def _utcnow_iso() -> str:
    return datetime.now(UTC).isoformat()


def _validate_namespace(namespace: str) -> None:
    if not isinstance(namespace, str) or not namespace.strip():
        msg = "namespace must be a non-empty string"
        raise ValueError(msg)
    if len(namespace) > MAX_NAMESPACE_LEN:
        msg = f"namespace too long (max {MAX_NAMESPACE_LEN})"
        raise ValueError(msg)
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in namespace):
        msg = "namespace contains control characters"
        raise ValueError(msg)


def _validate_namespace_id(namespace_id: str) -> None:
    if not isinstance(namespace_id, str) or not namespace_id.strip():
        msg = "namespace_id must be a non-empty string when provided"
        raise ValueError(msg)
    if len(namespace_id) > MAX_IDENTIFIER_LEN:
        msg = f"namespace_id too long (max {MAX_IDENTIFIER_LEN})"
        raise ValueError(msg)
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in namespace_id):
        msg = "namespace_id contains control characters"
        raise ValueError(msg)


def _validate_display_name(name: str) -> None:
    if not isinstance(name, str) or not name.strip():
        msg = "display_name must be a non-empty string"
        raise ValueError(msg)
    if len(name) > MAX_DISPLAY_NAME_LEN:
        msg = f"display_name too long (max {MAX_DISPLAY_NAME_LEN})"
        raise ValueError(msg)
    if any(ord(c) < 0x20 or ord(c) == 0x7F for c in name):
        msg = "display_name contains control characters"
        raise ValueError(msg)


def _validate_custom_fields(fields: dict[str, Any]) -> dict[str, Any]:
    """Decision #3: no schema, but reject obvious injection shapes.

    Allow string / int / float / bool / None. Reject dicts/lists/nested
    structures and overlong strings.
    """
    if not isinstance(fields, dict):
        msg = "custom_fields must be a dict"
        raise ValueError(msg)
    out: dict[str, Any] = {}
    for key, value in fields.items():
        if not isinstance(key, str):
            msg = "custom_fields keys must be strings"
            raise ValueError(msg)
        if len(key) > MAX_CUSTOM_FIELD_KEY_LEN:
            msg = f"custom_fields key {key!r} too long"
            raise ValueError(msg)
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in key):
            msg = f"custom_fields key {key!r} contains control characters"
            raise ValueError(msg)
        if isinstance(value, str):
            if len(value) > MAX_CUSTOM_FIELD_VALUE_LEN:
                msg = f"custom_fields value for {key!r} too long"
                raise ValueError(msg)
            if any(ord(c) < 0x20 or ord(c) == 0x7F for c in value):
                msg = f"custom_fields value for {key!r} contains control characters"
                raise ValueError(msg)
        elif isinstance(value, (bool, int, float)) or value is None:
            pass
        else:
            msg = (
                f"custom_fields value for {key!r} must be a primitive "
                f"(string, int, float, bool, or None); got {type(value).__name__}"
            )
            raise ValueError(msg)
        out[key] = value
    return out


def _validate_evaluation(text: str, tags: list[str], score: float | None) -> None:
    if not isinstance(text, str) or not text.strip():
        msg = "evaluation text must be a non-empty string"
        raise ValueError(msg)
    if len(text) > MAX_EVALUATION_TEXT_LEN:
        msg = f"evaluation text too long (max {MAX_EVALUATION_TEXT_LEN})"
        raise ValueError(msg)
    if any((ord(c) < 0x20 and c not in "\n\r\t") or ord(c) == 0x7F for c in text):
        msg = "evaluation text contains control characters"
        raise ValueError(msg)

    if not isinstance(tags, list):
        msg = "tags must be a list of strings"
        raise ValueError(msg)
    if len(tags) > MAX_TAGS_PER_EVALUATION:
        msg = f"too many tags (max {MAX_TAGS_PER_EVALUATION})"
        raise ValueError(msg)
    for tag in tags:
        if not isinstance(tag, str) or not tag.strip():
            msg = "tags must be non-empty strings"
            raise ValueError(msg)
        if len(tag) > MAX_TAG_LEN:
            msg = f"tag {tag!r} too long"
            raise ValueError(msg)
        if any(ord(c) < 0x20 or ord(c) == 0x7F for c in tag):
            msg = f"tag {tag!r} contains control characters"
            raise ValueError(msg)

    if score is not None:
        if isinstance(score, bool) or not isinstance(score, (int, float)):
            msg = "score must be a number when provided"
            raise ValueError(msg)
        if not math.isfinite(score):
            # Catches both NaN and ±inf. The latter would (a) poison any
            # downstream aggregation as a single +inf evaluation dominates
            # any unguarded mean / weighted sum, and (b) be written to disk
            # as the literal `Infinity`, which is non-RFC-7159 JSON and
            # rejected by strict parsers in non-Python ecosystems
            # (pentest 2026-04-30 / ADV-053).
            msg = "score must be a finite number (NaN and ±inf rejected)"
            raise ValueError(msg)
