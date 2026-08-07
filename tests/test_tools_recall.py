"""Tests for Tier-1 counterparty tools (remember, recall, evaluations)."""

from __future__ import annotations

import json

from synpareia_trust_mcp.tools.recall import (
    add_evaluation,
    find_evaluations,
    forget_counterparty,
    recall_counterparty,
    remember_counterparty,
)


class TestRememberCounterparty:
    def test_creates_new_record(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = remember_counterparty(
            namespace="slack",
            namespace_id="T0ABC/U0123",
            display_name="alice",
            ctx=ctx,
        )
        assert result["identifier"].startswith("local:")
        assert result["namespace"] == "slack"
        assert result["namespace_id"] == "T0ABC/U0123"
        assert result["display_names"] == ["alice"]
        assert result["tier_max"] == 1

    def test_upsert_returns_same_identifier(self, app_ctx) -> None:
        ctx, app = app_ctx
        first = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        second = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        assert first["identifier"] == second["identifier"]

    def test_merges_custom_fields(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(
            namespace="slack",
            namespace_id="U1",
            display_name="alice",
            custom_fields={"team_id": "T0ABC"},
            ctx=ctx,
        )
        updated = remember_counterparty(
            namespace="slack",
            namespace_id="U1",
            display_name="alice",
            custom_fields={"channel_id": "C0DEF"},
            ctx=ctx,
        )
        assert updated["custom_fields"] == {
            "team_id": "T0ABC",
            "channel_id": "C0DEF",
        }

    def test_tracks_display_name_history(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx)
        updated = remember_counterparty(
            namespace="slack",
            namespace_id="U1",
            display_name="alice_smith",
            ctx=ctx,
        )
        assert updated["display_names"] == ["alice", "alice_smith"]

    def test_rejects_empty_namespace(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = remember_counterparty(
            namespace="", namespace_id="U1", display_name="alice", ctx=ctx
        )
        assert "error" in result

    def test_rejects_control_characters(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = remember_counterparty(
            namespace="slack",
            namespace_id="U1",
            display_name="alice\x00sneaky",
            ctx=ctx,
        )
        assert "error" in result


class TestRecallCounterparty:
    def test_lookup_by_identifier(self, app_ctx) -> None:
        ctx, app = app_ctx
        created = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        result = recall_counterparty(identifier_or_name=created["identifier"], ctx=ctx)
        assert result["matches"][0]["identifier"] == created["identifier"]
        assert result["match_count"] == 1

    def test_lookup_by_display_name(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx)
        result = recall_counterparty(identifier_or_name="alice", ctx=ctx)
        assert result["match_count"] == 1
        assert result["matches"][0]["display_names"] == ["alice"]

    def test_lookup_case_insensitive_name(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(namespace="slack", namespace_id="U1", display_name="Alice", ctx=ctx)
        result = recall_counterparty(identifier_or_name="alice", ctx=ctx)
        assert result["match_count"] == 1

    def test_lookup_historical_name(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx)
        remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice_smith", ctx=ctx
        )
        result = recall_counterparty(identifier_or_name="alice", ctx=ctx)
        assert result["match_count"] == 1

    def test_multiple_matches_returned(self, app_ctx) -> None:
        ctx, app = app_ctx
        remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="bot_alice", ctx=ctx
        )
        remember_counterparty(
            namespace="discord", namespace_id="D1", display_name="bot_alice", ctx=ctx
        )
        result = recall_counterparty(identifier_or_name="bot_alice", ctx=ctx)
        assert result["match_count"] == 2

    def test_no_matches_empty_list(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = recall_counterparty(identifier_or_name="unknown", ctx=ctx)
        assert result["match_count"] == 0
        assert result["matches"] == []

    def test_returns_assurance_tier(self, app_ctx) -> None:
        ctx, app = app_ctx
        created = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        result = recall_counterparty(identifier_or_name=created["identifier"], ctx=ctx)
        assert result["assurance_tier"] == 1
        assert result["reputation_tier"] == 1


class TestAddEvaluation:
    def test_freetext_only(self, app_ctx) -> None:
        ctx, app = app_ctx
        created = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        result = add_evaluation(
            identifier=created["identifier"],
            text="Shipped on time.",
            ctx=ctx,
        )
        assert result["ok"] is True
        assert result["evaluation"]["text"] == "Shipped on time."
        assert result["evaluation"]["tags"] == []
        assert result["evaluation"]["score"] is None

    def test_with_tags_and_score(self, app_ctx) -> None:
        ctx, app = app_ctx
        created = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        result = add_evaluation(
            identifier=created["identifier"],
            text="Missed deadline.",
            tags=["missed_deadline"],
            score=0.3,
            ctx=ctx,
        )
        assert result["evaluation"]["tags"] == ["missed_deadline"]
        assert result["evaluation"]["score"] == 0.3

    def test_missing_record_returns_error(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = add_evaluation(
            identifier="local:does-not-exist",
            text="hello",
            ctx=ctx,
        )
        assert "error" in result

    def test_invalid_score_returns_error(self, app_ctx) -> None:
        ctx, app = app_ctx
        created = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        result = add_evaluation(
            identifier=created["identifier"],
            text="hello",
            score="not-a-number",  # type: ignore[arg-type]
            ctx=ctx,
        )
        assert "error" in result


class TestFindEvaluations:
    def test_finds_by_tag(self, app_ctx) -> None:
        ctx, app = app_ctx
        a = remember_counterparty(
            namespace="slack", namespace_id="U1", display_name="alice", ctx=ctx
        )
        b = remember_counterparty(namespace="slack", namespace_id="U2", display_name="bob", ctx=ctx)
        add_evaluation(
            identifier=a["identifier"],
            text="bad",
            tags=["missed_deadline"],
            ctx=ctx,
        )
        add_evaluation(
            identifier=b["identifier"],
            text="good",
            tags=["on_time"],
            ctx=ctx,
        )
        result = find_evaluations(tag="missed_deadline", ctx=ctx)
        assert result["match_count"] == 1
        assert result["results"][0]["record_identifier"] == a["identifier"]
        assert result["results"][0]["evaluation"]["text"] == "bad"

    def test_returns_empty_for_unknown_tag(self, app_ctx) -> None:
        ctx, app = app_ctx
        result = find_evaluations(tag="nonexistent", ctx=ctx)
        assert result["match_count"] == 0
        assert result["results"] == []


class TestForgetCounterparty:
    def test_erases_record_and_evaluations(self, app_ctx) -> None:
        ctx, app = app_ctx
        rec = remember_counterparty(
            namespace="slack", namespace_id="U9", display_name="mallory", ctx=ctx
        )
        add_evaluation(identifier=rec["identifier"], text="unreliable", tags=["late"], ctx=ctx)
        result = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        assert result["ok"] is True
        assert result["forgotten"] is True
        assert result["evaluations_erased"] == 1
        assert "mallory" in result["display_names"]
        # Gone from the journal.
        after = recall_counterparty(identifier_or_name=rec["identifier"], ctx=ctx)
        assert after["match_count"] == 0
        # And gone from evaluation search.
        assert find_evaluations(tag="late", ctx=ctx)["match_count"] == 0

    def test_erasure_is_idempotent(self, app_ctx) -> None:
        ctx, app = app_ctx
        # Never-seen identifier: no error, forgotten=False.
        result = forget_counterparty(identifier="local:does-not-exist", ctx=ctx)
        assert result["ok"] is True
        assert result["forgotten"] is False

    def test_erases_by_did_alias(self, app_ctx) -> None:
        ctx, app = app_ctx
        rec = remember_counterparty(
            namespace="synpareia", namespace_id="did:synpareia:abc", display_name="bob", ctx=ctx
        )
        # remember_counterparty stores a local:... id; erase by that id.
        result = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        assert result["forgotten"] is True
        assert recall_counterparty(identifier_or_name="bob", ctx=ctx)["match_count"] == 0

    def test_only_erases_the_named_record(self, app_ctx) -> None:
        ctx, app = app_ctx
        keep = remember_counterparty(
            namespace="slack", namespace_id="K1", display_name="keeper", ctx=ctx
        )
        drop = remember_counterparty(
            namespace="slack", namespace_id="D1", display_name="dropme", ctx=ctx
        )
        forget_counterparty(identifier=drop["identifier"], ctx=ctx)
        assert (
            recall_counterparty(identifier_or_name=keep["identifier"], ctx=ctx)["match_count"] == 1
        )
        assert (
            recall_counterparty(identifier_or_name=drop["identifier"], ctx=ctx)["match_count"] == 0
        )

    def test_success_message_scopes_erasure_to_journal(self, app_ctx) -> None:
        # Publish-gate legal: the return must not let an agent over-report
        # erasure — it names the journal scope and flags untouched audit trails.
        ctx, app = app_ctx
        rec = remember_counterparty(namespace="slack", namespace_id="S1", display_name="s", ctx=ctx)
        result = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        assert result["scope"] == "local_journal_only"
        assert "NOT erased" in result["message"]

    def test_malformed_row_does_not_crash_forget(self, app_ctx) -> None:
        # Publish-gate pentest LOW-1 + PR #329 review: a malformed row is
        # skipped centrally in _load, so forget over a journal that contains a
        # bad row still succeeds on the clean records rather than raising.
        ctx, app = app_ctx
        rec = remember_counterparty(
            namespace="slack", namespace_id="clean", display_name="ok", ctx=ctx
        )
        # Inject a malformed row alongside the clean one.
        path = app.journal_store._path
        data = json.loads(path.read_text())
        data.append({"identifier": "local:broken"})  # missing required fields
        path.write_text(json.dumps(data))
        result = forget_counterparty(identifier=rec["identifier"], ctx=ctx)
        assert result["ok"] is True
        assert result["forgotten"] is True

    def test_save_failure_fails_closed_not_raises(self, app_ctx, monkeypatch) -> None:
        # The write-path guard: an OSError from _save must return the
        # idempotent-no-error structured failure, not raise out of the tool.
        ctx, app = app_ctx

        def boom(identifier):
            raise OSError("disk full")

        monkeypatch.setattr(app.journal_store, "delete", boom)
        result = forget_counterparty(identifier="local:whatever", ctx=ctx)
        assert result["ok"] is False
        assert result["forgotten"] is False
        assert "error" in result and "OSError" in result["error"]


class TestEvaluationOnMissingRecordCarriesItsRecovery:
    """The dead end a live agent actually hit.

    `add_evaluation`'s docstring says to call `remember_counterparty` first. But
    an agent that reaches the error has already read past the docstring — a
    prerequisite stated only upstream of a failure is not available at the
    moment it is needed. A live agent attempting its one reputation workflow got
    "No record for identifier <name>" and stopped there (#142).

    So the error response must carry the recovery, not just the diagnosis.
    """

    def test_error_names_the_prerequisite_tool(self, app_ctx) -> None:  # noqa: ANN001
        from synpareia_trust_mcp.tools.recall import add_evaluation

        ctx, _ = app_ctx
        result = add_evaluation(identifier="nobody", text="a note", ctx=ctx)

        assert "error" in result
        recovery = result.get("recovery")
        assert recovery, "the failure gives no way forward"
        assert recovery["tool"] == "remember_counterparty"
        assert "nobody" in recovery["why"]
        assert "add_evaluation" in recovery["then"], "must say to retry the original call"

    def test_error_is_machine_dispatchable_not_just_prose(self, app_ctx) -> None:  # noqa: ANN001
        """A recovery an agent has to parse out of a sentence is a worse
        affordance than one it can branch on. Pin the code separately from the
        prose so rewording the message cannot silently drop it."""
        from synpareia_trust_mcp.tools.recall import add_evaluation

        ctx, _ = app_ctx
        result = add_evaluation(identifier="nobody", text="a note", ctx=ctx)
        assert result.get("code") == "no_such_counterparty"

    def test_the_recovery_path_actually_works(self, app_ctx) -> None:  # noqa: ANN001
        """Following the stated recovery must resolve the failure.

        Otherwise this is a recovery hint that has never been walked — the same
        class as an alerting path that has never fired.
        """
        from synpareia_trust_mcp.tools.recall import add_evaluation, remember_counterparty

        ctx, _ = app_ctx
        assert "error" in add_evaluation(identifier="wren", text="a note", ctx=ctx)

        remembered = remember_counterparty(
            namespace="forum", namespace_id="wren", display_name="wren", ctx=ctx
        )
        # NOTE: remember_counterparty returns the RECORD, while add_evaluation
        # returns an {"ok": True, ...} envelope. Asserting `.get("ok")` here
        # failed against correct code — the inconsistency is real but it is
        # pre-existing surface shape, tracked under #67, not this slice's to fix.
        assert "error" not in remembered, remembered
        assert "wren" in remembered["display_names"]

        # The naive retry — same string the agent used to record them — STILL
        # fails, because the record's identifier is an opaque local:<uuid>.
        # This is the second half of the dead end, and the reason the first
        # version of the recovery text was wrong.
        naive = add_evaluation(identifier="wren", text="a note", ctx=ctx)
        assert "error" in naive
        assert naive["code"] == "identifier_is_not_a_display_name"
        assert remembered["identifier"] in naive["recovery"]["use_identifier"]

        # Following the CORRECTED recovery resolves it.
        retried = add_evaluation(identifier=remembered["identifier"], text="a note", ctx=ctx)
        assert retried.get("ok"), retried
