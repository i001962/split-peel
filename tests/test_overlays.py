import json
from pathlib import Path

from split_peel.overlays import apply_overlays, build_pfp_overlays


def test_apply_overlays_adds_asset_and_media_cue(tmp_path):
    source = tmp_path / "desk.png"
    source.write_bytes(b"fake png")
    package_dir = tmp_path / "show"
    show = {
        "assets": [],
        "stage": {
            "audioTracks": [],
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
    track = show["stage"]["audioTracks"][0]
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
        },
    }

    apply_overlays(
        package_dir,
        show,
        [{"name": "highlight replay", "file": str(source), "start": 4, "dur": 8, "x": 0.78, "y": 0.24, "scale": 0.28}],
        duration=20,
    )

    assert show["assets"][0]["kind"] == "video"
    assert show["stage"]["audioTracks"][0]["cues"][0]["assetID"] == show["assets"][0]["id"]


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
