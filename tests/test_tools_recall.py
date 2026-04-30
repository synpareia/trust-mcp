"""Tests for Tier-1 counterparty tools (remember, recall, evaluations)."""

from __future__ import annotations

from synpareia_trust_mcp.tools.recall import (
    add_evaluation,
    find_evaluations,
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
