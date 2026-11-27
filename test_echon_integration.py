"""Test ECHON TTS Provider Integration inside TTS Studio."""

import os
import shutil
import tempfile
import unittest
import wave
from pathlib import Path

from tts_engine import DEFAULT_VOICE, ECHON_VOICE, TTSStudioEngine


class TestEchonStudioIntegration(unittest.TestCase):
    """Integration test suite for ECHON TTS inside TTS Studio."""

    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(__file__).resolve().parent / ".test_tmp"
        cls.temp_dir.mkdir(parents=True, exist_ok=True)
        # Seed voices cache with sample voices so test is 100% offline
        cache_file = cls.temp_dir / "voices_cache.json"
        import json
        cache_file.write_text(json.dumps([
            {"Name": "Microsoft Server Speech Text to Speech Voice (en-US, ChristopherNeural)", "ShortName": "en-US-ChristopherNeural", "Gender": "Male", "Locale": "en-US", "FriendlyName": "Christopher", "Provider": "Edge TTS"},
            {"Name": "Microsoft Server Speech Text to Speech Voice (en-US, JennyNeural)", "ShortName": "en-US-JennyNeural", "Gender": "Female", "Locale": "en-US", "FriendlyName": "Jenny", "Provider": "Edge TTS"},
        ]), encoding="utf-8")
        cls.engine = TTSStudioEngine(data_dir=str(cls.temp_dir))

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_01_provider_and_voices_listing(self):
        providers = self.engine.get_available_providers()
        self.assertIn("Edge TTS", providers)
        self.assertIn("ECHON", providers)

        voices = self.engine.list_voices_sync()
        echon_voice = next((v for v in voices if v.get("ShortName") == "echon-narrator"), None)
        self.assertIsNotNone(echon_voice, "ECHON Narrator voice not found in engine voice list!")
        self.assertEqual(echon_voice["Provider"], "ECHON")
        self.assertIn("ECHON Narrator", echon_voice["FriendlyName"])

        # Presets check
        presets = self.engine.get_all_presets()
        self.assertIn("echon", presets)
        self.assertEqual(presets["echon"]["voice"], "echon-narrator")

    def test_02_echon_speech_synthesis_and_wav_export(self):
        out_wav = Path(self.temp_dir) / "echon_output.wav"
        text = "Welcome to ECHON TTS, the compact neural speech engine integrated into TTS Studio."
        
        result = self.engine.synthesize_sync(
            text=text,
            voice="echon-narrator",
            output_path=str(out_wav),
            generate_subtitles=True,
        )

        self.assertTrue(out_wav.exists(), "Output WAV file was not created!")
        self.assertEqual(result.voice, "ECHON Narrator")
        self.assertGreater(len(result.audio_bytes), 1000)
        self.assertGreater(result.duration_estimate_sec, 0.5)

        # Subtitle verification
        self.assertIsNotNone(result.srt_subtitles)
        self.assertIsNotNone(result.srt_path)
        self.assertTrue(Path(result.srt_path).exists())
        self.assertTrue(Path(result.vtt_path).exists())

        # Check WAV audio header
        with wave.open(str(out_wav), "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)  # 16-bit PCM
            self.assertEqual(wf.getframerate(), 22050)
            self.assertGreater(wf.getnframes(), 1000)

    def test_03_echon_dialogue_synthesis(self):
        script = (
            "[Narrator | echon-narrator]: Scene one in the recording studio.\n"
            "[Host | echon-narrator | rate=+5%]: Testing offline dialogue generation.\n"
            "[Narrator | echon-narrator]: Confirmed operating with zero cloud latency."
        )
        out_wav = Path(self.temp_dir) / "echon_dialogue.wav"

        result = self.engine.synthesize_dialogue_sync(
            script_text=script,
            output_path=str(out_wav),
            generate_subtitles=True,
        ) if hasattr(self.engine, "synthesize_dialogue_sync") else None

        if result is None:
            import asyncio
            result = asyncio.run(
                self.engine.synthesize_dialogue(
                    script_text=script,
                    output_path=str(out_wav),
                    generate_subtitles=True,
                )
            )

        self.assertTrue(out_wav.exists())
        self.assertGreater(len(result.audio_bytes), 2000)
        self.assertIsNotNone(result.srt_path)
        self.assertTrue(Path(result.srt_path).exists())

        srt_content = Path(result.srt_path).read_text(encoding="utf-8")
        self.assertIn("[Narrator]", srt_content)
        self.assertIn("[Host]", srt_content)

    def test_04_history_recording(self):
        history = self.engine.get_history()
        self.assertGreater(len(history), 0)
        recent = history[-1]
        self.assertEqual(recent.voice, "ECHON Narrator")
        self.assertTrue(Path(recent.audio_path).exists())


if __name__ == "__main__":
    unittest.main()
