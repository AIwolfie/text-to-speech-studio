"""Offline regression tests with real encoded audio and deterministic provider doubles."""
import asyncio
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import wave

import numpy as np

import studio_audio as audio
import studio_project as projects
from tts_engine import DEFAULT_VOICE, TTSStudioEngine


class ProjectTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.engine = TTSStudioEngine(str(self.root))
        samples = np.full(2400, 1500, dtype="<i2").tobytes()
        self.tone = audio.wav(samples)
        self.mp3 = audio.transcode(self.tone, "-f", "mp3")
        self.online_frames = len(audio.pcm(self.mp3)) // 2
        self.spoken = []
        outer = self

        class Local:
            def synthesize(self, text, speed):
                outer.spoken.append(text)
                return outer.tone, .1

        class Online:
            def __init__(self, text, *args, **kwargs):
                self.text = text

            async def stream(self):
                yield {"type":"audio","data":outer.mp3}
                yield {"type":"SentenceBoundary","text":self.text,"offset":0,"duration":1000000}

        self.engine._echon_engine = Local()
        mock = patch("edge_tts.Communicate", Online)
        mock.start()
        self.addCleanup(mock.stop)

    def test_mixed_dialogue_duration_captions_and_codecs(self):
        for suffix in ("wav", "mp3"):
            path = self.root / ("dialogue." + suffix)
            res = asyncio.run(self.engine.synthesize_dialogue(
                "[Alice | echon-narrator]: First. Second.\nBob: Online.", str(path)))
            expected = (4800 + 8400 + self.online_frames) / 24000
            self.assertAlmostEqual(res.duration_estimate_sec, expected, places=2)
            self.assertIn("00:00:00,550", res.srt_subtitles)
            if suffix == "wav":
                with wave.open(str(path)) as stream:
                    self.assertEqual(stream.getnframes(), round(expected*24000))
            else:
                self.assertFalse(res.audio_bytes.startswith(b"RIFF"))
                self.assertTrue(audio.pcm(res.audio_bytes))
        single = self.engine.synthesize_sync("One. Two.", voice="echon-narrator", output_path=str(self.root/"one.wav"), generate_subtitles=True)
        with wave.open(single.audio_path) as stream:
            self.assertEqual(stream.getframerate(), 22050)
        self.assertEqual(single.srt_subtitles.count("-->"), 2)

    def test_portable_revision_mix_and_stems(self):
        rules = [{"word":"SQL","spoken":"sequel","locale":"en"}]
        project = dict(version=1, name="Episode", rules=rules, gains={"Bob":6}, offline=False, job="Ready", lines=[])
        for i,(name,text,voice) in enumerate([("Ada","Use SQL.","echon-narrator"),("Bob","OK.",DEFAULT_VOICE)]):
            line = dict(id=str(i),speaker=name,text=text,voice=voice,pause=.05)
            req = dict(line=line,rules=rules)
            take = projects.render(self.engine,self.root,req)
            self.assertEqual(projects.render(self.engine,self.root,req), take)
            line.update(takes=[take],active=take["key"])
            project["lines"].append(line)
        self.assertEqual(self.spoken, ["Use sequel."])
        self.assertEqual(project["lines"][0]["takes"][0]["cues"][0][2], "Use SQL.")
        buffer = io.BytesIO()
        projects.archive(project,self.root,buffer)
        restored = self.root/"restored"
        loaded = projects.restore(buffer,restored)
        self.assertEqual(project,loaded)
        saved = copy.deepcopy(loaded["lines"][0])
        second = loaded["lines"][1]
        second["text"]="Thanks."
        take=projects.render(self.engine,restored,dict(line=second,rules=rules))
        second.update(active=take["key"],takes=[take])
        self.assertEqual(loaded["lines"][0],saved)
        second["start"]=.05
        second["takes"][0]["cues"][0][2]="Thank you."
        mix=restored/"mix"
        metadata=projects.mix(self.engine,loaded,restored,mix,True)
        self.assertIn("00:00:00,050", (mix/"captions.srt").read_text())
        self.assertIn("Thank you.", (mix/"captions.vtt").read_text())
        def read(name):
            with wave.open(str(mix/name)) as f:
                return np.frombuffer(f.readframes(f.getnframes()),dtype="<i2").astype(int)
        stems=[read(name) for name in metadata["stems"].values()]
        self.assertLessEqual(np.max(np.abs(sum(stems)-read("master.wav"))),1)
        self.assertEqual(len(stems[0]),len(stems[1]))
        self.assertLess(metadata["peak_dbfs"], 0)
        projects.mix(self.engine,loaded,restored,restored/"preview")
        self.assertEqual((mix/"master.wav").read_bytes(),(restored/"preview"/"master.wav").read_bytes())

    def test_offline_policy_precedes_cache_and_online_provider(self):
        line=dict(speaker="A", voice=DEFAULT_VOICE, text="Hello")
        projects.render(self.engine,self.root,dict(line=line))
        with self.assertRaisesRegex(ValueError, "offline"):
            projects.render(self.engine,self.root,dict(line=line,offline=True))

if __name__ == "__main__":
    unittest.main()

