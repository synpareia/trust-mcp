"""Tests for the counterparty journal store (Tier 1 local records)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from synpareia_trust_mcp.journal import (
    JournalStore,
    RecordNotFoundError,
)


class TestLoadRobustness:
    """A corrupt counterparties.json must degrade gracefully, not crash the
    read tools that call _load (PR #329 review: the fix is central to _load,
    so recall/remember/add/find/forget all benefit)."""

    def test_malformed_row_is_skipped_not_raised(self, store: JournalStore, capsys) -> None:
        good = store.upsert(namespace="slack", namespace_id="G", display_name="good")
        # Append a row missing required fields — would KeyError in from_dict.
        data = json.loads(store._path.read_text())
        data.append({"identifier": "local:broken", "display_names": ["x"]})
        store._path.write_text(json.dumps(data))
        # A fresh store over the same file loads only the valid record.
        reloaded = JournalStore(store._data_dir)
        records = reloaded.all()
        assert [r.identifier for r in records] == [good.identifier]
        assert "skipping malformed journal record" in capsys.readouterr().err

    def test_non_list_top_level_is_empty_not_raised(self, store: JournalStore) -> None:
        store._path.parent.mkdir(parents=True, exist_ok=True)
        store._path.write_text(json.dumps({"not": "a list"}))
        assert JournalStore(store._data_dir).all() == []


@pytest.fixture()
def store(tmp_path: Path) -> JournalStore:
    return JournalStore(tmp_path / "journal")


class TestCreateAndRecall:
    def test_create_without_did_gets_local_identifier(self, store: JournalStore) -> None:
        record = store.upsert(
            namespace="slack",
            namespace_id="T0ABC/U0123",
            display_name="alice",
        )
        assert record.identifier.startswith("local:")
        assert record.namespace == "slack"
        assert record.namespace_id == "T0ABC/U0123"
        assert "alice" in record.display_names
        assert record.tier_max == 1
        assert record.first_seen_at is not None
        assert record.last_seen_at == record.first_seen_at

    def test_upsert_same_namespace_id_returns_same_record(self, store: JournalStore) -> None:
        first = store.upsert(namespace="slack", namespace_id="T0ABC/U0123", display_name="alice")
        second = store.upsert(namespace="slack", namespace_id="T0ABC/U0123", display_name="alice")
        assert first.identifier == second.identifier

    def test_upsert_tracks_display_name_history(self, store: JournalStore) -> None:
        store.upsert(namespace="slack", namespace_id="T0ABC/U0123", display_name="alice")
        updated = store.upsert(
            namespace="slack",
            namespace_id="T0ABC/U0123",
            display_name="alice_smith",
        )
        assert "alice" in updated.display_names
        assert "alice_smith" in updated.display_names
        assert updated.display_names[-1] == "alice_smith"

    def test_upsert_updates_last_seen(self, store: JournalStore) -> None:
        first = store.upsert(namespace="slack", namespace_id="T0ABC/U0123", display_name="alice")
        second = store.upsert(namespace="slack", namespace_id="T0ABC/U0123", display_name="alice")
        assert second.last_seen_at >= first.last_seen_at
        assert second.first_seen_at == first.first_seen_at

    def test_recall_by_identifier(self, store: JournalStore) -> None:
        created = store.upsert(namespace="slack", namespace_id="U1", display_name="bob")
        recalled = store.get(created.identifier)
        assert recalled is not None
        assert recalled.identifier == created.identifier
        assert recalled.display_names == ["bob"]

    def test_recall_by_missing_identifier_returns_none(self, store: JournalStore) -> None:
        assert store.get("local:does-not-exist") is None

    def test_find_by_display_name_exact(self, store: JournalStore) -> None:
        store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.upsert(namespace="discord", namespace_id="D1", display_name="bob")
        matches = store.find_by_name("alice")
        assert len(matches) == 1
        assert matches[0].namespace == "slack"

    def test_find_by_display_name_case_insensitive(self, store: JournalStore) -> None:
        store.upsert(namespace="slack", namespace_id="U1", display_name="Alice")
        matches = store.find_by_name("alice")
        assert len(matches) == 1

    def test_find_by_display_name_historical(self, store: JournalStore) -> None:
        """A counterparty's old name should still find them after rename."""
        store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.upsert(namespace="slack", namespace_id="U1", display_name="alice_smith")
        assert len(store.find_by_name("alice")) == 1
        assert len(store.find_by_name("alice_smith")) == 1

    def test_find_by_display_name_disambiguation(self, store: JournalStore) -> None:
        """Multiple counterparties with the same display name return a list."""
        store.upsert(namespace="slack", namespace_id="U1", display_name="bot_alice")
        store.upsert(namespace="discord", namespace_id="D1", display_name="bot_alice")
        matches = store.find_by_name("bot_alice")
        assert len(matches) == 2


class TestPersistence:
    def test_survives_reload(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "journal"
        store1 = JournalStore(data_dir)
        created = store1.upsert(
            namespace="slack",
            namespace_id="U1",
            display_name="alice",
            custom_fields={"team_id": "T0ABC", "channel_id": "C0DEF"},
        )

        store2 = JournalStore(data_dir)
        recalled = store2.get(created.identifier)
        assert recalled is not None
        assert recalled.custom_fields == {"team_id": "T0ABC", "channel_id": "C0DEF"}

    def test_store_file_has_restrictive_permissions(self, tmp_path: Path) -> None:
        """The journal can reveal interaction patterns — don't leak to other users."""
        data_dir = tmp_path / "journal"
        store = JournalStore(data_dir)
        store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        journal_path = data_dir / "counterparties.json"
        mode = journal_path.stat().st_mode & 0o777
        assert mode == 0o600


class TestDIDAlias:
    def test_add_did_alias_to_existing_record(self, store: JournalStore) -> None:
        """Per decision #2 (alias + lazy-merge): DID arrives later, becomes alias."""
        record = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        original_id = record.identifier

        updated = store.add_did(record.identifier, "did:synpareia:xyz")
        assert updated.identifier == original_id  # primary key unchanged
        assert "did:synpareia:xyz" in updated.aliases
        assert updated.tier_max >= 3  # DID verification bumps tier

    def test_recall_by_did_after_alias(self, store: JournalStore) -> None:
        record = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.add_did(record.identifier, "did:synpareia:xyz")
        found = store.get("did:synpareia:xyz")
        assert found is not None
        assert found.identifier == record.identifier


class TestEvaluations:
    def test_add_evaluation_freetext_only(self, store: JournalStore) -> None:
        record = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.add_evaluation(record.identifier, text="Shipped on time, clear comms.")
        recalled = store.get(record.identifier)
        assert recalled is not None
        assert len(recalled.evaluations) == 1
        assert recalled.evaluations[0].text == "Shipped on time, clear comms."
        assert recalled.evaluations[0].tags == []
        assert recalled.evaluations[0].score is None

    def test_add_evaluation_with_tags_and_score(self, store: JournalStore) -> None:
        record = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.add_evaluation(
            record.identifier,
            text="Missed deadline but recovered.",
            tags=["missed_deadline", "recovered"],
            score=0.6,
        )
        recalled = store.get(record.identifier)
        assert recalled is not None
        eval_ = recalled.evaluations[0]
        assert eval_.tags == ["missed_deadline", "recovered"]
        assert eval_.score == 0.6

    def test_add_evaluation_to_missing_record_raises(self, store: JournalStore) -> None:
        with pytest.raises(RecordNotFoundError):
            store.add_evaluation("local:nonexistent", text="anything")

    def test_find_evaluations_by_tag(self, store: JournalStore) -> None:
        a = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        b = store.upsert(namespace="slack", namespace_id="U2", display_name="bob")
        store.add_evaluation(a.identifier, text="bad", tags=["missed_deadline"])
        store.add_evaluation(b.identifier, text="good", tags=["on_time"])
        store.add_evaluation(a.identifier, text="recovered", tags=["recovered"])

        results = store.find_evaluations(tag="missed_deadline")
        assert len(results) == 1
        assert results[0]["record_identifier"] == a.identifier
        assert results[0]["evaluation"].text == "bad"


class TestInputValidation:
    """Matches the existing input-validation hardening across other tools (ADV-011)."""

    def test_rejects_empty_namespace(self, store: JournalStore) -> None:
        with pytest.raises(ValueError):
            store.upsert(namespace="", namespace_id="U1", display_name="alice")

    def test_rejects_control_characters_in_display_name(self, store: JournalStore) -> None:
        with pytest.raises(ValueError):
            store.upsert(namespace="slack", namespace_id="U1", display_name="alice\x00sneaky")

    def test_caps_display_name_length(self, store: JournalStore) -> None:
        with pytest.raises(ValueError):
            store.upsert(namespace="slack", namespace_id="U1", display_name="x" * 10_000)

    def test_rejects_non_primitive_custom_field_values(self, store: JournalStore) -> None:
        """Design decision #3: suggested vocabulary, but validation rejects injection shapes."""
        with pytest.raises(ValueError):
            store.upsert(
                namespace="slack",
                namespace_id="U1",
                display_name="alice",
                custom_fields={"injection": {"nested": {"dict": "payload"}}},
            )


class TestDataclassRoundtrip:
    def test_serialize_and_restore(self, tmp_path: Path) -> None:
        store = JournalStore(tmp_path / "journal")
        r = store.upsert(
            namespace="slack",
            namespace_id="U1",
            display_name="alice",
            custom_fields={"team_id": "T0ABC"},
        )
        store.add_evaluation(r.identifier, text="test eval", tags=["t1"], score=0.5)
        store2 = JournalStore(tmp_path / "journal")
        restored = store2.get(r.identifier)
        assert restored is not None
        assert restored.evaluations[0].text == "test eval"
        assert restored.evaluations[0].score == 0.5


class TestDelete:
    def test_delete_removes_record_and_returns_it(self, store: JournalStore) -> None:
        r = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.add_evaluation(r.identifier, text="note", tags=["t"], score=0.5)
        removed = store.delete(r.identifier)
        assert removed is not None
        assert removed.identifier == r.identifier
        assert len(removed.evaluations) == 1
        assert store.get(r.identifier) is None
        assert store.all() == []

    def test_delete_missing_returns_none(self, store: JournalStore) -> None:
        assert store.delete("local:nope") is None

    def test_delete_by_did_alias(self, store: JournalStore) -> None:
        r = store.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        store.add_did(r.identifier, "did:synpareia:deadbeef")
        removed = store.delete("did:synpareia:deadbeef")
        assert removed is not None
        assert store.get(r.identifier) is None

    def test_delete_leaves_other_records(self, store: JournalStore) -> None:
        keep = store.upsert(namespace="slack", namespace_id="K", display_name="keep")
        drop = store.upsert(namespace="slack", namespace_id="D", display_name="drop")
        store.delete(drop.identifier)
        assert store.get(keep.identifier) is not None
        assert store.get(drop.identifier) is None

    def test_delete_persists_to_disk(self, tmp_path: Path) -> None:
        d = tmp_path / "journal"
        s1 = JournalStore(d)
        r = s1.upsert(namespace="slack", namespace_id="U1", display_name="alice")
        s1.delete(r.identifier)
        # Fresh store reading the same file must not see the deleted record.
        s2 = JournalStore(d)
        assert s2.get(r.identifier) is None
