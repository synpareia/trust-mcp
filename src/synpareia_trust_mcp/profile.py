"""Profile management — creation, persistence, and loading."""

from __future__ import annotations

import base64
import contextlib
import json
import os
from datetime import UTC, datetime
from pathlib import Path

import synpareia


class ProfileCorruptError(RuntimeError):
    """Raised when profile.json exists but cannot be parsed/decoded.

    The server startup path catches this and either auto-recovers (moves
    the corrupt file aside and regenerates) or fails with a clean error —
    never a raw Python traceback (ADV-018).
    """


class ProfileManager:
    """Manages the agent's synpareia profile (keypair + DID).

    Identity discovery chain (per trust-capability.md §2c):
    1. Check SYNPAREIA_PRIVATE_KEY_B64 env var (explicit key import)
    2. Check {data_dir}/profile.json (previous run)
    3. Generate new Ed25519 keypair
    """

    def __init__(self, data_dir: Path, private_key_b64: str | None = None) -> None:
        self._data_dir = data_dir
        self._private_key_b64 = private_key_b64
        self._profile: synpareia.Profile | None = None

    @property
    def profile(self) -> synpareia.Profile:
        if self._profile is None:
            msg = "Profile not initialized -- call ensure_profile() first"
            raise RuntimeError(msg)
        return self._profile

    def ensure_profile(self) -> synpareia.Profile:
        """Load existing profile or generate a new one.

        Priority: explicit key env var > persisted profile > generate new.

        If profile.json is corrupt and SYNPAREIA_AUTO_RECOVER_PROFILE=true,
        the corrupt file is moved aside and a fresh keypair is generated.
        Otherwise raises ProfileCorruptError with a clean message.
        """
        profile_path = self._data_dir / "profile.json"

        if self._private_key_b64:
            try:
                private_key = base64.b64decode(self._private_key_b64)
                self._profile = synpareia.from_private_key(private_key)
            except Exception as e:
                msg = (
                    "SYNPAREIA_PRIVATE_KEY_B64 is not a valid base64 Ed25519 "
                    f"key: {type(e).__name__}"
                )
                raise ProfileCorruptError(msg) from e
            self._save_profile(profile_path, self._profile)
        elif profile_path.exists():
            self._profile = self._load_or_recover(profile_path)
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

    def _load_or_recover(self, path: Path) -> synpareia.Profile:
        """Load profile.json, falling back to auto-recovery if requested.

        On corruption: raise ProfileCorruptError unless the operator has
        set SYNPAREIA_AUTO_RECOVER_PROFILE=true, in which case the corrupt
        file is renamed to profile.json.corrupt-<timestamp> and a fresh
        keypair is generated.
        """
        try:
            return self._load_from_file(path)
        except (
            json.JSONDecodeError,
            KeyError,
            TypeError,
            ValueError,
            UnicodeDecodeError,
            OSError,
        ) as e:
            if os.environ.get("SYNPAREIA_AUTO_RECOVER_PROFILE", "").lower() == "true":
                stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
                backup = path.with_name(f"{path.name}.corrupt-{stamp}")
                path.rename(backup)
                return self._generate_and_save(path)
            msg = (
                f"profile.json at {path} is corrupt ({type(e).__name__}). "
                "Restore from backup or set SYNPAREIA_AUTO_RECOVER_PROFILE=true "
                "to regenerate a new keypair."
            )
            raise ProfileCorruptError(msg) from e

    def _load_from_file(self, path: Path) -> synpareia.Profile:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or "private_key" not in data:
            msg = "profile.json missing required 'private_key' field"
            raise KeyError(msg)
        private_key = base64.b64decode(data["private_key"])
        return synpareia.from_private_key(private_key)

    def _save_profile(self, path: Path, profile: synpareia.Profile) -> None:
        """Persist profile atomically with 0o600 permissions.

        Using os.open with O_CREAT|O_TRUNC and mode=0o600 means the file
        never exists with a more permissive mode — closes the TOCTOU race
        that a later chmod() would introduce (ADV-020).
        """
        self._data_dir.mkdir(parents=True, exist_ok=True)
        # Harden the data dir too — private key lives inside it.
        with contextlib.suppress(OSError):
            self._data_dir.chmod(0o700)

        payload = json.dumps(
            {
                "did": profile.id,
                "public_key": base64.b64encode(profile.public_key).decode(),
                "private_key": base64.b64encode(profile.private_key).decode(),  # type: ignore[arg-type]
                "created_at": datetime.now(UTC).isoformat(),
            },
            indent=2,
        ).encode()

        if path.exists():
            path.unlink()
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as f:
            f.write(payload)

    def _generate_and_save(self, path: Path) -> synpareia.Profile:
        profile = synpareia.generate()
        self._save_profile(path, profile)
        return profile
