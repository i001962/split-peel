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
        events_by_character[speaker_index].extend(clip.eye_events)
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
        events.append({"code": "Comma", "down": True, "t": round(t, 3)})
        events.append({"code": "Comma", "down": False, "t": round(t + 0.11, 3)})
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
    events = _resolve_eye_event_conflicts(events)
    return sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))


def _resolve_eye_event_conflicts(events: list[dict[str, object]]) -> list[dict[str, object]]:
    eye_codes = {"Comma", "Period", "Slash"}
    non_eye_events = [event for event in events if event.get("code") not in eye_codes]
    sorted_events = sorted(events, key=lambda event: (float(event["t"]), str(event["code"]), not bool(event["down"])))
    pending: dict[str, dict[str, object]] = {}
    pairs: list[tuple[int, float, float, dict[str, object], dict[str, object]]] = []
    priority_by_code = {"Comma": 1, "Period": 2, "Slash": 2}

    for event in sorted_events:
        code = event.get("code")
        if code not in eye_codes:
            continue
        if event.get("down"):
            if str(code) in pending:
                continue
            pending[str(code)] = event
            continue
        start_event = pending.pop(str(code), None)
        if start_event is None:
            continue
        start = float(start_event["t"])
        end = float(event["t"])
        if end <= start:
            continue
        pairs.append((priority_by_code.get(str(code), 1), start, end, start_event, event))

    selected: list[tuple[float, float, dict[str, object], dict[str, object]]] = []
    for _priority, start, end, start_event, end_event in sorted(pairs, key=lambda item: (-item[0], item[1])):
        padded_start = start - 0.08
        padded_end = end + 0.08
        if any(padded_start < kept_end and padded_end > kept_start for kept_start, kept_end, _, _ in selected):
            continue
        selected.append((padded_start, padded_end, start_event, end_event))

    eye_events: list[dict[str, object]] = []
    for _start, _end, start_event, end_event in selected:
        eye_events.extend([start_event, end_event])
    return non_eye_events + eye_events
