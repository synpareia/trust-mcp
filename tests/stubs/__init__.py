"""In-process ASGI stubs for external services (Moltbook, MolTrust).

These stubs let scenario, fuzzing, adversarial, and agent-flow tests
exercise the real HTTP code path without depending on live third-party
APIs. The pattern mirrors the witness-client tests: a Starlette app is
mounted via httpx.ASGITransport so requests never leave the process.

Stubs are intentionally minimal — enough to drive the provider adapters
in synpareia_trust_mcp.providers. They are NOT a general-purpose mock
library; they encode only the response shapes we actually depend on.
"""
