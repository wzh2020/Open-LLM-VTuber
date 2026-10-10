"""Real MCP stdio transport and subprocess lifecycle tests.

These tests import production MCPClient but provide a minimal registry adapter
to avoid requiring ASR/TTS/LLM providers in the test environment.
"""
import asyncio
import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path
from types import SimpleNamespace

import mcp  # noqa: F401


def _production_mcp_client():
    name = "r0_stdio_transport_test_package"
    package = types.ModuleType(name)
    package.__path__ = []
    sys.modules[name] = package

    class ServerRegistry:
        def __init__(self, server):
            self.server = server

        def get_server(self, server_name):
            return self.server if server_name == "fixture" else None

    registry_module = types.ModuleType(f"{name}.server_registry")
    registry_module.ServerRegistry = ServerRegistry
    sys.modules[registry_module.__name__] = registry_module

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "open_llm_vtuber"
        / "mcpp"
        / "mcp_client.py"
    )
    spec = importlib.util.spec_from_file_location(f"{name}.mcp_client", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.MCPClient, ServerRegistry


MCPClient, ServerRegistry = _production_mcp_client()
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "stdio_echo_server.py"


def _is_alive(pid):
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


async def _await_exit(pid, timeout=4.0):
    elapsed = 0.0
    while elapsed < timeout:
        if not _is_alive(pid):
            return
        await asyncio.sleep(0.05)
        elapsed += 0.05
    raise AssertionError(f"MCP child process {pid} survived client closure")


def _registry(script=FIXTURE):
    child = SimpleNamespace(
        command=sys.executable,
        args=[str(script)],
        cwd=None,
        env=os.environ.copy(),
        timeout=None,
    )
    return ServerRegistry(child)


class RealMCPStdioTest(unittest.IsolatedAsyncioTestCase):
    async def test_two_clients_have_distinct_child_processes_and_exit(self):
        first = MCPClient(_registry())
        second = MCPClient(_registry())
        pids = []
        try:
            tools_a, tools_b = await asyncio.wait_for(
                asyncio.gather(
                    first.list_tools("fixture"),
                    second.list_tools("fixture"),
                ),
                timeout=25,
            )
            self.assertIn("identity", [tool.name for tool in tools_a])
            self.assertIn("identity", [tool.name for tool in tools_b])

            res_a, res_b = await asyncio.wait_for(
                asyncio.gather(
                    first.call_tool("fixture", "identity", {"value": "session-A"}),
                    second.call_tool("fixture", "identity", {"value": "session-B"}),
                ),
                timeout=15,
            )
            value_a = res_a["content_items"][0]["text"]
            value_b = res_b["content_items"][0]["text"]
            pid_a, echoed_a = value_a.split(":", 1)
            pid_b, echoed_b = value_b.split(":", 1)
            pids = [int(pid_a), int(pid_b)]
            self.assertEqual((echoed_a, echoed_b), ("session-A", "session-B"))
            self.assertNotEqual(pid_a, pid_b)
            self.assertIsNot(first.active_sessions, second.active_sessions)
        finally:
            await first.aclose()
            await second.aclose()

        for pid in pids:
            await _await_exit(pid)
        self.assertEqual(first.active_sessions, {})
        self.assertEqual(second.active_sessions, {})
        await first.aclose()
        await second.aclose()

    async def test_cancelled_call_does_not_poison_active_subprocess(self):
        client = MCPClient(_registry())
        pid = None
        try:
            await asyncio.wait_for(client.list_tools("fixture"), timeout=15)
            with self.assertRaises(TimeoutError):
                await asyncio.wait_for(
                    client.call_tool(
                        "fixture",
                        "delayed_identity",
                        {"value": "abandoned", "milliseconds": 150},
                    ),
                    timeout=0.01,
                )
            response = await asyncio.wait_for(
                client.call_tool("fixture", "identity", {"value": "still-alive"}),
                timeout=15,
            )
            pid_str, value = response["content_items"][0]["text"].split(":", 1)
            pid = int(pid_str)
            self.assertEqual(value, "still-alive")
        finally:
            await client.aclose()
        if pid is not None:
            await _await_exit(pid)

    async def test_cancelled_startup_does_not_poison_shared_readiness(self):
        client = MCPClient(_registry())
        pid = None
        try:
            pending = asyncio.create_task(client.list_tools("fixture"))
            await asyncio.sleep(0.01)
            pending.cancel()
            await asyncio.gather(pending, return_exceptions=True)
            tools = await asyncio.wait_for(client.list_tools("fixture"), timeout=15)
            self.assertIn("identity", [tool.name for tool in tools])
            response = await client.call_tool("fixture", "identity", {"value": "ready"})
            pid_str, value = response["content_items"][0]["text"].split(":", 1)
            pid = int(pid_str)
            self.assertEqual(value, "ready")
        finally:
            await client.aclose()
        if pid is not None:
            await _await_exit(pid)

    async def test_eight_successive_real_stdio_sessions_leave_no_child(self):
        pids = []
        for index in range(8):
            client = MCPClient(_registry())
            try:
                result = await asyncio.wait_for(
                    client.call_tool(
                        "fixture", "identity", {"value": str(index)}
                    ),
                    timeout=15,
                )
                pid_str, value = result["content_items"][0]["text"].split(":", 1)
                self.assertEqual(value, str(index))
                pids.append(int(pid_str))
            finally:
                await client.aclose()
        for pid in pids:
            await _await_exit(pid)
        self.assertEqual(len(set(pids)), 8)

    async def test_unavailable_mcp_server_cleans_its_transport(self):
        missing = FIXTURE.with_name("not_a_real_mcp_server.py")
        client = MCPClient(_registry(missing))
        try:
            with self.assertRaises(RuntimeError):
                await asyncio.wait_for(client.list_tools("fixture"), timeout=15)
        finally:
            await client.aclose()
        self.assertEqual(client.active_sessions, {})


if __name__ == "__main__":
    unittest.main()
