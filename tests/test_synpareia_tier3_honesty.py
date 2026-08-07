"""The tier-3 lookup must not state a fact it did not learn.

WHY THIS FILE EXISTS SEPARATELY FROM `tests/stubs/test_providers_with_stubs.py`
------------------------------------------------------------------------------
That suite has always passed, and could never have caught this. Its stub
(`tests/stubs/synpareia_network.py`) *implements* `GET /api/v1/agents/{id}/reputation`
— the route `query_synpareia_network` requests. But no synpareia directory serves that
route, under any configuration:

  * `/api/v1/agents/{id}/reputation` is defined by no router. `agents.py` has
    `/register`, `/me`, `/me/api-key/rotate`, `/{agent_id}` — and no reputation path.
  * The nearest real route, `/api/v1/verify/{profile_id}`, sits behind
    `ENABLE_LEGACY_SURFACES`, which is off on the public service.
  * The v2 surface has no reputation read at all.

Verified live against https://synpareia.fly.dev: both v1 paths 404 while
`/api/v2/profiles/{did}` returns 200.

So the stub encoded the same wrong assumption as the code it was testing — the oracle
derived from the subject. A green suite meant "the parser handles the shape we
imagined", never "the request is one something answers".

These tests use a stub that behaves like the REAL service — 404 on the reputation path —
and assert the property that actually matters to a calling agent: *can it tell "we looked
and found nothing" apart from "nothing was looked at"?*
"""

from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from synpareia_trust_mcp.providers import query_synpareia_network


class _NoReputationRoute(BaseHTTPRequestHandler):
    """A directory that serves profiles but no reputation read — i.e. the real one."""

    protocol_version = "HTTP/1.1"
    body: bytes | None = None  # None => 404, as the live service does

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        payload = type(self).body
        if payload is None:
            self.send_response(404)
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args: object) -> None:
        """Silence the stub's access log."""


@pytest.fixture
def directory():
    server = HTTPServer(("127.0.0.1", 0), _NoReputationRoute)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()


@pytest.fixture
def url(directory):
    return f"http://127.0.0.1:{directory.server_port}"


def test_absent_route_is_reported_as_unavailable_not_as_not_found(url):
    """The defect: a 404 became a high-confidence claim about the counterparty."""
    _NoReputationRoute.body = None  # route absent, like production
    signals = asyncio.run(query_synpareia_network("did:synpareia:anyone", url))

    assert len(signals) == 1
    signal = signals[0]
    assert signal.value == "unavailable", (
        "a 404 means no reputation route is deployed; reporting it as 'not_found' asserts "
        "the counterparty has no record, which is a fact this call never established"
    )
    assert signal.confidence == "low"


def test_the_detail_does_not_read_as_a_finding_about_the_counterparty(url):
    """A calling agent reads `detail`. It must not sound like a considered verdict."""
    _NoReputationRoute.body = None
    detail = asyncio.run(query_synpareia_network("did:synpareia:anyone", url))[0].detail

    assert "NOT a statement" in detail
    assert "no information either way" in detail.lower()
    #: The old text was "No synpareia network record for '<id>'." — a positive claim.
    #: Anything of that shape is the regression.
    assert "no synpareia network record for" not in detail.lower()


def test_an_affirmative_absence_is_still_not_found_at_high_confidence(url):
    """`not_found` must remain REACHABLE — on evidence, when the service answers.

    Without this, the fix would be indistinguishable from deleting the capability: an
    always-unavailable provider is exactly as uninformative as an always-not_found one.
    This is the branch that makes the tier meaningful once the read route lands.
    """
    _NoReputationRoute.body = json.dumps({"exists": False}).encode()
    signals = asyncio.run(query_synpareia_network("did:synpareia:ghost", url))

    assert len(signals) == 1
    assert signals[0].value == "not_found"
    assert signals[0].confidence == "high"


def test_a_real_record_still_parses(url):
    """Positive control: the honest paths must not have eaten the working one."""
    _NoReputationRoute.body = json.dumps(
        {"interaction_count": 12, "average_quality": 0.8, "reputation_score": 0.7}
    ).encode()
    signals = asyncio.run(query_synpareia_network("did:synpareia:real", url))

    kinds = {s.signal_type for s in signals}
    assert "verified_interactions" in kinds
    assert "reputation_score" in kinds
    interactions = next(s for s in signals if s.signal_type == "verified_interactions")
    assert interactions.value["count"] == 12
