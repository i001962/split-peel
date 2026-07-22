import json
import math
import wave
from pathlib import Path
from typing import List, Tuple

from split_peel.audio import _synthesize_elevenlabs_tts, _synthesize_openai_tts, detect_eye_events, detect_mouth_events, synthesize_dialogue


def test_openai_tts_payload_includes_character_speed(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"RIFF....WAVE"

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("split_peel.audio.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("split_peel.audio._normalize_wav_header", lambda path: None)
    characters = {"characters": [{"id": "split", "voice": {"openai": "shimmer", "openaiSpeed": 1.35}}]}

    _synthesize_openai_tts("split", "hello", tmp_path / "voice.wav", characters, tone="breathless disbelief")

    assert captured["body"]["voice"] == "shimmer"
    assert captured["body"]["speed"] == 1.35
    assert "Line delivery: breathless disbelief" in captured["body"]["instructions"]


def test_synthesize_dialogue_passes_tone_to_openai_tts(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"RIFF....WAVE"

    def fake_urlopen(request, timeout):
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("SPLIT_PEEL_VOICE_PROVIDER", "openai")
    monkeypatch.setenv("SPLIT_PEEL_AUDIO_CACHE", "0")
    monkeypatch.setattr("split_peel.audio.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("split_peel.audio._normalize_wav_header", lambda path: None)
    monkeypatch.setattr("split_peel.audio.wav_duration", lambda path: 1.0)
    monkeypatch.setattr("split_peel.audio.detect_mouth_events", lambda path, offset=0.0: [])
    monkeypatch.setattr("split_peel.audio.detect_eye_events", lambda path, offset=0.0, tone="": [])

    synthesize_dialogue(
        [{"speaker": "peel", "line": "Wait, that is tactical confetti.", "tone": "start hushed, then explode"}],
        tmp_path,
        characters={"characters": [{"id": "peel", "voice": {"openai": "fable"}}]},
    )

    assert "Line delivery: start hushed, then explode" in captured["body"]["instructions"]


def test_synthesize_dialogue_defaults_to_elevenlabs(tmp_path, monkeypatch):
    called = {}

    def fake_elevenlabs_tts(speaker, text, output_wav, characters, tone=""):
        called["speaker"] = speaker
        called["tone"] = tone
        output_wav.write_bytes(b"RIFF")

    monkeypatch.delenv("SPLIT_PEEL_VOICE_PROVIDER", raising=False)
    monkeypatch.setenv("SPLIT_PEEL_AUDIO_CACHE", "0")
    monkeypatch.setattr("split_peel.audio._synthesize_elevenlabs_tts", fake_elevenlabs_tts)
    monkeypatch.setattr("split_peel.audio.wav_duration", lambda path: 1.0)
    monkeypatch.setattr("split_peel.audio.detect_mouth_events", lambda path, offset=0.0: [])
    monkeypatch.setattr("split_peel.audio.detect_eye_events", lambda path, offset=0.0, tone="": [])

    clips = synthesize_dialogue(
        [{"speaker": "split", "line": "Kickoff is loud.", "tone": "broadcast snap"}],
        tmp_path,
        characters={"characters": [{"id": "split", "voice": {"elevenlabs": "voice-split"}}]},
    )

    assert called == {"speaker": "split", "tone": "broadcast snap"}
    assert clips[0].speaker == "split"


def test_synthesize_dialogue_reuses_audio_cache(tmp_path, monkeypatch):
    cache_dir = tmp_path / "cache"
    calls = {"count": 0}

    def fake_elevenlabs_tts(speaker, text, output_wav, characters, tone=""):
        calls["count"] += 1
        _write_synthetic_wav(output_wav, [(0.0, 0.25, 7000)])

    monkeypatch.setenv("SPLIT_PEEL_VOICE_PROVIDER", "elevenlabs")
    monkeypatch.setenv("SPLIT_PEEL_AUDIO_CACHE_DIR", str(cache_dir))
    monkeypatch.setattr("split_peel.audio._synthesize_elevenlabs_tts", fake_elevenlabs_tts)
    monkeypatch.setattr("split_peel.audio.detect_mouth_events", lambda path, offset=0.0: [])
    monkeypatch.setattr("split_peel.audio.detect_eye_events", lambda path, offset=0.0, tone="": [])
    characters = {"characters": [{"id": "split", "voice": {"elevenlabs": "voice-split"}}]}
    dialogue = [{"speaker": "split", "line": "Kickoff is loud.", "tone": "broadcast snap"}]

    synthesize_dialogue(dialogue, tmp_path / "first", characters=characters)
    synthesize_dialogue(dialogue, tmp_path / "second", characters=characters)

    assert calls["count"] == 1
    assert list(cache_dir.glob("*.wav"))


def test_synthesize_dialogue_skip_voice_requires_reusable_audio(tmp_path, monkeypatch):
    monkeypatch.setenv("SPLIT_PEEL_AUDIO_CACHE", "0")

    try:
        synthesize_dialogue(
            [{"speaker": "split", "line": "No cache here.", "tone": "dry"}],
            tmp_path,
            characters={"characters": [{"id": "split"}]},
            skip_voice=True,
        )
    except RuntimeError as error:
        assert "voice generation skipped" in str(error)
    else:
        raise AssertionError("skip_voice should fail when reusable audio is missing")


def test_elevenlabs_tts_payload_includes_voice_and_delivery_tags(tmp_path, monkeypatch):
    captured = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def read(self):
            return b"MP3"

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return FakeResponse()

    monkeypatch.setenv("ELEVENLABS_API_KEY", "test-eleven-key")
    monkeypatch.setenv("SPLIT_PEEL_ELEVENLABS_MODEL", "eleven_v3")
    monkeypatch.setattr("split_peel.audio.urllib.request.urlopen", fake_urlopen)
    monkeypatch.setattr("split_peel.audio._convert_audio_to_wav", lambda source, output_wav: output_wav.write_bytes(b"RIFF"))
    characters = {"characters": [{"id": "peel", "voice": {"elevenlabs": "voice-peel"}}]}

    _synthesize_elevenlabs_tts("peel", "He is through!", tmp_path / "voice.wav", characters, tone="gasping, then shouting")

    assert "/v1/text-to-speech/voice-peel" in captured["url"]
    assert captured["body"]["model_id"] == "eleven_v3"
    assert captured["body"]["text"] == "[gasping, then shouting] He is through!"


def test_detect_mouth_events_tracks_speech_bursts_with_lead(tmp_path: Path, monkeypatch):
    wav_path = tmp_path / "speech.wav"
    _write_synthetic_wav(
        wav_path,
        [
            (0.0, 0.30, 0),
            (0.30, 0.55, 7000),
            (0.55, 0.75, 0),
            (0.75, 1.10, 9000),
            (1.10, 1.40, 0),
        ],
    )
    monkeypatch.setenv("SPLIT_PEEL_MOUTH_LEAD_SEC", "0.04")
    monkeypatch.setenv("SPLIT_PEEL_MOUTH_MAX_OPEN_SEC", "0.12")
    monkeypatch.setenv("SPLIT_PEEL_MOUTH_MIN_CLOSED_SEC", "0.04")

    events = detect_mouth_events(wav_path, offset=2.0)

    assert len(events) >= 6
    assert events[0] == {"code": "KeyM", "down": True, "t": 2.24}
    assert events[-1]["down"] is False
    assert [event["down"] for event in events] == [index % 2 == 0 for index in range(len(events))]

    open_events = events[::2]
    close_events = events[1::2]
    assert len(open_events) == len(close_events)
    for open_event, close_event in zip(open_events, close_events):
        assert 0.06 <= close_event["t"] - open_event["t"] <= 0.16


def test_detect_eye_events_adds_blinks_and_expression_peaks(tmp_path: Path, monkeypatch):
    wav_path = tmp_path / "expressive.wav"
    _write_synthetic_wav(
        wav_path,
        [
            (0.0, 0.30, 0),
            (0.30, 0.55, 4000),
            (0.55, 0.85, 0),
            (0.85, 1.15, 12000),
            (1.15, 1.70, 0),
            (1.70, 2.10, 5000),
            (2.10, 2.70, 0),
            (2.70, 3.00, 9500),
            (3.00, 3.80, 0),
        ],
    )
    monkeypatch.setenv("SPLIT_PEEL_BLINK_RATE_SEC", "1.6")

    events = detect_eye_events(wav_path, offset=4.0, tone="surprised disbelief")

    codes = {event["code"] for event in events}
    assert "Comma" in codes
    assert "Slash" in codes
    assert any(event["code"] == "Period" for event in events)
    assert [event["down"] for event in events].count(True) == [event["down"] for event in events].count(False)
    assert events == sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))


def _write_synthetic_wav(path: Path, segments: List[Tuple[float, float, int]], sample_rate: int = 22050) -> None:
    samples = []
    for start, end, amplitude in segments:
        frame_count = int((end - start) * sample_rate)
        for index in range(frame_count):
            value = int(amplitude * math.sin(2 * math.pi * 220 * (index / sample_rate))) if amplitude else 0
            samples.append(value)
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
