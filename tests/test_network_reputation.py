"""`network_reputation` — the read half of the topology loop.

The failure this file is shaped around is the one `record_interaction` shipped
with in the 0.9.0 candidate: a tool that is registered, documented, imported and
green, and makes no network call at all (see `test_directory_guard_contract.py`).
Registration is not evidence. So every test here drives the tool function itself
and asserts on what reached the client — the request had to be *made*, and made
with the right two DIDs the right way round.

The anchoring is the part worth guarding. This read is computed outward from the
asker, so passing the subject where the asker belongs — or the reverse — still
returns well-formed numbers about the wrong vantage point. That is silent, and
`test_the_call_is_anchored_on_us_and_asks_about_them` is the only thing here that
would notice.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import Any

import httpx
import pytest  # noqa: TC002 — a runtime fixture type (MonkeyPatch), not an annotation-only import

from synpareia_trust_mcp.tools import directory

_ME = "did:synpareia:" + "a" * 64
_THEM = "did:synpareia:" + "b" * 64


class _FakeClient:
    """Stands in for `ProfileClient`, recording the call rather than making it."""

    def __init__(self, result: dict[str, Any] | None = None, raises: BaseException | None = None):
        self.result = result if result is not None else {}
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def get_reputation(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


def _ctx(*, private_key: bytes | None = b"k" * 32, did: str = _ME) -> SimpleNamespace:
    profile = SimpleNamespace(id=did, private_key=private_key)
    app = SimpleNamespace(
        config=SimpleNamespace(network_url="https://d.example"),
        profile_manager=SimpleNamespace(profile=profile),
    )
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


def _call(ctx: SimpleNamespace, subject: str = _THEM) -> dict[str, Any]:
    """Invoke the tool **as the server dispatches it**.

    Resolved out of the live tool registry rather than imported from the module,
    so these tests exercise the callable an MCP client would actually reach. A
    tool that stopped being registered — or got registered under a different
    name — fails here with a KeyError instead of passing against an import.
    """
    from synpareia_trust_mcp.server import mcp

    tool = mcp._tool_manager._tools["network_reputation"]  # noqa: SLF001
    out: dict[str, Any] = asyncio.run(tool.fn(subject, ctx))
    return out


def _with_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(directory, "_build_profile_client", lambda _app: client)


class TestTheCallIsActuallyMade:
    def test_the_call_is_anchored_on_us_and_asks_about_them(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """THE control. Swapping the two DIDs returns a plausible answer to the
        wrong question — someone else's view of us — and nothing else here sees it.
        """
        client = _FakeClient({"subject": _THEM, "magnitude": 0.4, "confidence": 2.0})
        _with_client(monkeypatch, client)

        _call(_ctx())

        assert len(client.calls) == 1, "the tool made no request — it is inert"
        call = client.calls[0]
        assert call["subject_did"] == _THEM, "asked about the wrong agent"
        assert call["asker_did"] == _ME, (
            "the read was anchored on someone other than us — the numbers would "
            "describe a vantage point that is not ours"
        )
        assert call["private_key"] == b"k" * 32

    def test_the_served_numbers_are_passed_through_unaltered(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The tool adds a reading; it must not reshape, round or re-scale."""
        _with_client(
            monkeypatch, _FakeClient({"subject": _THEM, "magnitude": -0.25, "confidence": 3.5})
        )
        out = _call(_ctx())
        assert out["magnitude"] == -0.25
        assert out["confidence"] == 3.5
        assert out["subject"] == _THEM


class TestTheReadingWarnsWhereItMatters:
    def test_zero_confidence_says_to_ignore_the_magnitude(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """`{magnitude: 0.0, confidence: 0.0}` reads as "average" to anyone who
        skims. It means "no report at all", and the difference decides whether an
        agent treats a stranger as mediocre or as unknown."""
        _with_client(
            monkeypatch, _FakeClient({"subject": _THEM, "magnitude": 0.0, "confidence": 0.0})
        )
        reading = _call(_ctx())["reading"].lower()
        assert "ignore" in reading
        assert "not a bad report" in reading

    def test_a_backed_answer_does_not_carry_the_ignore_warning(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Positive control: a warning that fires on every response is not a warning."""
        _with_client(
            monkeypatch, _FakeClient({"subject": _THEM, "magnitude": 0.6, "confidence": 4.0})
        )
        reading = _call(_ctx())["reading"].lower()
        assert "ignore" not in reading
        assert "advisory" in reading


class TestRefusals:
    def test_asking_about_yourself_is_refused_without_a_request(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        client = _FakeClient({"subject": _ME, "magnitude": 0.0, "confidence": 0.0})
        _with_client(monkeypatch, client)

        out = _call(_ctx(), subject=_ME)

        assert out["code"] == "self_reputation"
        assert client.calls == [], "refused, but the request went out anyway"

    def test_an_unconfigured_directory_refuses_without_leaking_the_url(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The `_need_directory`/`_directory_error` confusion, at this tool."""
        client = _FakeClient()
        _with_client(monkeypatch, client)
        ctx = _ctx()
        ctx.request_context.lifespan_context.config.network_url = None

        out = _call(ctx)

        assert "SYNPAREIA_NETWORK_URL" in out["error"]
        assert client.calls == []

    def test_an_identity_with_no_private_key_cannot_ask(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The read is signed, so a key-less identity has no vantage point to
        anchor on. Refusing beats sending an unsigned request that 401s."""
        client = _FakeClient()
        _with_client(monkeypatch, client)

        out = _call(_ctx(private_key=None))

        assert "private key" in out["error"]
        assert client.calls == []

    def test_a_directory_error_comes_back_structured(self, monkeypatch: pytest.MonkeyPatch) -> None:
        request = httpx.Request("GET", "https://d.example/api/v2/reputation/x")
        response = httpx.Response(
            400, json={"detail": {"code": "self_reputation"}}, request=request
        )
        _with_client(
            monkeypatch,
            _FakeClient(raises=httpx.HTTPStatusError("boom", request=request, response=response)),
        )

        out = _call(_ctx())

        assert out["status_code"] == 400
        assert "error" in out
