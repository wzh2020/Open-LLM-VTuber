"""In-process real FastAPI/Starlette WebSocket integration tests.

Production WebSocketHandler and production route code are loaded unchanged.
Only heavy ASR/TTS/LLM/provider dependencies are stubbed; HTTP/WS ASGI stack,
frame decoding, session registry and disconnect cleanup are real.
"""
import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

import numpy as np  # noqa: F401
from fastapi import FastAPI
from fastapi.testclient import TestClient
from loguru import logger

ROOT = Path(__file__).resolve().parents[2] / "src" / "open_llm_vtuber"
PKG = "r0_ws_asgi_integration_pkg"


class Copyable:
    def __init__(self, **attrs):
        vars(self).update(attrs)

    def model_copy(self, deep=False):
        return Copyable(
            **{
                key: value.model_copy(deep=deep)
                if hasattr(value, "model_copy")
                else value
                for key, value in vars(self).items()
            }
        )


class TestServiceContext:
    instances = []

    def __init__(self):
        self.agent_engine = None
        self.closed = False
        self.__class__.instances.append(self)

    async def load_cache(self, **kwargs):
        vars(self).update(kwargs)

    async def init_agent(self, _config, _persona):
        self.agent_engine = object()

    async def close(self):
        self.closed = True


class GroupManager:
    def __init__(self):
        self.client_group_map = {}

    def get_client_group(self, _uid):
        return None

    def get_group_members(self, _uid):
        return []


class MessageHandler:
    def __init__(self):
        self.cleaned = []

    def handle_message(self, _uid, _data):
        pass

    def cleanup_client(self, uid):
        self.cleaned.append(uid)


MESSAGES = MessageHandler()


async def _noop(*_args, **_kwargs):
    return None


def _module(name, **attrs):
    module = types.ModuleType(name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load(path, qualified_name):
    spec = importlib.util.spec_from_file_location(qualified_name, ROOT / path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[qualified_name] = module
    spec.loader.exec_module(module)
    return module


def _install_provider_stubs():
    _module(PKG).__path__ = []
    _module(f"{PKG}.service_context", ServiceContext=TestServiceContext)
    _module(
        f"{PKG}.chat_group",
        ChatGroupManager=GroupManager,
        handle_group_operation=_noop,
        handle_client_disconnect=_noop,
        broadcast_to_group=_noop,
    )
    _module(f"{PKG}.message_handler", message_handler=MESSAGES)
    _module(f"{PKG}.utils").__path__ = []
    _module(
        f"{PKG}.utils.stream_audio",
        prepare_audio_payload=lambda **kwargs: kwargs,
    )
    _module(
        f"{PKG}.chat_history_manager",
        create_new_history=lambda *_args, **_kwargs: "history",
        get_history=lambda *_args, **_kwargs: [],
        delete_history=lambda *_args, **_kwargs: True,
        get_history_list=lambda *_args, **_kwargs: [],
    )
    _module(f"{PKG}.config_manager").__path__ = []
    _module(
        f"{PKG}.config_manager.utils",
        scan_config_alts_directory=lambda *_args, **_kwargs: [],
        scan_bg_directory=list,
    )
    _module(f"{PKG}.conversations").__path__ = []
    _module(
        f"{PKG}.conversations.conversation_handler",
        handle_conversation_trigger=_noop,
        handle_group_interrupt=_noop,
        handle_individual_interrupt=_noop,
    )
    _module(f"{PKG}.proxy_handler", ProxyHandler=object)


_install_provider_stubs()
HANDLER = _load("websocket_handler.py", f"{PKG}.websocket_handler")
ROUTES = _load("routes.py", f"{PKG}.routes")


def _default_context():
    character = Copyable(
        agent_config=object(),
        persona_prompt="stable persona",
        conf_name="test-character",
        conf_uid="integration-character",
    )
    return Copyable(
        config=Copyable(),
        system_config=Copyable(),
        character_config=character,
        live2d_model=Copyable(model_info={"name": "fixture"}),
        asr_engine=object(),
        tts_engine=object(),
        vad_engine=object(),
        agent_engine=object(),
        translate_engine=None,
        mcp_server_registery=None,
        tool_adapter=None,
    )


class ActualASGIWebSocketTest(unittest.TestCase):
    def setUp(self):
        TestServiceContext.instances.clear()
        MESSAGES.cleaned.clear()
        self.handler = HANDLER.WebSocketHandler(_default_context())
        self.app = FastAPI()
        self.app.include_router(
            ROUTES.init_client_ws_route(
                default_context_cache=self.handler.default_context_cache,
                ws_handler=self.handler,
            )
        )

    @staticmethod
    def _handshake(ws):
        messages = [json.loads(ws.receive_text()) for _ in range(5)]
        self_types = [msg["type"] for msg in messages]
        assert self_types == [
            "group-update",
            "full-text",
            "set-model-and-conf",
            "group-update",
            "control",
        ], self_types
        return messages[2]["client_uid"]

    def test_real_websocket_connect_heartbeat_and_disconnect(self):
        with TestClient(self.app) as client:
            with client.websocket_connect("/client-ws") as ws:
                uid = self._handshake(ws)
                self.assertIn(uid, self.handler.client_contexts)
                ws.send_json({"type": "heartbeat"})
                self.assertEqual(ws.receive_json(), {"type": "heartbeat-ack"})
                ws.send_json({"type": "request-init-config"})
                reply = ws.receive_json()
                self.assertEqual(reply["client_uid"], uid)
                self.assertEqual(reply["conf_uid"], "integration-character")
            self.assertNotIn(uid, self.handler.client_contexts)
            self.assertIn(uid, MESSAGES.cleaned)

    def test_overlapping_websocket_sessions_have_isolated_agents(self):
        with TestClient(self.app) as client:
            with client.websocket_connect("/client-ws") as one:
                uid_one = self._handshake(one)
                with client.websocket_connect("/client-ws") as two:
                    uid_two = self._handshake(two)
                    self.assertNotEqual(uid_one, uid_two)
                    self.assertIsNot(
                        self.handler.client_contexts[uid_one].agent_engine,
                        self.handler.client_contexts[uid_two].agent_engine,
                    )
                    two.send_json({"type": "heartbeat"})
                    self.assertEqual(two.receive_json()["type"], "heartbeat-ack")
                one.send_json({"type": "heartbeat"})
                self.assertEqual(one.receive_json()["type"], "heartbeat-ack")
        self.assertEqual(self.handler.client_contexts, {})
        self.assertEqual(self.handler.client_connections, {})
        self.assertTrue(all(ctx.closed for ctx in TestServiceContext.instances))

    def test_reconnect_stress_1000_cycles_has_no_session_registry_growth(self):
        logger.disable(PKG)
        try:
            self._assert_reconnect_stress()
        finally:
            logger.enable(PKG)

    def _assert_reconnect_stress(self):
        with TestClient(self.app) as client:
            for _ in range(1000):
                with client.websocket_connect("/client-ws") as ws:
                    uid = self._handshake(ws)
                    ws.send_json({"type": "heartbeat"})
                    self.assertEqual(ws.receive_json()["type"], "heartbeat-ack")
                self.assertNotIn(uid, self.handler.client_contexts)
                self.assertEqual(self.handler.current_conversation_tasks, {})
                self.assertEqual(self.handler.received_data_buffers, {})

        self.assertEqual(len(TestServiceContext.instances), 1000)
        self.assertTrue(all(ctx.closed for ctx in TestServiceContext.instances))
        self.assertEqual(len(MESSAGES.cleaned), 1000)


if __name__ == "__main__":
    unittest.main()
