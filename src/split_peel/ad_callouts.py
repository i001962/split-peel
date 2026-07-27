from __future__ import annotations

import hashlib
import io
import json
import textwrap
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont, ImageOps


class AdCalloutError(RuntimeError):
    pass


def load_ad_cast(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if "cast" in payload and isinstance(payload["cast"], dict):
        return payload
    if "text" in payload:
        return {"cast": payload}
    raise AdCalloutError("ad source must be a cast object or an object with cast{}")


def build_ad_callout_artifacts(
    ad_source: dict[str, Any],
    asset_dir: Path,
    *,
    start: float = 0.0,
    duration: float = 18.0,
    variant: str = "speech-bubble",
) -> dict[str, Any]:
    cast = normalize_ad_cast(ad_source)
    callout = _callout_config(ad_source)
    start = float(callout.get("start", start))
    duration = float(callout.get("duration", callout.get("dur", duration)))
    variant = str(callout.get("variant") or variant)

    asset_dir.mkdir(parents=True, exist_ok=True)
    image_path = asset_dir / f"ad-callout-{_slug(cast['author']['username'] or str(cast['author']['fid']))}.png"
    render_ad_callout_image(cast, image_path, variant=variant)

    return {
        "script": build_ad_callout_script(cast, ad_source),
        "overlays": {
            "overlays": [
                {
                    "name": f"ad callout @{cast['author']['username']}",
                    "trackName": "Ad Callout Bubble",
                    "file": str(image_path),
                    "start": round(max(0.0, start), 3),
                    "dur": round(max(1.0, duration), 3),
                    "x": 0.5,
                    "y": 0.42,
                    "scale": 0.68,
                }
            ]
        },
        "assets": {"calloutImage": str(image_path)},
    }


def insert_ad_callout(
    episode_script: dict[str, Any],
    callout_script: dict[str, Any],
    *,
    after_line_id: str,
    callout_id: str = "ad-callout",
) -> dict[str, Any]:
    dialogue = episode_script.get("dialogue")
    callout_dialogue = callout_script.get("dialogue")
    if not isinstance(dialogue, list):
        raise AdCalloutError("episode script does not contain a dialogue array")
    if not isinstance(callout_dialogue, list):
        raise AdCalloutError("callout script does not contain a dialogue array")

    insertion_index = _dialogue_index(dialogue, after_line_id)
    prefixed_callout_dialogue = [_prefix_callout_line(line, callout_id) for line in callout_dialogue]
    if not prefixed_callout_dialogue:
        raise AdCalloutError("callout script dialogue is empty")

    merged = dict(episode_script)
    merged["dialogue"] = [
        *dialogue[: insertion_index + 1],
        *prefixed_callout_dialogue,
        *dialogue[insertion_index + 1 :],
    ]
    merged["sourceCasts"] = _merge_source_casts(
        list(episode_script.get("sourceCasts") or []),
        list(callout_script.get("sourceCasts") or []),
    )
    merged.setdefault("adCallouts", [])
    if isinstance(merged["adCallouts"], list):
        merged["adCallouts"].append(
            {
                "id": callout_id,
                "afterLineId": after_line_id,
                "firstLineId": _line_id(prefixed_callout_dialogue[0]),
                "lastLineId": _line_id(prefixed_callout_dialogue[-1]),
                "source": callout_script.get("adCallout") or {},
            }
        )
    return merged


def insert_ad_callout_overlays(
    episode_overlays: dict[str, Any] | list[dict[str, Any]] | None,
    callout_overlays: dict[str, Any] | list[dict[str, Any]],
    *,
    anchor_line_id: str,
    callout_id: str = "ad-callout",
    offset: float = 0.0,
) -> dict[str, Any]:
    overlays = []
    overlays.extend(_overlay_list(episode_overlays))
    for overlay in _overlay_list(callout_overlays):
        anchored = dict(overlay)
        anchored["calloutId"] = callout_id
        anchored["anchorLineId"] = anchor_line_id
        anchored["anchorOffset"] = round(float(offset), 3)
        anchored.pop("start", None)
        overlays.append(anchored)
    return {"overlays": overlays}


def normalize_ad_cast(ad_source: dict[str, Any]) -> dict[str, Any]:
    cast = ad_source.get("cast") if isinstance(ad_source.get("cast"), dict) else ad_source
    if not isinstance(cast, dict):
        raise AdCalloutError("cast must be an object")

    text = " ".join(str(cast.get("text") or "").split())
    if not text:
        raise AdCalloutError("cast.text is required")

    author = cast.get("author") or {}
    if not isinstance(author, dict):
        raise AdCalloutError("cast.author must be an object")

    fid = author.get("fid") or cast.get("fid")
    username = str(author.get("username") or author.get("handle") or f"fid-{fid or 'mock'}").strip("@")
    display_name = str(author.get("displayName") or author.get("display_name") or username)
    pfp_url = str(author.get("pfpUrl") or author.get("pfp_url") or "").strip()
    pfp_path = str(author.get("pfpPath") or author.get("pfp_path") or "").strip()

    sponsor = ad_source.get("sponsor") if isinstance(ad_source.get("sponsor"), dict) else {}
    sponsor_name = str(sponsor.get("name") or display_name or username)

    return {
        "hash": str(cast.get("hash") or ""),
        "text": text,
        "timestamp": str(cast.get("timestamp") or ""),
        "author": {
            "fid": int(fid) if str(fid or "").isdigit() else fid,
            "username": username,
            "displayName": display_name,
            "pfpUrl": pfp_url,
            "pfpPath": pfp_path,
        },
        "sponsor": {
            "name": sponsor_name,
            "offer": str(sponsor.get("offer") or "").strip(),
            "cta": str(sponsor.get("cta") or "").strip(),
            "talkingPoints": [str(item).strip() for item in sponsor.get("talkingPoints") or [] if str(item).strip()],
        },
    }


def build_ad_callout_script(cast: dict[str, Any], ad_source: dict[str, Any]) -> dict[str, Any]:
    sponsor = cast["sponsor"]
    brand = sponsor["name"]
    username = cast["author"]["username"]
    offer = sponsor["offer"]
    cta = sponsor["cta"]
    point = sponsor["talkingPoints"][0] if sponsor["talkingPoints"] else _shorten(cast["text"], 120)
    peel_summary = sponsor["talkingPoints"][1] if len(sponsor["talkingPoints"]) > 1 else _plain_summary(cast["text"])
    action = cta or offer or peel_summary
    if "poidh" in brand.lower():
        action = "POIDH bounty: interview a politician, post, claim."
    brand_line = (
        "Management says: ad time."
        if "poidh" in brand.lower()
        else f"Management says read this: {short_callout_point(brand, 42)}"
    )

    dialogue = [
        {
            "id": "ad-callout-trigger",
            "speaker": "split",
            "line": brand_line,
            "tone": "resigned, official",
        },
        {
            "id": "ad-callout-mock",
            "speaker": "peel",
            "line": short_callout_point(action, 54),
            "tone": "mock-serious, accidentally helpful",
            "sourceUsername": username,
        },
    ]
    dialogue.append(
        {
            "id": "ad-callout-return",
            "speaker": "split",
            "line": "Are you done now?",
            "tone": "pause first; face says can I go now, then speak",
        }
    )

    return {
        "title": f"Ad Callout: {brand}",
        "episodeType": "ad-callout",
        "sourceCasts": [
            {
                "username": username,
                "fid": cast["author"]["fid"],
                "displayName": cast["author"]["displayName"],
                "pfpUrl": cast["author"]["pfpUrl"],
                "text": cast["text"],
                "hash": cast["hash"],
            }
        ],
        "adCallout": {
            "format": "callout-bubble",
            "source": "farcaster-cast-shaped-ad",
            "sponsor": sponsor,
            "transition": "speech bubble swallows the frame; Split and Peel reappear in Callout Land and return when it pops",
        },
        "dialogue": dialogue,
        "outroEffect": {"enabled": False},
    }


def render_ad_callout_image(cast: dict[str, Any], path: Path, *, variant: str = "speech-bubble") -> Path:
    width, height = 1280, 720
    image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)

    sponsor = cast["sponsor"]
    author = cast["author"]
    _draw_dream_cloud(image, variant=variant)

    avatar = _pfp_image(author, 112)
    image.alpha_composite(avatar, (156, 126))

    eyebrow_font = _font(24)
    title_font = _font(44)
    user_font = _font(23)
    body_font = _font(30)
    label_font = _font(21)
    pill_font = _font(24)

    draw.rounded_rectangle((294, 128, 575, 164), radius=18, fill=(220, 36, 65, 238))
    draw.text((318, 134), "POIDH CALLOUT", font=eyebrow_font, fill=(255, 255, 255, 255))
    draw.text((296, 176), _shorten(sponsor["name"], 34), font=title_font, fill=(14, 20, 31, 255))
    byline = f"@{author['username']}"
    if author.get("fid"):
        byline += f"  fid {author['fid']}"
    draw.text((298, 230), byline, font=user_font, fill=(76, 88, 110, 255))

    amount = sponsor["offer"] or "Bounty live now"
    draw.rounded_rectangle((822, 128, 1076, 176), radius=24, fill=(13, 25, 39, 245))
    draw.text((846, 139), _shorten(amount.replace("Bounty: ", ""), 28), font=pill_font, fill=(255, 255, 255, 255))

    draw.text((166, 300), "MISSION", font=label_font, fill=(220, 36, 65, 255))
    y = 330
    for line in _wrap(cast["text"], 50, max_lines=4):
        draw.text((166, y), line, font=body_font, fill=(17, 24, 36, 255))
        y += 38

    chips = _callout_chips(cast)
    chip_x = 166
    for chip in chips:
        chip_w = 168 if len(chip) <= 10 else 224
        draw.rounded_rectangle((chip_x, 510, chip_x + chip_w, 566), radius=24, fill=(240, 247, 252, 244), outline=(14, 20, 31, 135), width=2)
        draw.text((chip_x + 22, 526), chip, font=pill_font, fill=(17, 24, 36, 255))
        chip_x += chip_w + 16

    draw.text((890, 590), "CALL OUT LAND", font=_font(24), fill=(76, 88, 110, 210))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)
    return path


def _callout_config(ad_source: dict[str, Any]) -> dict[str, Any]:
    value = ad_source.get("callout")
    return value if isinstance(value, dict) else {}


def _dialogue_index(dialogue: list[dict[str, Any]], line_id: str) -> int:
    for index, line in enumerate(dialogue):
        if _line_id(line) == line_id:
            return index
    raise AdCalloutError(f"could not find insertion line id: {line_id}")


def _prefix_callout_line(line: dict[str, Any], callout_id: str) -> dict[str, Any]:
    copied = dict(line)
    copied["id"] = f"{callout_id}-{_line_id(line)}"
    return copied


def _line_id(line: dict[str, Any]) -> str:
    for key in ("line_id", "lineId", "id"):
        value = str(line.get(key) or "").strip()
        if value:
            return value
    raise AdCalloutError("dialogue line is missing id")


def _merge_source_casts(existing: list[Any], incoming: list[Any]) -> list[Any]:
    merged = []
    seen = set()
    for cast in [*existing, *incoming]:
        if not isinstance(cast, dict):
            continue
        key = str(cast.get("hash") or cast.get("username") or cast.get("fid") or cast)
        if key in seen:
            continue
        seen.add(key)
        merged.append(cast)
    return merged


def _overlay_list(value: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        overlays = value.get("overlays")
        if isinstance(overlays, list):
            return [item for item in overlays if isinstance(item, dict)]
    raise AdCalloutError("overlay manifest must be a list or an object with overlays[]")


def _pfp_image(author: dict[str, Any], size: int) -> Image.Image:
    image = _load_pfp(author)
    if image is None:
        image = _placeholder_pfp(str(author.get("fid") or author.get("username") or "ad"), size)
    image = ImageOps.fit(image.convert("RGBA"), (size, size))
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size - 1, size - 1), fill=255)
    image.putalpha(mask)
    return image


def _load_pfp(author: dict[str, Any]) -> Optional[Image.Image]:
    pfp_path = str(author.get("pfpPath") or "")
    if pfp_path:
        path = Path(pfp_path).expanduser()
        if path.exists():
            return Image.open(path)
    pfp_url = str(author.get("pfpUrl") or "")
    if not pfp_url:
        return None
    try:
        request = urllib.request.Request(pfp_url, headers={"User-Agent": "split-peel/0.1"})
        with urllib.request.urlopen(request, timeout=12) as response:
            return Image.open(io.BytesIO(response.read()))
    except (OSError, urllib.error.URLError, TimeoutError):
        return None


def _placeholder_pfp(seed_value: str, size: int) -> Image.Image:
    digest = hashlib.sha256(seed_value.encode("utf-8")).digest()
    c1 = (60 + digest[0] % 120, 70 + digest[1] % 110, 80 + digest[2] % 100, 255)
    c2 = (190 + digest[3] % 50, 180 + digest[4] % 60, 80 + digest[5] % 120, 255)
    image = Image.new("RGBA", (size, size), c1)
    draw = ImageDraw.Draw(image)
    draw.ellipse((-size // 4, size // 3, size, size + size // 3), fill=c2)
    draw.ellipse((size // 3, -size // 5, size + size // 5, size // 2), fill=(255, 255, 255, 54))
    return image


def _draw_fuzzy_backdrop(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for y in range(height):
        shade = int(232 + 18 * (y / height))
        draw.line((0, y, width, y), fill=(shade, 239, 247, 210))
    for index, color in enumerate(((255, 214, 112, 70), (83, 189, 232, 60), (236, 80, 108, 52))):
        x = 150 + index * 360
        draw.ellipse((x, 86 + index * 34, x + 360, 446 + index * 34), fill=color)


def _draw_dream_cloud(image: Image.Image, *, variant: str) -> None:
    mask = Image.new("L", image.size, 0)
    mask_draw = ImageDraw.Draw(mask)
    lobes = [
        (92, 150, 288, 374),
        (166, 82, 454, 392),
        (352, 70, 700, 390),
        (642, 90, 984, 390),
        (904, 134, 1176, 398),
        (128, 290, 440, 622),
        (380, 262, 780, 640),
        (720, 284, 1108, 618),
    ]

    for box in lobes:
        mask_draw.ellipse(box, fill=255)

    shadow = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shadow_mask = Image.new("L", image.size, 0)
    shadow_mask.paste(mask, (12, 18))
    shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(10)).point(lambda value: int(value * 0.25)))
    image.alpha_composite(shadow)

    fill = Image.new("RGBA", image.size, (255, 255, 255, 244))
    fill.putalpha(mask.point(lambda value: int(value * 0.96)))
    image.alpha_composite(fill)

    if variant == "dream":
        cloud = ImageDraw.Draw(image)
        for box in ((40, 38, 240, 180), (1040, 42, 1220, 184), (1020, 576, 1210, 704)):
            cloud.ellipse(box, fill=(137, 205, 255, 36))

    expanded = mask.filter(ImageFilter.MaxFilter(13))
    edge = ImageChops.subtract(expanded, mask)
    outline = Image.new("RGBA", image.size, (15, 23, 35, 230))
    outline.putalpha(edge.point(lambda value: min(230, value)))
    image.alpha_composite(outline)

    draw = ImageDraw.Draw(image)
    for box in ((208, 610, 270, 672), (138, 654, 176, 692), (84, 680, 110, 706)):
        draw.ellipse(box, fill=(255, 255, 255, 238), outline=(15, 23, 35, 210), width=4)
    for index, color in enumerate(((220, 36, 65, 92), (43, 148, 205, 70), (234, 194, 69, 78))):
        x = 830 + index * 54
        draw.ellipse((x, 82 + index * 26, x + 170, 252 + index * 26), fill=color)


def _wrap(text: str, width: int, max_lines: int) -> list[str]:
    lines = textwrap.wrap(" ".join(text.split()), width=width)
    if len(lines) <= max_lines:
        return lines
    return [*lines[: max_lines - 1], lines[max_lines - 1][: max(0, width - 3)].rstrip() + "..."]


def _callout_chips(cast: dict[str, Any]) -> list[str]:
    source = ((cast.get("sponsor") or {}).get("name") or "").lower()
    text = cast.get("text", "").lower()
    if "poidh" in source or "poidh" in text:
        return ["VIDEO", "10 QUESTIONS", "/POLITICS", "SUBMIT CLAIM"]
    return ["FIND INFO", "PROVE IT", "POST PROOF", "CLAIM"]


def _plain_summary(text: str) -> str:
    summary = _shorten(text, 96)
    if not summary.endswith("."):
        summary += "."
    return summary


def short_callout_point(text: str, limit: int = 72) -> str:
    return _shorten(text, limit).rstrip(".") + "."


def _shorten(text: str, limit: int) -> str:
    text = " ".join(text.split())
    if len(text) <= limit:
        return text
    clipped = text[: max(0, limit - 3)].rstrip()
    if " " in clipped:
        clipped = clipped.rsplit(" ", 1)[0].rstrip()
    return clipped + "..."


def _slug(value: str) -> str:
    slug = "".join(character.lower() if character.isalnum() else "-" for character in value).strip("-")
    return slug[:80] or "ad"


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in (
        "/System/Library/Fonts/SFNS.ttf",
        "/System/Library/Fonts/SFNSMono.ttf",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    return ImageFont.load_default()
