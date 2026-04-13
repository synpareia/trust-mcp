"""Entry point for the Synpareia Trust Toolkit MCP server."""

# Importing tools and resources registers them with the MCP server (side-effect)
import synpareia_trust_mcp.resources  # noqa: F401, E402
import synpareia_trust_mcp.tools  # noqa: F401, E402
from synpareia_trust_mcp.app import mcp


def main() -> None:
    """Run the MCP server (stdio transport)."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
