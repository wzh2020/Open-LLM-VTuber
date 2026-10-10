"""Real mixed ASGI/MCP stress probe with process-level resource snapshots.

Runs a genuine MCP SDK child process while real Starlette WebSocket sessions
connect through production routing code. Heavy provider models are fixtures.
Linux runner: checks active session state, subprocess exit, RSS/FD recovery.
"""
import asyncio
import gc
import os
import unittest

from fastapi.testclient import TestClient
from loguru import logger

from test_mcp_stdio import MCPClient, _await_exit, _registry
from test_ws_asgi import ActualASGIWebSocketTest, MESSAGES, PKG


def _rss():
    with open("/proc/self/statm", encoding="utf-8") as handle:
        pages = int(handle.readline().split()[1])
    return pages * os.sysconf("SC_PAGE_SIZE")


def _fd_count():
    return len(os.listdir("/proc/self/fd"))


def _drive_websockets():
    fixture = ActualASGIWebSocketTest(methodName="test_real_websocket_connect_heartbeat_and_disconnect")
    fixture.setUp()
    logger.disable(PKG)
    try:
        with TestClient(fixture.app) as client:
            for _ in range(120):
                with client.websocket_connect("/client-ws") as websocket:
                    uid = fixture._handshake(websocket)
                    websocket.send_json({"type": "heartbeat"})
                    assert websocket.receive_json()["type"] == "heartbeat-ack"
                assert uid not in fixture.handler.client_contexts
        assert not fixture.handler.client_contexts
        assert not fixture.handler.client_connections
        assert not fixture.handler.current_conversation_tasks
        assert not fixture.handler.received_data_buffers
        assert len(MESSAGES.cleaned) == 120
    finally:
        logger.enable(PKG)


@unittest.skipUnless(os.path.exists("/proc/self/statm"), "Linux-specific RSS/FD probe")
class MixedTransportStressTest(unittest.IsolatedAsyncioTestCase):
    async def test_mixed_reconnect_and_real_stdio_subprocess_leave_no_residuals(self):
        gc.collect()
        before_fd = _fd_count()
        before_rss = _rss()
        worker = asyncio.create_task(asyncio.to_thread(_drive_websockets))
        pids = []
        try:
            for index in range(6):
                client = MCPClient(_registry())
                try:
                    result = await asyncio.wait_for(
                        client.call_tool(
                            "fixture", "identity", {"value": str(index)}
                        ),
                        timeout=15,
                    )
                    pid_text, value = result["content_items"][0]["text"].split(":", 1)
                    self.assertEqual(value, str(index))
                    pids.append(int(pid_text))
                finally:
                    await client.aclose()
            await asyncio.wait_for(worker, timeout=45)
        finally:
            if not worker.done():
                worker.cancel()
            await asyncio.gather(worker, return_exceptions=True)

        for pid in pids:
            await _await_exit(pid)
        await asyncio.sleep(0.2)
        gc.collect()
        end_fd = _fd_count()
        end_rss = _rss()
        rss_growth_mib = (end_rss - before_rss) / (1024 * 1024)

        # Large headroom: checks gross leaks only, not a 24-hour stability claim.
        self.assertLessEqual(end_fd - before_fd, 16)
        self.assertLessEqual(rss_growth_mib, 96)
        self.assertEqual(len(pids), 6)
        self.assertEqual(len(set(pids)), 6)
        print(
            "R0_MIXED_STRESS "
            f"ws_cycles=120 mcp_children=6 "
            f"rss_growth_mib={rss_growth_mib:.1f} "
            f"fd_delta={end_fd-before_fd}"
        )


if __name__ == "__main__":
    unittest.main()
