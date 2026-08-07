"""`record_interaction` — the WRITE half of the topology loop, driven as a tool.

Why this file exists, and why it is not `test_record_interaction.py`.

That file already exists and is named after this tool, but it tests two helpers
(`_consent_aware_error`, `_stable_event_time`) and never invokes the tool itself:
`grep -rn 'record_interaction(' trust-toolkit/tests/ tests/ sdk/tests/` returns
nothing. That is worse than an empty directory. Anyone asking "is
`record_interaction` covered?" reads the filename and stops — the reassurance is
present and the property is absent, which is the exact shape `docs/vacuous-checks.md`
is about, applied to a test file rather than a check.

And it is how the tool shipped DEAD in 0.8.0. Its own diff docstring records that
it ran `if (missing := _need_directory(app)) is not None: return {"error": missing}`
on the SUCCESS path, so it returned the directory URL in an `error` field and never
made a request — with 608 tests green. Registration is not evidence. Import is not
evidence. Only "a request was made, with these arguments" is evidence.

So every test here drives the tool function as the server dispatches it and asserts
on what reached the client. The harness deliberately mirrors
`test_network_reputation.py`: the two halves of the same loop should fail the same
way when they break, and a reader who has understood one should recognise the other.
"""

from __future__ import annotations

import asyncio
import base64
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

import httpx
import pytest  # noqa: TC002 — a runtime fixture type (MonkeyPatch), not an annotation-only import
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from synpareia.block import Block, verify_block
from synpareia.hash import content_hash, jcs_canonicalize
from synpareia.topology import TOPOLOGY_EVENT_BLOCK_TYPE

from synpareia_trust_mcp.tools import directory

_ME = "did:synpareia:" + "a" * 64
_THEM = "did:synpareia:" + "b" * 64

_OUR_SEED = b"k" * 32
_NOT_OUR_SEED = b"z" * 32


def _public_key(seed: bytes) -> bytes:
    return Ed25519PrivateKey.from_private_bytes(seed).public_key().public_bytes_raw()


def _signature_verifies(envelope: dict[str, Any], public_key: bytes) -> bool:
    """THE realness assertion for this file (`docs/vacuous-checks.md` rule 4).

    Every other assertion here is a *shape* assertion — this key is present, that
    string is long enough. A shape assertion cannot tell a signature from any other
    88-character string, and the first draft of this file proved it: signing the
    envelope with a key that is not the author's left both tests named for the
    signature green. That is #382, one release after #382 was closed.

    So this reconstructs the block **the way the real consumer does** and calls the
    same verifier. The directory's ingest path builds this same `Block` from the wire
    envelope and calls this same public `verify_block(block, author_public_key)`; the
    field mapping below mirrors that reconstruction rather than being invented, so a
    divergence in how the directory reads an envelope shows up here as a failure
    instead of as a rejected event in production.

    Deliberately NOT reused from the SDK as a one-liner: there is no public
    "verify this envelope" helper, and adding a private-function import
    (`_signing_envelope`) would make the test depend on the signing internals it is
    meant to be independent of. `verify_block` is public and is what the far end runs.
    """
    content = jcs_canonicalize(envelope["tags"])
    block = Block(
        id=envelope["block_id"],
        # NOT read from the envelope — `build_topology_event` does not emit a
        # `block_type` key at all, and `TopologyEventEnvelope.block_type` supplies
        # this constant as a Pydantic default. The signature covers the block type,
        # so writer and reader agreeing on it is load-bearing and invisible: if the
        # SDK ever signed a different type, the far end would still validate against
        # its own default and reject every event. Importing the one constant both
        # sides use makes that divergence a failure here instead of in production.
        type=TOPOLOGY_EVENT_BLOCK_TYPE,
        author_id=envelope["author_did"],
        content_hash=content_hash(content),
        created_at=datetime.fromisoformat(envelope["created_at"]),
        content=content,
        signature=base64.b64decode(envelope["author_signature_b64"], validate=True),
        metadata=envelope["metadata"],
        co_signatures=(),
    )
    return verify_block(block, public_key)


class _FakeClient:
    """Stands in for `ProfileClient`, recording the call rather than making it."""

    def __init__(
        self, result: dict[str, Any] | None = None, raises: BaseException | None = None
    ) -> None:
        self.result = result if result is not None else {"idempotent": False}
        self.raises = raises
        self.calls: list[dict[str, Any]] = []

    async def __aenter__(self) -> _FakeClient:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None

    async def submit_event(self, **kwargs: Any) -> dict[str, Any]:
        self.calls.append(kwargs)
        if self.raises is not None:
            raise self.raises
        return self.result


def _ctx(
    *, private_key: bytes | None = b"k" * 32, did: str = _ME, tmp_path: Any = None
) -> SimpleNamespace:
    profile = SimpleNamespace(id=did, private_key=private_key)
    app = SimpleNamespace(
        config=SimpleNamespace(
            network_url="https://d.example",
            witness_token=None,
            data_dir=tmp_path,
        ),
        profile_manager=SimpleNamespace(profile=profile),
    )
    return SimpleNamespace(request_context=SimpleNamespace(lifespan_context=app))


def _call(ctx: SimpleNamespace, subject: str = _THEM, **kwargs: Any) -> dict[str, Any]:
    """Invoke the tool **as the server dispatches it**.

    Resolved out of the live tool registry rather than imported from the module,
    so a tool that stopped being registered — or got registered under a different
    name — fails here with a KeyError instead of passing against an import. This
    is the assertion `test_mcp_integration.py`'s `issubset` check cannot make.
    """
    from synpareia_trust_mcp.server import mcp

    tool = mcp._tool_manager._tools["record_interaction"]  # noqa: SLF001
    out: dict[str, Any] = asyncio.run(tool.fn(subject, ctx, **kwargs))
    return out


def _with_client(monkeypatch: pytest.MonkeyPatch, client: _FakeClient) -> None:
    monkeypatch.setattr(directory, "_build_profile_client", lambda _app: client)


class TestTheCallIsActuallyMade:
    """The 0.8.0 regression, made impossible to reintroduce silently."""

    def test_a_request_reaches_the_client(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """THE control for this file. In 0.8.0 this assertion is the one that
        fails: the tool returned an `error` dict on the success path and
        `client.calls` stayed empty while every other test in the package passed.
        """
        client = _FakeClient({"idempotent": False, "event_id": "evt_x"})
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path))

        assert len(client.calls) == 1, (
            "the tool made no request — it is inert, which is exactly how it "
            "shipped in 0.8.0 with 608 tests green"
        )

    def test_the_event_is_signed_by_us_and_names_both_parties(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """A write anchored on the wrong author, or naming one party, is still
        well-formed and still records the wrong thing about the wrong people."""
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path))

        call = client.calls[0]
        assert call["private_key"] == _OUR_SEED, "signed with the wrong key"
        envelope = call["envelope"]
        parties = envelope["tags"]["parties"]
        assert set(parties) == {_ME, _THEM}, (
            f"the edge names {parties}, not the two agents that dealt with each other"
        )
        assert envelope["author_did"] == _ME, "authored as someone else"
        # `author_did` above is a plaintext string anyone can write. This binds it
        # to the key that actually signed, which is what makes "by us" a claim
        # rather than a label.
        assert _signature_verifies(envelope, _public_key(_OUR_SEED)), (
            "the envelope declares us as author but is not signed by our key — the "
            "directory would reject this as signature_invalid"
        )

    def test_no_content_field_reaches_the_wire(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """The content-less invariant (legal §11.4 inv. 2) asserted at the point
        it could actually be violated, rather than in prose.

        ASSERTED AS AN ALLOWLIST, not as `"context" not in tags`. "No content
        reaches the wire" is a claim about the whole payload; naming the one field
        that would carry prose today tests a sample of one and says nothing about
        the next field someone adds. CLAUDE.md §3, derive the quantifier or drop
        it. An earlier draft asserted only the `context` case, and adding
        `tags["note"] = "<prose>"` to the tool left it green.

        So the allowlist below is the full set the tool may emit, and anything
        outside it fails — whether or not the author of the new field thought of
        this test. `metadata` is covered too: `visibility` is the only key
        `record_interaction` is permitted to set there (#249), and it is a
        classifier, not content.
        """
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path), magnitude=0.9, valence=-0.5)

        envelope = client.calls[0]["envelope"]
        permitted_tags = {"tag_schema_version", "parties", "interaction_magnitude", "valence"}
        assert set(envelope["tags"]) <= permitted_tags, (
            "a field outside the content-less allowlist reached the network: "
            f"{ {k: envelope['tags'][k] for k in set(envelope['tags']) - permitted_tags} }"
        )
        assert set(envelope["metadata"]) <= {"visibility"}, (
            "an unexpected metadata field reached the network: "
            f"{ {k: envelope['metadata'][k] for k in set(envelope['metadata']) - {'visibility'}} }"
        )


class TestTheArgumentsSurviveTheJourney:
    def test_the_float_api_is_encoded_as_milli_units_on_the_wire(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """The tool takes 0..1 floats; the wire carries integer milli-units
        (`0.75 -> 750`). A float-to-int scaling is exactly where a silent factor
        of ten lives, and every number downstream would still look plausible.
        Asserted on literals, not on `round(x * 1000)`, so the test does not
        reimplement the transform it is checking.
        """
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path), magnitude=0.75, valence=-0.25)

        tags = client.calls[0]["envelope"]["tags"]
        assert tags["interaction_magnitude"] == 750
        assert tags["valence"] == -250
        assert tags["tag_schema_version"] == "1", (
            "the row would be stored without provenance for its own encoding"
        )

    def test_omitting_valence_records_that_you_dealt_without_saying_how(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """A documented, meaningful case: `valence` absent is not `valence: 0`.
        Zero is a neutral verdict; absent is no verdict."""
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path), magnitude=0.5)

        tags = client.calls[0]["envelope"]["tags"]
        assert "valence" not in tags, (
            f"omitting valence recorded a verdict of {tags.get('valence')!r} anyway"
        )

    def test_shareable_governs_the_visibility_marker_and_defaults_to_private(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """`shareable` is the field deciding whether a third party can ever see
        this edge. It is carried as `metadata.visibility`, present only when
        True — so a default that leaked would be invisible to every assertion
        about the numbers, which would all still be right (#249)."""
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path))
        assert client.calls[0]["envelope"]["metadata"].get("visibility") is None, (
            "the default recorded an edge as network-traversable"
        )

        client.calls.clear()
        _call(_ctx(tmp_path=tmp_path), shareable=True, event_id="evt_distinct")
        assert client.calls[0]["envelope"]["metadata"]["visibility"] == "network_traversable"

    def test_the_event_is_signed_not_merely_assembled(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """An unsigned envelope is well-formed and rejected at the far end, which
        looks like a server problem from here.

        `len(sig) > 40` is a shape assertion and cannot tell a signature from any
        other 88-character string — an envelope signed by the wrong key passes it.
        So the real check is `_signature_verifies`, and the second half below is
        its POSITIVE CONTROL: a verifier that returned True unconditionally would
        satisfy the first assertion, and only the foreign-key case can catch that.
        Without the control this test would be asserting that a function it also
        wrote agrees with itself.
        """
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path))

        envelope = client.calls[0]["envelope"]
        sig = envelope["author_signature_b64"]
        assert isinstance(sig, str) and len(sig) > 40, f"not a signature: {sig!r}"
        assert _signature_verifies(envelope, _public_key(_OUR_SEED)), (
            "the envelope carries a signature-shaped string that does not verify"
        )
        assert not _signature_verifies(envelope, _public_key(_NOT_OUR_SEED)), (
            "the verifier accepts a foreign key, so the assertion above proves nothing"
        )

    def test_a_supplied_event_id_is_the_one_used(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        client = _FakeClient()
        _with_client(monkeypatch, client)

        _call(_ctx(tmp_path=tmp_path), event_id="evt_caller_chose_this")

        assert client.calls[0]["envelope"]["block_id"] == "evt_caller_chose_this"

    def test_the_derived_event_id_is_content_only_and_stable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """Two identical interactions must derive the same id, or a retry records
        twice. An earlier version mixed the date in, so the id drifted across
        midnight and the one thing meant to make retries safe became a source of
        divergence.

        THE CLOCK IS MOVED BETWEEN THE TWO CALLS, and that is the whole test.
        Calling twice in the same instant yields the same id whether or not the
        date is in the hash, so a version of this that just calls twice cannot
        observe the defect its own docstring describes — it asserts the property
        under precisely the conditions where the broken code also satisfies it
        (`docs/vacuous-checks.md` rule 3). Re-adding the date to the derivation
        left that version green; it turns this one red.

        23:59:59 → 00:00:01 the next day is the narrowest window that crosses the
        boundary, so the test fails for a date dependency and not for any
        coarser drift.
        """
        client = _FakeClient()
        _with_client(monkeypatch, client)

        class _Clock(datetime):
            """A `datetime` whose `now()` we control; `fromisoformat` et al. are
            inherited, so the memo read-back path is unaffected."""

            current = datetime(2026, 8, 7, 23, 59, 59, tzinfo=UTC)

            @classmethod
            def now(cls, tz: Any = None) -> datetime:  # noqa: ARG003 - signature parity
                return cls.current

        monkeypatch.setattr(directory, "datetime", _Clock)

        _call(_ctx(tmp_path=tmp_path), magnitude=0.5, valence=0.1)
        _Clock.current = datetime(2026, 8, 8, 0, 0, 1, tzinfo=UTC)
        _call(_ctx(tmp_path=tmp_path), magnitude=0.5, valence=0.1)

        first, second = (c["envelope"]["block_id"] for c in client.calls)
        assert first == second, (
            "an identical re-send one second later, across midnight, derived a "
            "different id — the date has got into the derivation and every retry "
            "spanning midnight records a second interaction"
        )
        assert first.startswith("evt_")
        # The memo is the other half of idempotency: a stable id with a moving
        # timestamp still rebuilds a different signing envelope.
        assert (
            client.calls[0]["envelope"]["created_at"] == client.calls[1]["envelope"]["created_at"]
        ), (
            "created_at moved with the clock, so the directory derives a different "
            "event hash and the retry is recorded as a new interaction"
        )


class TestRefusalsHappenBeforeAnyRequest:
    """Each of these must refuse *without* reaching the network. A refusal that
    still makes the call has already leaked the thing it refused to record."""

    def test_recording_yourself_is_refused_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        client = _FakeClient()
        _with_client(monkeypatch, client)

        out = _call(_ctx(tmp_path=tmp_path), subject=_ME)

        assert out["code"] == "self_interaction"
        assert client.calls == [], "refused, but sent the event anyway"

    def test_a_missing_private_key_is_refused_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        client = _FakeClient()
        _with_client(monkeypatch, client)

        out = _call(_ctx(private_key=None, tmp_path=tmp_path))

        assert "private key" in out["error"]
        assert client.calls == [], "signed nothing, but posted anyway"

    def test_an_out_of_range_magnitude_is_refused_and_sends_nothing(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        client = _FakeClient()
        _with_client(monkeypatch, client)

        out = _call(_ctx(tmp_path=tmp_path), magnitude=42.0)

        assert out["code"] == "invalid_arguments"
        assert client.calls == []


class TestTheResponseSaysWhatHappenedInWords:
    def test_an_idempotent_replay_says_so_rather_than_reading_as_a_second_write(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """`idempotent: true` is easy to skim past, and skimming past it means
        counting a retry as a second interaction."""
        _with_client(monkeypatch, _FakeClient({"idempotent": True}))
        out = _call(_ctx(tmp_path=tmp_path))
        assert "not a second interaction" in out["effect"]

    def test_a_first_write_does_not_claim_to_be_a_replay(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        _with_client(monkeypatch, _FakeClient({"idempotent": False}))
        out = _call(_ctx(tmp_path=tmp_path))
        assert out["effect"] == "recorded"

    def test_the_counterparty_is_echoed_so_the_caller_can_check_it(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        _with_client(monkeypatch, _FakeClient())
        assert _call(_ctx(tmp_path=tmp_path))["counterparty_did"] == _THEM


def _raising_403(code: str | None) -> _FakeClient:
    """A client whose `submit_event` raises a 403 carrying `code` (or a bare
    string detail, the shape the service's ACCESS GATE returns, when None)."""
    body: dict[str, Any] = (
        {"detail": {"detail": "not consented", "code": code}} if code else {"detail": "Forbidden"}
    )
    request = httpx.Request("POST", "https://d.example/api/v2/events")
    response = httpx.Response(403, json=body, request=request)
    return _FakeClient(raises=httpx.HTTPStatusError("403", request=request, response=response))


class TestA403IsExplainedOnlyWhenWeKnowWhy:
    """`_consent_aware_error` branches on the CODE, not on 403 alone. Both
    directions matter and only one of them is obvious."""

    def test_a_consent_refusal_is_reported_as_a_fact_about_them_not_a_bad_request(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """The remedy is to ask the counterparty, not to retry. An agent that
        reads this as its own error retries forever against something that will
        never succeed."""
        _with_client(monkeypatch, _raising_403("consent_missing"))

        out = _call(_ctx(tmp_path=tmp_path))

        assert out["code"] == "counterparty_has_not_consented"
        assert out["counterparty_did"] == _THEM
        assert "retrying will not help" in out["remedy"]
        assert out["server_detail"]["code"] == "consent_missing", (
            "the service's own words were paraphrased away; a multi-party event "
            "can fail on a party the caller was not thinking about"
        )

    def test_an_access_gate_403_does_not_accuse_the_counterparty(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Any
    ) -> None:
        """THE control for the pair. Under a legitimate re-gate (CLAUDE.md §0)
        the access middleware answers 403 with a bare `{"detail": "Forbidden"}`.
        Branching on the status alone would make the tool state, confidently and
        by name, that a specific third party had refused consent — a false claim
        about someone else. A generic error beats a wrong explanation.
        """
        _with_client(monkeypatch, _raising_403(None))

        out = _call(_ctx(tmp_path=tmp_path))

        assert out.get("code") != "counterparty_has_not_consented"
        assert "has not consented" not in str(out), (
            "a re-gated service was reported as the counterparty refusing consent"
        )
        assert out["status_code"] == 403
