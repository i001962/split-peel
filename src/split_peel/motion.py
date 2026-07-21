from __future__ import annotations

from split_peel.audio import VoiceClip


SPEAKER_CHARACTER_INDEX = {
    "split": 0,
    "peel": 1,
}


def build_character_events(clips: list[VoiceClip], character_count: int, duration: float) -> list[list[dict[str, object]]]:
    events_by_character: list[list[dict[str, object]]] = [[] for _ in range(character_count)]

    for character_index in range(character_count):
        events_by_character[character_index].extend(_blink_events(duration, phase=character_index * 1.3))

    for clip in clips:
        speaker_index = SPEAKER_CHARACTER_INDEX.get(clip.speaker, 0)
        if speaker_index >= character_count:
            continue
        events_by_character[speaker_index].extend(clip.mouth_events)
        events_by_character[speaker_index].extend(_speaker_reaction_events(clip.start))

        listener_index = 1 - speaker_index if character_count > 1 else speaker_index
        if listener_index < character_count:
            events_by_character[listener_index].extend(_listener_reaction_events(clip.start + 0.4))

    return [_sorted_events(events) for events in events_by_character]


def _blink_events(duration: float, phase: float) -> list[dict[str, object]]:
    events: list[dict[str, object]] = []
    t = 1.6 + phase
    intervals = [3.1, 4.4, 3.7, 5.2]
    index = 0
    while t < duration:
        events.append({"code": "Period", "down": True, "t": round(t, 3)})
        events.append({"code": "Period", "down": False, "t": round(t + 0.11, 3)})
        t += intervals[index % len(intervals)]
        index += 1
    return events


def _speaker_reaction_events(start: float) -> list[dict[str, object]]:
    return [
        {"code": "KeyT", "down": True, "t": round(start + 0.15, 3)},
        {"code": "KeyT", "down": False, "t": round(start + 0.27, 3)},
        {"code": "ArrowUp", "down": True, "t": round(start + 0.55, 3)},
        {"code": "ArrowUp", "down": False, "t": round(start + 0.66, 3)},
    ]


def _listener_reaction_events(start: float) -> list[dict[str, object]]:
    return [
        {"code": "KeyB", "down": True, "t": round(start, 3)},
        {"code": "KeyB", "down": False, "t": round(start + 0.09, 3)},
    ]


def _sorted_events(events: list[dict[str, object]]) -> list[dict[str, object]]:
    return sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))
