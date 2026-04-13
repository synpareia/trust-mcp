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

    def test_default_auto_register_is_true(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            config = Config.load()
            assert config.auto_register is True


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


class TestConfigFrozen:
    def test_config_is_immutable(self) -> None:
        config = Config(
            data_dir=Path("/tmp"),
            display_name=None,
            network_url=None,
            auto_register=True,
        )
        import pytest

        with pytest.raises(AttributeError):
            config.data_dir = Path("/other")  # type: ignore[misc]
