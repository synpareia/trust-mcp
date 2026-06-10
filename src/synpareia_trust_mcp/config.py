"""Configuration for the Synpareia Trust Toolkit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# The deployed synpareia services. Both have been public (no access gate)
# since 2026-05-16. A fresh install should find the live network without
# digging up env vars — agents opt OUT of network features rather than
# hand-assembling URLs to opt in (audit D-12b, 2026-06-10).
DEFAULT_NETWORK_URL = "https://synpareia.fly.dev"
DEFAULT_WITNESS_URL = "https://synpareia-witness.fly.dev"

_OPT_OUT_VALUES = {"", "none", "off", "disabled"}


def _url_env(name: str, default: str) -> str | None:
    """Resolve a service-URL env var with a live default and explicit opt-out.

    Unset -> the live default. Set to ''/'none'/'off'/'disabled'
    (case-insensitive) -> None, i.e. the feature is local-only. Any other
    value -> used as-is (self-hosted or staging instances).
    """
    value = os.environ.get(name)
    if value is None:
        return default
    if value.strip().lower() in _OPT_OUT_VALUES:
        return None
    return value.strip()


@dataclass(frozen=True)
class Config:
    """Trust Toolkit configuration, loaded from environment variables."""

    data_dir: Path
    display_name: str | None
    private_key_b64: str | None
    network_url: str | None
    auto_register: bool
    witness_url: str | None
    witness_token: str | None
    moltbook_api_url: str | None
    moltrust_api_key: str | None

    @classmethod
    def load(cls) -> Config:
        return cls(
            data_dir=Path(os.environ.get("SYNPAREIA_DATA_DIR", str(Path.home() / ".synpareia"))),
            display_name=os.environ.get("SYNPAREIA_DISPLAY_NAME"),
            private_key_b64=os.environ.get("SYNPAREIA_PRIVATE_KEY_B64"),
            network_url=_url_env("SYNPAREIA_NETWORK_URL", DEFAULT_NETWORK_URL),
            auto_register=os.environ.get("SYNPAREIA_AUTO_REGISTER", "false").lower() == "true",
            witness_url=_url_env("SYNPAREIA_WITNESS_URL", DEFAULT_WITNESS_URL),
            witness_token=os.environ.get("SYNPAREIA_WITNESS_TOKEN"),
            moltbook_api_url=os.environ.get("SYNPAREIA_MOLTBOOK_API_URL"),
            moltrust_api_key=os.environ.get("SYNPAREIA_MOLTRUST_API_KEY"),
        )
