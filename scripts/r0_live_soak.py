"""R0 opt-in 24-hour live-server soak (real models/config, no provider stubs).

Requires a separately started, already configured Open-LLM-VTuber server.
Tracks its process RSS and open descriptors/handles, replays real WebSocket
connect/heartbeat/disconnect, and writes JSONL evidence. Not run in normal CI.
"""
import argparse
import asyncio
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlsplit

import psutil
import websockets


async def reconnect_once(url: str, timeout: float) -> None:
    async with websockets.connect(
        url, open_timeout=timeout, close_timeout=timeout, max_size=2**20
    ) as ws:
        uid = None
        for _ in range(8):
            raw = await asyncio.wait_for(ws.recv(), timeout)
            message = json.loads(raw)
            if message.get("type") == "set-model-and-conf":
                uid = message.get("client_uid")
            if message.get("type") == "control" and message.get("text") == "start-mic":
                break
        if not uid:
            raise AssertionError("The server did not complete session initialization")
        await ws.send(json.dumps({"type": "heartbeat"}))
        for _ in range(4):
            message = json.loads(await asyncio.wait_for(ws.recv(), timeout))
            if message.get("type") == "heartbeat-ack":
                return
        raise AssertionError("Heartbeat was not acknowledged")


def metrics(pid: int) -> dict:
    process = psutil.Process(pid)
    if not process.is_running() or process.status() == psutil.STATUS_ZOMBIE:
        raise RuntimeError("Server process is not running")
    if hasattr(process, "num_fds"):
        handles = process.num_fds()
    elif hasattr(process, "num_handles"):
        handles = process.num_handles()
    else:
        handles = None
    return {
        "rss_bytes": process.memory_info().rss,
        "open_handles": handles,
        "threads": process.num_threads(),
    }


async def soak(args: argparse.Namespace) -> dict:
    hostname = urlsplit(args.ws_url).hostname
    if hostname not in {"localhost", "127.0.0.1", "::1"} and not args.allow_remote:
        raise ValueError("Remote WS soak requires --allow-remote")
    if args.duration_minutes <= 0:
        raise ValueError("duration-minutes must be positive")

    report = Path(args.report)
    report.parent.mkdir(parents=True, exist_ok=True)
    deadline = time.monotonic() + args.duration_minutes * 60
    total = 0
    errors = 0
    before = metrics(args.server_pid)
    last = before
    max_rss = before["rss_bytes"]

    with report.open("w", encoding="utf-8") as stream:
        while time.monotonic() < deadline:
            for _ in range(args.connections_per_interval):
                try:
                    await reconnect_once(args.ws_url, args.timeout_seconds)
                    total += 1
                except Exception as exc:
                    errors += 1
                    stream.write(
                        json.dumps(
                            {
                                "time": datetime.now(timezone.utc).isoformat(),
                                "event": "connection_error",
                                "error_type": type(exc).__name__,
                            }
                        ) + "\n"
                    )
                    stream.flush()
                    if errors >= args.max_errors:
                        raise RuntimeError("Too many failed WebSocket connections") from exc
            last = metrics(args.server_pid)
            max_rss = max(last["rss_bytes"], max_rss)
            stream.write(
                json.dumps(
                    {
                        "time": datetime.now(timezone.utc).isoformat(),
                        "event": "sample",
                        "total_connections": total,
                        "total_errors": errors,
                        **last,
                    }
                ) + "\n"
            )
            stream.flush()
            await asyncio.sleep(
                min(args.interval_seconds, max(0, deadline - time.monotonic()))
            )

    rss_growth_mib = (last["rss_bytes"] - before["rss_bytes"]) / (1024**2)
    handle_growth = (
        last["open_handles"] - before["open_handles"]
        if last["open_handles"] is not None and before["open_handles"] is not None
        else None
    )
    status = (
        "PASS"
        if errors == 0
        and rss_growth_mib <= args.max_rss_growth_mib
        and (handle_growth is None or handle_growth <= args.max_handle_growth)
        else "FAIL"
    )
    summary = {
        "status": status,
        "test_type": "live-server-websocket-soak",
        "duration_minutes": args.duration_minutes,
        "successful_connections": total,
        "errors": errors,
        "rss_growth_mib": round(rss_growth_mib, 2),
        "peak_rss_mib": round(max_rss / (1024**2), 2),
        "handle_growth": handle_growth,
        "server_pid": args.server_pid,
        "report_jsonl": str(report),
    }
    summary_path = report.with_suffix(".summary.json")
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ws-url", default="ws://127.0.0.1:12393/client-ws")
    parser.add_argument("--server-pid", type=int, required=True)
    parser.add_argument("--duration-minutes", type=float, default=1440)
    parser.add_argument("--interval-seconds", type=float, default=30)
    parser.add_argument("--connections-per-interval", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=15)
    parser.add_argument("--max-rss-growth-mib", type=float, default=128)
    parser.add_argument("--max-handle-growth", type=int, default=32)
    parser.add_argument("--max-errors", type=int, default=1)
    parser.add_argument("--allow-remote", action="store_true")
    parser.add_argument("--report", default="artifacts/r0-live-soak.jsonl")
    args = parser.parse_args()
    result = asyncio.run(soak(args))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    if result["status"] != "PASS":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
