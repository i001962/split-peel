from pathlib import Path

from PIL import Image

from split_peel.youtube_assets import BANNER_SAFE_SIZE, BANNER_SIZE, THUMBNAIL_SIZE, render_youtube_banner, render_youtube_thumbnail


def test_render_youtube_thumbnail_writes_1280_by_720_image(tmp_path: Path):
    out = tmp_path / "youtube-thumbnail.png"

    result = render_youtube_thumbnail(out, title="Shopping For A Club", subtitle="Split & Peel")

    assert result["path"] == str(out)
    assert Image.open(out).size == THUMBNAIL_SIZE


def test_render_youtube_thumbnail_uses_match_logos_when_available(tmp_path: Path):
    logo = tmp_path / "ars.png"
    Image.new("RGBA", (80, 80), (255, 0, 0, 255)).save(logo)
    out = tmp_path / "youtube-thumbnail.png"

    render_youtube_thumbnail(
        out,
        title="Match Preview",
        match_context={
            "match": {
                "shortName": "ARS v PSG",
                "teams": [
                    {"abbreviation": "ARS", "localLogo": str(logo)},
                    {"abbreviation": "PSG", "localLogo": str(logo)},
                ],
            }
        },
    )

    assert Image.open(out).size == THUMBNAIL_SIZE


def test_render_youtube_banner_writes_safe_area_metadata(tmp_path: Path):
    out = tmp_path / "channel-banner.png"

    result = render_youtube_banner(out, title="Final Whistle", subtitle="With Split & Peel")

    assert Image.open(out).size == BANNER_SIZE
    assert result["safe_area"]["width"] == BANNER_SAFE_SIZE[0]
    assert result["safe_area"]["height"] == BANNER_SAFE_SIZE[1]
