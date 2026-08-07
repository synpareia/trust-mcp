"""`_need_directory` raises; it never returns None. Guards must match that.

`record_interaction` shipped in the 0.9.0 candidate as:

    if (missing := _need_directory(app)) is not None:
        return {"error": missing}

`_need_directory` raises when the directory is unconfigured and returns the URL
otherwise — so it never returns None, the guard was always true, and the tool
returned `{"error": "<the directory URL>"}` to the model and made zero network
calls. The headline tool of the release was inert, and 608 tests passed, because
no test called it. The publish-gate pentest caught it by invoking the tool
through the real MCP dispatch path.

These tests pin the contract that made the misuse possible, and forbid its shape
returning to the source.
"""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from synpareia_trust_mcp.tools import directory

SRC = Path(directory.__file__)


def _app(network_url: str | None) -> SimpleNamespace:
    return SimpleNamespace(config=SimpleNamespace(network_url=network_url))


class TestTheTwoHelpersHaveOppositeContracts:
    def test_need_directory_returns_the_url_and_never_none(self) -> None:
        assert directory._need_directory(_app("https://d.example")) == "https://d.example"

    def test_need_directory_raises_when_unconfigured(self) -> None:
        for empty in (None, ""):
            with pytest.raises(RuntimeError, match="SYNPAREIA_NETWORK_URL"):
                directory._need_directory(_app(empty))

    def test_directory_error_is_none_when_configured(self) -> None:
        """The `is not None` guard shape is only correct against THIS helper."""
        assert directory._directory_error(_app("https://d.example")) is None

    def test_directory_error_returns_a_payload_when_unconfigured(self) -> None:
        err = directory._directory_error(_app(None))
        assert err is not None
        assert "SYNPAREIA_NETWORK_URL" in err["error"]

    def test_the_error_payload_never_leaks_the_url(self) -> None:
        """The bug's symptom: the configured URL arriving in an `error` field."""
        url = "https://internal-directory.example:8443"
        assert directory._directory_error(_app(url)) is None
        assert url not in directory.DIRECTORY_NOT_CONFIGURED


class TestTheMisuseShapeCannotReturn:
    def test_no_guard_tests_need_directory_for_none(self) -> None:
        """`_need_directory(...) is not None` is always true — forbid it outright."""
        source = SRC.read_text()
        offenders = re.findall(r"_need_directory\([^)]*\)\s*(?:is\s+not\s+None|!=\s*None)", source)
        assert offenders == [], (
            f"{SRC.name} tests _need_directory() against None ({offenders}); it raises "
            "rather than returning None, so that guard is always true. Use "
            "_directory_error() when a structured error is wanted."
        )

    def test_every_walrus_error_guard_uses_the_none_returning_helper(self) -> None:
        source = SRC.read_text()
        walrus = re.findall(r"if \((\w+) := (_\w+)\(app\)\) is not None:", source)
        assert walrus, "no walrus error-guard found — has the pattern changed?"
        wrong = [(n, fn) for n, fn in walrus if fn != "_directory_error"]
        assert wrong == [], (
            f"walrus `is not None` guard(s) bound to a helper that never returns None: {wrong}"
        )
