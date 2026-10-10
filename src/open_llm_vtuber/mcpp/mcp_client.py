"""MCP Client for Open-LLM-Vtuber.

A stdio transport and its AnyIO cancel scopes MUST be entered and exited
by the same asyncio task. The per-server worker owns both the connection and
all SDK operations, regardless of which session task requests the tool.
"""

import asyncio
from collections.abc import Callable
from contextlib import AsyncExitStack
from datetime import timedelta
from typing import Any

from loguru import logger
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.types import Tool

from .server_registry import ServerRegistry

DEFAULT_TIMEOUT = timedelta(seconds=30)


class _StdioWorker:
    """Own MCP's AnyIO scopes on one stable asyncio task for their lifetime."""

    def __init__(self, name, server, on_connect):
        self.name = name
        self._server = server
        self._on_connect = on_connect
        self._queue: asyncio.Queue = asyncio.Queue()
        self._ready = asyncio.get_running_loop().create_future()
        self._task = asyncio.create_task(self._run(), name=f"mcp-stdio:{name}")
        self._closing = False

    async def ready(self):
        await self._ready

    async def invoke(self, operation, *args):
        await self.ready()
        if self._closing:
            raise RuntimeError(f"MCP server {self.name} is closing")
        response = asyncio.get_running_loop().create_future()
        self._queue.put_nowait((operation, args, response))
        return await response

    async def close(self):
        if not self._closing:
            self._closing = True
            self._queue.put_nowait(("__close__", (), None))
        # Awaiting the worker is safe: only the worker itself exits the
        # AsyncExitStack and AnyIO cancel scopes, never this caller task.
        await asyncio.gather(self._task, return_exceptions=True)

    async def _run(self):
        server = self._server
        timeout = server.timeout if server.timeout else DEFAULT_TIMEOUT
        parameters = StdioServerParameters(
            command=server.command,
            args=server.args,
            env=server.env,
            cwd=server.cwd,
        )
        try:
            async with AsyncExitStack() as stack:
                read, write = await stack.enter_async_context(stdio_client(parameters))
                session = await stack.enter_async_context(
                    ClientSession(read, write, read_timeout_seconds=timeout)
                )
                await session.initialize()
                self._on_connect(session)
                self._ready.set_result(True)
                while True:
                    operation, args, response = await self._queue.get()
                    if operation == "__close__":
                        break
                    try:
                        if operation == "list_tools":
                            result = await session.list_tools()
                        elif operation == "call_tool":
                            result = await session.call_tool(*args)
                        else:
                            raise ValueError(f"Unsupported MCP operation: {operation}")
                        if not response.done():
                            response.set_result(result)
                    except Exception as exc:
                        if not response.done():
                            response.set_exception(exc)
        except Exception as exc:
            logger.error(f"MCPC: MCP worker {self.name} failed: {exc}")
            if not self._ready.done():
                self._ready.set_exception(exc)
        finally:
            if not self._ready.done():
                self._ready.set_exception(
                    RuntimeError(f"MCP server {self.name} ended before startup")
                )
            while not self._queue.empty():
                _operation, _args, response = self._queue.get_nowait()
                if response is not None and not response.done():
                    response.set_exception(
                        RuntimeError(f"MCP server {self.name} has stopped")
                    )


class MCPClient:
    """Persistent stdio MCP connection per server, with task-safe teardown."""

    def __init__(
        self,
        server_registery: ServerRegistry,
        send_text: Callable | None = None,
        client_uid: str | None = None,
    ) -> None:
        if not isinstance(server_registery, ServerRegistry):
            raise TypeError(
                "MCPC: Invalid server manager. Must be an instance of ServerRegistry."
            )
        self.server_registery = server_registery
        self._send_text = send_text
        self._client_uid = client_uid
        self.active_sessions: dict[str, ClientSession] = {}
        self._list_tools_cache: dict[str, list[Tool]] = {}
        self._workers: dict[str, _StdioWorker] = {}
        self._lock = asyncio.Lock()
        self._closed = False
        logger.info("MCPC: Initialized MCPClient instance.")

    async def _worker(self, server_name: str) -> _StdioWorker:
        async with self._lock:
            if self._closed:
                raise RuntimeError("MCPC: Cannot use a closed MCP client")
            worker = self._workers.get(server_name)
            if worker is None:
                server = self.server_registery.get_server(server_name)
                if server is None:
                    raise ValueError(
                        f"MCPC: Server '{server_name}' not found in available servers."
                    )
                worker = _StdioWorker(
                    server_name,
                    server,
                    lambda session: self.active_sessions.__setitem__(
                        server_name, session
                    ),
                )
                self._workers[server_name] = worker
        try:
            await worker.ready()
        except Exception as exc:
            logger.exception(f"MCPC: Failed to connect to '{server_name}'")
            raise RuntimeError(
                f"MCPC: Failed to connect to server '{server_name}'."
            ) from exc
        return worker

    async def list_tools(self, server_name: str) -> list[Tool]:
        if server_name in self._list_tools_cache:
            return self._list_tools_cache[server_name]
        worker = await self._worker(server_name)
        response = await worker.invoke("list_tools")
        self._list_tools_cache[server_name] = response.tools
        return response.tools

    async def call_tool(
        self, server_name: str, tool_name: str, tool_args: dict[str, Any]
    ) -> dict[str, Any]:
        worker = await self._worker(server_name)
        response = await worker.invoke("call_tool", tool_name, tool_args)
        if response.isError:
            error_text = (
                response.content[0].text
                if response.content and hasattr(response.content[0], "text")
                else "Unknown server error"
            )
            logger.error(f"MCPC: Tool '{tool_name}' failed: {error_text}")
            return {
                "metadata": getattr(response, "metadata", {}),
                "content_items": [{"type": "error", "text": error_text}],
            }

        content_items = []
        for item in response.content or []:
            item_dict = {"type": getattr(item, "type", "text")}
            for attr in ("text", "data", "mimeType", "url", "altText"):
                value = getattr(item, attr, None)
                if value is not None:
                    item_dict[attr] = value
            content_items.append(item_dict)
        if not content_items:
            content_items.append({"type": "text", "text": ""})
        return {
            "metadata": getattr(response, "metadata", {}),
            "content_items": content_items,
        }

    async def aclose(self) -> None:
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            workers = list(self._workers.values())
            self._workers.clear()
        outcomes = await asyncio.gather(
            *(worker.close() for worker in workers), return_exceptions=True
        )
        for outcome in outcomes:
            if isinstance(outcome, BaseException):
                logger.error(f"MCPC: Worker close failed: {outcome}")
        self.active_sessions.clear()
        self._list_tools_cache.clear()
        logger.info("MCPC: Client instance closed.")

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:
        await self.aclose()
        if exc_type:
            logger.error(f"MCPC: Exception in async context: {exc_value}")
