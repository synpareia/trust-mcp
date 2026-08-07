"""Tier-1 counterparty tools — local journal for agent-maintained records.

Per the four-tier reputation-evidence taxonomy
(docs/trust-capability.md §8, docs/explorations/counterparty-reputation.md):

- `remember_counterparty` — create/upsert a local record on first contact.
- `recall_counterparty` — read-only lookup by identifier or display name.
- `add_evaluation` — write an agent-authored note/tags/score to a record.
- `find_evaluations` — search evaluations across all records by tag.
- `forget_counterparty` — erase a record and all its evaluations (Art. 17).

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

    `custom_fields` is a free-form dict of hints — use your own consistent
    vocabulary per namespace (e.g. `role`, `org`, `first_seen`). Nested dicts
    are rejected; primitive values only (strings, numbers, booleans, lists of
    primitives).

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

    # AgentRecord.to_dict flattens the Evaluation dataclasses for tool output.
    return record.to_dict()


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
        "matches": [r.to_dict() for r in matches],
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
        # The docstring above already says to call remember_counterparty first
        # — but an agent that reached THIS error has, by definition, already
        # read past the docstring. A prerequisite stated only upstream of the
        # failure is not available at the moment it is needed.
        #
        # This is not hypothetical: it is the one reputation workflow a live
        # agent attempted, and a bare "No record for identifier" ended it. The
        # agent had the tools, had the intent, and got a dead end (#142).
        # And the naive recovery ("call remember_counterparty, then retry with
        # the same identifier") DOES NOT WORK. `upsert` assigns an opaque
        # `local:<uuid>` as the record's identifier; resolution matches only
        # that or an explicit alias, never a display name. So an agent that
        # records a counterparty by display name and then evaluates that same
        # name hits this error a
        # second time, having done exactly what it was told.
        #
        # Resolution semantics are deliberately left alone here — matching on
        # display names would make lookup ambiguous whenever two counterparties
        # share a name, which is a design call, not a bugfix (raised under #67).
        # What changes is the DIAGNOSIS: if a record with that display name
        # exists, hand back the identifier that will actually work.
        by_name = app.journal_store.find_by_name(identifier)
        if by_name:
            return {
                "error": str(e),
                "code": "identifier_is_not_a_display_name",
                "recovery": {
                    "why": (
                        f"{identifier!r} is a display name, not an identifier. "
                        f"{len(by_name)} record(s) display it."
                    ),
                    "use_identifier": [r.identifier for r in by_name],
                    "then": (
                        "Retry add_evaluation with one of those identifier values "
                        "(the `identifier` field of the record, not its name)."
                    ),
                },
            }
        return {
            "error": str(e),
            "code": "no_such_counterparty",
            "recovery": {
                "tool": "remember_counterparty",
                "why": (
                    f"Evaluations attach to a counterparty you have already recorded, "
                    f"and no record matches {identifier!r} yet."
                ),
                "then": (
                    "Retry add_evaluation using the `identifier` field from that "
                    "call's response — a `local:<uuid>` value. Passing the display "
                    "name again will fail the same way."
                ),
            },
        }
    except (TypeError, ValueError) as e:
        return {"error": str(e)}

    return {
        "ok": True,
        "identifier": identifier,
        "evaluation": asdict(evaluation),
    }


@mcp.tool()
def forget_counterparty(
    identifier: str,
    ctx: Context,
) -> dict[str, Any]:
    """Erase a counterparty and all your evaluations of them from the local journal.

    Permanently removes the Tier-1 record matched by `identifier` (a
    `local:...` id or a DID alias) — its display-name history, custom fields,
    and every note/score you attached. This is the local-data counterpart to
    the directory-side `delete_profile`: it is how "erasure stays under your
    control" is enforced for **the counterparty journal** (GDPR Art. 17, on
    your own machine). Your private notes were never uploaded, so there is no
    journal copy elsewhere to recall.

    Scope — read this before reporting an erasure to a data subject: this
    erases the **journal** record only. Signed conversation/recording chains
    (stored in ``conversations/`` as ``conv_<id>.json``) that reference the
    same counterparty are NOT touched by this tool (deleting them would break
    the tamper-evidence property they exist for); the response says so on every
    successful erase so you don't over-report.

    Erasure is idempotent: forgetting an identifier that isn't (or is no
    longer) in the journal returns ``forgotten: false`` without error — the
    end state (no such record) is what erasure guarantees. Call
    `recall_counterparty` first if you want to confirm the identifier before
    erasing.
    """
    app: AppContext = ctx.request_context.lifespan_context
    # _load now skips malformed rows centrally (journal.py), so a corrupt row
    # no longer raises here. This guards the remaining write-path failure (an
    # OSError from _save: disk full / permission) so the documented
    # idempotent-no-error erasure contract holds even then. Narrow, not bare —
    # a programming error in delete() still surfaces loudly (reviewer nit).
    try:
        removed = app.journal_store.delete(identifier)
    except OSError as exc:
        return {
            "ok": False,
            "forgotten": False,
            "identifier": identifier,
            "error": f"{type(exc).__name__}: {exc}"[:200],
            "message": (
                "Could not complete erasure — the local journal could not be "
                "rewritten (disk full or permissions?). No record was removed. "
                "Inspect the counterparties.json data file."
            ),
        }
    if removed is None:
        return {
            "ok": True,
            "forgotten": False,
            "identifier": identifier,
            "message": (
                f"No journal record matched '{identifier}' — nothing to erase. "
                "It may already be gone, or the identifier is wrong "
                "(recall_counterparty to check)."
            ),
        }
    return {
        "ok": True,
        "forgotten": True,
        "identifier": removed.identifier,
        "display_names": list(removed.display_names),
        "evaluations_erased": len(removed.evaluations),
        "scope": "local_journal_only",
        "message": (
            "Erased from your local journal — this counterparty record and all "
            "your evaluations of them are permanently removed. Note: any signed "
            "conversation/recording chains (in conversations/) reference the "
            "counterparty by DID and are NOT erased by this tool."
        ),
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
    Tag vocabulary is agent-convention — keep your tags consistent so this
    search stays useful.
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
