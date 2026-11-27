"""Portable project archives, immutable takes, and block-based timeline mixing."""
import asyncio
import contextlib
import hashlib
import json
import math
from pathlib import Path
import re
import tempfile
import uuid
import wave
from zipfile import ZipFile, ZIP_DEFLATED

import numpy as np

import studio_audio as audio
from tts_engine import DialogueLine


def take_path(root, key):
    if not isinstance(key, str) or not re.fullmatch("[0-9a-f]{64}", key):
        raise ValueError("Invalid take identifier.")
    return root / "takes" / (key + ".wav")


def validate(project):
    if not isinstance(project, dict) or project.get("version") != 1 or not isinstance(project.get("lines"), list):
        raise ValueError("Choose a version 1 TTS Studio project.")
    for key, default in (("name", "Untitled session"), ("rules", []), ("gains", {}), ("job", "Ready")):
        if not isinstance(project.setdefault(key, default), type(default)):
            raise ValueError(f"Invalid project {key}.")
    for rule in project["rules"]:
        if not isinstance(rule, dict) or not all(isinstance(rule.get(k, ""), str) for k in ("word", "spoken", "locale")):
            raise ValueError("Invalid pronunciation rule.")
    seen = set()
    for line in project["lines"]:
        if not all(isinstance(line.get(k), str) for k in ("id", "speaker", "text", "voice")):
            raise ValueError("Invalid project line.")
        if line["id"] in seen:
            raise ValueError("Duplicate line identifier.")
        seen.add(line["id"])
        line.setdefault("takes", [])
        for take in line["takes"]:
            take_path(Path("."), take["key"])
        if line.get("active") and line["active"] not in [t["key"] for t in line.get("takes", [])]:
            raise ValueError("Selected take is missing.")
    return project


def render(engine, root, data):
    fields = data["line"]
    line = DialogueLine(**{k: fields[k] for k in ("speaker", "text", "voice", "rate", "pitch", "volume") if k in fields})
    if data.get("offline") and not line.voice.lower().startswith("echon"):
        raise ValueError("Choose ECHON for this offline-only project.")
    rules = data.get("rules", [])
    signature = audio.take_key(line, rules)
    cache = engine.data_dir / "take-index"
    cache.mkdir(exist_ok=True)
    index = cache / (signature + ".json")
    if index.exists() and not data.get("force"):
        take = json.loads(index.read_text(encoding="utf8"))
        if take_path(root, take["key"]).is_file():
            return take
    samples, cues = asyncio.run(audio.render_take(engine, line, rules, data.get("offline", False)))
    if not samples:
        raise ValueError("The voice returned empty audio.")
    raw = audio.wav(samples)
    key = hashlib.sha256(raw).hexdigest()
    path = take_path(root, key)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix("." + uuid.uuid4().hex + ".tmp")
    tmp.write_bytes(raw)
    tmp.replace(path)
    take = dict(key=key, frames=len(samples)//2, cues=cues, signature=signature)
    engine._atomic_json_write(index, take)
    return take


def take_keys(project):
    return {take["key"] for line in project["lines"] for take in line.get("takes", [])}


def archive(project, root, target):
    validate(project)
    with ZipFile(target, "w", ZIP_DEFLATED, compresslevel=1) as bundle:
        bundle.writestr("project.json", json.dumps(project, ensure_ascii=False))
        for key in take_keys(project):
            bundle.write(take_path(root, key), "takes/" + key + ".wav")


def restore(source, root):
    with ZipFile(source) as bundle:
        if bundle.getinfo("project.json").file_size > 16 * 1024**2:
            raise ValueError("Project manifest exceeds 16 MiB.")
        project = validate(json.loads(bundle.read("project.json")))
        keys = take_keys(project)
        total = sum(bundle.getinfo("takes/" + key + ".wav").file_size for key in keys)
        if total > 8 * 1024**3:
            raise ValueError("Expanded project audio exceeds 8 GiB.")
        for key in keys:
            path = take_path(root, key)
            path.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as temp:
                staging = Path(temp.name)
            try:
                digest = hashlib.sha256()
                with bundle.open("takes/" + key + ".wav") as src, staging.open("wb") as dest:
                    while chunk := src.read(1024 * 1024):
                        digest.update(chunk)
                        dest.write(chunk)
                if digest.hexdigest() != key:
                    raise ValueError("Damaged audio take in project.")
                with wave.open(str(staging)) as stream:
                    if (stream.getframerate(), stream.getnchannels(), stream.getsampwidth()) != (audio.RATE, 1, 2):
                        raise ValueError("Unsupported project audio.")
                staging.replace(path)
            finally:
                staging.unlink(missing_ok=True)
    return project


def mix(engine, project, root, dest, stems=False):
    validate(project)
    clips, cues, cursor = [], [], 0
    gains = project.get("gains", {})
    for line in project["lines"]:
        take = next((t for t in line.get("takes", []) if t["key"] == line.get("active")
                     and (not line.get("takeId") or t.get("id") == line["takeId"])), None)
        if not take:
            raise ValueError("Render every line before exporting the timeline.")
        path = take_path(root, take["key"])
        with wave.open(str(path)) as stream:
            count = stream.getnframes()
        start = cursor if line.get("start") is None else round(float(line["start"]) * audio.RATE)
        pause = round(float(line.get("pause", .35)) * audio.RATE)
        if start < 0 or pause < 0 or start + count + pause > audio.RATE * 3600 * 12:
            raise ValueError("Timeline must fit within 12 hours.")
        gain = float(gains.get(line["speaker"], 0))
        if not math.isfinite(gain) or abs(gain) > 36:
            raise ValueError("Speaker gain must be between -36 and 36 dB.")
        clips.append((start, count, path, line["speaker"], 10 ** (gain/20)))
        cursor = start + count + pause
        for begin, end, label in take["cues"]:
            if not 0 <= begin < end <= math.ceil(count * 1000 / audio.RATE):
                raise ValueError("Caption times must fit inside their clip.")
            offset = round(start * 1000 / audio.RATE)
            cues.append([offset + begin, offset + end, f'[{line["speaker"]}] {label}'])
    if not clips:
        raise ValueError("Add at least one line.")
    clips.sort(key=lambda clip: clip[0])
    length = max(start + count for start, count, *_ in clips)
    speakers = list(dict.fromkeys(clip[3] for clip in clips))
    dest.mkdir(parents=True, exist_ok=True)
    stem_files = {s: f"speaker-{i+1}.wav" for i, s in enumerate(speakers)} if stems else {}
    total_squared = peak = 0.0
    with contextlib.ExitStack() as stack:
        def writer(filename):
            stream = stack.enter_context(wave.open(str(dest / filename), "wb"))
            stream.setparams((1, 2, audio.RATE, 0, "NONE", ""))
            return stream
        master = writer("master.wav")
        writers = {s: writer(f) for s, f in stem_files.items()}
        active, index = [], 0
        for pos in range(0, length, 32768):
            size = min(32768, length-pos)
            while index < len(clips) and clips[index][0] < pos + size:
                active.append(clips[index])
                index += 1
            block = np.zeros(size, dtype=np.float64)
            tracks = {clip[3]: np.zeros(size) for clip in active}
            for start, count, path, speaker, gain in active:
                left, right = max(pos, start), min(pos + size, start + count)
                with wave.open(str(path)) as stream:
                    stream.setpos(left - start)
                    data = np.frombuffer(stream.readframes(right-left), dtype="<i2") * gain
                block[left-pos:right-pos] += data
                tracks[speaker][left-pos:right-pos] += data
            active = [clip for clip in active if clip[0] + clip[1] > pos + size]
            # One envelope for the master and stems preserves their relative levels.
            magnitude = np.abs(block)
            for track in tracks.values():
                magnitude = np.maximum(magnitude, np.abs(track))
            envelope = 30000 / np.maximum(30000, magnitude)
            block *= envelope
            peak = max(peak, float(np.abs(block).max()))
            total_squared += float(np.dot(block, block))
            master.writeframesraw(np.rint(block).astype("<i2").tobytes())
            for speaker, writer_ in writers.items():
                writer_.writeframesraw(np.rint(tracks.get(speaker, np.zeros(size)) * envelope).astype("<i2").tobytes())
    srt = engine._format_cues(sorted(cues, key=lambda c: c[0]))
    (dest/"captions.srt").write_text(srt, encoding="utf8")
    (dest/"captions.vtt").write_text(engine._convert_srt_to_vtt(srt), encoding="utf8")
    def db(value):
        return round(20 * math.log10(value / 32768), 1) if value else None
    metadata = dict(seconds=length/audio.RATE, peak_dbfs=db(peak), rms_dbfs=db(math.sqrt(total_squared/length)), stems=stem_files)
    (dest/"mix.json").write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf8")
    return metadata

