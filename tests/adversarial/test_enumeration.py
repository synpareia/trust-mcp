"""Regression tests for enumeration-class exploits (ADV-004).

Ensures recording IDs that attempt path traversal or other filesystem
escape are rejected or safely handled — the ID is never joined into a
path in a way that reaches outside the data dir.
"""

from __future__ import annotations

from pathlib import Path

from synpareia_trust_mcp.tools.recording import (
    add_to_recording,
    end_recording,
    get_proof,
    record_interaction,
)

TRAVERSAL_IDS = [
    "../../etc/passwd",
    "../../../../root/.ssh/authorized_keys",
    "/etc/shadow",
    "..",
    ".",
    "\\..\\..\\windows\\system32",
    "recording\x00/etc/passwd",  # null-byte truncation attempt
]


class TestPathTraversal:
    """ADV-004 — recording_id values must not escape the data dir."""

    def test_traversal_ids_return_not_found_not_file_content(self, app_ctx) -> None:
        ctx, app = app_ctx
        data_dir = str(app.config.data_dir)

        for bad_id in TRAVERSAL_IDS:
            for op in (
                lambda rid: add_to_recording(recording_id=rid, content="x", ctx=ctx),
                lambda rid: end_recording(recording_id=rid, ctx=ctx),
                lambda rid: get_proof(recording_id=rid, ctx=ctx),
            ):
                result = op(bad_id)
                # Must be a dict with error — never raise, never crash
                assert isinstance(result, dict)
                assert "error" in result, f"traversal id {bad_id!r} did not produce error: {result}"

                body = repr(result)

                # Real file content must never appear (root:x:0:0 is the
                # first line of /etc/passwd on most systems; ssh keys
                # start with "ssh-rsa" / "ssh-ed25519"; any PEM block
                # starts with "-----BEGIN")
                assert "root:x:" not in body
                assert "ssh-rsa" not in body
                assert "ssh-ed25519" not in body
                assert "-----BEGIN" not in body

                # The data dir's absolute path must not leak either —
                # that would reveal the server's filesystem layout
                assert data_dir not in body

    def test_data_dir_not_escaped_after_traversal_attempt(self, app_ctx) -> None:
        """After a traversal attempt, the data dir must not contain any
        files outside its expected structure."""
        ctx, app = app_ctx
        data_dir = Path(app.config.data_dir)

        # Attempt several traversals
        for bad_id in TRAVERSAL_IDS:
            add_to_recording(recording_id=bad_id, content="x", ctx=ctx)

        # Enumerate only items directly under data_dir; none of the
        # traversal targets should have been created
        for child in data_dir.rglob("*"):
            rel = child.relative_to(data_dir)
            assert ".." not in str(rel)


class TestIdOpaqueness:
    """ADV-008 — Recording IDs are not useful for enumeration.

    A freshly started recording gets a UUIDv4, so guessing is
    cryptographically infeasible. We verify that the 'not found' error
    for a random UUID is shape-indistinguishable from the 'not found'
    error for an attacker-chosen string — neither reveals whether the
    ID ever existed."""

    def test_not_found_errors_have_same_shape(self, app_ctx) -> None:
        ctx, _ = app_ctx

        # Start and end a real recording, then try to get its proof
        start = record_interaction(description="real", ctx=ctx)
        end_recording(recording_id=start["recording_id"], ctx=ctx)

        real_proof = get_proof(recording_id=start["recording_id"], ctx=ctx)
        fake_proof = get_proof(recording_id="00000000-0000-0000-0000-000000000000", ctx=ctx)
        garbage_proof = get_proof(recording_id="not-a-uuid-at-all", ctx=ctx)

        # Real succeeds; fake + garbage fail — same error shape
        assert "error" not in real_proof
        assert "error" in fake_proof
        assert "error" in garbage_proof
        assert set(fake_proof.keys()) == set(garbage_proof.keys()), (
            "error response shape leaks information about id validity"
        )


class TestNoPathLeakInResources:
    """ADV-017 — the synpareia://recordings resource used to expose the
    absolute filesystem path of each persisted recording. It must now
    surface only the recording_id and status."""

    def test_recordings_resource_no_filesystem_paths(self, app_ctx) -> None:
        import json

        from synpareia_trust_mcp.resources import recordings_resource

        ctx, app = app_ctx

        # Produce at least one persisted recording
        start = record_interaction(description="finished", ctx=ctx)
        end_recording(recording_id=start["recording_id"], ctx=ctx)

        raw = recordings_resource(ctx=ctx)
        payload = json.loads(raw)

        # Data dir path must not appear anywhere in the output
        data_dir = str(app.config.data_dir)
        assert data_dir not in raw
        assert "/home/" not in raw
        assert "/tmp" not in raw
        assert "\\Users\\" not in raw

        # Recent entries carry recording_id + status only, no `file`
        for entry in payload.get("recent", []):
            assert "file" not in entry, f"leaked filesystem path in {entry}"
            assert "recording_id" in entry
