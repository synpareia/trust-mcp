"""The degradation message's version must equal the declared dependency floor.

Eight call sites in `tools/directory.py` used to carry the sentence
"upgrade SDK to 0.5.0+" as a literal, and a ninth said "0.7.0+". The floor in
`pyproject.toml` had moved to 0.7.0, so those eight told an operator running
0.6.x to upgrade to a version they already had. Nothing failed, because nothing
compared the sentence to the floor — the message is only ever emitted on the
path where the SDK import failed, which no green test exercises.

That is a restated constant (CLAUDE.md §3, "prefer derive over restate"). The
message cannot be *derived* at runtime — it exists precisely for the case where
`import synpareia.profile` raised, so it cannot ask the SDK its version, and
reading our own dist metadata is unavailable in an editable/source checkout.
So the floor is declared once in `pyproject.toml`, mirrored once in
`MIN_PROFILE_SDK_VERSION`, and this module asserts the mirror.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
from packaging.requirements import Requirement

from synpareia_trust_mcp.tools import directory

PYPROJECT = Path(__file__).resolve().parent.parent / "pyproject.toml"
DIRECTORY_SRC = Path(directory.__file__)


def _declared_sdk_floor() -> str:
    """The `>=` floor this package declares on the `synpareia` SDK."""
    deps = tomllib.loads(PYPROJECT.read_text())["project"]["dependencies"]
    for raw in deps:
        req = Requirement(raw)
        if req.name != "synpareia":
            continue
        floors = [s.version for s in req.specifier if s.operator == ">="]
        assert len(floors) == 1, f"expected exactly one >= floor, got {floors}"
        return floors[0]
    pytest.fail(f"no `synpareia` requirement found in {PYPROJECT}")


def test_the_constant_equals_the_declared_floor() -> None:
    """If someone bumps the floor and forgets the message, this fails."""
    assert _declared_sdk_floor() == directory.MIN_PROFILE_SDK_VERSION


def test_the_emitted_message_names_that_version() -> None:
    """Guards the mirror being right while the f-string stops using it."""
    floor = _declared_sdk_floor()
    error = directory._profile_sdk_unavailable()["error"]
    assert f"{floor}+" in error, error
    assert "synpareia.profile not available" in error, error


def test_no_call_site_hardcodes_a_version_instead_of_the_constant() -> None:
    """The defect was nine literals, so forbid re-adding a tenth.

    Without this, the fix holds only until the next person writes the sentence
    out by hand in a new guard — which is exactly how it reached nine.
    """
    source = DIRECTORY_SRC.read_text()
    hardcoded = re.findall(r"upgrade SDK to \d+\.\d+\.\d+", source)
    assert hardcoded == [], (
        f"{DIRECTORY_SRC.name} hardcodes a version in a degradation message "
        f"({hardcoded}); call _profile_sdk_unavailable() instead"
    )


def test_every_profile_sdk_guard_returns_the_shared_payload() -> None:
    """Each `if not HAS_PROFILE_SDK:` must be followed by the helper call.

    Counts the guards and the helper's uses at their real call sites, so a new
    guard that invents its own error dict is caught rather than merely
    discouraged by the comment above the constant.
    """
    source = DIRECTORY_SRC.read_text()
    guards = re.findall(
        r"if not HAS_PROFILE_SDK:\s*\n\s*return ([^\n]+)",
        source,
    )
    assert guards, "no HAS_PROFILE_SDK guards found — has the pattern changed?"
    # The regex only sees guards *already* of the form `return <expr>`. Without
    # this, a guard that raises, or has any line between `if` and `return`, simply
    # drops out of `guards` and the assertion below iterates over a shorter list
    # and passes. Three of four realistic regressions escaped that way.
    total = len(re.findall(r"if not HAS_PROFILE_SDK:", source))
    assert len(guards) == total, (
        f"{total - len(guards)} of {total} HAS_PROFILE_SDK guards are not a bare "
        "`return <expr>` — they escaped this check rather than failing it"
    )
    non_conforming = [g for g in guards if g.strip() != "_profile_sdk_unavailable()"]
    assert non_conforming == [], (
        f"{len(non_conforming)} of {len(guards)} profile-SDK guards return "
        f"something other than _profile_sdk_unavailable(): {non_conforming}"
    )


def test_the_payload_is_not_shared_mutable_state() -> None:
    """Tool results go back to clients; one caller must not poison the next."""
    first = directory._profile_sdk_unavailable()
    first["error"] = "mutated"
    assert directory._profile_sdk_unavailable()["error"] != "mutated"
