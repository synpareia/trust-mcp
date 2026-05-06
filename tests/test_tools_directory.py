"""Phase 1g — directory tools tests.

Drives ``publish_profile`` / ``get_profile`` / ``update_profile_policy``
/ ``enable_persistence`` / ``disable_persistence`` /
``delete_profile_history`` / ``delete_profile`` against a tiny
FastAPI stub mirroring the Phase 1d/1e wire shape. Avoids the
SDK / main-service ``synpareia`` package shadow by not requiring
the live main service.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import os
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any
from unittest.mock import patch

from fastapi import FastAPI, Request

# Importing tools registers them on ``mcp`` (side-effect).
import synpareia_trust_mcp.tools  # noqa: F401, E402
from synpareia_trust_mcp.app import AppContext, app_lifespan, mcp

# ---------------------------------------------------------------------------
# Stub directory
# ---------------------------------------------------------------------------


def _make_stub() -> tuple[FastAPI, dict[str, Any]]:
    app = FastAPI()
    state: dict[str, Any] = {"captured": [], "profiles": {}}

    @app.post("/api/v2/profiles/{did:path}")
    async def publish(did: str, request: Request) -> dict[str, Any]:
        body = json.loads((await request.body()).decode())
        card_bytes = base64.b64decode(body["card_b64"])
        card_dict = json.loads(card_bytes.decode())
        state["captured"].append({"method": "POST", "card": card_dict})

        existing = state["profiles"].get(did)
        new_version = (existing["version"] + 1) if existing else 1
        state["profiles"][did] = {
            "card_dict": card_dict,
            "version": new_version,
            "history": (existing["history"] if existing else [])
            + [{"version": new_version, "tombstoned_at": None}],
        }
        return {
            "did": did,
            "version": new_version,
            "card_hash_hex": hashlib.sha256(card_bytes).hexdigest(),
        }

    @app.get("/api/v2/profiles/{did:path}")
    async def get_existence(did: str) -> dict[str, Any]:
        prof = state["profiles"].get(did)
        if prof is None:
            return {
                "did": did,
                "exists": False,
                "name": None,
                "description": None,
                "public_key_b64": None,
                "version": None,
            }
        c = prof["card_dict"]
        return {
            "did": did,
            "exists": True,
            "name": c.get("name"),
            "description": c.get("description"),
            "public_key_b64": c.get("public_key_b64"),
            "version": c.get("version"),
        }

    @app.delete("/api/v2/profiles/{did:path}/history/{version}", status_code=204)
    async def delete_version(did: str, version: int) -> None:
        prof = state["profiles"].get(did)
        if prof is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        # If the currently-published card has card_history opt-in,
        # 403 to mirror the directory's persistence-opt-in gate.
        scope = (
            prof["card_dict"]
            .get("extensions", {})
            .get("synpareia", {})
            .get("persistence", {})
            .get("scope", [])
        )
        if "card_history" in scope:
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail={
                    "detail": "persistence opt-in",
                    "code": "persistence_opt_in",
                    "scope": "card_history",
                },
            )
        for row in prof["history"]:
            if row["version"] == version:
                row["tombstoned_at"] = "2026-01-01T00:00:00+00:00"
                return
        from fastapi import HTTPException

        raise HTTPException(status_code=404)

    @app.delete("/api/v2/profiles/{did:path}", status_code=204)
    async def delete_profile(did: str) -> None:
        prof = state["profiles"].get(did)
        if prof is None:
            from fastapi import HTTPException

            raise HTTPException(status_code=404)
        scope = (
            prof["card_dict"]
            .get("extensions", {})
            .get("synpareia", {})
            .get("persistence", {})
            .get("scope", [])
        )
        if {"card_history", "key_chain"} & set(scope):
            from fastapi import HTTPException

            raise HTTPException(
                status_code=403,
                detail={"code": "persistence_opt_in", "scope": list(scope)},
            )
        for row in prof["history"]:
            row["tombstoned_at"] = "2026-01-01T00:00:00+00:00"

    return app, state


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@asynccontextmanager
async def _trust_mcp_with_stub(tmp_path: Path):
    """Spin up the Trust MCP lifespan + redirect ProfileClient at the stub.

    Patches ``httpx.AsyncClient`` so any client built inside the
    lifespan or the directory tools routes through the stub via
    ASGITransport.
    """
    from httpx import ASGITransport, AsyncClient

    stub_app, state = _make_stub()
    real_async_client = AsyncClient

    def make_client(*args: Any, **kwargs: Any) -> AsyncClient:
        kwargs.pop("base_url", None)
        kwargs.pop("headers", None)
        kwargs.pop("timeout", None)
        return real_async_client(transport=ASGITransport(app=stub_app), base_url="http://stub")

    env = {
        "SYNPAREIA_DATA_DIR": str(tmp_path),
        "SYNPAREIA_NETWORK_URL": "http://stub",
        "SYNPAREIA_AUTO_REGISTER": "false",
    }
    with (
        patch.dict(os.environ, env, clear=False),
        patch("synpareia.profile.client.httpx.AsyncClient", make_client),
    ):
        async with app_lifespan(mcp) as ctx:
            yield ctx, state


# ---------------------------------------------------------------------------
# Helpers to invoke tools (FastMCP exposes _tool_manager._tools)
# ---------------------------------------------------------------------------


def _get_tool(tool_name: str):  # type: ignore[no-untyped-def]
    return mcp._tool_manager._tools[tool_name]


async def _call_tool(tool_name: str, ctx_obj: AppContext, **kwargs: Any) -> Any:
    """Invoke a registered tool with a faked Context carrying ``ctx_obj``.

    FastMCP tools take a ``Context`` whose
    ``request_context.lifespan_context`` is the AppContext. We
    construct a minimal stand-in.
    """
    from types import SimpleNamespace

    fake_request_context = SimpleNamespace(lifespan_context=ctx_obj)
    fake_ctx = SimpleNamespace(request_context=fake_request_context)
    tool = _get_tool(tool_name)
    fn = tool.fn
    return await fn(ctx=fake_ctx, **kwargs)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_publish_profile_writes_cache_and_returns_directory_response(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            result = await _call_tool("publish_profile", ctx, name="Alice")
            assert result["version"] == 1
            assert result["did"] == ctx.profile_manager.profile.id
            cache = json.loads((tmp_path / "published_card.json").read_text())
            assert cache["a2a"]["name"] == "Alice"

    asyncio.run(run())


def test_get_profile_returns_existence_view(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool("publish_profile", ctx, name="Bob")
            view = await _call_tool("get_profile", ctx, did=ctx.profile_manager.profile.id)
            assert view["exists"] is True
            assert view["name"] == "Bob"

            other_did = "did:synpareia:" + "0" * 64
            unknown = await _call_tool("get_profile", ctx, did=other_did)
            assert unknown["exists"] is False

    asyncio.run(run())


def test_update_profile_policy_preserves_unspecified_fields(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool(
                "publish_profile",
                ctx,
                name="Carol",
                description="Initial",
                first_contact_fee_credits=5,
            )
            result = await _call_tool("update_profile_policy", ctx, description="Updated")
            assert result["version"] == 2
            view = await _call_tool("get_profile", ctx, did=ctx.profile_manager.profile.id)
            assert view["name"] == "Carol"  # preserved
            assert view["description"] == "Updated"

    asyncio.run(run())


def test_enable_then_disable_persistence(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool("publish_profile", ctx, name="Dave")

            opted = await _call_tool("enable_persistence", ctx, scope=["card_history"])
            assert opted["version"] == 2
            cache = json.loads((tmp_path / "published_card.json").read_text())
            assert cache["synpareia"]["persistence_scope"] == ["card_history"]
            assert cache["synpareia"]["persistence_opted_in_at"] is not None

            withdrawn = await _call_tool("disable_persistence", ctx)
            assert withdrawn["version"] == 3
            cache = json.loads((tmp_path / "published_card.json").read_text())
            assert cache["synpareia"]["persistence_scope"] is None

    asyncio.run(run())


def test_delete_history_blocked_by_card_history_opt_in(tmp_path: Path) -> None:
    """Persistence-opt-in 403 surfaces with structured code/scope."""

    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool("publish_profile", ctx, name="Erin")
            await _call_tool("enable_persistence", ctx, scope=["card_history"])

            result = await _call_tool("delete_profile_history", ctx, version=2)
            assert result["status_code"] == 403
            assert result["code"] == "persistence_opt_in"
            assert result["scope"] == "card_history"

    asyncio.run(run())


def test_delete_profile_blocked_by_key_chain_opt_in(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool("publish_profile", ctx, name="Frank")
            await _call_tool("enable_persistence", ctx, scope=["key_chain"])

            result = await _call_tool("delete_profile", ctx)
            assert result["status_code"] == 403
            assert result["code"] == "persistence_opt_in"
            assert "key_chain" in result["scope"]

    asyncio.run(run())


def test_delete_profile_succeeds_with_no_opt_in(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            await _call_tool("publish_profile", ctx, name="Grace")
            result = await _call_tool("delete_profile", ctx)
            assert result["ok"] is True

    asyncio.run(run())


def test_publish_requires_directory_url(tmp_path: Path) -> None:
    """When SYNPAREIA_NETWORK_URL is unset, publish_profile errors cleanly."""

    async def run() -> None:
        env = {
            "SYNPAREIA_DATA_DIR": str(tmp_path),
            "SYNPAREIA_AUTO_REGISTER": "false",
        }
        # Important: clear so any inherited NETWORK_URL doesn't leak.
        with patch.dict(os.environ, env, clear=True):
            async with app_lifespan(mcp) as ctx:
                result = await _call_tool("publish_profile", ctx, name="Noop")
                assert "error" in result
                assert "SYNPAREIA_NETWORK_URL" in result["error"]

    asyncio.run(run())


def test_orient_surfaces_directory_state(tmp_path: Path) -> None:
    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            from types import SimpleNamespace

            fake_ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=ctx))

            # Before publish.
            tool = mcp._tool_manager._tools["orient"]
            result = tool.fn(ctx=fake_ctx)
            assert result["identity"]["directory"]["published"] is False

            # After publish.
            await _call_tool("publish_profile", ctx, name="Hank")
            result = tool.fn(ctx=fake_ctx)
            assert result["identity"]["directory"]["published"] is True
            assert result["identity"]["directory"]["name"] == "Hank"

    asyncio.run(run())


def test_orient_reports_tombstoned_after_full_delete(tmp_path: Path) -> None:
    """After ``delete_profile`` succeeds, the cache stays for inspection
    but is marked tombstoned, and ``orient`` reports ``published: False``
    with the tombstone metadata.
    """

    async def run() -> None:
        async with _trust_mcp_with_stub(tmp_path) as (ctx, state):
            from types import SimpleNamespace

            fake_ctx = SimpleNamespace(request_context=SimpleNamespace(lifespan_context=ctx))

            await _call_tool("publish_profile", ctx, name="Iris")
            result = await _call_tool("delete_profile", ctx, reason="end of trial")
            assert result["ok"] is True

            tool = mcp._tool_manager._tools["orient"]
            after = tool.fn(ctx=fake_ctx)
            directory = after["identity"]["directory"]
            assert directory["published"] is False
            assert directory["tombstoned_at"] is not None
            assert directory["tombstoned_reason"] == "end of trial"
            # Cache file must remain on disk for inspection.
            assert (tmp_path / "published_card.json").exists()

    asyncio.run(run())


def test_access_token_forwarded_to_directory(tmp_path: Path) -> None:
    """When ``SYNPAREIA_WITNESS_TOKEN`` is set, the directory client
    forwards it as ``X-Access-Token`` (the deployed directory and the
    witness currently share one token).
    """

    async def run() -> None:

        from fastapi import FastAPI
        from httpx import ASGITransport, AsyncClient

        captured: list[dict[str, Any]] = []
        app = FastAPI()

        @app.post("/api/v2/profiles/{did:path}")
        async def publish(did: str, request: Request) -> dict[str, Any]:
            captured.append({"headers": dict(request.headers)})
            body = json.loads((await request.body()).decode())
            card_bytes = base64.b64decode(body["card_b64"])
            return {
                "did": did,
                "version": 1,
                "card_hash_hex": hashlib.sha256(card_bytes).hexdigest(),
            }

        real_async_client = AsyncClient

        def make_client(*args: Any, **kwargs: Any) -> AsyncClient:
            # Drop base_url/timeout but **keep** headers — the
            # access-token forwarding test relies on the header
            # set by ``ProfileClient.__init__`` reaching the stub.
            kwargs.pop("base_url", None)
            kwargs.pop("timeout", None)
            return real_async_client(
                transport=ASGITransport(app=app),
                base_url="http://stub",
                headers=kwargs.get("headers"),
            )

        env = {
            "SYNPAREIA_DATA_DIR": str(tmp_path),
            "SYNPAREIA_NETWORK_URL": "http://stub",
            "SYNPAREIA_WITNESS_TOKEN": "secret-stub-token",
            "SYNPAREIA_AUTO_REGISTER": "false",
        }
        with (
            patch.dict(os.environ, env, clear=False),
            patch("synpareia.profile.client.httpx.AsyncClient", make_client),
        ):
            async with app_lifespan(mcp) as ctx:
                result = await _call_tool("publish_profile", ctx, name="Token")
                assert result.get("version") == 1

        assert len(captured) == 1
        # httpx lowercases header keys when iterating; do a
        # case-insensitive lookup.
        token_header = next(
            (v for k, v in captured[0]["headers"].items() if k.lower() == "x-access-token"),
            None,
        )
        assert token_header == "secret-stub-token"

    asyncio.run(run())
