"""Conservative access policy for provider instances shared across sessions.

The wrapper serializes calls to potentially stateful ASR/TTS/VAD providers.
It is not used for per-session Agents or shared MCPClient transports.
"""
import asyncio
import threading
from typing import Any


class SerializedProvider:
    """Adapt a shared provider with a single concurrent-call slot.

    The wrapper does not own or close the underlying engine. Engine teardown
    belongs to the application that allocated the original provider.
    """

    concurrency_policy = "SERIALIZED"
    owner_scope = "APPLICATION"

    def __init__(self, provider: Any, kind: str) -> None:
        self._provider = provider
        self.kind = kind
        self._async_lock = asyncio.Lock()
        self._sync_lock = threading.RLock()
        self._active = 0
        self._peak = 0

    @property
    def original_provider(self) -> Any:
        return self._provider

    @property
    def peak_concurrency(self) -> int:
        return self._peak

    def __getattr__(self, name: str) -> Any:
        return getattr(self._provider, name)

    async def _run_async(self, method: str, *args: Any, **kwargs: Any) -> Any:
        async with self._async_lock:
            self._active += 1
            self._peak = max(self._peak, self._active)
            try:
                return await getattr(self._provider, method)(*args, **kwargs)
            finally:
                self._active -= 1

    async def async_transcribe_np(self, *args: Any, **kwargs: Any) -> Any:
        return await self._run_async("async_transcribe_np", *args, **kwargs)

    async def async_generate_audio(self, *args: Any, **kwargs: Any) -> Any:
        return await self._run_async("async_generate_audio", *args, **kwargs)

    def _run_sync(self, method: str, *args: Any, **kwargs: Any) -> Any:
        with self._sync_lock:
            return getattr(self._provider, method)(*args, **kwargs)

    def detect_speech(self, *args: Any, **kwargs: Any) -> Any:
        return self._run_sync("detect_speech", *args, **kwargs)

    def transcribe_np(self, *args: Any, **kwargs: Any) -> Any:
        return self._run_sync("transcribe_np", *args, **kwargs)

    def generate_audio(self, *args: Any, **kwargs: Any) -> Any:
        return self._run_sync("generate_audio", *args, **kwargs)


def serialize_shared_engines(default_context: Any) -> dict[str, SerializedProvider]:
    """Wrap each shared default engine exactly once, including supplied caches."""
    guarded: dict[str, SerializedProvider] = {}
    for field, kind in (
        ("asr_engine", "ASR"),
        ("tts_engine", "TTS"),
        ("vad_engine", "VAD"),
    ):
        engine = getattr(default_context, field, None)
        if engine is None:
            continue
        if not isinstance(engine, SerializedProvider):
            engine = SerializedProvider(engine, kind=kind)
            setattr(default_context, field, engine)
        guarded[field] = engine
    return guarded
