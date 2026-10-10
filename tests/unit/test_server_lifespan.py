import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


class _App:
    def __init__(self, **kwargs):
        self.lifespan = kwargs["lifespan"]

    def add_middleware(self, *_args, **_kwargs):
        pass

    def include_router(self, *_args, **_kwargs):
        pass

    def mount(self, *_args, **_kwargs):
        pass


class _StaticFiles:
    def __init__(self, **_kwargs):
        pass


class _ServiceContext:
    def __init__(self):
        self.load_from_config = AsyncMock()
        self.close = AsyncMock()


class _WebSocketHandler:
    def __init__(self, _context):
        self.shutdown = AsyncMock()


def _install_module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_server():
    pkg = "r0_server_lifespan_test_package"
    package = _install_module(pkg)
    package.__path__ = []

    # Isolate the real lifecycle implementation from optional heavyweight
    # voice/model dependencies. A live ASGI integration test remains a later gate.
    _install_module("fastapi", FastAPI=_App)
    for name in ("starlette", "starlette.middleware"):
        _install_module(name).__path__ = []
    _install_module("starlette.middleware.cors", CORSMiddleware=object)
    _install_module("starlette.responses", Response=object)
    _install_module("starlette.staticfiles", StaticFiles=_StaticFiles)

    _install_module(
        f"{pkg}.routes",
        init_client_ws_route=lambda **_kwargs: object(),
        init_webtool_routes=lambda **_kwargs: object(),
        init_proxy_route=lambda **_kwargs: object(),
    )
    _install_module(f"{pkg}.service_context", ServiceContext=_ServiceContext)
    _install_module(f"{pkg}.websocket_handler", WebSocketHandler=_WebSocketHandler)
    _install_module(f"{pkg}.provider_access", serialize_shared_engines=lambda _c: {})
    _install_module(f"{pkg}.config_manager").__path__ = []
    _install_module(f"{pkg}.config_manager.utils", Config=object)

    source = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "open_llm_vtuber"
        / "server.py"
    )
    spec = importlib.util.spec_from_file_location(f"{pkg}.server", source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


SERVER = _load_server()


class ServerLifespanTest(unittest.IsolatedAsyncioTestCase):
    def _server(self, cache=None):
        config = types.SimpleNamespace(
            system_config=types.SimpleNamespace(enable_proxy=False)
        )
        return SERVER.WebSocketServer(config=config, default_context_cache=cache)

    async def test_lifespan_initializes_and_closes_in_same_async_scope(self):
        server = self._server()
        async with server._lifespan(server.app):
            server.default_context_cache.load_from_config.assert_awaited_once()
            self.assertTrue(server._initialized)
            server.ws_handler.shutdown.assert_not_awaited()
        server.ws_handler.shutdown.assert_awaited_once()
        server.default_context_cache.close.assert_awaited_once()

    async def test_initialization_failure_still_drains_owned_resources(self):
        server = self._server()
        server.default_context_cache.load_from_config.side_effect = RuntimeError(
            "simulated setup failure"
        )
        with self.assertRaisesRegex(RuntimeError, "setup failure"):
            async with server._lifespan(server.app):
                self.fail("the ASGI scope should never start")
        server.ws_handler.shutdown.assert_awaited_once()
        server.default_context_cache.close.assert_awaited_once()

    async def test_preinitialized_cache_skips_reinitialization(self):
        cache = _ServiceContext()
        server = self._server(cache=cache)
        async with server._lifespan(server.app):
            cache.load_from_config.assert_not_awaited()
        cache.close.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
