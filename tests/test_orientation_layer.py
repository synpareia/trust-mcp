"""Guards for the L0 orientation layer — `AREAS_OF_CONCERN` <-> `AREA_GUIDES`, and
the shape of `start_here`.

WHY THESE EXIST. A live agent used this package daily for a fortnight and concluded
synpareia was "a narrow wedge" — reasoning, in its words, "from orient's table of
contents". The 2026-07-28 surface audit traced that to `orient()` being an inventory
with no deliberative layer: `start_here` was keyed on conclusions the agent had to
reach unaided ("need to prove your side of an interaction later"), so an agent that
never thought to ask "should this exchange carry evidence at all?" never entered the
table.

The fix added a `deciding-what-to-establish` area and reframed `start_here` so each
value names WHAT IS BEING ESTABLISHED before naming a tool. These tests pin both
properties, because the surrounding tests do not: the existing
`test_network_unconfigured_invites_joining_with_reputation_framing` asserts only loose
substrings, and it neither caught the original defect nor would catch a revert.
"""

from __future__ import annotations

import pytest

from synpareia_trust_mcp.guides import AREA_GUIDES
from synpareia_trust_mcp.tools.orient import AREAS_OF_CONCERN, START_HERE, orient

# start_here entries that are META — they answer "what is this / where am I", not
# "here is a situation and what you would establish in it". Listed explicitly so a
# NEW entry cannot quietly join the exemption; adding one here is a visible decision.
_META_SITUATIONS = frozenset({"not sure any of this applies", "lost context / fresh session"})


def test_start_here_is_what_orient_actually_returns(app_ctx) -> None:  # noqa: ANN001
    """The constant and the RESPONSE must not diverge — so this calls `orient()`.

    `START_HERE` is module-level so it can be asserted on; it was previously a literal
    inside `orient()`, reachable only by executing the whole tool, which is precisely
    why the L0 property went unpinned. But hoisting introduces its own risk: the
    function could return a copy, a filtered view, or a stale duplicate, and every
    assertion in this file would still pass while agents received something else.

    The first version of this test asserted only on the constant and was NAMED as
    though it checked the response. Fixed by actually calling orient().
    """
    ctx, _ = app_ctx
    returned = orient(ctx)["start_here"]

    assert returned == START_HERE, "orient() returned a start_here that diverges from START_HERE"
    assert returned, "start_here must not be empty — it is the routing surface"
    assert all(isinstance(k, str) and isinstance(v, str) for k, v in returned.items())


@pytest.mark.parametrize(
    "situation", sorted(set(START_HERE) - _META_SITUATIONS), ids=lambda s: s[:40]
)
def test_each_situation_names_what_is_being_established_before_a_tool(situation: str) -> None:
    """The L0 property, mechanically.

    A bare tool name ("verify_claim") tells an agent WHICH HAMMER. It does not help it
    notice it is holding a nail. Every non-meta entry must lead with what the agent
    would be ESTABLISHING, so the reasoning step is present in the surface rather than
    left to the reader.

    This is the assertion that would have failed against the pre-2026-07-28 table, and
    that fails again if someone "simplifies" these back to tool names.
    """
    value = START_HERE[situation]
    assert value.startswith("Establish:"), (
        f"{situation!r} routes straight to a tool without naming what is being "
        f"established. Got: {value[:80]!r}"
    )
    assert "->" in value, f"{situation!r} names an aim but no tool to reach it with"
    # The aim must come FIRST — an aim appended after the tool is decoration.
    assert value.index("Establish:") < value.index("->"), (
        f"{situation!r} names the tool before the aim; the aim is the point"
    )


@pytest.mark.parametrize("situation", sorted(_META_SITUATIONS))
def test_meta_situations_are_deliberate_not_forgotten(situation: str) -> None:
    """The two exemptions must still exist. If one is renamed or dropped, this fails
    loudly rather than silently shrinking the exemption set to fit."""
    assert situation in START_HERE, (
        f"{situation!r} is exempted from the Establish: rule but is no longer in "
        "START_HERE — update _META_SITUATIONS deliberately rather than leaving a "
        "stale exemption"
    )


def test_there_is_an_explicit_off_ramp() -> None:
    """An L0 layer that cannot say "you don't need this" is a funnel, not deliberation.

    The honest answer for most exchanges is that no evidence is required. If every
    route leads to a tool, the surface is selling rather than helping.
    """
    off_ramp = START_HERE.get("not sure any of this applies", "")
    assert "need no" in off_ramp or "not" in off_ramp.lower(), (
        "start_here must contain a route that legitimises doing nothing"
    )


def test_every_area_has_a_guide() -> None:
    """An area without a guide is a DEAD LINK: `learn(area)` returns an error dict.

    `orient()` advertises every area with "Call learn('<area>') for detailed
    guidance", so a missing guide turns advertised guidance into a 404 — the exact
    shape of failure this package keeps finding elsewhere (a surface promising a
    capability that isn't there).
    """
    areas = {a["area"] for a in AREAS_OF_CONCERN}
    missing = areas - set(AREA_GUIDES)
    assert not missing, (
        f"areas advertised by orient() with no guide behind them: {sorted(missing)}. "
        "learn() would return an error for each."
    )


def test_every_guide_is_reachable_from_orient() -> None:
    """The converse: a guide no area points at cannot be discovered.

    An agent learns which areas exist from `orient()`. A guide absent from
    AREAS_OF_CONCERN is reachable only by guessing its name.
    """
    areas = {a["area"] for a in AREAS_OF_CONCERN}
    orphaned = set(AREA_GUIDES) - areas
    assert not orphaned, f"guides unreachable from orient(): {sorted(orphaned)}"


def test_the_deliberation_area_exists_and_comes_first() -> None:
    """L0 must be present AND first.

    Order is not cosmetic here: every other area answers "how do I do X", and this one
    answers "is X worth doing at all". An agent reading top-down should meet the
    question before the catalogue.
    """
    assert AREAS_OF_CONCERN[0]["area"] == "deciding-what-to-establish", (
        "the deliberation area must be first — it is the step before tool selection, "
        f"but the list currently opens with {AREAS_OF_CONCERN[0]['area']!r}"
    )
    assert "deciding-what-to-establish" in AREA_GUIDES


def test_the_deliberation_guide_states_what_evidence_cannot_do() -> None:
    """The L0 layer must ship with its limits, or it is just a nicer overclaim.

    Leading with outcomes ("structure interactions to yield evidence") is exactly where
    over-promising gets easy. The guide has to say what a signature, a timestamp and a
    recording do NOT establish, or an agent will over-read its own evidence.
    """
    guide = AREA_GUIDES["deciding-what-to-establish"]
    for must_deny in ("not truth", "not evidence against", "says nothing about"):
        assert must_deny in guide, (
            f"the deliberation guide does not contain {must_deny!r}. It must state the "
            "limits of evidence alongside the encouragement to gather it."
        )


@pytest.mark.parametrize("area", sorted({a["area"] for a in AREAS_OF_CONCERN}))
def test_each_area_advertises_a_when(area: str) -> None:
    """Every area must say WHEN it applies, not just what it is.

    `when` is the field that lets an agent self-route. An area with a description and
    no trigger is a chapter title.
    """
    entry = next(a for a in AREAS_OF_CONCERN if a["area"] == area)
    assert entry.get("when", "").strip(), f"{area} has no 'when' trigger"


# ---------------------------------------------------------------------------
# The capability block — structure teaches shape before prose does
# ---------------------------------------------------------------------------
#
# WHY THESE EXIST. The same live agent that read this package as "a narrow
# wedge" gave a mechanical reason the surface audit had missed: the capability
# block itself taught the inverted architecture. It listed four NAMED offline
# bullets, then a two-item network list in which the entire reputation layer
# appeared once, at the end, in parentheses — "Synpareia network (reputation,
# discovery)". Its words: "the substrate gets four named bullets; the apex
# appears once, at the end of a two-item list, IN PARENTHESES."
#
# An agent parsing structure sees that before it reads a word of guidance. So
# the ordering and the naming are product decisions, and they get pinned like
# any other product decision.


def _capabilities(ctx) -> dict:  # noqa: ANN001
    return orient(ctx)["capabilities"]


def test_network_is_presented_before_the_offline_substrate(app_ctx) -> None:  # noqa: ANN001
    """Key order is the first thing a structural reader sees.

    Dict insertion order survives JSON serialisation to the caller, so this is
    not an implementation detail — it is what the agent receives.
    """
    ctx, _ = app_ctx
    keys = list(_capabilities(ctx))
    assert "network" in keys and "offline" in keys
    assert keys.index("network") < keys.index("offline"), (
        "the offline substrate is listed before the network layer again — that is "
        "the ordering which taught a live agent that the primitives were the product"
    )


def test_the_capability_block_states_which_layer_is_the_point(app_ctx) -> None:  # noqa: ANN001
    ctx, _ = app_ctx
    framing = _capabilities(ctx).get("what_this_is_for", "")
    assert framing, "the capability block must say which layer is the point"
    assert "network" in framing.lower()
    # Must state the RELATIONSHIP, not merely mention both halves. The defect
    # being fixed was a surface that named everything and ranked nothing.
    assert "substrate" in framing.lower()


def test_reputation_is_a_named_capability_not_a_parenthetical(app_ctx_with_stubs) -> None:  # noqa: ANN001
    """The exact regression: reputation surviving only inside brackets.

    An entry that merely CONTAINS the word passes a naive substring check while
    reproducing the defect — "Synpareia network (reputation, discovery)" contains
    it. So require reputation to be the SUBJECT of its own entry.
    """
    ctx, _ = app_ctx_with_stubs
    network = _capabilities(ctx)["network"]
    assert any(entry.lower().startswith("reputation") for entry in network), (
        f"no network capability leads with reputation; got {network!r}. A "
        f"parenthetical mention is what this test exists to reject."
    )


def test_the_directory_is_also_named_in_its_own_right(app_ctx_with_stubs) -> None:  # noqa: ANN001
    ctx, _ = app_ctx_with_stubs
    network = _capabilities(ctx)["network"]
    assert any(entry.lower().startswith("directory") for entry in network)


def test_the_reputation_capability_describes_the_loop_not_a_read_only_surface(
    app_ctx_with_stubs,  # noqa: ANN001
) -> None:
    """This test used to REQUIRE the words "read-only", and that is the point.

    It was written when reputation genuinely was three GETs, to stop a prominent
    capability line overclaiming. Then `record_interaction` shipped, then the
    anchored read route — and the guard against overclaiming had become a guard
    holding an UNDERclaim in place. An agent reading `orient` was told the one
    thing it most needed to act on was impossible.

    So the assertion is inverted rather than deleted. Deleting it would leave the
    line free to drift back; what it should pin is that both halves of the loop
    are named, since a capability list that mentions only lookups is how the old
    wording gets reintroduced by someone summarising.
    """
    ctx, _ = app_ctx_with_stubs
    reputation_entries = [
        entry for entry in _capabilities(ctx)["network"] if entry.lower().startswith("reputation")
    ]
    assert reputation_entries
    joined = " ".join(reputation_entries).lower()
    assert "read-only" not in joined, (
        "the reputation capability still tells agents the network cannot be written to"
    )
    assert "record_interaction" in joined and "network_reputation" in joined, (
        "the capability names neither half of the loop by the tool that does it — "
        "an agent cannot act on a capability whose tool it cannot find"
    )
    # The residual constraint is still real and still worth stating: what travels
    # is a magnitude and a valence, not the substance of an evaluation.
    assert "local journal" in joined, (
        "no longer says the substance of your own evaluations stays local"
    )
