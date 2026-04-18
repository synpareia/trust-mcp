"""Integration tests — verify the MCP server boots and exposes tools/resources."""

from __future__ import annotations

import asyncio
import os
from unittest.mock import patch


class TestMCPServerSetup:
    """Verify the MCP server imports, registers tools, and boots correctly."""

    def test_server_imports_cleanly(self) -> None:
        """The server module should import without errors."""
        import synpareia_trust_mcp.server  # noqa: F401

    def test_mcp_instance_exists(self) -> None:
        from synpareia_trust_mcp.server import mcp

        assert mcp is not None
        assert mcp.name == "Synpareia Trust Toolkit"

    def test_tools_registered(self) -> None:
        """All expected tools should be registered on the MCP instance."""
        from synpareia_trust_mcp.server import mcp

        tool_manager = mcp._tool_manager
        tool_names = set(tool_manager._tools.keys())

        expected_tools = {
            # Information architecture (Tier 1 & 2)
            "orient",
            "learn",
            # Claims and verification
            "make_claim",
            "verify_claim",
            # Trust evaluation
            "evaluate_agent",
            # Independence proofs
            "prove_independence",
            # Recording
            "record_interaction",
            "add_to_recording",
            "end_recording",
            "get_proof",
            "my_recordings",
            # Witness
            "get_witness_info",
            "request_timestamp_seal",
            "request_state_seal",
            "verify_seal_offline",
            "submit_blind_conclusion",
            "get_blind_conclusion",
        }
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    def test_resources_registered_as_templates(self) -> None:
        """MCP resources with context params are registered as templates."""
        from synpareia_trust_mcp.server import mcp

        resource_manager = mcp._resource_manager
        template_uris = set(resource_manager._templates.keys())

        assert "synpareia://identity" in template_uris
        assert "synpareia://recordings" in template_uris

    def test_instructions_are_tier0(self) -> None:
        """Server instructions should be the Tier 0 entry point text."""
        from synpareia_trust_mcp.server import mcp

        assert mcp.instructions is not None
        assert "orient" in mcp.instructions
        assert "Trust tools" in mcp.instructions

    def test_tool_count(self) -> None:
        """Track the tool count to catch accidental additions/removals."""
        from synpareia_trust_mcp.server import mcp

        tool_count = len(mcp._tool_manager._tools)
        # 2 (orient/learn) + 2 (make_claim/verify_claim) + 1 (evaluate_agent)
        # + 1 (prove_independence) + 5 (recording) + 6 (witness) = 17
        assert tool_count == 17, f"Expected 17 tools, got {tool_count}"


class TestMCPLifespan:
    """Test the lifespan context initialization."""

    def test_lifespan_creates_profile(self, tmp_path: str) -> None:
        """The lifespan should generate a profile in the data dir."""
        from synpareia_trust_mcp.app import AppContext, app_lifespan, mcp

        async def _run() -> None:
            env = {
                "SYNPAREIA_DATA_DIR": str(tmp_path),
                "SYNPAREIA_AUTO_REGISTER": "false",
            }
            with patch.dict(os.environ, env, clear=False):
                async with app_lifespan(mcp) as ctx:
                    assert isinstance(ctx, AppContext)
                    assert ctx.profile_manager.profile is not None
                    assert ctx.profile_manager.profile.id.startswith("did:synpareia:")

        asyncio.run(_run())


class TestEntryPoint:
    """Verify the package entry point is wired correctly."""

    def test_console_script_target_exists(self) -> None:
        """The main() function should exist and be callable."""
        from synpareia_trust_mcp.server import main

        assert callable(main)

    def test_package_metadata(self) -> None:
        """Package metadata should be accessible."""
        import synpareia_trust_mcp

        assert synpareia_trust_mcp.__version__ == "0.2.0"
