from __future__ import annotations

import json
import os
import re
import shutil
import tempfile
import zipfile
from pathlib import Path
from typing import Any, Optional

from split_peel.audio import VoiceClip, detect_mouth_events, synthesize_dialogue
from split_peel.motion import SPEAKER_CHARACTER_INDEX, build_character_events
from split_peel.overlays import apply_overlays, load_overlay_manifest


class BannyPackageError(RuntimeError):
    pass


def inspect_package(template: Path) -> dict[str, Any]:
    with zipfile.ZipFile(template) as archive:
        names = archive.namelist()
        if "show.json" not in names:
            raise BannyPackageError(f"{template} does not contain show.json")
        show = json.loads(archive.read("show.json").decode("utf-8"))

    stage = show.get("stage") or {}
    return {
        "path": str(template),
        "files": len(names),
        "hasShowJson": True,
        "assetCount": len(show.get("assets") or []),
        "audioTrackCount": len(stage.get("audioTracks") or []),
        "backgroundTrackCount": len(stage.get("backgroundTracks") or []),
        "characterCount": len(stage.get("characters") or []),
    }


def roundtrip_package(template: Path, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="split-peel-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(template) as archive:
            archive.extractall(tmp_path)
        _validate_show_json(tmp_path / "show.json")
        _zip_directory(tmp_path, out)


def unpack_package(template: Path, out: Path, overwrite: bool = False) -> None:
    if out.exists():
        if not overwrite:
            raise BannyPackageError(f"{out} already exists; pass --overwrite to replace it")
        shutil.rmtree(out)

    out.mkdir(parents=True)
    with zipfile.ZipFile(template) as archive:
        archive.extractall(out)
    _validate_show_json(out / "show.json")


def retime_mouth_events(template: Path, out: Path, overwrite: bool = False) -> None:
    if out.exists():
        if not overwrite:
            raise BannyPackageError(f"{out} already exists; pass --overwrite to replace it")
        if out.is_dir():
            shutil.rmtree(out)
        else:
            out.unlink()

    out.parent.mkdir(parents=True, exist_ok=True)
    if template.is_dir():
        shutil.copytree(template, out)
        _validate_show_json(out / "show.json")
        _retime_mouth_events_in_dir(out)
        return

    with tempfile.TemporaryDirectory(prefix="split-peel-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(template) as archive:
            archive.extractall(tmp_path)
        _validate_show_json(tmp_path / "show.json")
        _retime_mouth_events_in_dir(tmp_path)
        _zip_directory(tmp_path, out)


def build_show(
    template: Path,
    script: Optional[Path],
    out: Path,
    background_gain: Optional[float] = None,
    overlays: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="split-peel-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(template) as archive:
            archive.extractall(tmp_path)
        _validate_show_json(tmp_path / "show.json")

        if script is not None:
            payload = json.loads(script.read_text(encoding="utf-8"))
            _apply_script_to_package(
                tmp_path,
                payload,
                background_gain=background_gain,
                overlays_path=overlays,
                characters=characters,
            )

        _zip_directory(tmp_path, out)


def _apply_script_to_package(
    package_dir: Path,
    script: dict[str, Any],
    background_gain: Optional[float] = None,
    overlays_path: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
) -> None:
    dialogue = script.get("dialogue")
    if not isinstance(dialogue, list):
        raise BannyPackageError("script does not contain a dialogue array")

    show_path = package_dir / "show.json"
    show = json.loads(show_path.read_text(encoding="utf-8"))
    stage = show.get("stage")
    if not isinstance(stage, dict):
        raise BannyPackageError("show.json is missing stage")

    audio_dir = package_dir / "audio"
    clips = synthesize_dialogue(dialogue, audio_dir, characters=characters)
    if not clips:
        raise BannyPackageError("script did not produce any voice clips")

    _replace_dialogue_track(stage, clips)
    _set_background_audio_gain(stage, background_gain)
    duration = max(clip.start + clip.duration for clip in clips) + 1.0
    _replace_character_events(stage, clips, duration)
    _replace_character_subtitles(stage, clips)
    _extend_show_duration(show, duration)
    _trim_timeline_to_duration(stage, duration)
    apply_overlays(package_dir, show, load_overlay_manifest(overlays_path), duration)
    _remove_unreferenced_audio(package_dir, stage)

    show_path.write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _set_background_audio_gain(stage: dict[str, Any], background_gain: Optional[float]) -> None:
    gain = _resolve_background_gain(background_gain)
    audio_tracks = stage.get("audioTracks")
    if not isinstance(audio_tracks, list) or len(audio_tracks) < 2:
        return

    for track in audio_tracks[1:]:
        fx = track.setdefault("fx", {})
        if isinstance(fx, dict):
            fx["gain"] = gain
        for clip in track.get("clips") or []:
            clip_fx = clip.setdefault("fx", {})
            if isinstance(clip_fx, dict):
                clip_fx["gain"] = gain


def _resolve_background_gain(background_gain: Optional[float]) -> float:
    if background_gain is None:
        raw_gain = os.environ.get("SPLIT_PEEL_BACKGROUND_GAIN", "0.22")
        try:
            background_gain = float(raw_gain)
        except ValueError as error:
            raise BannyPackageError(f"invalid SPLIT_PEEL_BACKGROUND_GAIN: {raw_gain}") from error

    if not 0 <= background_gain <= 1:
        raise BannyPackageError("background gain must be between 0 and 1")
    return round(background_gain, 3)


def _replace_dialogue_track(stage: dict[str, Any], clips: list[VoiceClip]) -> None:
    audio_tracks = stage.get("audioTracks")
    if not isinstance(audio_tracks, list) or not audio_tracks:
        raise BannyPackageError("stage is missing audioTracks")

    track = audio_tracks[0]
    track["name"] = "Dialogue"
    track["clips"] = [
        {
            "dur": clip.duration,
            "fx": {
                "gain": 1,
                "high": 0,
                "low": 0,
                "mid": 0,
                "pan": "follow",
                "reverb": 0,
            },
            "id": clip.clip_id,
            "name": f"{clip.speaker}-{index + 1}",
            "offset": 0,
            "srcDur": clip.duration,
            "start": clip.start,
        }
        for index, clip in enumerate(clips)
    ]


def _replace_character_events(stage: dict[str, Any], clips: list[VoiceClip], duration: float) -> None:
    characters = stage.get("characters")
    if not isinstance(characters, list) or not characters:
        raise BannyPackageError("stage is missing characters")

    events_by_character = build_character_events(clips, len(characters), duration)
    for character, events in zip(characters, events_by_character):
        character["events"] = events


def _replace_character_subtitles(stage: dict[str, Any], clips: list[VoiceClip]) -> None:
    characters = stage.get("characters")
    if not isinstance(characters, list) or not characters:
        raise BannyPackageError("stage is missing characters")

    subs_by_character: list[list[dict[str, object]]] = [[] for _ in range(len(characters))]
    for clip in clips:
        character_index = SPEAKER_CHARACTER_INDEX.get(clip.speaker, 0)
        if character_index >= len(subs_by_character):
            continue
        subs_by_character[character_index].extend(_caption_segments(clip.line, clip.start, clip.duration))

    for character, subs in zip(characters, subs_by_character):
        character["subs"] = subs


def _caption_segments(text: str, start: float, duration: float) -> list[dict[str, object]]:
    max_chars = _caption_max_chars()
    chunks = _caption_text_chunks(text, max_chars)
    if not chunks:
        return []

    total_weight = sum(max(1, len(chunk)) for chunk in chunks)
    cursor = start
    captions: list[dict[str, object]] = []
    for index, chunk in enumerate(chunks):
        if index == len(chunks) - 1:
            chunk_duration = round(start + duration - cursor, 3)
        else:
            chunk_duration = round(duration * (max(1, len(chunk)) / total_weight), 3)
        captions.append({"dur": max(0.1, chunk_duration), "start": round(cursor, 3), "text": chunk})
        cursor += chunk_duration
    return captions


def _caption_text_chunks(text: str, max_chars: int) -> list[str]:
    words = re.findall(r"\S+", text.strip())
    chunks: list[str] = []
    current: list[str] = []

    for word in words:
        candidate = " ".join([*current, word])
        if current and len(candidate) > max_chars:
            chunks.append(" ".join(current))
            current = [word]
        else:
            current.append(word)

    if current:
        chunks.append(" ".join(current))
    return chunks


def _caption_max_chars() -> int:
    raw_value = os.environ.get("SPLIT_PEEL_CAPTION_MAX_CHARS", "42")
    try:
        value = int(raw_value)
    except ValueError as error:
        raise BannyPackageError(f"invalid SPLIT_PEEL_CAPTION_MAX_CHARS: {raw_value}") from error
    return max(16, min(72, value))


def _extend_show_duration(show: dict[str, Any], duration: float) -> None:
    for scene in show.get("show") or []:
        if isinstance(scene, dict):
            scene["from"] = 0
            scene["to"] = round(duration, 3)

    stage = show.get("stage") or {}
    for track_name in ("backgroundTracks", "lightTracks"):
        for track in stage.get(track_name) or []:
            for cue in track.get("cues") or []:
                cue["start"] = min(float(cue.get("start") or 0), round(duration, 3))
                cue["dur"] = round(duration - float(cue.get("start") or 0), 3)


def _trim_timeline_to_duration(stage: dict[str, Any], duration: float) -> None:
    duration = round(duration, 3)
    for track_name in ("audioTracks", "imageTracks"):
        for index, track in enumerate(stage.get(track_name) or []):
            if track_name == "audioTracks" and index == 0:
                continue
            for item_name in ("clips", "cues"):
                trimmed_items = []
                for item in track.get(item_name) or []:
                    start = float(item.get("start") or 0)
                    if start >= duration:
                        continue
                    end = start + float(item.get("dur") or 0)
                    if end > duration:
                        item["dur"] = round(duration - start, 3)
                    trimmed_items.append(item)
                if item_name in track:
                    track[item_name] = trimmed_items


def _remove_unreferenced_audio(package_dir: Path, stage: dict[str, Any]) -> None:
    referenced_ids = set()
    for track in stage.get("audioTracks") or []:
        for clip in track.get("clips") or []:
            clip_id = clip.get("id")
            if clip_id:
                referenced_ids.add(str(clip_id))

    audio_dir = package_dir / "audio"
    if not audio_dir.exists():
        return

    for path in audio_dir.iterdir():
        if path.is_file() and path.stem not in referenced_ids and not path.name.startswith("._"):
            path.unlink()


def _retime_mouth_events_in_dir(package_dir: Path) -> None:
    show_path = package_dir / "show.json"
    show = json.loads(show_path.read_text(encoding="utf-8"))
    stage = show.get("stage")
    if not isinstance(stage, dict):
        raise BannyPackageError("show.json is missing stage")

    audio_tracks = stage.get("audioTracks")
    if not isinstance(audio_tracks, list) or not audio_tracks:
        raise BannyPackageError("stage is missing audioTracks")
    dialogue_clips = audio_tracks[0].get("clips")
    if not isinstance(dialogue_clips, list):
        raise BannyPackageError("dialogue track is missing clips")

    characters = stage.get("characters")
    if not isinstance(characters, list) or not characters:
        raise BannyPackageError("stage is missing characters")

    events_by_character: list[list[dict[str, object]]] = []
    for character in characters:
        existing_events = character.get("events") or []
        events_by_character.append([event for event in existing_events if event.get("code") != "KeyM"])

    for clip in dialogue_clips:
        clip_id = str(clip.get("id") or "")
        wav_path = package_dir / "audio" / f"{clip_id}.wav"
        if not clip_id or not wav_path.exists():
            raise BannyPackageError(f"dialogue audio is missing for clip {clip_id or '<unknown>'}")
        character_index = SPEAKER_CHARACTER_INDEX.get(_speaker_from_clip(clip), 0)
        if character_index >= len(events_by_character):
            continue
        events_by_character[character_index].extend(detect_mouth_events(wav_path, offset=float(clip.get("start") or 0)))

    for character, events in zip(characters, events_by_character):
        character["events"] = sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))

    show_path.write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _speaker_from_clip(clip: dict[str, Any]) -> str:
    name = str(clip.get("name") or "").strip().lower()
    if "-" in name:
        return name.split("-", 1)[0]
    return name or "split"


def _validate_show_json(path: Path) -> None:
    if not path.exists():
        raise BannyPackageError("unpacked package is missing show.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "stage" not in payload:
        raise BannyPackageError("show.json is missing stage")


def _zip_directory(source: Path, out: Path) -> None:
    if out.exists():
        out.unlink()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_STORED) as archive:
        for path in sorted(source.rglob("*")):
            if path.is_file() and not path.name.startswith("._"):
                archive.write(path, path.relative_to(source).as_posix())


def copy_template(source: Path, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, destination)
