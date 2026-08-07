"""Structural invariants for the interaction-Forms layer.

The Forms are recipes: they tell an agent which calls to make, in order. That
makes a wrong tool name in a Form body categorically worse than a wrong tool
name in prose — the agent follows it, the call fails, and it fails in front of
a counterparty mid-interaction. The Manual of Forms these are distilled from
specifies primitives that do NOT exist on this surface (co-signed commitments,
``derivative_signal_policy``, stakes), so the risk is concrete and was
introduced by this very slice.

``test_every_tool_named_in_a_recipe_actually_exists`` is therefore the
load-bearing test here: it enumerates the LIVE tool registry and refuses any
call a Form names that the server does not register. It would have caught a
recipe written from the design doc instead of from the code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from synpareia_trust_mcp.forms import (
    FORM_GUIDES,
    FORMS,
    FULL,
    GAP_NO_CLAIM_TRANSPORT,
    GAP_NO_COSIGN,
    GAP_NO_POLICY,
    GAP_NO_STAKE,
    render_index,
)
from synpareia_trust_mcp.guides import AREA_GUIDES, LEARNABLE
from synpareia_trust_mcp.tools.orient import AREAS_OF_CONCERN, START_HERE, learn

# ---------------------------------------------------------------------------
# The live tool registry
# ---------------------------------------------------------------------------


def _registered_tool_names() -> set[str]:
    """Names the MCP server actually registers, read from the registry.

    Deliberately NOT a hand-maintained list — a hardcoded copy would drift the
    moment a tool is renamed, and would then agree with a stale Form instead of
    catching it.
    """
    from synpareia_trust_mcp import tools  # noqa: F401  (registers the tools)
    from synpareia_trust_mcp.app import mcp

    return {tool.name for tool in mcp._tool_manager.list_tools()}


# Every snake_case token, not just the ones written with parentheses.
#
# The first version of this check only matched `name(`, and caught 4 of the 16
# tool references in these recipes. The other 12 are written as prose —
# "recording_start / recording_append / recording_end around it" — which is just
# as much an instruction to an agent, and just as wrong if the name is wrong.
_SNAKE_RE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")

# Parameter and response-field names that legitimately appear in recipe prose.
# Explicit and small so that adding one is a deliberate act with a reviewer,
# not a silent widening. Every OTHER snake_case token must be a live tool.
_PARAMETER_NAMES = frozenset(
    {
        "block_hash_hex",  # make_claim response / witness_seal_timestamp param
        "claim_type",  # verify_claim param
        "commitment_hash",  # prove_independence response
        "nonce_b64",  # prove_independence response
        "witness_followup",  # make_claim response field
        "derivative_signal_policy",  # named precisely because it does NOT exist
    }
)


def _identifiers_in(text: str) -> set[str]:
    return set(_SNAKE_RE.findall(text)) - _PARAMETER_NAMES


# ---------------------------------------------------------------------------
# The load-bearing check
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_every_tool_named_in_a_recipe_actually_exists(form) -> None:
    """A Form must not instruct an agent to call something that isn't there."""
    registered = _registered_tool_names()
    named = _identifiers_in(form.body)
    unknown = named - registered
    assert not unknown, (
        f"{form.key} names call(s) that the MCP server does not register: "
        f"{sorted(unknown)}. Either the tool was renamed, or this recipe was "
        f"written from the design doc rather than from the code."
    )


def test_the_forms_index_names_no_unknown_tools() -> None:
    unknown = _identifiers_in(render_index()) - _registered_tool_names()
    assert not unknown, f"interaction-forms index names unknown call(s): {sorted(unknown)}"


def test_at_least_one_real_tool_is_named_across_the_forms() -> None:
    """Guard the guard.

    If ``_SNAKE_RE`` stopped matching, every check above would pass vacuously
    while asserting nothing — a green suite that has stopped looking. The
    threshold is set near the real count (16 at the time of writing) rather
    than at 1, so that a regex change which silently halves the coverage fails
    here instead of quietly narrowing what the suite examines.
    """
    found: set[str] = set()
    for form in FORMS:
        found |= _identifiers_in(form.body)
    matched = found & _registered_tool_names()
    assert len(matched) >= 12, (
        f"Extraction matched only {len(matched)} live tools ({sorted(matched)}) — "
        f"the identifier regex has probably narrowed, which would make the "
        f"tool-existence checks pass while examining almost nothing."
    )


# ---------------------------------------------------------------------------
# Reachability
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_every_form_is_reachable_through_learn(form) -> None:
    result = learn(form.key)
    assert "error" not in result
    assert result["area"] == form.key
    assert result["guide"] == form.body


def test_forms_index_is_reachable_and_lists_every_form() -> None:
    index = learn("interaction-forms")
    assert "error" not in index
    guide = index["guide"]
    for form in FORMS:
        assert form.key in guide, f"{form.key} missing from the index"
        assert form.situation in guide, f"{form.key}'s situation line missing from the index"


def test_interaction_forms_is_an_area_and_comes_second() -> None:
    """First is deciding-what-to-establish (is evidence worth it), then the
    shapes. Everything after is organised by capability rather than situation.
    """
    keys = [a["area"] for a in AREAS_OF_CONCERN]
    assert keys[0] == "deciding-what-to-establish"
    assert keys[1] == "interaction-forms"


def test_individual_forms_are_not_listed_as_areas() -> None:
    """Ten extra area rows would rebuild the table-of-contents problem that the
    orientation rework exists to remove. They stay behind the one index entry.
    """
    area_keys = {a["area"] for a in AREAS_OF_CONCERN}
    assert not (area_keys & set(FORM_GUIDES)), "Form keys must not appear in AREAS_OF_CONCERN"


def test_unknown_area_error_offers_both_areas_and_forms() -> None:
    result = learn("no-such-area")
    assert "error" in result
    assert "interaction-forms" in result["available_areas"]
    assert set(result["available_forms"]) == set(FORM_GUIDES)


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_cross_references_between_forms_resolve(form) -> None:
    """No dead links. A recipe that punts to a neighbouring Form is only useful
    if the neighbour exists under that exact key.
    """
    referenced = set(re.findall(r"\bform-[a-z-]+", form.body))
    dangling = referenced - set(FORM_GUIDES) - {form.key}
    assert not dangling, f"{form.key} references non-existent Form(s): {sorted(dangling)}"


def test_learnable_is_the_union_and_has_no_key_collisions() -> None:
    assert set(LEARNABLE) == set(AREA_GUIDES) | set(FORM_GUIDES)
    assert not (set(AREA_GUIDES) & set(FORM_GUIDES)), "an area and a Form share a key"


# ---------------------------------------------------------------------------
# Honesty about limits
# ---------------------------------------------------------------------------

_ALL_GAPS = (GAP_NO_COSIGN, GAP_NO_POLICY, GAP_NO_CLAIM_TRANSPORT, GAP_NO_STAKE)


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_a_degraded_form_declares_and_states_its_gaps(form) -> None:
    """A Form that cannot be fully delivered must say so IN THE BODY.

    Metadata alone is not enough: the agent reads the body, not the dataclass.
    This is the check that stops a recipe reading as complete while its
    load-bearing phase is missing.
    """
    if form.delivery == FULL:
        assert not form.gaps, f"{form.key} claims full delivery but declares gaps"
        return

    assert form.gaps, f"{form.key} is not full delivery but names no gap"
    for gap in form.gaps:
        assert gap in _ALL_GAPS, f"{form.key} declares an unrecognised gap constant"
        assert gap.marker.casefold() in form.body.casefold(), (
            f"{form.key} declares the {gap.marker!r} gap in metadata, but its body "
            f"never mentions it. The agent only ever sees the body — a gap declared "
            f"where only the code can read it has not been disclosed."
        )


def test_each_gap_paragraph_contains_its_own_marker() -> None:
    """The marker must be a phrase a Form quoting the gap IN FULL would satisfy.

    Otherwise a Form could paste the canonical paragraph verbatim — the most
    complete possible disclosure — and still fail the check above.
    """
    for gap in _ALL_GAPS:
        assert gap.marker.casefold() in gap.text.casefold(), (
            f"gap marker {gap.marker!r} does not appear in its own paragraph"
        )


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_a_degraded_form_says_so_where_it_can_be_seen(form) -> None:
    if form.delivery == FULL:
        return
    assert "WHAT YOU CANNOT DO HERE YET" in form.body or "DOES NOT WORK HERE" in form.body


def test_the_index_states_all_four_structural_gaps() -> None:
    index = render_index()
    for phrase in ("co-signing", "propagation policy", "does not travel", "stake"):
        assert phrase in index, f"index does not mention the {phrase!r} gap"


def test_no_surface_still_says_reputation_is_read_only() -> None:
    """The inverse of what this test used to assert, and the reason it is here.

    Until the read route landed, the Forms declared "NOTHING FLOWS. Reputation is
    read-only in v1", and this file REQUIRED the phrase — so the surface's most
    load-bearing false claim was pinned in place by a green test. It was false in
    the other direction too: the write path (`record_interaction`) had shipped a
    release earlier while every Form still told agents no such thing existed.

    Both halves now exist, so the claim is checked for ABSENCE. Any surface an
    agent reads must not tell them the network cannot be written to or read from.
    The residual constraint is real but narrower — the claim's SUBSTANCE cannot be
    published — and `test_the_index_states_all_four_structural_gaps` above is what
    holds the surface to still saying that much.
    """
    surfaces = {f"form:{form.key}": form.body for form in FORMS}
    surfaces["index"] = render_index()
    surfaces |= {f"gap:{gap.marker}": gap.text for gap in _ALL_GAPS}
    for name, text in surfaces.items():
        assert "read-only in v1" not in text.casefold(), (
            f"{name} still tells agents reputation is read-only. Both the write "
            f"(record_interaction) and the read (network_reputation) exist."
        )


def test_the_claim_transport_gap_still_names_what_actually_works() -> None:
    """A gap paragraph that only says "no" is the failure mode in the other
    direction: an agent reading it concludes the network is useless to them.

    This one must name both sides — what does travel and what does not — or the
    correction above just swaps one misleading surface for another.
    """
    text = GAP_NO_CLAIM_TRANSPORT.text
    assert "record_interaction" in text, "does not name the write path that exists"
    assert "network_reputation" in text, "does not name the read path that exists"
    assert "by design" in text, (
        "reads as a v1 limitation. Unilateral publication of content-bearing claims "
        "about a counterparty is excluded permanently, not deferred — an agent told "
        "otherwise will wait for a release that is not coming."
    )


def _witness_flag_sites() -> list[tuple[str, str]]:
    """EVERY agent-facing string that mentions ``witness=True``, from any surface.

    Deliberately not parametrised over ``FORMS`` alone. The first version of
    this check was, and the gate caught what that missed: two sites outside the
    Forms — a ``deciding-what-to-establish`` paragraph and a ``start_here``
    entry — said ``witness=True`` and named no second call, while a CHANGELOG
    line asserted the property held everywhere and was "enforced by a test".
    A check scoped to one surface cannot support a claim about all of them.
    """
    sites = [(f"form:{form.key}", form.body) for form in FORMS]
    sites += [(f"area:{key}", text) for key, text in AREA_GUIDES.items()]
    sites += [(f"start_here:{key}", text) for key, text in START_HERE.items()]
    sites.append(("index", render_index()))
    return sites


def test_the_witness_check_covers_every_agent_facing_surface() -> None:
    """Guard the SCOPE of the check above, not just its assertion.

    Once the copy is correct, silently narrowing ``_witness_flag_sites`` back to
    ``FORMS`` alone breaks nothing — the removed sites no longer had anything to
    catch, so the suite stays green while examining 22 fewer strings. That is
    how the defect the gate caught got in: a check scoped to one surface
    supporting a claim about all of them. So assert the scope explicitly.
    """
    labels = [where for where, _ in _witness_flag_sites()]
    assert len(labels) == len(FORMS) + len(AREA_GUIDES) + len(START_HERE) + 1
    assert any(label.startswith("area:") for label in labels)
    assert any(label.startswith("start_here:") for label in labels)
    assert "index" in labels


@pytest.mark.parametrize(
    ("where", "text"), _witness_flag_sites(), ids=lambda v: v if isinstance(v, str) else ""
)
def test_every_witness_flag_mention_names_the_second_call(where: str, text: str) -> None:
    """``make_claim(witness=True)`` signs; it does NOT seal.

    ``tools/identity.py`` attaches a ``witness_followup`` instruction naming
    ``witness_seal_timestamp``; the flag alone obtains nothing. Any surface that
    tells an agent to pass it and stops there leaves them holding proof of
    AUTHORSHIP and no proof of TIME — the exact property the calibration and
    precommitment shapes exist to establish, silently absent.
    """
    if "witness=True" not in text:
        return
    assert "witness_seal_timestamp" in text, (
        f"{where} says witness=True without naming witness_seal_timestamp — "
        f"an agent following it would believe it had a timestamp it does not have."
    )


# ---------------------------------------------------------------------------
# Drift against the canonical Manual
# ---------------------------------------------------------------------------


def _manual_dir() -> Path | None:
    """Locate ``docs/forms/`` in the monorepo, or None outside it.

    Absent when the package is installed from a wheel or the public repo is
    checked out alone — ``docs/`` ships in neither. The drift tests SKIP there
    with a stated reason rather than passing silently, because "no docs to
    compare against" and "docs agree" are different observations and must not
    produce the same result.
    """
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "docs" / "forms"
        if candidate.is_dir():
            return candidate
    return None


def _frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}
    _, block, _ = text.split("---", 2)
    out = {}
    for line in block.strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            out[key.strip()] = value.strip()
    return out


def _manual_files(manual: Path) -> list[Path]:
    return sorted(
        p for p in manual.rglob("*.md") if p.name != "README.md" and not p.name.startswith("_")
    )


def test_every_manual_form_has_a_guide() -> None:
    """A Form added to the Manual but not here is invisible to every agent."""
    manual = _manual_dir()
    if manual is None:
        pytest.skip("docs/forms/ not present — not running inside the monorepo")

    documented = {p.relative_to(manual).as_posix() for p in _manual_files(manual)}
    inlined = {form.doc for form in FORMS}
    assert documented == inlined, (
        f"Manual and guides disagree. Only in docs/forms/: {sorted(documented - inlined)}. "
        f"Only in forms.py: {sorted(inlined - documented)}."
    )


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_guide_metadata_matches_the_manual(form) -> None:
    manual = _manual_dir()
    if manual is None:
        pytest.skip("docs/forms/ not present — not running inside the monorepo")

    path = manual / form.doc
    assert path.is_file(), f"{form.key} cites {form.doc}, which does not exist"

    meta = _frontmatter(path)
    assert meta.get("phase") == form.phase, (
        f"{form.key} says phase={form.phase!r}; the Manual says {meta.get('phase')!r}"
    )

    heading = next(
        line[2:].strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.startswith("# ")
    )
    assert heading == form.name, (
        f"{form.key} says name={form.name!r}; the Manual's heading is {heading!r}"
    )


@pytest.mark.parametrize("form", FORMS, ids=lambda f: f.key)
def test_each_guide_points_back_at_its_canonical_source(form) -> None:
    assert f"docs/forms/{form.doc}" in form.body, (
        f"{form.key} does not cite its canonical Manual path, so a reader who "
        f"needs the full recipe has nowhere to go."
    )
