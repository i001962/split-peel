from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from split_peel.motion import SPEAKER_CHARACTER_INDEX
from split_peel.package_ids import make_id
from split_peel.voice_manifest import load_voice_manifest


class PerformancePlanError(RuntimeError):
    pass


def load_performance_plan(path: Optional[Path]) -> dict[str, Any]:
    if not path:
        return {}
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise PerformancePlanError("performance plan must be a JSON object")
    return payload


def apply_performance_plan(
    stage: dict[str, Any],
    plan: dict[str, Any],
    voice_manifest_path: Optional[Path],
) -> float:
    if not plan:
        return 0.0
    if not voice_manifest_path:
        raise PerformancePlanError("performance plan requires a voice manifest")

    voice_manifest = load_voice_manifest(voice_manifest_path)
    clips_by_line_id = {str(clip.get("line_id")): clip for clip in voice_manifest.get("clips") or []}
    _merge_reaction_definitions(stage, plan.get("reactionLibrary") or plan.get("reactions") or [])

    end = 0.0
    for index, beat in enumerate(plan.get("beats") or []):
        if not isinstance(beat, dict):
            continue
        start = _resolve_start(beat, clips_by_line_id)
        duration = _resolve_duration(beat)
        end = max(end, start + duration)
        reaction_id = str(beat.get("reaction") or beat.get("reactionID") or "").strip()
        if reaction_id:
            _apply_reaction_instance(stage, beat, index, reaction_id, start, duration)
        camera = beat.get("camera") or beat.get("shot")
        if isinstance(camera, dict):
            _apply_camera_cue(stage, beat, index, camera, start, duration)
    return round(end, 3)


def _merge_reaction_definitions(stage: dict[str, Any], definitions: list[Any]) -> None:
    if not definitions:
        return
    library = stage.setdefault("reactionLibrary", [])
    if not isinstance(library, list):
        stage["reactionLibrary"] = library = []
    existing = {str(item.get("id")) for item in library if isinstance(item, dict)}
    for definition in definitions:
        if not isinstance(definition, dict):
            continue
        reaction_id = str(definition.get("id") or "").strip()
        if reaction_id and reaction_id not in existing:
            library.append(definition)
            existing.add(reaction_id)


def _resolve_start(beat: dict[str, Any], clips_by_line_id: dict[str, dict[str, Any]]) -> float:
    line_id = str(beat.get("line_id") or beat.get("lineId") or "").strip()
    if not line_id:
        return round(float(beat.get("start") or beat.get("at") or 0), 3)
    clip = clips_by_line_id.get(line_id)
    if not clip:
        raise PerformancePlanError(f"performance beat references unknown line_id: {line_id}")
    anchor = str(beat.get("anchor") or "start").strip().lower()
    clip_start = float(clip.get("start") or 0)
    clip_duration = float(clip.get("duration") or 0)
    if anchor == "end":
        start = clip_start + clip_duration
    elif anchor in {"mid", "middle", "center"}:
        start = clip_start + clip_duration / 2
    else:
        start = clip_start
    return round(start + float(beat.get("offset") or 0), 3)


def _resolve_duration(beat: dict[str, Any]) -> float:
    raw = beat.get("duration") or beat.get("dur") or 1.0
    return round(max(0.05, float(raw)), 3)


def _apply_reaction_instance(
    stage: dict[str, Any],
    beat: dict[str, Any],
    index: int,
    reaction_id: str,
    start: float,
    duration: float,
) -> None:
    characters = stage.get("characters")
    if not isinstance(characters, list) or not characters:
        raise PerformancePlanError("stage is missing characters")
    character_index = _character_index(beat.get("character"), characters)
    if character_index >= len(characters):
        raise PerformancePlanError(f"performance beat references missing character index: {character_index}")
    character = characters[character_index]
    reactions = character.setdefault("reactions", [])
    if not isinstance(reactions, list):
        character["reactions"] = reactions = []
    instance_id = str(beat.get("id") or make_id(f"{reaction_id}-{character_index}-{start}-{index}"))
    reactions.append(
        {
            "id": instance_id,
            "reactionID": reaction_id,
            "start": start,
            "dur": duration,
            "intensity": float(beat.get("intensity") or 1),
        }
    )


def _character_index(value: Any, characters: list[dict[str, Any]]) -> int:
    if value is None:
        return 0
    raw = str(value).strip().lower()
    if raw.isdigit():
        return int(raw)
    if raw in SPEAKER_CHARACTER_INDEX:
        return SPEAKER_CHARACTER_INDEX[raw]
    for index, character in enumerate(characters):
        if str(character.get("name") or "").strip().lower() == raw:
            return index
    raise PerformancePlanError(f"unknown character reference: {value}")


def _apply_camera_cue(
    stage: dict[str, Any],
    beat: dict[str, Any],
    index: int,
    camera: dict[str, Any],
    start: float,
    duration: float,
) -> None:
    background = _background_reference(stage, start)
    if not background:
        return
    tracks = stage.setdefault("backgroundTracks", [])
    camera_track = next((track for track in tracks if track.get("id") == "camera-beats"), None)
    if camera_track is None:
        camera_track = {"id": "camera-beats", "name": "Camera Beats", "hidden": False, "cues": [], "presence": []}
        tracks.append(camera_track)
    cam_state = {
        "x": float(camera.get("x", 0.5)),
        "y": float(camera.get("y", 0.5)),
        "zoom": float(camera.get("zoom", 1.0)),
    }
    cue_id = str(beat.get("camera_id") or beat.get("shot_id") or make_id(f"camera-{start}-{index}"))
    camera_track.setdefault("cues", []).append(
        {
            "id": cue_id,
            "assetID": background["assetID"],
            "start": start,
            "dur": duration,
            "crop": background.get("crop") or "cover",
            "label": str(beat.get("id") or cue_id),
            "camFrom": cam_state,
            "camTo": cam_state,
        }
    )


def _background_reference(stage: dict[str, Any], start: float) -> Optional[dict[str, Any]]:
    for track in reversed(stage.get("backgroundTracks") or []):
        for cue in reversed(track.get("cues") or []):
            cue_start = float(cue.get("start") or 0)
            cue_dur = float(cue.get("dur") or 0)
            if cue_start <= start < cue_start + cue_dur:
                return cue
    for track in reversed(stage.get("backgroundTracks") or []):
        cues = track.get("cues") or []
        if cues:
            return cues[0]
    return None
