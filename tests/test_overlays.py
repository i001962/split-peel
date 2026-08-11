import json
from pathlib import Path

from split_peel.overlays import apply_overlays, build_key_moment_takeover_overlays, build_pfp_overlays


def test_apply_overlays_adds_asset_and_media_cue(tmp_path):
    source = tmp_path / "desk.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "imageTracks": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "desk", "file": str(source), "start": 2.5, "dur": "full", "x": 0.5, "y": 0.8, "scale": 0.45}],
        duration=10,
    )

    assert len(show["assets"]) == 1
    assert (package_dir / "assets" / show["assets"][0]["file"]).exists()
    assert show["stage"]["audioTracks"] == []
    track = show["stage"]["imageTracks"][0]
    assert track["name"] == "desk"
    assert track["cues"][0]["dur"] == 7.5
    assert track["cues"][0]["from"] == {"scale": 0.45, "x": 0.5, "y": 0.8}


def test_apply_overlays_marks_video_assets(tmp_path):
    source = tmp_path / "highlight.mp4"
    source.write_bytes(b"fake mp4")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "imageTracks": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "highlight replay", "file": str(source), "start": 4, "dur": 8, "x": 0.78, "y": 0.24, "scale": 0.28}],
        duration=20,
    )

    assert show["assets"][0]["kind"] == "video"
    assert show["stage"]["imageTracks"][0]["cues"][0]["assetID"] == show["assets"][0]["id"]


def test_apply_overlays_can_target_background_tracks(tmp_path):
    source = tmp_path / "stadium.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "backgroundTracks": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "stadium", "file": str(source), "target": "background", "start": 0, "dur": "full", "scale": 1.0}],
        duration=12,
    )

    assert show["stage"]["audioTracks"] == []
    assert show["stage"]["backgroundTracks"][0]["name"] == "stadium"
    assert show["stage"]["backgroundTracks"][0]["presence"] == []
    assert show["stage"]["backgroundTracks"][0]["cues"][0]["dur"] == 12
    assert show["stage"]["backgroundTracks"][0]["cues"][0]["crop"] == "cover"
    assert "from" not in show["stage"]["backgroundTracks"][0]["cues"][0]


def test_apply_overlays_can_place_visual_tracks_around_cast(tmp_path):
    behind = tmp_path / "tactics-board.png"
    front = tmp_path / "desk.png"
    behind.write_bytes(b"fake png")
    front.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [{"id": "dialogue"}],
            "backgroundTracks": [{"id": "scenes", "name": "Scenes", "cues": []}],
            "characters": [{"body": "original"}, {"body": "original"}],
            "imageTracks": [],
            "lightTracks": [],
            "rowOrder": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [
            {"name": "tactics board", "file": str(behind), "layer": "behind-cast", "start": 0, "dur": "full"},
            {"name": "desk", "file": str(front), "layer": "front-of-cast", "start": 0, "dur": "full"},
        ],
        duration=10,
    )

    behind_track = show["stage"]["imageTracks"][0]["id"]
    front_track = show["stage"]["imageTracks"][1]["id"]
    assert show["stage"]["rowOrder"] == ["scenes", behind_track, "c-0", "c-1", front_track, "dialogue"]


def test_apply_overlays_normalizes_partial_row_order_before_layering(tmp_path):
    source = tmp_path / "lower-third.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [{"id": "dialogue"}],
            "backgroundTracks": [{"id": "scenes", "name": "Scenes", "cues": []}],
            "characters": [{"body": "original"}, {"body": "original"}],
            "imageTracks": [],
            "rowOrder": ["scenes"],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "lower third", "file": str(source), "layer": "front", "start": 1, "dur": 3}],
        duration=10,
    )

    track_id = show["stage"]["imageTracks"][0]["id"]
    assert show["stage"]["rowOrder"] == ["scenes", "c-0", "c-1", track_id, "dialogue"]


def test_apply_overlays_passes_through_motion_and_appearance_fields(tmp_path):
    source = tmp_path / "highlight.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "imageTracks": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [
            {
                "name": "highlight",
                "file": str(source),
                "start": 1,
                "dur": 4,
                "x": 0.5,
                "y": 0.4,
                "scale": 0.3,
                "rotation": -4,
                "to": {"x": 0.58, "y": 0.42, "scale": 0.34, "rotation": 2},
                "pivot": {"x": 0.12, "y": 0.88},
                "mask": "roundedRectangle",
                "maskRadius": 0.08,
                "appearance": {"shadow": 0.35, "outline": 2},
                "playback": {"loop": True, "rate": 1.0},
            }
        ],
        duration=10,
    )

    cue = show["stage"]["imageTracks"][0]["cues"][0]
    assert cue["from"] == {"scale": 0.3, "x": 0.5, "y": 0.4, "rotation": -4.0}
    assert cue["to"] == {"x": 0.58, "y": 0.42, "scale": 0.34, "rotation": 2}
    assert cue["pivot"] == {"x": 0.12, "y": 0.88}
    assert cue["mask"] == "roundedRectangle"
    assert cue["maskRadius"] == 0.08
    assert cue["appearance"] == {"shadow": 0.35, "outline": 2}
    assert cue["playback"] == {"loop": True, "rate": 1.0}


def test_apply_background_overlay_can_replace_existing_background(tmp_path):
    source = tmp_path / "stadium.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "backgroundTracks": [{"id": "old", "name": "old", "cues": [], "presence": [], "hidden": False}],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "stadium", "file": str(source), "target": "background", "replace": True, "start": 0, "dur": "full"}],
        duration=12,
    )

    assert len(show["stage"]["backgroundTracks"]) == 1
    assert show["stage"]["backgroundTracks"][0]["name"] == "stadium"


def test_apply_overlays_can_exclude_episode_types(tmp_path):
    source = tmp_path / "title.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
            "imageTracks": [],
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "title", "file": str(source), "excludeEpisodeTypes": ["outtake"]}],
        duration=10,
        episode_type="outtake",
    )

    assert show["assets"] == []
    assert show["stage"]["audioTracks"] == []
    assert show["stage"]["imageTracks"] == []

    apply_overlays(
        package_dir,
        show,
        [{"name": "title", "file": str(source), "excludeEpisodeTypes": ["outtake"]}],
        duration=10,
        episode_type="match-event",
    )

    assert show["assets"][0]["name"] == "title"
    assert show["stage"]["imageTracks"][0]["name"] == "title"


def test_overlay_example_manifest_is_valid_json():
    with open("examples/overlays.desk-and-logos.json", encoding="utf-8") as file:
        payload = json.load(file)

    assert "overlays" in payload


def test_build_pfp_overlays_uses_script_line_timing(tmp_path, monkeypatch):
    def fake_download(url: str, username: str, asset_dir: Path) -> Path:
        path = asset_dir / f"{username}.png"
        path.write_bytes(b"fake")
        return path

    monkeypatch.setattr("split_peel.overlays._download_pfp", fake_download)
    script = {
        "sourceCasts": [{"username": "fan", "pfpUrl": "https://example.com/fan.png"}],
        "dialogue": [{"sourceUsername": "fan", "start": 10.0}],
    }

    manifest = build_pfp_overlays(script, tmp_path)

    assert manifest["overlays"][0]["name"] == "@fan pfp"
    assert manifest["overlays"][0]["start"] == 9.8
    assert manifest["overlays"][0]["dur"] == 5.0
    assert manifest["overlays"][0]["scale"] == 0.12
    assert manifest["overlays"][0]["assetPolicy"] == "square-pfp-512"


def test_build_pfp_overlays_uses_farcaster_mentions_as_asset_source(tmp_path, monkeypatch):
    def fake_download(url: str, username: str, asset_dir: Path) -> Path:
        path = asset_dir / f"{username}.png"
        path.write_bytes(b"fake")
        return path

    monkeypatch.setattr("split_peel.overlays._download_pfp", fake_download)
    script = {
        "sourceCasts": [],
        "farcasterMentions": [{"username": "latefan", "pfpUrl": "https://example.com/latefan.png"}],
        "dialogue": [{"sourceUsername": "latefan", "start": 14.0}],
    }

    manifest = build_pfp_overlays(script, tmp_path)

    assert manifest["overlays"][0]["name"] == "@latefan pfp"
    assert manifest["overlays"][0]["start"] == 13.8


def test_build_key_moment_takeover_overlays_uses_dialogue_timing(tmp_path):
    script = {
        "match": {
            "shortName": "ARS @ PSG",
            "teams": [
                {"abbreviation": "ARS", "score": "1"},
                {"abbreviation": "PSG", "score": "1"},
            ],
            "keyMoments": [
                {"clock": "6'", "type": "Goal", "text": "K. Havertz: Goal", "team": "ARS"},
                {"clock": "65'", "type": "Penalty - Scored", "text": "O. Dembele: Penalty - Scored", "team": "PSG"},
                {"clock": "90'", "type": "Yellow Card", "text": "Late Yellow Card", "team": "ARS"},
            ],
        },
        "dialogue": [
            {"line": "Welcome back", "start": 0.5},
            {"line": "The match detonates at 6': K. Havertz: Goal for ARS.", "start": 6.0},
            {"line": "Then 65' brings O. Dembele: Penalty - Scored from PSG.", "start": 10.0},
            {"line": "Back to the desk.", "start": 15.0},
        ],
    }

    manifest = build_key_moment_takeover_overlays(script, tmp_path)

    overlay = manifest["overlays"][0]
    assert overlay["name"] == "key moments takeover"
    assert overlay["start"] == 5.8
    assert overlay["dur"] == 9.05
    assert overlay["x"] == 0.5
    assert overlay["y"] == 0.5
    assert overlay["scale"] == 1.0
    assert Path(overlay["file"]).exists()


def test_build_key_moment_takeover_overlays_skips_without_matching_dialogue(tmp_path):
    script = {
        "match": {"keyMoments": [{"clock": "6'", "type": "Goal", "text": "K. Havertz: Goal"}]},
        "dialogue": [{"line": "Generic show line", "start": 0.5}],
    }

    assert build_key_moment_takeover_overlays(script, tmp_path) == {"overlays": []}
