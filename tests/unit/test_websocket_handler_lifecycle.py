import importlib.util
import sys
import types
import unittest
from pathlib import Path
from unittest.mock import AsyncMock


class _Logger:
    def __getattr__(self, _name):
        return lambda *args, **kwargs: None


class _FakeArray(list):
    pass


class _ChatGroupManager:
    def __init__(self):
        self.client_group_map = {}

    def get_client_group(self, _client_uid):
        return None

    def get_group_members(self, _client_uid):
        return []


class _MessageHandler:
    def __init__(self):
        self.cleaned = []

    def handle_message(self, *_args, **_kwargs):
        return None

    def cleanup_client(self, client_uid):
        self.cleaned.append(client_uid)

    async def wait_for_response(self, *_args, **_kwargs):
        return None


MESSAGE_HANDLER = _MessageHandler()


class _Copyable:
    def __init__(self, **values):
        self.__dict__.update(values)

    def model_copy(self, deep=False):
        copied = {
            key: value.model_copy(deep=deep) if hasattr(value, "model_copy") else value
            for key, value in self.__dict__.items()
        }
        return _Copyable(**copied)


class _SessionContext:
    instances = []

    def __init__(self):
        self.loaded_kwargs = None
        self.agent_engine = None
        self.closed = False
        self.__class__.instances.append(self)

    async def load_cache(self, **kwargs):
        self.loaded_kwargs = kwargs
        self.config = kwargs["config"]
        self.system_config = kwargs["system_config"]
        self.character_config = kwargs["character_config"]
        self.live2d_model = kwargs["live2d_model"]
        self.asr_engine = kwargs["asr_engine"]
        self.tts_engine = kwargs["tts_engine"]
        self.vad_engine = kwargs["vad_engine"]
        self.agent_engine = kwargs["agent_engine"]
        self.translate_engine = kwargs["translate_engine"]

    async def init_agent(self, agent_config, persona_prompt):
        self.initialized_with = (agent_config, persona_prompt)
        self.agent_engine = object()

    async def close(self):
        self.closed = True


async def _noop_async(*_args, **_kwargs):
    return None


def _install_module(name, **attributes):
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    sys.modules[name] = module
    return module


def _load_websocket_handler_module():
    package = types.ModuleType("open_llm_vtuber")
    package.__path__ = []
    sys.modules["open_llm_vtuber"] = package

    _install_module(
        "fastapi",
        WebSocket=object,
        WebSocketDisconnect=type("WebSocketDisconnect", (Exception,), {}),
    )
    _install_module(
        "numpy",
        ndarray=_FakeArray,
        float32=float,
        int16=int,
        array=lambda values=None, dtype=None: _FakeArray(values or []),
        append=lambda current, new: _FakeArray([*current, *new]),
        frombuffer=lambda *_args, **_kwargs: _FakeArray(),
    )
    _install_module("loguru", logger=_Logger())
    _install_module(
        "open_llm_vtuber.service_context", ServiceContext=_SessionContext
    )
    _install_module(
        "open_llm_vtuber.chat_group",
        ChatGroupManager=_ChatGroupManager,
        handle_group_operation=_noop_async,
        handle_client_disconnect=_noop_async,
        broadcast_to_group=_noop_async,
    )
    _install_module(
        "open_llm_vtuber.message_handler", message_handler=MESSAGE_HANDLER
    )

    utils_package = types.ModuleType("open_llm_vtuber.utils")
    utils_package.__path__ = []
    sys.modules["open_llm_vtuber.utils"] = utils_package
    _install_module(
        "open_llm_vtuber.utils.stream_audio",
        prepare_audio_payload=lambda **kwargs: kwargs,
    )
    _install_module(
        "open_llm_vtuber.chat_history_manager",
        create_new_history=lambda *_args, **_kwargs: "history",
        get_history=lambda *_args, **_kwargs: [],
        delete_history=lambda *_args, **_kwargs: True,
        get_history_list=lambda *_args, **_kwargs: [],
    )

    config_package = types.ModuleType("open_llm_vtuber.config_manager")
    config_package.__path__ = []
    sys.modules["open_llm_vtuber.config_manager"] = config_package
    _install_module(
        "open_llm_vtuber.config_manager.utils",
        scan_config_alts_directory=lambda *_args, **_kwargs: [],
        scan_bg_directory=lambda: [],
    )

    conversations_package = types.ModuleType("open_llm_vtuber.conversations")
    conversations_package.__path__ = []
    sys.modules["open_llm_vtuber.conversations"] = conversations_package
    _install_module(
        "open_llm_vtuber.conversations.conversation_handler",
        handle_conversation_trigger=_noop_async,
        handle_group_interrupt=_noop_async,
        handle_individual_interrupt=_noop_async,
    )

    source_path = (
        Path(__file__).resolve().parents[2]
        / "src"
        / "open_llm_vtuber"
        / "websocket_handler.py"
    )
    spec = importlib.util.spec_from_file_location(
        "open_llm_vtuber.websocket_handler", source_path
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


MODULE = _load_websocket_handler_module()


class _FakeTask:
    def __init__(self):
        self.cancelled = False

    def done(self):
        return False

    def cancel(self):
        self.cancelled = True


class WebSocketHandlerLifecycleTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        _SessionContext.instances.clear()
        MESSAGE_HANDLER.cleaned.clear()

        character_config = _Copyable(
            agent_config=object(),
            persona_prompt="persona",
        )
        self.default_context = _Copyable(
            config=_Copyable(),
            system_config=_Copyable(),
            character_config=character_config,
            live2d_model=object(),
            asr_engine=object(),
            tts_engine=object(),
            vad_engine=object(),
            agent_engine=object(),
            translate_engine=object(),
            mcp_server_registery=object(),
            tool_adapter=object(),
        )
        self.handler = MODULE.WebSocketHandler(self.default_context)

    async def test_each_client_receives_a_distinct_agent(self):
        first = await self.handler._init_service_context(AsyncMock(), "client-a")
        second = await self.handler._init_service_context(AsyncMock(), "client-b")

        self.assertIsNot(first, second)
        self.assertIsNot(first.agent_engine, second.agent_engine)
        self.assertIsNot(first.agent_engine, self.default_context.agent_engine)
        self.assertIsNot(second.agent_engine, self.default_context.agent_engine)
        self.assertIsNone(first.loaded_kwargs["agent_engine"])
        self.assertIsNone(second.loaded_kwargs["agent_engine"])

    async def test_disconnect_closes_context_and_removes_session_state(self):
        context = _SessionContext()
        task = _FakeTask()
        client_uid = "client-a"
        self.handler.client_contexts[client_uid] = context
        self.handler.client_connections[client_uid] = object()
        self.handler.received_data_buffers[client_uid] = _FakeArray([1.0])
        self.handler.current_conversation_tasks[client_uid] = task

        await self.handler.handle_disconnect(client_uid)

        self.assertTrue(context.closed)
        self.assertTrue(task.cancelled)
        self.assertNotIn(client_uid, self.handler.client_contexts)
        self.assertNotIn(client_uid, self.handler.client_connections)
        self.assertNotIn(client_uid, self.handler.received_data_buffers)
        self.assertNotIn(client_uid, self.handler.current_conversation_tasks)
        self.assertIn(client_uid, MESSAGE_HANDLER.cleaned)

    async def test_failed_connection_cleanup_closes_registered_context(self):
        context = _SessionContext()
        task = _FakeTask()
        client_uid = "failed-client"
        self.handler.client_contexts[client_uid] = context
        self.handler.current_conversation_tasks[client_uid] = task
        self.handler.chat_group_manager.client_group_map[client_uid] = "group"

        await self.handler._cleanup_failed_connection(client_uid)

        self.assertTrue(context.closed)
        self.assertTrue(task.cancelled)
        self.assertNotIn(client_uid, self.handler.client_contexts)
        self.assertNotIn(client_uid, self.handler.current_conversation_tasks)
        self.assertNotIn(client_uid, self.handler.chat_group_manager.client_group_map)
        self.assertIn(client_uid, MESSAGE_HANDLER.cleaned)

    def test_config_file_name_validation_rejects_path_traversal(self):
        self.assertTrue(MODULE._is_safe_config_file_name("conf.yaml"))
        self.assertTrue(MODULE._is_safe_config_file_name("character.yml"))

        unsafe_names = (
            "../character.yaml",
            "..\\character.yaml",
            "/tmp/character.yaml",
            "C:\\temp\\character.yaml",
            "characters/character.yaml",
            "character.json",
        )
        for file_name in unsafe_names:
            with self.subTest(file_name=file_name):
                self.assertFalse(MODULE._is_safe_config_file_name(file_name))

    async def test_config_switch_rejects_unsafe_file_name_before_context_call(self):
        client_uid = "client-a"
        context = types.SimpleNamespace(handle_config_switch=AsyncMock())
        websocket = types.SimpleNamespace(send_text=AsyncMock())
        self.handler.client_contexts[client_uid] = context

        await self.handler._handle_config_switch(
            websocket,
            client_uid,
            {"file": "../outside.yaml"},
        )

        context.handle_config_switch.assert_not_awaited()
        websocket.send_text.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
