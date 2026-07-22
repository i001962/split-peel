from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional


DEFAULT_CHARACTERS_PATH = Path("characters/default.json")


DEFAULT_CHARACTERS = {
    "characters": [
        {
            "id": "split",
            "displayName": "Split",
            "voice": {"openai": "ash", "local": "Alex"},
            "voiceDirection": (
                "Speak with a female cartoon banana sports-announcer voice: bright, elastic, "
                "mischievous, fast, and exaggerated, while still being understandable. "
                "Give dry jokes a theatrical commentator punch."
            ),
            "appearance": {
                "baseOutfit": {
                    "5": "eyeliner",
                    "7": "gapteeth",
                    "9": "sweatsuit",
                    "12": "dorthy-hair",
                }
            },
            "personality": [
                "cartoon banana football commentator",
                "dry, sharp, skeptical, and stat-aware",
                "female lead host with eyeliner, gap teeth, a sweatsuit, and Dorthy hair",
                "sounds like she is calling the match from inside a fruit bowl",
                "enjoys calling out overconfident fan bases and lazy tactical takes",
            ],
            "preferences": {
                "targets": ["meltdowns", "lazy tactical takes", "fans declaring eras after one match"],
                "avoid": ["slurs", "real harassment", "punching down"],
            },
            "catchphrases": ["put it in the match report"],
        },
        {
            "id": "peel",
            "displayName": "Peel",
            "voice": {"openai": "verse", "local": "Samantha"},
            "voiceDirection": (
                "Speak like a bouncy cartoon banana co-commentator: bright, theatrical, "
                "playful, quick, and slightly chaotic. React to fan comments like every "
                "post is a dramatic plot twist."
            ),
            "personality": [
                "cartoon banana co-commentator",
                "bright, bouncy, theatrical, and playful",
                "warm but mischievous",
                "turns fan comments into escalating bits and silly sports-drama",
            ],
            "preferences": {
                "targets": ["dramatic fans", "premature victory laps", "conspiracy-level referee discourse"],
                "avoid": ["slurs", "real harassment", "punching down"],
            },
            "catchphrases": ["the timeline has entered stoppage time"],
        },
    ]
}


def load_characters(path: Optional[Path] = None) -> dict[str, Any]:
    if path is None:
        path = DEFAULT_CHARACTERS_PATH
    if not path.exists():
        return DEFAULT_CHARACTERS
    return json.loads(path.read_text(encoding="utf-8"))


def character_map(characters: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {str(character.get("id")): character for character in characters.get("characters") or []}


def character_ids(characters: dict[str, Any]) -> list[str]:
    ids = [str(character.get("id")) for character in characters.get("characters") or [] if character.get("id")]
    return ids or ["split", "peel"]


def voice_for_speaker(characters: dict[str, Any], speaker: str, provider: str, fallback: str) -> str:
    character = character_map(characters).get(speaker) or {}
    voice = character.get("voice") or {}
    return str(voice.get(provider) or fallback)


def voice_speed_for_speaker(
    characters: dict[str, Any],
    speaker: str,
    provider: str,
    fallback: float = 1.0,
) -> float:
    character = character_map(characters).get(speaker) or {}
    voice = character.get("voice") or {}
    raw_speed = voice.get(f"{provider}Speed", fallback)
    try:
        speed = float(raw_speed)
    except (TypeError, ValueError) as error:
        raise ValueError(f"invalid {provider}Speed for speaker {speaker}: {raw_speed}") from error
    return max(0.25, min(speed, 4.0))


def instructions_for_speaker(characters: dict[str, Any], speaker: str, fallback: str) -> str:
    character = character_map(characters).get(speaker) or {}
    pieces = []
    if character.get("displayName"):
        pieces.append(f"Character name: {character['displayName']}.")
    if character.get("voiceDirection"):
        pieces.append("Voice direction: " + str(character["voiceDirection"]))
    if character.get("personality"):
        pieces.append("Personality: " + "; ".join(str(item) for item in character["personality"]) + ".")
    preferences = character.get("preferences") or {}
    if preferences.get("targets"):
        pieces.append("Comic targets: " + "; ".join(str(item) for item in preferences["targets"]) + ".")
    if preferences.get("avoid"):
        pieces.append("Avoid: " + "; ".join(str(item) for item in preferences["avoid"]) + ".")
    pieces.append(fallback)
    return " ".join(pieces)
