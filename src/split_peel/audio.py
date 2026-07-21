from __future__ import annotations

import math
import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
import wave
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Optional

from split_peel.characters import DEFAULT_CHARACTERS, instructions_for_speaker, voice_for_speaker, voice_speed_for_speaker
from split_peel.package_ids import make_id


VOICE_BY_SPEAKER = {
    "split": "Alex",
    "peel": "Samantha",
}

OPENAI_VOICE_BY_SPEAKER = {
    "split": "onyx",
    "peel": "verse",
}

ELEVENLABS_VOICE_BY_SPEAKER = {
    "split": "",
    "peel": "",
}

OPENAI_INSTRUCTIONS_BY_SPEAKER = {
    "split": (
        "A sharp, dry football commentator. Confident, witty, slightly sarcastic, "
        "with energetic sports-broadcast timing."
    ),
    "peel": (
        "A playful football co-commentator. Warm, animated, quick with banter, "
        "and amused by fan overreactions."
    ),
}


@dataclass(frozen=True)
class VoiceClip:
    clip_id: str
    speaker: str
    line: str
    start: float
    duration: float
    mouth_events: list[dict[str, object]]


def local_tts_available() -> bool:
    return shutil.which("say") is not None and shutil.which("afconvert") is not None


def synthesize_dialogue(
    dialogue: list[dict],
    audio_dir: Path,
    start_at: float = 0.5,
    characters: Optional[dict] = None,
) -> list[VoiceClip]:
    audio_dir.mkdir(parents=True, exist_ok=True)
    clips: list[VoiceClip] = []
    cursor = start_at
    provider = os.environ.get("SPLIT_PEEL_VOICE_PROVIDER", "local").strip().lower()
    characters = characters or DEFAULT_CHARACTERS

    for index, line in enumerate(dialogue):
        speaker = str(line.get("speaker") or "split").lower()
        text = str(line.get("line") or "").strip()
        tone = str(line.get("tone") or "").strip()
        if not text:
            continue

        clip_id = make_id(f"{index:03d}-{speaker}-{text}-{tone}")
        output_wav = audio_dir / f"{clip_id}.wav"

        if provider == "openai":
            _synthesize_openai_tts(speaker, text, output_wav, characters, tone=tone)
        elif provider == "elevenlabs":
            _synthesize_elevenlabs_tts(speaker, text, output_wav, characters, tone=tone)
        elif provider in {"local", "say"}:
            _synthesize_local_tts(speaker, text, output_wav, characters)
        else:
            raise RuntimeError(f"unknown voice provider: {provider}")

        duration = wav_duration(output_wav)
        mouth_events = detect_mouth_events(output_wav, offset=cursor)

        clips.append(
            VoiceClip(
                clip_id=clip_id,
                speaker=speaker,
                line=text,
                start=round(cursor, 3),
                duration=round(duration, 3),
                mouth_events=mouth_events,
            )
        )
        cursor += duration + 0.35

    return clips


def _synthesize_local_tts(speaker: str, text: str, output_wav: Path, characters: dict) -> None:
    if not local_tts_available():
        raise RuntimeError("local TTS requires macOS 'say' and 'afconvert' commands")

    voice = voice_for_speaker(characters, speaker, "local", VOICE_BY_SPEAKER.get(speaker, "Alex"))
    with TemporaryDirectory(prefix="split-peel-voice-") as tmp:
        tmp_path = Path(tmp)
        aiff_path = tmp_path / "voice.aiff"
        _run(["say", "-v", voice, "-o", str(aiff_path), text])
        _run(["afconvert", str(aiff_path), str(output_wav), "-f", "WAVE", "-d", "LEI16@22050"])


def _synthesize_openai_tts(speaker: str, text: str, output_wav: Path, characters: dict, tone: str = "") -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("SPLIT_PEEL_VOICE_PROVIDER=openai requires OPENAI_API_KEY in the environment or .env")

    model = os.environ.get("SPLIT_PEEL_OPENAI_TTS_MODEL", "gpt-4o-mini-tts")
    voice = _openai_voice_for_speaker(speaker, characters)
    instructions = _openai_instructions_for_speaker(speaker, characters, tone=tone)
    speed = _openai_speed_for_speaker(speaker, characters)
    payload = {
        "model": model,
        "voice": voice,
        "input": text,
        "instructions": instructions,
        "response_format": "wav",
        "speed": speed,
    }
    body = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        "https://api.openai.com/v1/audio/speech",
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "split-peel/0.1",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            output_wav.write_bytes(response.read())
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI TTS request failed ({error.code}): {detail}") from error

    _normalize_wav_header(output_wav)


def _synthesize_elevenlabs_tts(speaker: str, text: str, output_wav: Path, characters: dict, tone: str = "") -> None:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("SPLIT_PEEL_VOICE_PROVIDER=elevenlabs requires ELEVENLABS_API_KEY in the environment or .env")

    voice_id = _elevenlabs_voice_for_speaker(speaker, characters)
    if not voice_id:
        raise RuntimeError(f"missing ElevenLabs voice id for speaker {speaker}; set voice.elevenlabs or SPLIT_PEEL_*_ELEVENLABS_VOICE_ID")

    model = os.environ.get("SPLIT_PEEL_ELEVENLABS_MODEL", "eleven_v3")
    output_format = os.environ.get("SPLIT_PEEL_ELEVENLABS_OUTPUT_FORMAT", "mp3_44100_128")
    payload = {
        "text": _elevenlabs_text_with_delivery(text, tone),
        "model_id": model,
    }
    request = urllib.request.Request(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format={output_format}",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "xi-api-key": api_key,
            "Content-Type": "application/json",
            "User-Agent": "split-peel/0.1",
        },
        method="POST",
    )

    with TemporaryDirectory(prefix="split-peel-elevenlabs-") as tmp:
        tmp_path = Path(tmp)
        source_audio = tmp_path / "voice.mp3"
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                source_audio.write_bytes(response.read())
        except urllib.error.HTTPError as error:
            detail = error.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"ElevenLabs TTS request failed ({error.code}): {detail}") from error
        _convert_audio_to_wav(source_audio, output_wav)


def _openai_voice_for_speaker(speaker: str, characters: dict) -> str:
    if speaker == "split":
        fallback = os.environ.get("SPLIT_PEEL_SPLIT_VOICE", OPENAI_VOICE_BY_SPEAKER["split"])
        return voice_for_speaker(characters, speaker, "openai", fallback)
    if speaker == "peel":
        fallback = os.environ.get("SPLIT_PEEL_PEEL_VOICE", OPENAI_VOICE_BY_SPEAKER["peel"])
        return voice_for_speaker(characters, speaker, "openai", fallback)
    return voice_for_speaker(characters, speaker, "openai", OPENAI_VOICE_BY_SPEAKER["split"])


def _elevenlabs_voice_for_speaker(speaker: str, characters: dict) -> str:
    if speaker == "split":
        fallback = os.environ.get("SPLIT_PEEL_SPLIT_ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_BY_SPEAKER["split"])
        return voice_for_speaker(characters, speaker, "elevenlabs", fallback)
    if speaker == "peel":
        fallback = os.environ.get("SPLIT_PEEL_PEEL_ELEVENLABS_VOICE_ID", ELEVENLABS_VOICE_BY_SPEAKER["peel"])
        return voice_for_speaker(characters, speaker, "elevenlabs", fallback)
    return voice_for_speaker(characters, speaker, "elevenlabs", ELEVENLABS_VOICE_BY_SPEAKER["split"])


def _openai_instructions_for_speaker(speaker: str, characters: dict, tone: str = "") -> str:
    if speaker == "split":
        fallback = os.environ.get("SPLIT_PEEL_SPLIT_INSTRUCTIONS", OPENAI_INSTRUCTIONS_BY_SPEAKER["split"])
        return _with_line_delivery(instructions_for_speaker(characters, speaker, fallback), tone)
    if speaker == "peel":
        fallback = os.environ.get("SPLIT_PEEL_PEEL_INSTRUCTIONS", OPENAI_INSTRUCTIONS_BY_SPEAKER["peel"])
        return _with_line_delivery(instructions_for_speaker(characters, speaker, fallback), tone)
    return _with_line_delivery(instructions_for_speaker(characters, speaker, OPENAI_INSTRUCTIONS_BY_SPEAKER["split"]), tone)


def _with_line_delivery(base_instructions: str, tone: str) -> str:
    tone = " ".join(tone.split()).strip()
    if not tone:
        return base_instructions
    return (
        f"{base_instructions} "
        f"Line delivery: {tone}. Treat this as performance direction, not text to say. "
        "Vary pitch, pacing, emphasis, pauses, and emotional shape to match it. "
        "Make the delivery animated and specific while keeping the words clear."
    )


def _elevenlabs_text_with_delivery(text: str, tone: str) -> str:
    tone = " ".join(tone.split()).strip()
    if not tone:
        return text
    return f"[{tone}] {text}"


def _openai_speed_for_speaker(speaker: str, characters: dict) -> float:
    if speaker == "split":
        fallback = float(os.environ.get("SPLIT_PEEL_SPLIT_SPEED", os.environ.get("SPLIT_PEEL_OPENAI_TTS_SPEED", "1.0")))
        return voice_speed_for_speaker(characters, speaker, "openai", fallback)
    if speaker == "peel":
        fallback = float(os.environ.get("SPLIT_PEEL_PEEL_SPEED", os.environ.get("SPLIT_PEEL_OPENAI_TTS_SPEED", "1.0")))
        return voice_speed_for_speaker(characters, speaker, "openai", fallback)
    fallback = float(os.environ.get("SPLIT_PEEL_OPENAI_TTS_SPEED", "1.0"))
    return voice_speed_for_speaker(characters, speaker, "openai", fallback)


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as wav:
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())
    actual_frame_count = len(frames) / float(sample_width * channels)
    duration = actual_frame_count / float(sample_rate)
    if duration > 600:
        raise RuntimeError(f"implausible WAV duration for {path}: {duration:.2f}s")
    return duration


def detect_mouth_events(path: Path, offset: float = 0.0, window_sec: float = 0.04) -> list[dict[str, object]]:
    with wave.open(str(path), "rb") as wav:
        if wav.getsampwidth() != 2:
            raise RuntimeError("mouth detection expects 16-bit PCM WAV audio")
        channels = wav.getnchannels()
        sample_rate = wav.getframerate()
        frames = wav.readframes(wav.getnframes())

    samples = _pcm16_samples(frames, channels)
    window_size = max(1, int(sample_rate * window_sec))
    levels: list[float] = []
    for start in range(0, len(samples), window_size):
        window = samples[start : start + window_size]
        if not window:
            continue
        rms = math.sqrt(sum(sample * sample for sample in window) / len(window))
        levels.append(rms)

    if not levels:
        return []

    levels = _smooth_levels(levels)
    peak = max(levels)
    noise_floor = _percentile(levels, 0.18)
    threshold_on = max(noise_floor + (peak - noise_floor) * 0.22, 260.0)
    threshold_off = max(noise_floor + (peak - noise_floor) * 0.11, 180.0)
    lead_sec = float(os.environ.get("SPLIT_PEEL_MOUTH_LEAD_SEC", "0.06"))
    max_open_sec = float(os.environ.get("SPLIT_PEEL_MOUTH_MAX_OPEN_SEC", "0.12"))
    min_closed_sec = float(os.environ.get("SPLIT_PEEL_MOUTH_MIN_CLOSED_SEC", "0.04"))
    max_open_frames = max(1, int(round(max_open_sec / window_sec)))
    min_closed_frames = max(1, int(round(min_closed_sec / window_sec)))
    events: list[dict[str, object]] = []
    mouth_open = False
    loud_streak = 0
    quiet_streak = 0
    open_frame_index = 0
    last_close_frame_index = -min_closed_frames
    last_close_t = offset
    open_t = offset

    for index, level in enumerate(levels):
        is_loud = level >= threshold_on
        is_quiet = level < threshold_off
        loud_streak = loud_streak + 1 if is_loud else 0
        quiet_streak = quiet_streak + 1 if is_quiet else 0
        t = offset + index * window_sec

        can_open = index - last_close_frame_index >= min_closed_frames
        if loud_streak >= 1 and not mouth_open and can_open:
            open_t = max(offset, last_close_t + min_closed_sec, t - lead_sec)
            events.append({"code": "KeyM", "down": True, "t": round(open_t, 3)})
            mouth_open = True
            open_frame_index = index
            quiet_streak = 0
        elif mouth_open and (quiet_streak >= 2 or index - open_frame_index >= max_open_frames or t - open_t >= max_open_sec):
            close_t = min(t, open_t + max_open_sec)
            events.append({"code": "KeyM", "down": False, "t": round(close_t, 3)})
            mouth_open = False
            last_close_frame_index = index
            last_close_t = close_t
            loud_streak = 0

    if mouth_open:
        close_t = offset + len(levels) * window_sec
        events.append({"code": "KeyM", "down": False, "t": round(close_t, 3)})

    return _remove_tiny_mouth_flaps(events, min_duration=min(0.06, max_open_sec * 0.5))


def _pcm16_samples(frames: bytes, channels: int) -> list[int]:
    samples: list[int] = []
    frame_width = channels * 2
    for index in range(0, len(frames), frame_width):
        channel_values = []
        for channel in range(channels):
            start = index + channel * 2
            channel_values.append(int.from_bytes(frames[start : start + 2], "little", signed=True))
        samples.append(int(sum(channel_values) / len(channel_values)))
    return samples


def _smooth_levels(levels: list[float]) -> list[float]:
    if len(levels) < 3:
        return levels
    smoothed: list[float] = []
    for index, level in enumerate(levels):
        previous_level = levels[index - 1] if index else level
        next_level = levels[index + 1] if index < len(levels) - 1 else level
        smoothed.append(previous_level * 0.25 + level * 0.5 + next_level * 0.25)
    return smoothed


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, int(round((len(ordered) - 1) * percentile))))
    return ordered[index]


def _remove_tiny_mouth_flaps(events: list[dict[str, object]], min_duration: float = 0.06) -> list[dict[str, object]]:
    cleaned: list[dict[str, object]] = []
    pending_open: Optional[dict[str, object]] = None

    for event in events:
        if event["down"]:
            pending_open = event
            continue
        if pending_open is None:
            continue
        if float(event["t"]) - float(pending_open["t"]) >= min_duration:
            cleaned.extend([pending_open, event])
        pending_open = None

    return cleaned


def _run(command: list[str]) -> None:
    result = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    if result.returncode != 0:
        stderr = result.stderr.strip()
        raise RuntimeError(f"command failed ({result.returncode}): {' '.join(command)}\n{stderr}")


def _normalize_wav_header(path: Path) -> None:
    if shutil.which("afconvert") is None:
        return
    normalized = path.with_suffix(".normalized.wav")
    _run(["afconvert", str(path), str(normalized), "-f", "WAVE", "-d", "LEI16@24000"])
    normalized.replace(path)


def _convert_audio_to_wav(source: Path, output_wav: Path) -> None:
    if shutil.which("afconvert") is None:
        raise RuntimeError("ElevenLabs TTS conversion requires macOS 'afconvert' to produce WAV dialogue clips")
    _run(["afconvert", str(source), str(output_wav), "-f", "WAVE", "-d", "LEI16@24000"])
