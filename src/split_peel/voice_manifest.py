from __future__ import annotations

import hashlib
import json
import os
import shutil
import zipfile
from pathlib import Path
from typing import Any, Optional

from split_peel.audio import VoiceClip, synthesize_dialogue


VOICE_MANIFEST_VERSION = 1


class VoiceManifestError(RuntimeError):
    pass


def build_voice_manifest(
    script_path: Path,
    out: Path,
    audio_dir: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
    reuse_audio_from: Optional[Path] = None,
    skip_voice: bool = False,
) -> dict[str, Any]:
    script = json.loads(script_path.read_text(encoding="utf-8"))
    dialogue = script.get("dialogue")
    if not isinstance(dialogue, list):
        raise VoiceManifestError("script does not contain a dialogue array")

    out.parent.mkdir(parents=True, exist_ok=True)
    audio_dir = audio_dir or out.parent / "voice" / "audio"
    audio_dir.mkdir(parents=True, exist_ok=True)
    reuse_dirs = _reuse_audio_dirs(out.parent, reuse_audio_from)
    clips = synthesize_dialogue(
        dialogue,
        audio_dir,
        characters=characters,
        reuse_audio_dirs=reuse_dirs,
        skip_voice=skip_voice,
    )

    clips_by_index = {index: clip for index, clip in enumerate(clips)}
    manifest_clips = []
    produced_index = 0
    for line_index, line in enumerate(dialogue):
        text = str(line.get("line") or "").strip()
        if not text:
            continue
        clip = clips_by_index[produced_index]
        produced_index += 1
        line_id = line_id_for_dialogue(line, line_index)
        audio_path = audio_dir / f"{clip.clip_id}.wav"
        manifest_clips.append(
            {
                "line_id": line_id,
                "line_index": line_index,
                "speaker": clip.speaker,
                "text": clip.line,
                "tone": str(line.get("tone") or "").strip(),
                "text_hash": _text_hash(clip.speaker, clip.line, str(line.get("tone") or "").strip()),
                "audio_id": clip.clip_id,
                "start": clip.start,
                "duration": clip.duration,
                "path": os.path.relpath(audio_path, out.parent),
                "mouth_events": clip.mouth_events,
                "eye_events": clip.eye_events,
            }
        )

    manifest = {
        "version": VOICE_MANIFEST_VERSION,
        "script_path": os.path.relpath(script_path, out.parent),
        "audio_dir": os.path.relpath(audio_dir, out.parent),
        "clips": manifest_clips,
    }
    out.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    shutil.rmtree(out.parent / "_reuse_audio", ignore_errors=True)
    return manifest


def load_voice_manifest(path: Path) -> dict[str, Any]:
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("version") != VOICE_MANIFEST_VERSION:
        raise VoiceManifestError(f"unsupported voice manifest version: {manifest.get('version')}")
    clips = manifest.get("clips")
    if not isinstance(clips, list):
        raise VoiceManifestError("voice manifest does not contain a clips array")
    return manifest


def voice_clips_from_manifest(path: Path) -> list[VoiceClip]:
    manifest = load_voice_manifest(path)
    clips = []
    for item in manifest["clips"]:
        clips.append(
            VoiceClip(
                clip_id=str(item["audio_id"]),
                speaker=str(item["speaker"]),
                line=str(item["text"]),
                start=round(float(item["start"]), 3),
                duration=round(float(item["duration"]), 3),
                mouth_events=list(item.get("mouth_events") or []),
                eye_events=list(item.get("eye_events") or []),
                line_id=str(item.get("line_id") or ""),
            )
        )
    return clips


def copy_manifest_audio(manifest_path: Path, audio_dir: Path) -> None:
    manifest = load_voice_manifest(manifest_path)
    audio_dir.mkdir(parents=True, exist_ok=True)
    for item in manifest["clips"]:
        source = _resolve_manifest_path(manifest_path, str(item.get("path") or ""))
        if not source.exists():
            raise VoiceManifestError(f"voice manifest audio is missing: {source}")
        destination = audio_dir / f"{item['audio_id']}.wav"
        if source.resolve() != destination.resolve():
            shutil.copy2(source, destination)


def line_id_for_dialogue(line: dict[str, Any], index: int) -> str:
    for key in ("line_id", "lineId", "id"):
        value = str(line.get(key) or "").strip()
        if value:
            return value
    speaker = str(line.get("speaker") or "split").lower()
    return f"{speaker}-{index + 1:03d}"


def _text_hash(speaker: str, text: str, tone: str) -> str:
    payload = json.dumps(
        {"speaker": speaker, "text": text, "tone": tone},
        sort_keys=True,
        ensure_ascii=False,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _resolve_manifest_path(manifest_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return manifest_path.parent / path


def _reuse_audio_dirs(work_dir: Path, reuse_audio_from: Optional[Path]) -> list[Path]:
    if not reuse_audio_from:
        return []
    source = reuse_audio_from.expanduser()
    if not source.exists():
        raise VoiceManifestError(f"reuse audio source does not exist: {source}")
    if source.is_dir():
        audio_dir = source / "audio"
        return [audio_dir] if audio_dir.exists() else []

    extracted = work_dir / "_reuse_audio"
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            if info.filename.startswith("audio/") and info.filename.endswith(".wav"):
                (extracted / Path(info.filename).name).write_bytes(archive.read(info.filename))
    return [extracted]
