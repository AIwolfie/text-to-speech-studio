"""Shared sample-accurate dialogue and project take rendering."""
import hashlib
import importlib.metadata
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import wave
from xml.sax.saxutils import unescape

RATE = 24000


def transcode(data, *options):
    executable = shutil.which("ffmpeg")
    if not executable:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe
            executable = get_ffmpeg_exe()
        except ImportError as exc:
            raise RuntimeError("Install the studio requirements or put FFmpeg on PATH.") from exc
    result = subprocess.run([executable, "-hide_banner", "-loglevel", "error", "-i", "pipe:0",
                             *options, "pipe:1"], input=data, capture_output=True, timeout=600)
    if result.returncode:
        raise ValueError("Audio conversion failed: " + result.stderr.decode(errors="replace")[-400:])
    return result.stdout


def pcm(data, rate=RATE):
    if data.startswith(b"RIFF"):
        with wave.open(io.BytesIO(data)) as stream:
            if (stream.getframerate(), stream.getsampwidth(), stream.getnchannels()) == (rate, 2, 1):
                return stream.readframes(stream.getnframes())
    return transcode(data, "-ar", str(rate), "-ac", "1", "-f", "s16le")


def wav(data, rate=RATE):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as stream:
        stream.setparams((1, 2, rate, 0, "NONE", ""))
        stream.writeframes(data)
    return buffer.getvalue()


def echon_paths():
    root = Path(os.environ.get("ECHON_HOME", "D:/project/echon-tts")).expanduser()
    paths = [root / "checkpoints" / name for name in ("echon_tts.safetensors", "echon_best.safetensors")]
    return root, next((path for path in paths if path.is_file()), paths[0])


def model_version(voice):
    if voice.lower().startswith("echon"):
        _, model = echon_paths()
        return str(model.stat().st_mtime_ns) if model.is_file() else "missing"
    try:
        return "edge-" + importlib.metadata.version("edge-tts")
    except importlib.metadata.PackageNotFoundError:
        return "edge-unavailable"


def pronunciation(text, rules, voice):
    """Map spans in substituted speech back to the original caption characters."""
    locale = "en-US" if voice.lower().startswith("echon") else "-".join(voice.split("-")[:2])
    replacements = {r["word"]: r["spoken"] for r in rules if r["word"] and r["spoken"]
                    and r.get("locale", "").lower() in ("", locale.lower(), locale[:2].lower())}
    if not replacements:
        return text, list(range(len(text) + 1))
    words = "|".join(re.escape(k) for k in sorted(replacements, key=len, reverse=True))
    parts, boundaries, pos = [], [0], 0
    for match in re.finditer(r"(?<!\w)(?:" + words + r")(?!\w)", text):
        parts.append(text[pos:match.start()])
        boundaries.extend(range(pos + 1, match.start() + 1))
        spoken = replacements[match.group()]
        parts.append(spoken)
        boundaries.extend(match.start() + round(i * len(match.group()) / len(spoken))
                          for i in range(1, len(spoken) + 1))
        pos = match.end()
    parts.append(text[pos:])
    boundaries.extend(range(pos + 1, len(text) + 1))
    return "".join(parts), boundaries


def phrases(text):
    return [part.strip() for part in re.split(r"(?<=[.!?。！？])\s+|\n+", text) if part.strip()]


async def render_take(engine, line, rules=(), offline=False, sample_rate=RATE):
    voice, original = line.voice, line.text.strip()
    local = voice.lower().startswith("echon")
    if offline and not local:
        raise ValueError("Offline-only projects require an ECHON voice.")
    if not original:
        raise ValueError("Enter text for this clip.")
    if local:
        with engine._echon_lock:
            model = engine._get_echon_engine()
        speed = 1 + int(engine._normalize_tts_param(line.rate, "%")[:-1]) / 100
        if speed <= 0:
            raise ValueError("Speech speed must be positive.")
        samples, cues = bytearray(), []
        for phrase in phrases(original):
            spoken, _ = pronunciation(phrase, rules, voice)
            with engine._echon_lock:
                audio, _ = model.synthesize(spoken, speed=speed)
            start = len(samples) // 2
            samples.extend(pcm(audio, sample_rate))
            cues.append([round(start * 1000 / sample_rate), round(len(samples) * 500 / sample_rate), phrase])
        return bytes(samples), cues

    import aiohttp
    import edge_tts
    spoken, mapping = pronunciation(original, rules, voice)
    stream = edge_tts.Communicate(spoken, voice, rate=engine._normalize_tts_param(line.rate, "%"),
                                  pitch=engine._normalize_tts_param(line.pitch, "Hz"),
                                  volume=engine._normalize_tts_param(line.volume, "%"))
    audio, cues, pos = bytearray(), [], 0
    try:
        async for chunk in stream.stream():
            if chunk["type"] == "audio":
                audio.extend(chunk["data"])
            elif chunk["type"] in ("WordBoundary", "SentenceBoundary"):
                token = unescape(chunk["text"])
                start = spoken.find(token, pos)
                if start < 0:
                    continue
                pos = start + len(token)
                label = original[mapping[start]:mapping[pos]].strip()
                if label:
                    cues.append([chunk["offset"] // 10000, (chunk["offset"] + chunk["duration"]) // 10000, label])
    except (aiohttp.ClientError, edge_tts.exceptions.NoAudioReceived) as exc:
        raise ConnectionError(f"The online voice service could not finish the line: {exc}") from exc
    samples = pcm(bytes(audio))
    duration = round(len(samples) * 500 / RATE)
    if not cues or spoken[pos:].strip(" .,!?"):
        cues = [[0, duration, original]]
    for cue in cues:
        cue[0], cue[1] = min(cue[0], duration), min(cue[1], duration)
    return samples, [cue for cue in cues if cue[1] > cue[0]]


def take_key(line, rules):
    payload = [line.text, line.voice, line.rate, line.pitch, line.volume, rules, model_version(line.voice), 1]
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False).encode()).hexdigest()

