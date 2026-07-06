"""Lifecycle tests — install → setup → use → reinstall → persistence.

Per the testing strategy, the full lifecycle is a separate class of
test from unit/integration. It exercises the *operational* contract:
- Zero env vars: everything still boots.
- First run: profile generated with the right mode.
- Subsequent runs: same DID.
- Data dir override (SYNPAREIA_DATA_DIR) respected.
- Config reload picks up new env vars.
- No stdout pollution (MCP protocol is stdin/stdout, stray prints break the client).

`pip install` and real subprocess-based reinstall are deferred — they
require a clean venv per invocation which is slow and flaky in CI.
Those are covered by the agent-flow harness (Phase 5) which spawns an
external agent against a real install.
"""

from __future__ import annotations

import base64
import contextlib
import io
import json
import os
import stat
from pathlib import Path

import synpareia

from synpareia_trust_mcp.config import DEFAULT_NETWORK_URL, DEFAULT_WITNESS_URL, Config
from synpareia_trust_mcp.conversations import ConversationManager
from synpareia_trust_mcp.profile import ProfileManager


@contextlib.contextmanager
def _clean_env(**overrides: str | None):
    """Temporarily replace SYNPAREIA_* env vars with the given mapping.

    None values unset the variable. Restores the original environment
    when the block exits.
    """
    keys = [k for k in os.environ if k.startswith("SYNPAREIA_")] + list(overrides.keys())
    saved = {k: os.environ.get(k) for k in keys}
    try:
        # Unset all SYNPAREIA_* first
        for k in list(os.environ):
            if k.startswith("SYNPAREIA_"):
                del os.environ[k]
        # Apply the overrides
        for k, v in overrides.items():
            if v is not None:
                os.environ[k] = v
        yield
    finally:
        for k, v in saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


class TestFreshInstall:
    def test_zero_env_load_does_not_raise(self, tmp_path: Path) -> None:
        with _clean_env(SYNPAREIA_DATA_DIR=str(tmp_path / "data")):
            config = Config.load()
            # Live-by-default since 0.6 (audit D-12b): zero env points the
            # service URLs at the deployed network; everything else stays off.
            assert config.witness_url == DEFAULT_WITNESS_URL
            assert config.network_url == DEFAULT_NETWORK_URL
            assert config.moltbook_api_url is None
            assert config.moltrust_api_key is None

    def test_data_dir_override_respected(self, tmp_path: Path) -> None:
        target = tmp_path / "custom-dir"
        with _clean_env(SYNPAREIA_DATA_DIR=str(target)):
            config = Config.load()
        assert config.data_dir == target

    def test_first_run_creates_profile_with_0600(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        with _clean_env(SYNPAREIA_DATA_DIR=str(data_dir)):
            pm = ProfileManager(data_dir)
            pm.ensure_profile()

        profile_path = data_dir / "profile.json"
        assert profile_path.is_file()
        perms = stat.S_IMODE(profile_path.stat().st_mode)
        assert perms == 0o600, f"profile.json must be mode 0600, got {oct(perms)}"

    def test_first_run_generates_valid_keypair(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        pm = ProfileManager(data_dir)
        pm.ensure_profile()
        # Must have a DID and a usable Ed25519 keypair
        assert pm.profile.id.startswith("did:synpareia:")
        assert len(pm.profile.public_key) == 32
        # Keypair actually works for signing
        sig = synpareia.sign(pm.profile.private_key, b"test message")
        assert synpareia.verify(pm.profile.public_key, b"test message", sig)


class TestIdentityPersistence:
    def test_same_did_across_restarts(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"

        pm1 = ProfileManager(data_dir)
        pm1.ensure_profile()
        first_did = pm1.profile.id

        # Simulate restart — new instance, same dir
        pm2 = ProfileManager(data_dir)
        pm2.ensure_profile()

        assert pm2.profile.id == first_did

    def test_explicit_key_override_creates_matching_did(self, tmp_path: Path) -> None:
        """SYNPAREIA_PRIVATE_KEY_B64 must create a profile whose DID
        matches the provided key — even if a previous profile existed."""
        data_dir = tmp_path / "data"

        existing = synpareia.generate()
        key_b64 = base64.b64encode(existing.private_key).decode()

        pm = ProfileManager(data_dir, private_key_b64=key_b64)
        pm.ensure_profile()
        assert pm.profile.id == existing.id

    def test_conversations_persist_to_disk(self, tmp_path: Path) -> None:
        """End a recording, simulate restart, confirm the proof is still
        retrievable via the new manager."""
        data_dir = tmp_path / "data"
        pm1 = ProfileManager(data_dir)
        pm1.ensure_profile()
        cm1 = ConversationManager(pm1, data_dir)

        conv = cm1.start("persistent recording")
        rid = conv.conversation_id
        cm1.add_message(rid, "hello")
        cm1.end(rid)

        # Simulate restart
        pm2 = ProfileManager(data_dir)
        pm2.ensure_profile()
        cm2 = ConversationManager(pm2, data_dir)

        export = cm2.export(rid)
        assert export["chain_id"] == conv.chain.id


class TestConfigActivation:
    def test_setting_witness_url_shows_in_config(self, tmp_path: Path) -> None:
        with _clean_env(
            SYNPAREIA_DATA_DIR=str(tmp_path),
            SYNPAREIA_WITNESS_URL="https://witness.example.com",
        ):
            config = Config.load()
        assert config.witness_url == "https://witness.example.com"

    def test_setting_network_url_shows_in_config(self, tmp_path: Path) -> None:
        with _clean_env(
            SYNPAREIA_DATA_DIR=str(tmp_path),
            SYNPAREIA_NETWORK_URL="https://network.example.com",
        ):
            config = Config.load()
        assert config.network_url == "https://network.example.com"

    def test_all_provider_env_vars_wire_through(self, tmp_path: Path) -> None:
        with _clean_env(
            SYNPAREIA_DATA_DIR=str(tmp_path),
            SYNPAREIA_WITNESS_URL="https://witness",
            SYNPAREIA_WITNESS_TOKEN="tok",
            SYNPAREIA_NETWORK_URL="https://network",
            SYNPAREIA_AUTO_REGISTER="true",
            SYNPAREIA_DISPLAY_NAME="Alice",
            SYNPAREIA_MOLTBOOK_API_URL="https://mb",
            SYNPAREIA_MOLTRUST_API_KEY="mk",
        ):
            config = Config.load()

        assert config.witness_url == "https://witness"
        assert config.witness_token == "tok"
        assert config.network_url == "https://network"
        assert config.auto_register is True
        assert config.display_name == "Alice"
        assert config.moltbook_api_url == "https://mb"
        assert config.moltrust_api_key == "mk"

    def test_auto_register_parsing_is_strict(self, tmp_path: Path) -> None:
        """Only "true" (case-insensitive) should flip auto_register on."""
        for value, expected in [
            ("true", True),
            ("TRUE", True),
            ("false", False),
            ("1", False),
            ("yes", False),
        ]:
            with _clean_env(
                SYNPAREIA_DATA_DIR=str(tmp_path),
                SYNPAREIA_AUTO_REGISTER=value,
            ):
                assert Config.load().auto_register is expected


class TestNoStdoutPollution:
    """The MCP protocol uses stdout for JSON-RPC — stray prints corrupt
    the stream and break the client. This suite runs the lifecycle
    operations with captured stdout and asserts nothing leaked."""

    def test_config_load_is_silent(self) -> None:
        with _clean_env():
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                Config.load()
        assert buf.getvalue() == "", f"stray stdout: {buf.getvalue()!r}"

    def test_profile_bootstrap_is_silent(self, tmp_path: Path) -> None:
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            pm = ProfileManager(tmp_path / "data")
            pm.ensure_profile()
        assert buf.getvalue() == "", f"stray stdout: {buf.getvalue()!r}"

    def test_conversation_lifecycle_is_silent(self, tmp_path: Path) -> None:
        pm = ProfileManager(tmp_path / "data")
        pm.ensure_profile()
        cm = ConversationManager(pm, tmp_path / "data")

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            conv = cm.start("silent")
            cm.add_message(conv.conversation_id, "m")
            cm.end(conv.conversation_id)
            cm.export(conv.conversation_id)
        assert buf.getvalue() == "", f"stray stdout: {buf.getvalue()!r}"


class TestFirstRunDisclosure:
    """The GDPR §6 first-run disclosure MUST go to stderr, never stdout —
    stdout is the stdio-MCP JSON-RPC channel and a stray write there breaks
    every host. (Publish-gate close-read M1 / coverage G1 / pentest INFO-1.)"""

    def test_disclosure_goes_to_stderr_not_stdout(self, tmp_path: Path, capsys) -> None:
        from synpareia_trust_mcp.app import _emit_first_run_disclosure
        from synpareia_trust_mcp.config import Config

        did = "did:synpareia:testdisclosure"
        cfg = Config(
            data_dir=tmp_path / "data",
            display_name="t",
            private_key_b64=None,
            network_url=None,
            auto_register=False,
            witness_url=None,
            witness_token=None,
            moltbook_api_url=None,
            moltrust_api_key=None,
        )
        _emit_first_run_disclosure(cfg, did)
        captured = capsys.readouterr()
        # Load-bearing: nothing on the JSON-RPC channel.
        assert captured.out == "", f"disclosure leaked to stdout: {captured.out!r}"
        # Content lands on stderr: DID, path, and the 'nothing sent' assurance.
        assert did in captured.err
        assert "profile.json" in captured.err
        assert "nothing has been sent" in captured.err

    def test_disclosure_only_fires_on_fresh_mint(self, tmp_path: Path, capsys) -> None:
        # A fresh mint sets newly_generated True; a reload leaves it False and
        # the lifespan branch (if newly_generated: emit) must stay silent.
        from synpareia_trust_mcp.profile import ProfileManager

        data_dir = tmp_path / "data"
        first = ProfileManager(data_dir)
        first.ensure_profile()
        assert first.newly_generated is True
        capsys.readouterr()  # clear
        reloaded = ProfileManager(data_dir)
        reloaded.ensure_profile()
        assert reloaded.newly_generated is False  # so the emit branch is skipped


class TestPersistedProfileShape:
    """Guard against profile.json schema drift."""

    def test_profile_json_shape(self, tmp_path: Path) -> None:
        data_dir = tmp_path / "data"
        pm = ProfileManager(data_dir)
        pm.ensure_profile()

        data = json.loads((data_dir / "profile.json").read_text())
        for field in ("did", "public_key", "private_key", "created_at"):
            assert field in data, f"profile.json missing {field}"

        # public/private are base64 — make sure they decode to the right lengths
        assert len(base64.b64decode(data["public_key"])) == 32
        assert len(base64.b64decode(data["private_key"])) >= 32
