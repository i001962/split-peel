from __future__ import annotations

import json
import os
import zipfile
from pathlib import Path
from typing import Any


ASSET_REGISTRY_VERSION = 1


class AssetRegistryError(RuntimeError):
    pass


def extract_asset_registry(source: Path, out: Path, preset_id: str = "default", preset_name: str = "Default Studio") -> dict[str, Any]:
    show = _read_show_json(source)
    stage = show.get("stage")
    if not isinstance(stage, dict):
        raise AssetRegistryError("source show is missing stage")

    out.parent.mkdir(parents=True, exist_ok=True)
    registry = {
        "version": ASSET_REGISTRY_VERSION,
        "source_package": os.path.relpath(source, out.parent) if not source.is_absolute() else str(source),
        "assets": show.get("assets") or [],
        "scenePresets": [
            {
                "id": preset_id,
                "name": preset_name,
                "stage": stage,
                "settings": show.get("settings") or {"activeScene": 0, "lightSize": 0, "frameW": 16, "frameH": 9},
                "show": show.get("show") or [{"sceneID": "", "name": preset_name, "from": 0, "to": 1}],
            }
        ],
    }
    out.write_text(json.dumps(registry, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return registry


def load_asset_registry(path: Path) -> dict[str, Any]:
    registry = json.loads(path.read_text(encoding="utf-8"))
    if registry.get("version") != ASSET_REGISTRY_VERSION:
        raise AssetRegistryError(f"unsupported asset registry version: {registry.get('version')}")
    if not isinstance(registry.get("scenePresets"), list):
        raise AssetRegistryError("asset registry does not contain scenePresets")
    return registry


def scene_preset(registry: dict[str, Any], preset_id: str = "default") -> dict[str, Any]:
    for preset in registry.get("scenePresets") or []:
        if isinstance(preset, dict) and str(preset.get("id")) == preset_id:
            return preset
    raise AssetRegistryError(f"asset registry does not contain scene preset: {preset_id}")


def copy_registry_assets(registry_path: Path, registry: dict[str, Any], destination: Path) -> None:
    source = _resolve_source_package(registry_path, str(registry.get("source_package") or ""))
    destination.mkdir(parents=True, exist_ok=True)
    if source.is_dir():
        asset_dir = source / "assets"
        if asset_dir.exists():
            for file in asset_dir.iterdir():
                if file.is_file() and not file.name.startswith("."):
                    (destination / file.name).write_bytes(file.read_bytes())
        return
    if source.exists():
        with zipfile.ZipFile(source) as archive:
            for info in archive.infolist():
                if info.filename.startswith("assets/") and not info.is_dir():
                    (destination / Path(info.filename).name).write_bytes(archive.read(info.filename))


def _read_show_json(source: Path) -> dict[str, Any]:
    if source.is_dir():
        show_path = source / "show.json"
        if not show_path.exists():
            raise AssetRegistryError(f"{source} does not contain show.json")
        return json.loads(show_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(source) as archive:
        if "show.json" not in archive.namelist():
            raise AssetRegistryError(f"{source} does not contain show.json")
        return json.loads(archive.read("show.json").decode("utf-8"))


def _resolve_source_package(registry_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return registry_path.parent / path
