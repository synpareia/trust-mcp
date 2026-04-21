"""Smoke tests for the external-service stubs themselves.

These confirm the stubs parse paths, return canned data, handle 404s,
and route correctly through httpx.ASGITransport. Scenario tests then
trust this layer.
"""

from __future__ import annotations

import asyncio

import httpx

from tests.stubs.fixtures import (
    MOLTBOOK_TEST_URL,
    SYNPAREIA_NETWORK_TEST_URL,
)
from tests.stubs.moltbook import DEFAULT_FIXTURES as MOLTBOOK_FIXTURES
from tests.stubs.moltbook import make_moltbook_app
from tests.stubs.moltrust import VALID_API_KEY, make_moltrust_app
from tests.stubs.synpareia_network import make_synpareia_network_app


def _run(coro):
    return asyncio.run(coro)


class TestMoltbookStub:
    def test_known_identifier_returns_fixture(self) -> None:
        app = make_moltbook_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=MOLTBOOK_TEST_URL,
            ) as client:
                return await client.get("/api/v1/agents/alice")

        resp = _run(go())
        assert resp.status_code == 200
        data = resp.json()
        assert data["username"] == "alice"
        assert data["karma"] == MOLTBOOK_FIXTURES["alice"]["karma"]
        assert data["is_claimed"] is True

    def test_unknown_identifier_returns_404(self) -> None:
        app = make_moltbook_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=MOLTBOOK_TEST_URL,
            ) as client:
                return await client.get("/api/v1/agents/nonexistent")

        resp = _run(go())
        assert resp.status_code == 404

    def test_fail_mode_500(self) -> None:
        app = make_moltbook_app(fail_mode="500")

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=MOLTBOOK_TEST_URL,
            ) as client:
                return await client.get("/api/v1/agents/alice")

        resp = _run(go())
        assert resp.status_code == 500


class TestMoltrustStub:
    def test_requires_auth_by_default(self) -> None:
        app = make_moltrust_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://api.moltrust.ch",
            ) as client:
                return await client.get("/v1/agents/alice/reputation")

        resp = _run(go())
        assert resp.status_code == 401

    def test_valid_key_returns_fixture(self) -> None:
        app = make_moltrust_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://api.moltrust.ch",
            ) as client:
                return await client.get(
                    "/v1/agents/alice/reputation",
                    headers={"Authorization": f"Bearer {VALID_API_KEY}"},
                )

        resp = _run(go())
        assert resp.status_code == 200
        data = resp.json()
        assert data["reputation_score"] == 0.87

    def test_unknown_did_returns_404(self) -> None:
        app = make_moltrust_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="https://api.moltrust.ch",
            ) as client:
                return await client.get(
                    "/v1/agents/unknown/reputation",
                    headers={"Authorization": f"Bearer {VALID_API_KEY}"},
                )

        resp = _run(go())
        assert resp.status_code == 404


class TestSynpareiaNetworkStub:
    def test_known_did_returns_interaction_history(self) -> None:
        app = make_synpareia_network_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=SYNPAREIA_NETWORK_TEST_URL,
            ) as client:
                return await client.get("/api/v1/agents/alice/reputation")

        resp = _run(go())
        assert resp.status_code == 200
        data = resp.json()
        assert data["interaction_count"] == 54
        assert data["reputation_score"] == 0.82

    def test_newcomer_has_null_signals(self) -> None:
        app = make_synpareia_network_app()

        async def go() -> httpx.Response:
            async with httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url=SYNPAREIA_NETWORK_TEST_URL,
            ) as client:
                return await client.get("/api/v1/agents/newcomer/reputation")

        resp = _run(go())
        assert resp.status_code == 200
        assert resp.json()["interaction_count"] == 0


class TestMultiProviderRoutingViaMounts:
    """Confirms the mounts pattern used by stub_providers works."""

    def test_mounts_route_by_host(self) -> None:
        moltbook = make_moltbook_app()
        moltrust = make_moltrust_app()
        network = make_synpareia_network_app()

        mounts = {
            MOLTBOOK_TEST_URL: httpx.ASGITransport(app=moltbook),
            SYNPAREIA_NETWORK_TEST_URL: httpx.ASGITransport(app=network),
            "https://api.moltrust.ch": httpx.ASGITransport(app=moltrust),
        }

        async def go() -> tuple[int, int, int]:
            async with httpx.AsyncClient(mounts=mounts) as client:
                r1 = await client.get(f"{MOLTBOOK_TEST_URL}/api/v1/agents/bob")
                r2 = await client.get(
                    "https://api.moltrust.ch/v1/agents/bob/reputation",
                    headers={"Authorization": f"Bearer {VALID_API_KEY}"},
                )
                r3 = await client.get(f"{SYNPAREIA_NETWORK_TEST_URL}/api/v1/agents/bob/reputation")
            return r1.status_code, r2.status_code, r3.status_code

        statuses = _run(go())
        assert statuses == (200, 200, 200)
