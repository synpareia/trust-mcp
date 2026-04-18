"""Tests for configuration loading."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import patch

from synpareia_trust_mcp.config import Config


class TestConfigDefaults:
    def test_default_data_dir_is_home(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.data_dir == Path.home() / ".synpareia"

    def test_default_display_name_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.display_name is None

    def test_default_network_url_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.network_url is None

    def test_default_auto_register_is_false(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.auto_register is False

    def test_default_private_key_b64_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.private_key_b64 is None

    def test_default_moltbook_api_url_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.moltbook_api_url is None

    def test_default_moltrust_api_key_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.moltrust_api_key is None

    def test_default_witness_url_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.witness_url is None

    def test_default_witness_token_is_none(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.witness_token is None


class TestConfigFromEnv:
    def test_custom_data_dir(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_DATA_DIR": "/tmp/custom"}):
            config = Config.load()
            assert config.data_dir == Path("/tmp/custom")

    def test_display_name(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_DISPLAY_NAME": "My Agent"}):
            config = Config.load()
            assert config.display_name == "My Agent"

    def test_network_url(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_NETWORK_URL": "https://api.example.com"}):
            config = Config.load()
            assert config.network_url == "https://api.example.com"

    def test_auto_register_false(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_AUTO_REGISTER": "false"}):
            config = Config.load()
            assert config.auto_register is False

    def test_auto_register_case_insensitive(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_AUTO_REGISTER": "FALSE"}):
            config = Config.load()
            assert config.auto_register is False

    def test_witness_url(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_WITNESS_URL": "https://witness.example.com"}):
            config = Config.load()
            assert config.witness_url == "https://witness.example.com"

    def test_witness_token(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_WITNESS_TOKEN": "secret123"}):
            config = Config.load()
            assert config.witness_token == "secret123"

    def test_private_key_b64(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_PRIVATE_KEY_B64": "dGVzdGtleQ=="}):
            config = Config.load()
            assert config.private_key_b64 == "dGVzdGtleQ=="

    def test_moltbook_api_url(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_MOLTBOOK_API_URL": "https://moltbook.com"}):
            config = Config.load()
            assert config.moltbook_api_url == "https://moltbook.com"

    def test_moltrust_api_key(self) -> None:
        with patch.dict(os.environ, {"SYNPAREIA_MOLTRUST_API_KEY": "mt_key_123"}):
            config = Config.load()
            assert config.moltrust_api_key == "mt_key_123"


class TestConfigFrozen:
    def test_config_is_immutable(self) -> None:
        config = Config(
            data_dir=Path("/tmp"),
            display_name=None,
            private_key_b64=None,
            network_url=None,
            auto_register=True,
            witness_url=None,
            witness_token=None,
            moltbook_api_url=None,
            moltrust_api_key=None,
        )
        import pytest

        with pytest.raises(AttributeError):
            config.data_dir = Path("/other")  # type: ignore[misc]
