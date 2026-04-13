"""Profile management — creation, persistence, and loading."""

from __future__ import annotations

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

import synpareia


class ProfileManager:
    """Manages the agent's synpareia profile (keypair + DID).

    Creates a new identity on first run and persists it for future sessions.
    """

    def __init__(self, data_dir: Path) -> None:
        self._data_dir = data_dir
        self._profile: synpareia.Profile | None = None

    @property
    def profile(self) -> synpareia.Profile:
        if self._profile is None:
            msg = "Profile not initialized -- call ensure_profile() first"
            raise RuntimeError(msg)
        return self._profile

    def ensure_profile(self) -> synpareia.Profile:
        """Load existing profile or generate a new one."""
        profile_path = self._data_dir / "profile.json"

        if profile_path.exists():
            self._profile = self._load_from_file(profile_path)
        else:
            self._profile = self._generate_and_save(profile_path)

        return self._profile

    def get_profile_data(self) -> dict:
        """Return the profile as a serializable dict (no private key)."""
        return {
            "did": self.profile.id,
            "public_key_b64": base64.b64encode(self.profile.public_key).decode(),
            "has_private_key": self.profile.private_key is not None,
        }

    def _load_from_file(self, path: Path) -> synpareia.Profile:
        data = json.loads(path.read_text())
        private_key = base64.b64decode(data["private_key"])
        return synpareia.from_private_key(private_key)

    def _generate_and_save(self, path: Path) -> synpareia.Profile:
        self._data_dir.mkdir(parents=True, exist_ok=True)
        profile = synpareia.generate()

        data = {
            "did": profile.id,
            "public_key": base64.b64encode(profile.public_key).decode(),
            "private_key": base64.b64encode(profile.private_key).decode(),  # type: ignore[arg-type]  # generate() always provides private_key
            "created_at": datetime.now(UTC).isoformat(),
        }
        path.write_text(json.dumps(data, indent=2))
        path.chmod(0o600)

        return profile
