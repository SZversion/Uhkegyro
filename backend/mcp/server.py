"""Compatibility import for the MCP server entrypoint."""
from mcp_server.server import (
    app, create_mcp_app, get_active_term_card, load_catalog_snapshot,
    mcp, search_pinterest_pins, settings,
)
