"""Tier-1 counterparty tools — local journal for agent-maintained records.

Per the four-tier reputation-evidence taxonomy
(docs/trust-capability.md §8, docs/explorations/counterparty-reputation.md):

- `remember_counterparty` — create/upsert a local record on first contact.
- `recall_counterparty` — read-only lookup by identifier or display name.
- `add_evaluation` — write an agent-authored note/tags/score to a record.
- `find_evaluations` — search evaluations across all records by tag.

These tools form a closed Tier-1 loop: nothing leaves the local data dir
and no external services are contacted. Agents can build durable,
searchable memory of counterparties without any network or identity
prerequisites.
"""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from mcp.server.fastmcp import Context

from synpareia_trust_mcp.app import AppContext, mcp
from synpareia_trust_mcp.journal import AgentRecord, RecordNotFoundError


@mcp.tool()
def remember_counterparty(
    namespace: str,
    namespace_id: str,
    display_name: str,
    ctx: Context,
    custom_fields: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Create or update a Tier-1 local record for a counterparty.

    `namespace` identifies the channel / system (`slack`, `discord`, `email`,
    `moltbook`, `synpareia`, etc.). `namespace_id` is the stable identifier
    within that namespace. Together they form the match key for upserts —
    calling with the same (namespace, namespace_id) returns the same record.

    `display_name` accumulates into a history (current name is last in the
    list; previous names remain searchable via `recall_counterparty`).

    `custom_fields` is a free-form dict of hints. See `learn("disambiguation")`
    for suggested vocabulary per namespace. Nested dicts are rejected;
    primitive values only (strings, numbers, booleans, lists of primitives).

    Returns the record dict including the local `identifier` (e.g.
    `local:<uuid4>`) — pass that identifier to `add_evaluation` or
    `recall_counterparty`.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        record = app.journal_store.upsert(
            namespace=namespace,
            namespace_id=namespace_id,
            display_name=display_name,
            custom_fields=custom_fields,
        )
    except ValueError as e:
        return {"error": str(e)}

    return _record_to_dict(record)


@mcp.tool()
def recall_counterparty(
    identifier_or_name: str,
    ctx: Context,
) -> dict[str, Any]:
    """Look up a counterparty in the Tier-1 local journal (read-only).

    Accepts either a record identifier (`local:...` or a DID alias) or a
    display name (exact or historical, case-insensitive). Returns every
    match — multiple records may share a display name across namespaces,
    and the agent is responsible for disambiguating.

    Zero matches returns an empty list; no error. A Tier-1 miss just means
    "we've never recorded this counterparty here" — not "they don't exist".
    """
    app: AppContext = ctx.request_context.lifespan_context
    matches: list[AgentRecord] = []

    direct = app.journal_store.get(identifier_or_name)
    if direct is not None:
        matches.append(direct)
    else:
        matches = app.journal_store.find_by_name(identifier_or_name)

    return {
        "query": identifier_or_name,
        "match_count": len(matches),
        "matches": [_record_to_dict(r) for r in matches],
        "reputation_tier": 1,
        "assurance_tier": 1,
    }


@mcp.tool()
def add_evaluation(
    identifier: str,
    text: str,
    ctx: Context,
    tags: list[str] | None = None,
    score: float | None = None,
) -> dict[str, Any]:
    """Attach an agent-written evaluation to an existing counterparty record.

    `text` is always required — a free-text note about the interaction.
    `tags` (optional) enables later search via `find_evaluations`.
    `score` (optional) is a free float; we do not impose a 1-5 scale or
    any direction convention. Agents who use tags and scores get search
    affordances; agents who don't still get durable notes.

    `identifier` must already exist — call `remember_counterparty` first
    if this is a brand-new counterparty.
    """
    app: AppContext = ctx.request_context.lifespan_context
    try:
        evaluation = app.journal_store.add_evaluation(
            identifier=identifier,
            text=text,
            tags=tags,
            score=score,
        )
    except RecordNotFoundError as e:
        return {"error": str(e)}
    except (TypeError, ValueError) as e:
        return {"error": str(e)}

    return {
        "ok": True,
        "identifier": identifier,
        "evaluation": asdict(evaluation),
    }


@mcp.tool()
def find_evaluations(
    tag: str,
    ctx: Context,
) -> dict[str, Any]:
    """Search Tier-1 evaluations across all counterparties by tag.

    Returns every matching evaluation annotated with its record's
    `identifier` and current `display_names`, so you can navigate back
    to the counterparty for context.

    Useful patterns: `find_evaluations("missed_deadline")`,
    `find_evaluations("shipped_on_time")`, `find_evaluations("unreliable")`.
    Tag vocabulary is agent-convention; see `learn("disambiguation")` for
    suggestions.
    """
    app: AppContext = ctx.request_context.lifespan_context
    raw = app.journal_store.find_evaluations(tag)
    results = [
        {
            "record_identifier": r["record_identifier"],
            "record_display_names": r["record_display_names"],
            "evaluation": asdict(r["evaluation"]),
        }
        for r in raw
    ]
    return {
        "tag": tag,
        "match_count": len(results),
        "results": results,
    }


def _record_to_dict(record: AgentRecord) -> dict[str, Any]:
    """Serialise an AgentRecord for tool output, flattening Evaluation dataclasses."""
    data = record.to_dict()
    return data
