import asyncio
import importlib.util
import unittest
from pathlib import Path
from unittest.mock import AsyncMock

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "open_llm_vtuber"
    / "resource_scope.py"
)
spec = importlib.util.spec_from_file_location("r0_resource_scope_test", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
AsyncResourceScope = module.AsyncResourceScope


class ResourceScopeTest(unittest.IsolatedAsyncioTestCase):
    async def test_resources_close_once_in_reverse_acquisition_order(self):
        scope = AsyncResourceScope()
        order = []

        class Resource:
            def __init__(self, label):
                self.label = label

            async def aclose(self):
                order.append(self.label)

        one, two = Resource("first"), Resource("second")
        scope.track(one, name="first")
        scope.track(two, name="second")
        scope.track(one, name="first-again")
        await scope.aclose()
        await scope.aclose()
        self.assertEqual(order, ["second", "first"])
        self.assertTrue(scope.closed)

    async def test_failure_does_not_skip_next_closer(self):
        scope = AsyncResourceScope()
        done = []

        def first():
            done.append("first")

        async def failing():
            done.append("failing")
            raise ValueError("simulated resource error")

        def last():
            done.append("last")

        scope.register("first", first)
        scope.register("failure", failing)
        scope.register("last", last)
        with self.assertLogs(module.logger.name, level="ERROR"):
            await scope.aclose()
        self.assertEqual(done, ["last", "failing", "first"])

    async def test_concurrent_close_only_executes_once(self):
        scope = AsyncResourceScope()
        closer = AsyncMock()
        scope.register("session", closer)
        await asyncio.gather(*(scope.aclose() for _ in range(10)))
        closer.assert_awaited_once()

    async def test_sync_closer_and_late_registration(self):
        scope = AsyncResourceScope()
        done = []
        scope.register("sync", lambda: done.append("closed"))
        await scope.aclose()
        self.assertEqual(done, ["closed"])
        with self.assertRaisesRegex(RuntimeError, "scope closure"):
            scope.register("late", lambda: None)
        with self.assertRaisesRegex(RuntimeError, "scope closure"):
            scope.track(object(), name="late")


if __name__ == "__main__":
    unittest.main()
