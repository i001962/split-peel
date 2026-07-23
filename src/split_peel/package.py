from __future__ import annotations

import json
import math
import os
import re
import shutil
import tempfile
import wave
import zipfile
from pathlib import Path
from typing import Any, Optional

from split_peel.asset_registry import copy_registry_assets, load_asset_registry, scene_preset
from split_peel.audio import VoiceClip, detect_eye_events, detect_mouth_events, synthesize_dialogue
from split_peel.characters import character_ids, character_map
from split_peel.motion import SPEAKER_CHARACTER_INDEX, build_character_events
from split_peel.overlays import apply_overlays, load_overlay_manifest
from split_peel.performance_plan import apply_performance_plan, load_performance_plan
from split_peel.voice_manifest import copy_manifest_audio, voice_clips_from_manifest


class BannyPackageError(RuntimeError):
    pass


def write_starter_show(out: Path, character_count: int = 2, overwrite: bool = False) -> None:
    if out.exists():
        if not overwrite:
            raise BannyPackageError(f"{out} already exists; pass --overwrite to replace it")
        if out.is_dir():
            shutil.rmtree(out)
        else:
            out.unlink()

    count = max(1, min(4, int(character_count)))
    bodies = ["original", "original", "alien", "orange"]
    characters = []
    for index in range(count):
        x = 0.5 if count == 1 else 0.25 + 0.5 * index / (count - 1)
        default_names = ["Split", "Peel", "Banny 3", "Banny 4"]
        characters.append(
            {
                "body": bodies[index % len(bodies)],
                "x": round(x, 3),
                "depth": 0,
                "size": 2,
                "face": 1 if x <= 0.5 else -1,
                "baseOutfit": {},
                "subs": [],
                "clips": [],
                "voicePitch": 0,
                "voiceSpeed": 1,
                "events": [],
                "reactions": [],
                "armedGroups": ["move", "depth", "tilt", "talk", "blink", "jump", "spin", "zoom"],
                "name": default_names[index],
                "trackFx": {
                    "gain": 1,
                    "low": 0,
                    "mid": 0,
                    "high": 0,
                    "reverb": 0,
                    "pan": "follow",
                },
                "speed": 320,
                "rotationSpeed": 90,
                "rotationPivot": None,
                "wobble": 7,
                "hidden": False,
                "locked": False,
                "solo": False,
                "presence": [],
            }
        )

    show = {
        "version": 3,
        "assets": [],
        "settings": {"activeScene": 0, "lightSize": 0, "frameW": 16, "frameH": 9},
        "show": [{"sceneID": "", "name": "Starter", "from": 0, "to": 1}],
        "stage": {
            "characters": characters,
            "reactionLibrary": [],
            "audioTracks": [{"id": "dialogue", "name": "Dialogue", "fx": _default_track_fx(), "clips": [], "cues": [], "hidden": False, "presence": []}],
            "imageTracks": [],
            "backgroundTracks": [],
            "lightTracks": [],
            "lights": [],
            "cropAnchors": [],
            "gScale": 0.6,
            "gravity": 1,
            "gSize": 1,
            "rowOrder": [],
        },
    }

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="split-peel-starter-") as tmp:
        tmp_path = Path(tmp)
        (tmp_path / "show.json").write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        _write_package_output(tmp_path, out)


def _default_track_fx() -> dict[str, Any]:
    return {"gain": 1, "low": 0, "mid": 0, "high": 0, "reverb": 0, "pan": "follow"}


def inspect_package(template: Path) -> dict[str, Any]:
    if template.is_dir():
        show_path = template / "show.json"
        if not show_path.exists():
            raise BannyPackageError(f"{template} does not contain show.json")
        names = [str(path.relative_to(template)) for path in template.rglob("*") if path.is_file()]
        show = json.loads(show_path.read_text(encoding="utf-8"))
    else:
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
        _copy_package_to_dir(template, tmp_path)
        _validate_show_json(tmp_path / "show.json")
        _zip_directory(tmp_path, out)


def unpack_package(template: Path, out: Path, overwrite: bool = False) -> None:
    if out.exists():
        if not overwrite:
            raise BannyPackageError(f"{out} already exists; pass --overwrite to replace it")
        shutil.rmtree(out)

    out.mkdir(parents=True)
    _copy_package_to_dir(template, out)
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


def repair_banny_wardrobe(package: Path, catalog: dict[str, Any]) -> list[dict[str, str]]:
    if package.is_dir():
        return _repair_banny_wardrobe_in_dir(package, catalog)

    with tempfile.TemporaryDirectory(prefix="split-peel-") as tmp:
        tmp_path = Path(tmp)
        with zipfile.ZipFile(package) as archive:
            archive.extractall(tmp_path)
        repairs = _repair_banny_wardrobe_in_dir(tmp_path, catalog)
        if repairs:
            _zip_directory(tmp_path, package)
        return repairs


def build_show(
    template: Path,
    script: Optional[Path],
    out: Path,
    background_gain: Optional[float] = None,
    overlays: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
    reuse_audio_from: Optional[Path] = None,
    skip_voice: bool = False,
    voice_manifest: Optional[Path] = None,
    performance_plan: Optional[Path] = None,
) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="split-peel-") as tmp:
        tmp_path = Path(tmp)
        _copy_package_to_dir(template, tmp_path)
        _validate_show_json(tmp_path / "show.json")
        reuse_audio_dirs = _reuse_audio_dirs(tmp_path, reuse_audio_from, include_template=skip_voice)

        if script is not None:
            payload = json.loads(script.read_text(encoding="utf-8"))
            _apply_script_to_package(
                tmp_path,
                payload,
                background_gain=background_gain,
                overlays_path=overlays,
                characters=characters,
                reuse_audio_dirs=reuse_audio_dirs,
                skip_voice=skip_voice,
                voice_manifest_path=voice_manifest,
                performance_plan_path=performance_plan,
            )

        shutil.rmtree(tmp_path / "_reuse_audio", ignore_errors=True)
        _write_package_output(tmp_path, out)


def build_show_from_registry(
    registry_path: Path,
    script: Path,
    out: Path,
    scene_preset_id: str = "default",
    background_gain: Optional[float] = None,
    overlays: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
    voice_manifest: Optional[Path] = None,
    performance_plan: Optional[Path] = None,
) -> None:
    registry = load_asset_registry(registry_path)
    preset = scene_preset(registry, scene_preset_id)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="split-peel-compose-") as tmp:
        tmp_path = Path(tmp)
        show = {
            "version": 3,
            "assets": registry.get("assets") or [],
            "settings": preset.get("settings") or {"activeScene": 0, "lightSize": 0, "frameW": 16, "frameH": 9},
            "show": preset.get("show") or [{"sceneID": "", "name": str(preset.get("name") or scene_preset_id), "from": 0, "to": 1}],
            "stage": preset.get("stage") or {},
        }
        (tmp_path / "show.json").write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        copy_registry_assets(registry_path, registry, tmp_path / "assets")
        _validate_show_json(tmp_path / "show.json")
        payload = json.loads(script.read_text(encoding="utf-8"))
        _apply_script_to_package(
            tmp_path,
            payload,
            background_gain=background_gain,
            overlays_path=overlays,
            characters=characters,
            voice_manifest_path=voice_manifest,
            performance_plan_path=performance_plan,
            skip_voice=bool(voice_manifest),
        )
        _write_package_output(tmp_path, out)


def _apply_script_to_package(
    package_dir: Path,
    script: dict[str, Any],
    background_gain: Optional[float] = None,
    overlays_path: Optional[Path] = None,
    characters: Optional[dict[str, Any]] = None,
    reuse_audio_dirs: Optional[list[Path]] = None,
    skip_voice: bool = False,
    voice_manifest_path: Optional[Path] = None,
    performance_plan_path: Optional[Path] = None,
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
    if voice_manifest_path:
        copy_manifest_audio(voice_manifest_path, audio_dir)
        clips = voice_clips_from_manifest(voice_manifest_path)
    else:
        clips = synthesize_dialogue(
            dialogue,
            audio_dir,
            characters=characters,
            reuse_audio_dirs=reuse_audio_dirs,
            skip_voice=skip_voice,
        )
    if not clips:
        raise BannyPackageError("script did not produce any voice clips")

    _apply_character_appearance(stage, characters)
    _replace_dialogue_track(stage, clips)
    _set_background_audio_gain(stage, background_gain)
    dialogue_end = max(clip.start + clip.duration for clip in clips)
    effect_end = _append_outro_effect(stage, script, audio_dir, dialogue_end)
    duration = max(dialogue_end, effect_end) + 1.0
    _replace_character_events(stage, clips, duration)
    _replace_character_subtitles(stage, clips)
    performance_end = apply_performance_plan(stage, load_performance_plan(performance_plan_path), voice_manifest_path)
    if performance_end:
        duration = max(duration, performance_end + 1.0)
    _extend_show_duration(show, duration)
    _trim_timeline_to_duration(stage, duration)
    apply_overlays(package_dir, show, load_overlay_manifest(overlays_path), duration, episode_type=script.get("episodeType"))
    _remove_unreferenced_audio(package_dir, stage)

    show_path.write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _copy_package_to_dir(source: Path, destination: Path) -> None:
    if source.is_dir():
        for item in source.iterdir():
            target = destination / item.name
            if item.is_dir():
                shutil.copytree(item, target)
            else:
                shutil.copy2(item, target)
        return

    with zipfile.ZipFile(source) as archive:
        archive.extractall(destination)


def _write_package_output(package_dir: Path, out: Path) -> None:
    if out.exists():
        if out.is_dir():
            shutil.rmtree(out)
        else:
            out.unlink()
    if out.suffix == ".bannyshow":
        shutil.copytree(package_dir, out)
        return
    _zip_directory(package_dir, out)


def _reuse_audio_dirs(package_dir: Path, reuse_audio_from: Optional[Path], include_template: bool = False) -> list[Path]:
    dirs: list[Path] = []
    if include_template:
        template_audio = package_dir / "audio"
        if template_audio.exists():
            dirs.append(template_audio)
    if not reuse_audio_from:
        return dirs

    source = reuse_audio_from.expanduser()
    if not source.exists():
        raise BannyPackageError(f"reuse audio source does not exist: {source}")
    if source.is_dir():
        audio_dir = source / "audio"
        if audio_dir.exists():
            dirs.append(audio_dir)
        return dirs

    extracted = package_dir / "_reuse_audio"
    extracted.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            if info.filename.startswith("audio/") and info.filename.endswith(".wav"):
                destination = extracted / Path(info.filename).name
                destination.write_bytes(archive.read(info.filename))
    dirs.append(extracted)
    return dirs


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


def _append_outro_effect(stage: dict[str, Any], script: dict[str, Any], audio_dir: Path, dialogue_end: float) -> float:
    effect = script.get("outroEffect") or {}
    if not isinstance(effect, dict) or effect.get("enabled") is False:
        return dialogue_end
    if effect.get("type") != "static-disconnect":
        return dialogue_end

    audio_tracks = stage.get("audioTracks")
    if not isinstance(audio_tracks, list) or not audio_tracks:
        return dialogue_end

    duration = _outro_effect_duration(effect)
    start = round(dialogue_end + 0.12, 3)
    clip_id = "static-disconnect"
    _write_static_disconnect_wav(audio_dir / f"{clip_id}.wav", duration)
    audio_tracks[0].setdefault("clips", []).append(
        {
            "dur": duration,
            "fx": {
                "gain": 0.82,
                "high": 10,
                "low": -8,
                "mid": 2,
                "pan": "follow",
                "reverb": 0,
            },
            "id": clip_id,
            "name": "effect-static-disconnect",
            "offset": 0,
            "srcDur": duration,
            "start": start,
        }
    )
    return start + duration


def _outro_effect_duration(effect: dict[str, Any]) -> float:
    try:
        duration = float(effect.get("durationSec") or 0.85)
    except (TypeError, ValueError):
        duration = 0.85
    return round(max(0.25, min(3.0, duration)), 3)


def _write_static_disconnect_wav(path: Path, duration: float, sample_rate: int = 22050) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame_count = max(1, int(duration * sample_rate))
    seed = 0x5EED
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frame_count):
            seed = (1103515245 * seed + 12345) & 0x7FFFFFFF
            white = ((seed / 0x7FFFFFFF) * 2.0) - 1.0
            crackle = 1.0 if index % 997 < 24 else 0.0
            fade = 1.0 - (index / frame_count)
            carrier = math.sin(2 * math.pi * 4300 * (index / sample_rate)) * 0.24
            sample = int(max(-1.0, min(1.0, (white * 0.72 + carrier + crackle * 0.55) * fade)) * 22000)
            wav.writeframesraw(sample.to_bytes(2, byteorder="little", signed=True))


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


def _apply_character_appearance(stage: dict[str, Any], characters: Optional[dict[str, Any]]) -> None:
    profiles = characters or {}
    profile_map = character_map(profiles)
    speaker_ids = character_ids(profiles)
    stage_characters = stage.get("characters")
    if not isinstance(stage_characters, list):
        return

    for index, speaker_id in enumerate(speaker_ids):
        if index >= len(stage_characters):
            continue
        profile = profile_map.get(speaker_id) or {}
        appearance = profile.get("appearance") or {}
        base_outfit = appearance.get("baseOutfit")
        if isinstance(base_outfit, dict):
            _apply_base_outfit(stage_characters[index], base_outfit)
        if appearance.get("body"):
            stage_characters[index]["body"] = str(appearance["body"])


def _apply_base_outfit(character: dict[str, Any], base_outfit: dict[str, Any]) -> None:
    outfit = character.setdefault("baseOutfit", {})
    if not isinstance(outfit, dict):
        outfit = {}
        character["baseOutfit"] = outfit

    normalized = {str(slot): str(name) for slot, name in base_outfit.items() if name}
    for slot in normalized:
        for hidden_slot in _exclusive_slots(slot):
            outfit.pop(hidden_slot, None)
    outfit.update(normalized)


def _exclusive_slots(slot: str) -> tuple[str, ...]:
    if slot == "4":
        return ("6", "12")
    if slot == "9":
        return ("10", "11")
    return ()


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
    retimed_codes = {"KeyM", "Comma", "Period", "Slash"}
    for character in characters:
        existing_events = character.get("events") or []
        events_by_character.append([event for event in existing_events if event.get("code") not in retimed_codes])

    for clip in dialogue_clips:
        if _is_outro_effect_clip(clip):
            continue
        clip_id = str(clip.get("id") or "")
        wav_path = package_dir / "audio" / f"{clip_id}.wav"
        if not clip_id or not wav_path.exists():
            raise BannyPackageError(f"dialogue audio is missing for clip {clip_id or '<unknown>'}")
        character_index = SPEAKER_CHARACTER_INDEX.get(_speaker_from_clip(clip), 0)
        if character_index >= len(events_by_character):
            continue
        start = float(clip.get("start") or 0)
        events_by_character[character_index].extend(detect_mouth_events(wav_path, offset=start))
        events_by_character[character_index].extend(detect_eye_events(wav_path, offset=start))

    for character, events in zip(characters, events_by_character):
        character["events"] = sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))

    show_path.write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _repair_banny_wardrobe_in_dir(package_dir: Path, catalog: dict[str, Any]) -> list[dict[str, str]]:
    valid_by_slot = _catalog_outfits_by_slot(catalog)
    if not valid_by_slot:
        return []

    show_path = package_dir / "show.json"
    show = json.loads(show_path.read_text(encoding="utf-8"))
    characters = ((show.get("stage") or {}).get("characters") or [])
    repairs: list[dict[str, str]] = []

    for character_index, character in enumerate(characters):
        base_outfit = character.get("baseOutfit")
        if not isinstance(base_outfit, dict):
            continue
        for slot, outfit in list(base_outfit.items()):
            slot_key = str(slot)
            outfit_name = str(outfit)
            if outfit_name in valid_by_slot.get(slot_key, set()):
                continue
            del base_outfit[slot]
            repairs.append(
                {
                    "character": str(character_index),
                    "slot": slot_key,
                    "outfit": outfit_name,
                    "action": "removed-invalid-baseOutfit",
                }
            )

    if repairs:
        show_path.write_text(json.dumps(show, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return repairs


def _catalog_outfits_by_slot(catalog: dict[str, Any]) -> dict[str, set[str]]:
    valid_by_slot: dict[str, set[str]] = {}
    for slot_entry in catalog.get("slots") or []:
        slot = str(slot_entry.get("slot"))
        names = {
            str(outfit.get("name"))
            for outfit in slot_entry.get("outfits") or []
            if isinstance(outfit, dict) and outfit.get("name")
        }
        valid_by_slot[slot] = names
    eyes = {str(name) for name in catalog.get("eyes") or [] if name}
    if eyes:
        valid_by_slot["5"] = eyes
    mouths = {str(name) for name in catalog.get("mouths") or [] if name}
    if mouths:
        valid_by_slot["7"] = mouths
    return valid_by_slot


def _speaker_from_clip(clip: dict[str, Any]) -> str:
    name = str(clip.get("name") or "").strip().lower()
    if "-" in name:
        return name.split("-", 1)[0]
    return name or "split"


def _is_outro_effect_clip(clip: dict[str, Any]) -> bool:
    clip_id = str(clip.get("id") or "").strip()
    name = str(clip.get("name") or "").strip()
    return clip_id == "static-disconnect" or name == "effect-static-disconnect"


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
