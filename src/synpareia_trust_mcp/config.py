"""Configuration for the Synpareia Trust Toolkit."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Config:
    """Trust Toolkit configuration, loaded from environment variables."""

    data_dir: Path
    display_name: str | None
    network_url: str | None
    auto_register: bool
    witness_url: str | None
    witness_token: str | None

    @classmethod
    def load(cls) -> Config:
        return cls(
            data_dir=Path(os.environ.get("SYNPAREIA_DATA_DIR", str(Path.home() / ".synpareia"))),
            display_name=os.environ.get("SYNPAREIA_DISPLAY_NAME"),
            network_url=os.environ.get("SYNPAREIA_NETWORK_URL"),
            auto_register=os.environ.get("SYNPAREIA_AUTO_REGISTER", "true").lower() == "true",
            witness_url=os.environ.get("SYNPAREIA_WITNESS_URL"),
            witness_token=os.environ.get("SYNPAREIA_WITNESS_TOKEN"),
        )
