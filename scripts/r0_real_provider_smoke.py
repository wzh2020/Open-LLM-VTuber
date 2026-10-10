"""Opt-in real ASR -> Agent/LLM -> TTS smoke using production factories.

Run locally from repository root with actual conf.yaml, model files/provider
credentials and a 16kHz 16-bit PCM WAV sample. NOT executed in keyless CI.
No fake providers are installed and no full transcripts or prompts are logged.
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

import numpy as np
import soundfile as sf

from src.open_llm_vtuber.agent.input_types import BatchInput, TextData, TextSource
from src.open_llm_vtuber.agent.output_types import AudioOutput, SentenceOutput
from src.open_llm_vtuber.config_manager import read_yaml, validate_config
from src.open_llm_vtuber.service_context import ServiceContext


def _sample(wav_path: Path) -> np.ndarray:
    if not wav_path.is_file():
        raise FileNotFoundError(f"Sample WAV not found: {wav_path}")
    waveform, sample_rate = sf.read(str(wav_path), dtype="float32")
    if sample_rate != 16000:
        raise ValueError("ASR smoke sample must have sample_rate=16000 Hz")
    if waveform.ndim == 2:
        waveform = waveform.mean(axis=1)
    if not waveform.size:
        raise ValueError("ASR sample is empty")
    if len(waveform) > 16000 * 30:
        raise ValueError("Keep ASR smoke sample within 30 seconds")
    return np.asarray(waveform, dtype=np.float32)


async def real_pipeline(args: argparse.Namespace) -> dict:
    config = validate_config(read_yaml(str(args.config)))
    context = ServiceContext()
    times = {}
    started = time.monotonic()

    try:
        # Executes configured production ASR/TTS/LLM factories and their own
        # model/network paths. No mocks and no canned model text are supplied.
        await context.load_from_config(config)
        times["initialization_ms"] = round((time.monotonic() - started) * 1000)
        waveform = _sample(args.wav)

        asr_started = time.monotonic()
        transcript = await context.asr_engine.async_transcribe_np(waveform)
        times["asr_ms"] = round((time.monotonic() - asr_started) * 1000)
        if not isinstance(transcript, str) or not transcript.strip():
            raise AssertionError("Real ASR returned no transcription")

        chat_started = time.monotonic()
        input_data = BatchInput(
            texts=[
                TextData(
                    source=TextSource.INPUT,
                    content=transcript,
                    from_name=context.character_config.human_name,
                )
            ]
        )
        speech_text = ""
        generated = 0
        async for item in context.agent_engine.chat(input_data):
            if isinstance(item, SentenceOutput):
                async for _display_text, tts_text, _actions in item:
                    if tts_text.strip():
                        speech_text = tts_text.strip()
                        generated += 1
                        break
            elif isinstance(item, AudioOutput):
                # Direct speech-output agents bypass TTS; this suite requires
                # the full text-to-speech pipeline and explicitly fails here.
                raise AssertionError("Agent produced direct audio, not TTS text")
            if speech_text:
                break
        times["llm_first_sentence_ms"] = round(
            (time.monotonic() - chat_started) * 1000
        )
        if not speech_text:
            raise AssertionError("No text sentence produced by real Agent/LLM")

        tts_started = time.monotonic()
        output_path = await context.tts_engine.async_generate_audio(
            text=speech_text,
            file_name_no_ext="r0-real-provider-smoke",
        )
        times["tts_first_audio_ms"] = round(
            (time.monotonic() - tts_started) * 1000
        )
        if not output_path:
            raise AssertionError("Real TTS did not return an audio locator")

        return {
            "status": "PASS",
            "environment": "user-supplied real model/provider configuration",
            "asr_model": context.character_config.asr_config.asr_model,
            "tts_model": context.character_config.tts_config.tts_model,
            "agent_choice": context.character_config.agent_config.conversation_agent_choice,
            "transcription_chars": len(transcript),
            "first_sentence_chars": len(speech_text),
            "speech_sentences_observed": generated,
            "audio_locator_present": True,
            "latency": times,
        }
    finally:
        await context.close()


async def _main(args: argparse.Namespace) -> dict:
    return await asyncio.wait_for(real_pipeline(args), timeout=args.timeout)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("conf.yaml"))
    parser.add_argument("--wav", type=Path, required=True, help="16kHz sample")
    parser.add_argument("--timeout", type=float, default=120.0)
    parser.add_argument("--report", type=Path, default=Path("r0-real-smoke-result.json"))
    args = parser.parse_args()
    try:
        result = asyncio.run(_main(args))
    except Exception as exc:
        # Keep secrets/transcripts out of the report.
        result = {"status": "FAIL", "error_type": type(exc).__name__}
        args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
        raise
    args.report.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
