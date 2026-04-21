"""Tool registration -- importing this module registers all tools with the MCP server."""

from synpareia_trust_mcp.tools import (  # noqa: F401
    commitment,
    identity,
    orient,
    recording,
    trust,
    witness,
)
