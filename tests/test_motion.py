from split_peel.audio import VoiceClip
from split_peel.motion import build_character_events


def test_build_character_events_uses_custom_speaker_map():
    clips = [
        VoiceClip("perry1", "perry", "Perry line", 0.5, 1.0, [{"code": "KeyM", "down": True, "t": 0.6}]),
        VoiceClip("faux1", "fauxnana", "Faux line", 2.0, 1.0, [{"code": "KeyM", "down": True, "t": 2.1}]),
    ]

    events = build_character_events(clips, 2, 4.0, {"perry": 0, "fauxnana": 1})

    assert {"code": "KeyM", "down": True, "t": 0.6} in events[0]
    assert {"code": "KeyM", "down": True, "t": 2.1} in events[1]
    assert {"code": "KeyM", "down": True, "t": 2.1} not in events[0]
