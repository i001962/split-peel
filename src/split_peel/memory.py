from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


DEFAULT_MEMORY_DIR = Path("memory")


def load_episode_memory(memory_dir: Optional[Path] = None, limit: int = 5) -> list[dict[str, Any]]:
    if memory_dir is None:
        memory_dir = DEFAULT_MEMORY_DIR
    if not memory_dir.exists():
        return []
    episodes = []
    for path in sorted(memory_dir.glob("*.json"), reverse=True):
        try:
            episodes.append(json.loads(path.read_text(encoding="utf-8")))
        except json.JSONDecodeError:
            continue
        if len(episodes) >= limit:
            break
    return episodes


def save_episode_memory(script: dict[str, Any], memory_dir: Optional[Path] = None) -> Path:
    if memory_dir is None:
        memory_dir = DEFAULT_MEMORY_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc)
    slug = _slug(script.get("title") or "episode")
    path = memory_dir / f"{now.strftime('%Y%m%dT%H%M%SZ')}-{slug}.json"
    payload = {
        "createdAt": now.isoformat(),
        "title": script.get("title"),
        "match": script.get("match"),
        "beats": script.get("beats") or [],
        "sourceCastUsers": [cast.get("username") for cast in script.get("sourceCasts") or []],
        "fallbackCastCount": len(script.get("fallbackCasts") or []),
        "dialogue": [
            {
                "speaker": line.get("speaker"),
                "line": line.get("line"),
                "tone": line.get("tone"),
            }
            for line in script.get("dialogue") or []
        ],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return path


def _slug(value: str) -> str:
    return "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-")[:80]
