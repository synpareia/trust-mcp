"""Tests for the MCP write path's two load-bearing behaviours.

Both were found BROKEN by a gate review, in a surface that had no tests in this
package. Keeping them here rather than in the monorepo's service suite is the
point: this is what the published repo's CI actually runs.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from synpareia_trust_mcp.tools.directory import _consent_aware_error, _stable_event_time

_NOW = datetime(2026, 7, 30, 12, 0, 0, tzinfo=UTC)
_LATER = datetime(2026, 7, 30, 13, 30, 0, tzinfo=UTC)


class TestStableEventTime:
    def test_a_retry_reuses_the_first_timestamp(self, tmp_path: Path) -> None:
        """The bug this exists for: without it, `record_interaction` had NO
        idempotency while documenting that it did.

        `created_at` binds into the signing envelope, so a fresh `now()` per
        attempt yields a different event hash every time — a retry after a
        network timeout records a second interaction on a live shared graph and
        re-applies the valence. A stable id alone does not help; the timestamp
        beside it is what varies.
        """
        first = _stable_event_time(tmp_path, "evt_abc", _NOW)
        second = _stable_event_time(tmp_path, "evt_abc", _LATER)
        assert first == _NOW
        assert second == _NOW, (
            "a retry got a fresh timestamp — the envelope differs, so the "
            "directory sees a second interaction rather than a duplicate"
        )

    def test_a_different_id_gets_its_own_timestamp(self, tmp_path: Path) -> None:
        """Positive control. Without it the test above would pass against an
        implementation that pinned ONE timestamp for everything, which would
        mis-date every subsequent interaction."""
        _stable_event_time(tmp_path, "evt_abc", _NOW)
        assert _stable_event_time(tmp_path, "evt_xyz", _LATER) == _LATER

    def test_it_survives_a_corrupt_or_missing_memo(self, tmp_path: Path) -> None:
        """Degrading to "a new event" is acceptable; refusing to record is not.

        This is a retry aid, not the durable record — the directory's ledger is
        that. A caller who cannot write a cache file should still be able to
        report an interaction.
        """
        (tmp_path / "event_times.json").write_text("{ not json")
        assert _stable_event_time(tmp_path, "evt_abc", _NOW) == _NOW

    def test_the_memo_is_bounded(self, tmp_path: Path) -> None:
        """It is a cache, not an audit log; unbounded growth buys nothing once a
        send has succeeded."""
        import json

        for i in range(600):
            _stable_event_time(tmp_path, f"evt_{i:04d}", _NOW)
        assert len(json.loads((tmp_path / "event_times.json").read_text())) <= 500


def _http_error(status: int, body: Any) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "https://example.invalid/api/v2/events")
    response = httpx.Response(status, json=body, request=request)
    return httpx.HTTPStatusError("boom", request=request, response=response)


class TestConsentAwareError:
    def test_a_consent_refusal_says_so_and_says_retrying_will_not_help(self) -> None:
        """A 403 here is a fact about the counterparty, not a bug in the request.
        Reported generically, an agent burns retries on something that can never
        succeed."""
        exc = _http_error(
            403,
            {"detail": {"code": "consent_missing", "subject": "did:ex:b", "channel": "valence"}},
        )
        out = _consent_aware_error(exc, counterparty_did="did:ex:b")
        assert out["code"] == "counterparty_has_not_consented"
        assert "will not help" in out["remedy"]
        # Echoed, not paraphrased: a multi-party event can fail on a party the
        # caller was not thinking about, so the server's own naming must survive.
        assert out["server_detail"]["subject"] == "did:ex:b"
        assert out["server_detail"]["channel"] == "valence"

    def test_an_access_gate_403_is_not_reported_as_a_consent_refusal(self) -> None:
        """The regression that matters most here.

        The service's access gate also answers 403, with a bare
        `{"detail": "Forbidden"}`. Branching on the status alone would tell the
        agent that a named third party had refused consent — a confident,
        specific, false statement about someone else. A generic error is worse
        than a good one and far better than a wrong one.
        """
        out = _consent_aware_error(
            _http_error(403, {"detail": "Forbidden"}), counterparty_did="did:ex:b"
        )
        assert out.get("code") != "counterparty_has_not_consented", (
            "an access-gate refusal was reported as the counterparty withholding "
            "consent — a false claim about a third party"
        )

    @pytest.mark.parametrize("status", [400, 401, 422, 500])
    def test_other_failures_fall_through_to_the_generic_handler(self, status: int) -> None:
        out = _consent_aware_error(
            _http_error(status, {"detail": "nope"}), counterparty_did="did:ex:b"
        )
        assert out.get("code") != "counterparty_has_not_consented"
