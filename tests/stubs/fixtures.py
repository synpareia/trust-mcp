"""Pytest fixtures that mount the external-service stubs into httpx.

Activated via `pytest_plugins = ["tests.stubs.fixtures"]` in the root
conftest. Scenario, fuzz, and adversarial tests can then depend on
`stub_providers` to make every provider call land inside an ASGI stub
in the same process.

The wiring pattern:

1. Build Starlette apps from the stub factories.
2. Map real hostnames → ASGI transports via `httpx.AsyncClient(mounts=...)`.
3. Monkeypatch `synpareia_trust_mcp.providers._make_http_client` to
   return the mounted client. Every provider call in the test process
   is now served in-process.

Known URL contracts (MUST match providers.py):

    moltbook: {moltbook_api_url}/api/v1/agents/{identifier}
    moltrust: https://api.moltrust.ch/v1/agents/{identifier}/reputation
    synpareia: {network_url}/api/v1/agents/{identifier}/reputation

The conventional test URLs used for moltbook and synpareia are
`http://moltbook.test` and `http://synpareia.test`. MolTrust's URL is
hardcoded in providers and cannot be overridden per-call, so the mount
intercepts the real hostname.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from tests.stubs.moltbook import make_moltbook_app
from tests.stubs.moltrust import VALID_API_KEY, make_moltrust_app
from tests.stubs.synpareia_network import make_synpareia_network_app
from tests.stubs.witness import make_witness_app

# Test-only URLs for the providers whose URL IS user-configurable.
# These can be anything — the mount routes them regardless of DNS.
MOLTBOOK_TEST_URL = "http://moltbook.test"
SYNPAREIA_NETWORK_TEST_URL = "http://synpareia.test"
WITNESS_TEST_URL = "http://witness.test"
MOLTRUST_API_KEY = VALID_API_KEY


@pytest.fixture()
def moltbook_app():
    """Default Moltbook stub app. Override fixtures dict by calling
    make_moltbook_app directly in a test-local fixture."""
    return make_moltbook_app()


@pytest.fixture()
def moltrust_app():
    return make_moltrust_app()


@pytest.fixture()
def synpareia_network_app():
    return make_synpareia_network_app()


@pytest.fixture()
def witness_app():
    """In-process witness service. Fresh keypair per test."""
    return make_witness_app()


@pytest.fixture()
def witness_client(witness_app):
    """WitnessClient wired to the in-process witness stub. The client
    hits the stub via httpx.ASGITransport rather than the network. Call
    sites should use this fixture to test flows that require a live
    witness (timestamp_seal, state_seal, offline verification)."""
    from synpareia.witness.client import WitnessClient

    transport = httpx.ASGITransport(app=witness_app)
    http_client = httpx.AsyncClient(
        transport=transport,
        base_url=WITNESS_TEST_URL,
        timeout=10.0,
    )
    client = WitnessClient.__new__(WitnessClient)
    client._base_url = WITNESS_TEST_URL
    client._client = http_client
    return client


@pytest.fixture()
def stub_providers(
    moltbook_app,
    moltrust_app,
    synpareia_network_app,
    monkeypatch,
):
    """Route provider HTTP calls into in-process ASGI stubs.

    Patches providers._make_http_client so every call during the test
    body goes to the stub. Yields the three Starlette apps so a test
    can override them mid-test if needed.
    """
    from synpareia_trust_mcp import providers

    mounts = {
        f"{MOLTBOOK_TEST_URL}": httpx.ASGITransport(app=moltbook_app),
        f"{SYNPAREIA_NETWORK_TEST_URL}": httpx.ASGITransport(app=synpareia_network_app),
        "https://api.moltrust.ch": httpx.ASGITransport(app=moltrust_app),
    }

    def _make_client(timeout: float = 10.0) -> httpx.AsyncClient:
        return httpx.AsyncClient(mounts=mounts, timeout=timeout)

    monkeypatch.setattr(providers, "_make_http_client", _make_client)

    return {
        "moltbook": moltbook_app,
        "moltrust": moltrust_app,
        "synpareia_network": synpareia_network_app,
        "moltbook_url": MOLTBOOK_TEST_URL,
        "synpareia_network_url": SYNPAREIA_NETWORK_TEST_URL,
        "moltrust_api_key": MOLTRUST_API_KEY,
    }


@pytest.fixture()
def config_with_stubs(tmp_path: Path, stub_providers):
    """Config that points every provider URL at the stubs."""
    from synpareia_trust_mcp.config import Config

    return Config(
        data_dir=tmp_path / "synpareia",
        display_name="Test Agent",
        private_key_b64=None,
        network_url=stub_providers["synpareia_network_url"],
        auto_register=False,
        witness_url=None,
        witness_token=None,
        moltbook_api_url=stub_providers["moltbook_url"],
        moltrust_api_key=stub_providers["moltrust_api_key"],
    )
