"""Generic MCP tool discovery and execution boundary."""

import asyncio
from types import SimpleNamespace

import pytest

from backend.services.mcp_tool_gateway import McpToolGateway
from backend.schemas.enums import FailureCode
from backend.services.failure_mapping import OperationalFailure


def test_lists_mcp_tool_schema_and_calls_listed_tool():
    calls = []

    async def operation(url, operation, name=None, arguments=None):
        calls.append((operation, name, arguments))
        if operation == "list_tools":
            return SimpleNamespace(tools=[{
                "name": "lookup", "description": "Look up a card",
                "inputSchema": {"type": "object", "properties": {"term_id": {"type": "string"}}, "required": ["term_id"]},
            }])
        return SimpleNamespace(isError=False, structuredContent={"status": "found"}, content=[])

    gateway = McpToolGateway(mcp_url="http://mcp:8001/mcp", operation_caller=operation)
    tools = asyncio.run(gateway.list_tools())
    result = asyncio.run(gateway.call_tool("lookup", {"term_id": "pose_x"}))

    assert tools == [{
        "name": "lookup", "description": "Look up a card",
        "inputSchema": {"type": "object", "properties": {"term_id": {"type": "string"}}, "required": ["term_id"]},
    }]
    assert result == {"status": "found"}
    assert calls[-1] == ("call_tool", "lookup", {"term_id": "pose_x"})


def test_rejects_unlisted_tool_and_arguments_outside_schema():
    async def operation(url, operation, name=None, arguments=None):
        return SimpleNamespace(tools=[{
            "name": "lookup", "description": "Look up a card",
            "inputSchema": {"type": "object", "properties": {"term_id": {"type": "string"}}, "required": ["term_id"], "additionalProperties": False},
        }])

    gateway = McpToolGateway(mcp_url="http://mcp:8001/mcp", operation_caller=operation)
    asyncio.run(gateway.list_tools())

    with pytest.raises(ValueError, match="not listed"):
        asyncio.run(gateway.call_tool("unknown", {}))
    with pytest.raises(ValueError, match="arguments"):
        asyncio.run(gateway.call_tool("lookup", {"unexpected": "x"}))


def test_rejects_mcp_error_malformed_tool_list_and_missing_url():
    async def broken_call(url, operation, name=None, arguments=None):
        if operation == "list_tools":
            return SimpleNamespace(tools=[{
                "name": "lookup", "description": "Look up a card",
                "inputSchema": {"type": "object", "properties": {}},
            }])
        return SimpleNamespace(isError=True, structuredContent=None, content=[])

    async def malformed_list(url, operation, name=None, arguments=None):
        return SimpleNamespace(tools=[{"name": "lookup", "inputSchema": {"type": "not-a-json-schema-type"}}])

    with pytest.raises(RuntimeError, match="MCP tool call failed"):
        asyncio.run(McpToolGateway(
            mcp_url="http://mcp:8001/mcp", operation_caller=broken_call,
        ).call_tool("lookup", {}))

    with pytest.raises(ValueError, match="tool schema"):
        asyncio.run(McpToolGateway(
            mcp_url="http://mcp:8001/mcp", operation_caller=malformed_list,
        ).list_tools())

    with pytest.raises(OperationalFailure) as error:
        asyncio.run(McpToolGateway(mcp_url="").list_tools())
    assert error.value.failure_code is FailureCode.CONFIGURATION_ERROR
