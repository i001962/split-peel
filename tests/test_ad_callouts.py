import json
from pathlib import Path

from PIL import Image

from split_peel.ad_callouts import build_ad_callout_artifacts, insert_ad_callout, insert_ad_callout_overlays, normalize_ad_cast
from split_peel.cli import main


def _ad_source():
    return {
        "cast": {
            "hash": "0xabc",
            "text": "Use Sideline Soup to get one clean pre-match read before everyone starts lying with confidence.",
            "author": {
                "fid": 777,
                "username": "sidelinesoup",
                "displayName": "Sideline Soup",
            },
        },
        "sponsor": {
            "name": "Sideline Soup",
            "offer": "Use code SPLIT.",
            "cta": "Visit sidelinesoup.example.",
            "talkingPoints": [
                "Sideline Soup turns noisy match context into one clean read.",
                "It is a cheat sheet for sounding prepared.",
            ],
        },
        "callout": {"start": 8.5, "duration": 19},
    }


def test_normalize_ad_cast_accepts_fid_without_pfp_url():
    cast = normalize_ad_cast(_ad_source())

    assert cast["author"]["fid"] == 777
    assert cast["author"]["username"] == "sidelinesoup"
    assert cast["author"]["pfpUrl"] == ""
    assert cast["sponsor"]["name"] == "Sideline Soup"


def test_build_ad_callout_artifacts_writes_speech_bubble_image(tmp_path: Path):
    artifacts = build_ad_callout_artifacts(_ad_source(), tmp_path / "assets")

    script = artifacts["script"]
    overlay = artifacts["overlays"]["overlays"][0]
    image_path = Path(overlay["file"])

    assert script["episodeType"] == "ad-callout"
    assert script["sourceCasts"][0]["fid"] == 777
    assert script["dialogue"][0]["line"] == "Management says read this: Sideline Soup."
    assert script["dialogue"][1]["line"] == "Visit sidelinesoup.example."
    assert len(script["dialogue"]) == 3
    assert script["dialogue"][1]["sourceUsername"] == "sidelinesoup"
    assert overlay["trackName"] == "Ad Callout Bubble"
    assert overlay["start"] == 8.5
    assert overlay["dur"] == 19.0
    assert image_path.exists()
    with Image.open(image_path) as image:
        assert image.size == (1280, 720)


def test_build_ad_callout_cli_writes_script_and_overlays(tmp_path: Path):
    ad_path = tmp_path / "ad.json"
    script_path = tmp_path / "script.json"
    overlays_path = tmp_path / "overlays.json"
    asset_dir = tmp_path / "assets"
    ad_path.write_text(json.dumps(_ad_source()), encoding="utf-8")

    main(
        [
            "build-ad-callout",
            "--ad",
            str(ad_path),
            "--script-out",
            str(script_path),
            "--overlays-out",
            str(overlays_path),
            "--asset-dir",
            str(asset_dir),
        ]
    )

    script = json.loads(script_path.read_text(encoding="utf-8"))
    overlays = json.loads(overlays_path.read_text(encoding="utf-8"))

    assert script["adCallout"]["format"] == "callout-bubble"
    assert overlays["overlays"][0]["file"].endswith("ad-callout-sidelinesoup.png")
    assert Path(overlays["overlays"][0]["file"]).exists()


def test_insert_ad_callout_cuts_after_requested_line_id(tmp_path: Path):
    episode = {
        "title": "Knock Knock VAR",
        "sourceCasts": [{"username": "fan", "hash": "0xfan"}],
        "dialogue": [
            {"id": "knock", "speaker": "split", "line": "Knock knock."},
            {"id": "var-who", "speaker": "peel", "line": "VAR who?"},
            {"id": "payoff", "speaker": "split", "line": "VAR waiting on the oracle."},
        ],
    }
    callout = build_ad_callout_artifacts(_ad_source(), tmp_path / "assets")["script"]

    inserted = insert_ad_callout(episode, callout, after_line_id="var-who", callout_id="test-ad")

    assert [line["id"] for line in inserted["dialogue"][:4]] == [
        "knock",
        "var-who",
        "test-ad-ad-callout-trigger",
        "test-ad-ad-callout-mock",
    ]
    assert inserted["dialogue"][-1]["id"] == "payoff"
    assert inserted["adCallouts"][0]["afterLineId"] == "var-who"
    assert inserted["adCallouts"][0]["firstLineId"] == "test-ad-ad-callout-trigger"
    assert inserted["sourceCasts"][1]["username"] == "sidelinesoup"


def test_insert_ad_callout_overlays_anchors_to_inserted_first_line():
    merged = insert_ad_callout_overlays(
        {"overlays": [{"name": "existing", "file": "existing.png"}]},
        {"overlays": [{"name": "ad", "file": "ad.png", "start": 8.5, "dur": 19}]},
        anchor_line_id="test-ad-ad-callout-trigger",
        callout_id="test-ad",
        offset=0.12,
    )

    assert merged["overlays"][0]["name"] == "existing"
    assert merged["overlays"][1]["anchorLineId"] == "test-ad-ad-callout-trigger"
    assert merged["overlays"][1]["anchorOffset"] == 0.12
    assert "start" not in merged["overlays"][1]
