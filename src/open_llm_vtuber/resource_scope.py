"""Session-owned resource registry with idempotent async teardown.

Only register resources created and owned by the current runtime scope.
Shared provider instances must be managed by the owning application scope.
"""

import asyncio
import inspect
import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


class AsyncResourceScope:
    """Owns cleanup callbacks in reverse acquisition order.

    Callbacks are registered immediately after resource acquisition. Each callback
    is invoked at most once. One failing closer does not prevent later closers.
    """

    def __init__(self) -> None:
        self._callbacks: list[tuple[str, Callable[[], Any]]] = []
        self._owned: set[int] = set()
        self._close_lock = asyncio.Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        return self._closed

    def register(self, name: str, closer: Callable[[], Any]) -> None:
        if self._closed:
            raise RuntimeError("Cannot register a resource after scope closure")
        self._callbacks.append((name, closer))

    def track(self, resource: Any, *, name: str, method: str = "aclose") -> Any:
        """Register a concrete owned object; never register shared engines here."""
        if self._closed:
            raise RuntimeError("Cannot track a resource after scope closure")
        if id(resource) not in self._owned:
            closer = getattr(resource, method)
            self.register(name, closer)
            self._owned.add(id(resource))
        return resource

    async def aclose(self) -> None:
        async with self._close_lock:
            if self._closed:
                return
            self._closed = True
            callbacks = self._callbacks
            self._callbacks = []
            self._owned.clear()
            for name, closer in reversed(callbacks):
                try:
                    result = closer()
                    if inspect.isawaitable(result):
                        await result
                except Exception:
                    logger.exception("Failed to close owned resource: %s", name)
