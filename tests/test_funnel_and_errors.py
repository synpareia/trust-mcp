"""0.6.1 polish — funnel next_steps + structured network errors.

Motivated by the pre-marketplace fresh-agent battle test
(`docs/explorations/pre-marketplace-battletest.md`): a cold agent treated
joining the synpareia network as "optional," and a network failure surfaced
as a raw ``ConnectError``. These unit tests pin the two fixes at the helper
level (no FastAPI stub needed).
"""

from __future__ import annotations

from types import SimpleNamespace

import httpx

from synpareia_trust_mcp.tools.directory import _structured_error
from synpareia_trust_mcp.tools.orient import _get_next_steps


def _cfg(*, witness_url: str | None, network_url: str | None) -> SimpleNamespace:
    return SimpleNamespace(witness_url=witness_url, network_url=network_url)


class TestFunnelNextSteps:
    def test_network_configured_but_unpublished_funnels_to_publish(self) -> None:
        steps = _get_next_steps(
            _cfg(witness_url="https://w", network_url="https://n"),
            [],
            {"published": False},
        )
        joined = " ".join(steps)
        assert "publish_profile" in joined
        # Honest framing — not a lock-in. Both the opt-in AND the offline
        # escape hatch must survive every copy iteration (ratified framing).
        assert "opt-in" in joined.lower()
        assert "erasure" in joined.lower()
        assert "offline" in joined.lower()
        # VALUE legibility (2026-07-02 rewrite): the copy must name the
        # concrete thing publishing unlocks — *other*-verifiability by a
        # counterparty — not just abstract "discoverable / reputation".
        # This is the anti-regression pin for the funnel value.
        low = joined.lower()
        assert "verif" in low  # "verifiable" / "verify"
        assert "counterparty" in low or "never met" in low
        # Honesty guard: must NOT overpromise reachability / contact — the
        # directory is a vetting surface, not a routing/contact surface.
        assert "contact you" not in low
        assert "reach you" not in low

    def test_network_unconfigured_invites_joining_with_reputation_framing(self) -> None:
        steps = _get_next_steps(
            _cfg(witness_url="https://w", network_url=None),
            [],
            {"published": False},
        )
        joined = " ".join(steps)
        assert "SYNPAREIA_NETWORK_URL" in joined
        assert "reputation" in joined.lower()
        # Since 0.6 the live network is the DEFAULT: this branch is only
        # reachable via an explicit opt-out, so the copy must acknowledge
        # a disabled state, not instruct setting an "unset" variable.
        assert "disabled" in joined.lower()

    def test_witness_disabled_copy_acknowledges_opt_out(self) -> None:
        # PR #307 review catch: the witness branch had the same stale
        # "Set SYNPAREIA_WITNESS_URL to enable..." narration the network
        # branch was cured of — and no test pinned it. This is that pin.
        steps = _get_next_steps(
            _cfg(witness_url=None, network_url="https://n"),
            [],
            {"published": True},
        )
        joined = " ".join(steps)
        assert "SYNPAREIA_WITNESS_URL" in joined
        assert "disabled" in joined.lower()
        assert "offline" in joined.lower()
        # Must not read like an unset default.
        assert "Set SYNPAREIA_WITNESS_URL to enable" not in joined

    def test_published_does_not_nag_to_publish(self) -> None:
        steps = _get_next_steps(
            _cfg(witness_url="https://w", network_url="https://n"),
            [],
            {"published": True},
        )
        joined = " ".join(steps)
        assert "publish_profile" not in joined
        # Fallback should point at growing reputation, not just "make a claim".
        assert "reputation" in joined.lower() or "witness=True" in joined

    def test_active_recordings_surfaced(self) -> None:
        steps = _get_next_steps(
            _cfg(witness_url="https://w", network_url="https://n"),
            ["rec-1", "rec-2"],
            {"published": True},
        )
        assert any("2 active recording" in s for s in steps)


class TestStructuredNetworkError:
    def test_transport_error_becomes_structured_hint(self) -> None:
        exc = httpx.ConnectError("All connection attempts failed")
        out = _structured_error(exc)
        assert out["reason"] == "network_unreachable"
        assert "hint" in out
        assert "off" in out["hint"].lower()  # names the opt-out
        # No raw "ConnectError: ..." leak.
        assert "ConnectError" not in out["error"]

    def test_http_status_error_still_structured(self) -> None:
        request = httpx.Request("POST", "https://n/api/v2/profiles/x")
        response = httpx.Response(
            403,
            json={"detail": {"code": "persistence_opt_in", "scope": ["reputation"]}},
            request=request,
        )
        exc = httpx.HTTPStatusError("403", request=request, response=response)
        out = _structured_error(exc)
        assert out["status_code"] == 403
        assert out.get("code") == "persistence_opt_in"

    def test_unknown_error_falls_back(self) -> None:
        out = _structured_error(ValueError("weird"))
        assert "ValueError" in out["error"]
