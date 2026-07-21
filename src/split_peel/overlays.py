from __future__ import annotations

import json
import shutil
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

from split_peel.package_ids import make_id


def load_overlay_manifest(path: Path | None) -> list[dict[str, Any]]:
    if path is None:
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    overlays = payload.get("overlays", payload if isinstance(payload, list) else [])
    if not isinstance(overlays, list):
        raise ValueError("overlay manifest must be a list or an object with overlays[]")
    return overlays


def apply_overlays(package_dir: Path, show: dict[str, Any], overlays: list[dict[str, Any]], duration: float) -> None:
    if not overlays:
        return

    assets = show.setdefault("assets", [])
    stage = show.setdefault("stage", {})
    audio_tracks = stage.setdefault("audioTracks", [])
    assets_dir = package_dir / "assets"
    assets_dir.mkdir(parents=True, exist_ok=True)

    for index, overlay in enumerate(overlays):
        source = Path(str(overlay["file"])).expanduser()
        if not source.is_absolute():
            source = Path.cwd() / source
        if not source.exists():
            raise FileNotFoundError(f"overlay asset does not exist: {source}")

        name = str(overlay.get("name") or source.stem)
        asset_id = make_id(f"asset-{name}-{source.name}-{index}")
        cue_id = make_id(f"cue-{name}-{index}")
        track_id = make_id(f"track-{name}-{index}")
        destination = assets_dir / f"{asset_id}{source.suffix.lower()}"
        shutil.copy2(source, destination)

        assets.append(
            {
                "file": destination.name,
                "id": asset_id,
                "kind": str(overlay.get("kind") or _asset_kind(source)),
                "name": name,
            }
        )

        start = float(overlay.get("start", 0))
        cue_duration = _overlay_duration(overlay.get("dur", "full"), start, duration)
        audio_tracks.append(
            {
                "clips": [],
                "cues": [
                    {
                        "assetID": asset_id,
                        "dur": round(cue_duration, 3),
                        "from": {
                            "scale": float(overlay.get("scale", 0.3)),
                            "x": float(overlay.get("x", 0.5)),
                            "y": float(overlay.get("y", 0.5)),
                        },
                        "id": cue_id,
                        "start": round(start, 3),
                    }
                ],
                "fx": {
                    "gain": 1,
                    "high": 0,
                    "low": 0,
                    "mid": 0,
                    "pan": "narrow",
                    "reverb": 0,
                },
                "hidden": False,
                "id": track_id,
                "name": str(overlay.get("trackName") or name),
                "presence": [],
            }
        )


def build_pfp_overlays(script: dict[str, Any], asset_dir: Path, limit: int = 5) -> dict[str, Any]:
    source_casts = {
        cast.get("username"): cast
        for cast in script.get("sourceCasts") or []
        if cast.get("username") and cast.get("pfpUrl")
    }
    if not source_casts:
        return {"overlays": []}

    asset_dir.mkdir(parents=True, exist_ok=True)
    overlays: list[dict[str, Any]] = []
    used: set[str] = set()
    positions = [{"x": 0.08, "y": 0.28}, {"x": 0.92, "y": 0.28}]

    for line in script.get("dialogue") or []:
        username = line.get("sourceUsername")
        if not username or username in used or username not in source_casts:
            continue
        cast = source_casts[username]
        local_path = _download_pfp(str(cast["pfpUrl"]), username, asset_dir)
        position = positions[len(overlays) % len(positions)]
        start = max(0.0, float(line.get("start") or 0) - 0.2)
        overlays.append(
            {
                "name": f"@{username} pfp",
                "file": str(local_path),
                "start": round(start, 3),
                "dur": 5.0,
                "x": position["x"],
                "y": position["y"],
                "scale": 0.12,
            }
        )
        used.add(username)
        if len(overlays) >= limit:
            break

    return {"overlays": overlays}


def _overlay_duration(raw_duration: Any, start: float, show_duration: float) -> float:
    if raw_duration == "full" or raw_duration is None:
        return max(0.0, show_duration - start)
    return float(raw_duration)


def _asset_kind(source: Path) -> str:
    if source.suffix.lower() in {".mp4", ".mov", ".m4v", ".webm"}:
        return "video"
    return "image"


def _download_pfp(url: str, username: str, asset_dir: Path) -> Path:
    parsed = urllib.parse.urlparse(url)
    suffix = Path(parsed.path).suffix
    if suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        suffix = ".png"
    destination = asset_dir / f"{_slug(username)}-pfp{suffix}"
    request = urllib.request.Request(url, headers={"User-Agent": "split-peel/0.1"})
    with urllib.request.urlopen(request, timeout=30) as response:
        destination.write_bytes(response.read())
    return destination


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-")[:80]
