"""Entry point for the Nexla Doc MCP server."""

from src.server import main, mcp  # noqa: F401 — mcp must be importable for `mcp dev`

if __name__ == "__main__":
    main()
