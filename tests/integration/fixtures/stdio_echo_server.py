"""Local MCP server fixture used only by integration tests.

No external network or privileged tools required.
"""
import os
import time

from mcp.server.fastmcp import FastMCP

server = FastMCP("r0-stdio-echo")


@server.tool()
def identity(value: str) -> str:
    """Return the server PID and the supplied value."""
    return f"{os.getpid()}:{value}"


@server.tool()
def delayed_identity(value: str, milliseconds: int) -> str:
    """Sleep briefly to exercise caller cancellation without stopping MCP."""
    time.sleep(milliseconds / 1000)
    return f"{os.getpid()}:{value}"


if __name__ == "__main__":
    server.run(transport="stdio")
