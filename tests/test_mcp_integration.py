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
            "get_my_identity",
            "sign_content",
            "verify_signature",
            "check_agent_trust",
            "verify_identity",
            "seal_commitment",
            "reveal_commitment",
            "start_conversation",
            "add_to_conversation",
            "end_conversation",
            "get_conversation_proof",
            "list_conversations",
        }
        assert expected_tools.issubset(tool_names), f"Missing tools: {expected_tools - tool_names}"

    def test_resources_registered_as_templates(self) -> None:
        """MCP resources with context params are registered as templates."""
        from synpareia_trust_mcp.server import mcp

        resource_manager = mcp._resource_manager
        template_uris = set(resource_manager._templates.keys())

        assert "synpareia://identity" in template_uris
        assert "synpareia://conversations" in template_uris

    def test_instructions_present(self) -> None:
        """Server instructions should be set for agent guidance."""
        from synpareia_trust_mcp.server import mcp

        assert mcp.instructions is not None
        assert "Trust Toolkit" in mcp.instructions
        assert "get_my_identity" in mcp.instructions

    def test_tool_count(self) -> None:
        """Track the tool count to catch accidental additions/removals."""
        from synpareia_trust_mcp.server import mcp

        tool_count = len(mcp._tool_manager._tools)
        assert tool_count == 12, f"Expected 12 tools, got {tool_count}"


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

        assert synpareia_trust_mcp.__version__ == "0.1.0"
