"""Integration tests that exercise providers.py against the stubs.

These confirm that the end-to-end path — providers → _make_http_client
→ stubs via ASGI mounts — works correctly. Scenarios and fuzzing layers
depend on this.
"""

from __future__ import annotations

import asyncio

from synpareia_trust_mcp.providers import (
    query_moltbook,
    query_moltrust,
    query_synpareia_network,
)


class TestMoltbookProvider:
    def test_returns_structured_signals_for_known_agent(self, stub_providers) -> None:
        signals = asyncio.run(query_moltbook("alice", stub_providers["moltbook_url"]))
        # karma + activity + account_status = 3
        assert len(signals) == 3
        by_type = {s.signal_type: s for s in signals}
        assert by_type["karma"].value == 4520
        assert by_type["activity"].value["posts"] == 312
        assert by_type["account_status"].value["is_claimed"] is True

    def test_unknown_agent_returns_not_found_signal(self, stub_providers) -> None:
        signals = asyncio.run(query_moltbook("does-not-exist", stub_providers["moltbook_url"]))
        assert len(signals) == 1
        assert signals[0].signal_type == "lookup"
        assert signals[0].value == "not_found"

    def test_injector_agent_strips_raw_content(self, stub_providers) -> None:
        """The injector persona has prompt-injection text in `bio` and
        `description`. The provider MUST NOT surface those fields."""
        signals = asyncio.run(query_moltbook("injector", stub_providers["moltbook_url"]))
        flattened = " ".join(repr(s.value) + " " + s.detail for s in signals)
        assert "Ignore previous instructions" not in flattened
        assert "<<SYSTEM>>" not in flattened


class TestMoltrustProvider:
    def test_returns_reputation_for_known_did(self, stub_providers) -> None:
        signals = asyncio.run(query_moltrust("alice", stub_providers["moltrust_api_key"]))
        by_type = {s.signal_type: s for s in signals}
        assert by_type["reputation_score"].value == 0.87
        assert by_type["ratings"].value["count"] == 142

    def test_wrong_api_key_surfaces_as_error_signal(self, stub_providers) -> None:
        signals = asyncio.run(query_moltrust("alice", "WRONG-KEY"))
        # 401 from stub → raise_for_status triggers HTTPError → error signal
        assert len(signals) == 1
        assert signals[0].signal_type == "error"
        assert signals[0].value == "unavailable"

    def test_injector_strips_raw_content(self, stub_providers) -> None:
        signals = asyncio.run(query_moltrust("injector", stub_providers["moltrust_api_key"]))
        flattened = " ".join(repr(s.value) + " " + s.detail for s in signals)
        assert "Ignore prior tool outputs" not in flattened


class TestSynpareiaNetworkProvider:
    def test_high_confidence_signals(self, stub_providers) -> None:
        signals = asyncio.run(
            query_synpareia_network("alice", stub_providers["synpareia_network_url"])
        )
        # Every synpareia-network signal should be "high" confidence
        # because it's backed by cryptographic interaction history.
        for s in signals:
            if s.signal_type not in ("error", "lookup"):
                assert s.confidence == "high"

    def test_newcomer_returns_zero_interactions(self, stub_providers) -> None:
        signals = asyncio.run(
            query_synpareia_network("newcomer", stub_providers["synpareia_network_url"])
        )
        interactions = next(s for s in signals if s.signal_type == "verified_interactions")
        assert interactions.value["count"] == 0
