"""R0 shared-provider concurrency contract, without heavyweight model packages."""
import asyncio
import importlib.util
import time
import types
import unittest
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "open_llm_vtuber"
    / "provider_access.py"
)
spec = importlib.util.spec_from_file_location("r0_provider_access", SOURCE)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class StrictProvider:
    def __init__(self):
        self.concurrent = 0
        self.peak = 0
        self.calls = 0
        self.fail = False

    async def _run(self, label):
        self.concurrent += 1
        self.peak = max(self.peak, self.concurrent)
        try:
            if self.concurrent != 1:
                raise AssertionError("stateful model engine entered concurrently")
            await asyncio.sleep(0.002)
            self.calls += 1
            if self.fail:
                raise RuntimeError("provider failure")
            return label
        finally:
            self.concurrent -= 1

    async def async_transcribe_np(self, audio):
        return await self._run(audio)

    async def async_generate_audio(self, text, file_name_no_ext=None):
        return await self._run((text, file_name_no_ext))


class ProviderAccessTest(unittest.IsolatedAsyncioTestCase):
    async def test_shared_asr_calls_are_serialized_between_sessions(self):
        raw = StrictProvider()
        context = types.SimpleNamespace(asr_engine=raw, tts_engine=None, vad_engine=None)
        first = module.serialize_shared_engines(context)
        second = module.serialize_shared_engines(context)
        self.assertIs(first["asr_engine"], second["asr_engine"])
        self.assertIs(first["asr_engine"].original_provider, raw)
        self.assertEqual(first["asr_engine"].owner_scope, "APPLICATION")
        results = await asyncio.gather(
            *(context.asr_engine.async_transcribe_np(str(i)) for i in range(50))
        )
        self.assertEqual(len(set(results)), 50)
        self.assertEqual(raw.calls, 50)
        self.assertEqual(raw.peak, 1)
        self.assertEqual(context.asr_engine.peak_concurrency, 1)

    async def test_tts_serialization_survives_concurrent_requests_and_failures(self):
        raw = StrictProvider()
        wrapper = module.SerializedProvider(raw, "TTS")
        raw.fail = True
        with self.assertRaisesRegex(RuntimeError, "provider failure"):
            await wrapper.async_generate_audio("bad")
        raw.fail = False
        results = await asyncio.gather(
            *(wrapper.async_generate_audio(str(i), file_name_no_ext=str(i)) for i in range(30))
        )
        self.assertEqual(len(results), 30)
        self.assertEqual(raw.peak, 1)
        self.assertEqual(raw.concurrent, 0)

    async def test_cancellation_releases_shared_provider_lock(self):
        started = asyncio.Event()
        release = asyncio.Event()

        class Blocking:
            async def async_transcribe_np(self, audio):
                started.set()
                await release.wait()
                return audio

        wrapper = module.SerializedProvider(Blocking(), "ASR")
        task = asyncio.create_task(wrapper.async_transcribe_np("first"))
        await started.wait()
        task.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await task
        release.set()
        self.assertEqual(
            await asyncio.wait_for(wrapper.async_transcribe_np("second"), 1),
            "second",
        )
        self.assertEqual(wrapper.peak_concurrency, 1)

    async def test_app_owned_shared_providers_close_once(self):
        class Closable:
            def __init__(self):
                self.count = 0

            async def aclose(self):
                self.count += 1

        engine = Closable()
        cache = types.SimpleNamespace(
            asr_engine=engine, tts_engine=engine, vad_engine=None
        )
        wrapped = module.serialize_shared_engines(cache)
        self.assertIsNot(wrapped["asr_engine"], wrapped["tts_engine"])
        await module.close_shared_engines(cache)
        await module.close_shared_engines(cache)
        self.assertEqual(engine.count, 1)

    async def test_bad_shared_engine_does_not_block_another_close(self):
        class Bad:
            async def aclose(self):
                raise RuntimeError("provider close error")

        class Good:
            def __init__(self):
                self.closed = False

            def close(self):
                self.closed = True

        good = Good()
        cache = types.SimpleNamespace(asr_engine=Bad(), tts_engine=good)
        module.serialize_shared_engines(cache)
        with self.assertLogs(module.logger.name, level="ERROR"):
            await module.close_shared_engines(cache)
        self.assertTrue(good.closed)

    def test_sync_vad_not_entered_concurrently_across_threads(self):
        class StrictVAD:
            def __init__(self):
                self.running = False

            def detect_speech(self, _data):
                if self.running:
                    raise AssertionError("VAD accessed concurrently")
                self.running = True
                try:
                    time.sleep(0.001)
                    return True
                finally:
                    self.running = False

        import concurrent.futures

        vad = module.SerializedProvider(StrictVAD(), "VAD")
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            self.assertTrue(all(pool.map(vad.detect_speech, range(25))))
        self.assertEqual(vad.concurrency_policy, "SERIALIZED")


if __name__ == "__main__":
    unittest.main()
