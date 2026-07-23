import json
import math
import wave
import zipfile
from pathlib import Path

from split_peel.cli import main
from split_peel.package_ids import make_id
from split_peel.voice_manifest import build_voice_manifest, voice_clips_from_manifest


def test_build_voice_manifest_reuses_audio_and_records_line_ids(tmp_path: Path):
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "voice-manifest.json"
    reuse = tmp_path / "reuse.bs"
    line = {"id": "peel-shock-001", "speaker": "peel", "line": "Wait, what?", "tone": "shocked"}
    clip_id = make_id(f"000-peel-{line['line']}-{line['tone']}")
    script_path.write_text(json.dumps({"dialogue": [line]}), encoding="utf-8")
    with zipfile.ZipFile(reuse, "w", compression=zipfile.ZIP_STORED) as archive:
        archive.writestr("show.json", "{}")
        archive.writestr(f"audio/{clip_id}.wav", _test_wav_bytes([(0.0, 0.4, 7000)]))

    manifest = build_voice_manifest(script_path, manifest_path, reuse_audio_from=reuse, skip_voice=True)
    clips = voice_clips_from_manifest(manifest_path)

    assert manifest["clips"][0]["line_id"] == "peel-shock-001"
    assert manifest["clips"][0]["audio_id"] == clip_id
    assert (tmp_path / manifest["clips"][0]["path"]).exists()
    assert clips[0].line_id == "peel-shock-001"
    assert clips[0].speaker == "peel"


def test_build_voice_command_writes_manifest(tmp_path: Path):
    script_path = tmp_path / "script.json"
    manifest_path = tmp_path / "run/voice-manifest.json"
    reuse = tmp_path / "reuse.bannyshow"
    line = {"speaker": "split", "line": "Reusable command line.", "tone": "dry"}
    clip_id = make_id(f"000-split-{line['line']}-{line['tone']}")
    script_path.write_text(json.dumps({"dialogue": [line]}), encoding="utf-8")
    (reuse / "audio").mkdir(parents=True)
    (reuse / "show.json").write_text("{}", encoding="utf-8")
    (reuse / "audio" / f"{clip_id}.wav").write_bytes(_test_wav_bytes([(0.0, 0.3, 7000)]))

    main(
        [
            "build-voice",
            "--script",
            str(script_path),
            "--out",
            str(manifest_path),
            "--reuse-audio-from",
            str(reuse),
            "--skip-voice",
        ]
    )

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["clips"][0]["line_id"] == "split-001"
    assert (manifest_path.parent / manifest["clips"][0]["path"]).exists()


def _test_wav_bytes(segments, sample_rate: int = 22050) -> bytes:
    import io

    samples = []
    for start, end, amplitude in segments:
        frame_count = int((end - start) * sample_rate)
        for index in range(frame_count):
            value = int(amplitude * math.sin(2 * math.pi * 220 * (index / sample_rate))) if amplitude else 0
            samples.append(value)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(sample.to_bytes(2, "little", signed=True) for sample in samples))
    return buffer.getvalue()
