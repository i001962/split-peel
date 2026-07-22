from __future__ import annotations

import textwrap
from pathlib import Path
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont


THUMBNAIL_SIZE = (1280, 720)
BANNER_SIZE = (2560, 1440)
BANNER_SAFE_SIZE = (1546, 423)
DEFAULT_BRAND_LOCKUP = Path("examples/assets/final-whistle-title.png")


def render_youtube_thumbnail(
    out_path: Path,
    *,
    title: str,
    subtitle: str = "",
    match_context: Optional[dict[str, Any]] = None,
    background_path: Optional[Path] = None,
    brand_lockup_path: Optional[Path] = DEFAULT_BRAND_LOCKUP,
) -> dict[str, Any]:
    image = _base_canvas(THUMBNAIL_SIZE, background_path)
    draw = ImageDraw.Draw(image)
    width, height = THUMBNAIL_SIZE

    draw.rectangle((0, 0, width, height), fill=(4, 8, 18, 122))
    _draw_pitch_lines(draw, width, height, alpha=44)
    _draw_team_strip(image, draw, match_context, top=44)

    lockup_box = (62, 78, 555, 236)
    if not _paste_contained(image, brand_lockup_path, lockup_box):
        draw.text((72, 90), "FINAL WHISTLE", font=_font(54), fill=(248, 246, 232, 255), stroke_width=3, stroke_fill=(0, 48, 35, 255))

    title_text = _clean_text(title) or "Final Whistle"
    lines = _wrap_lines(title_text.upper(), _font(88), max_width=1035, max_lines=3)
    y = 298
    for line in lines:
        draw.text((74, y), line, font=_font(88), fill=(255, 222, 80, 255), stroke_width=5, stroke_fill=(0, 58, 42, 255))
        y += 92

    subline = _clean_text(subtitle) or _match_subtitle(match_context)
    if subline:
        sub_font = _font(34)
        sub_width = min(848, max(260, _text_width(draw, subline, sub_font) + 72))
        draw.rounded_rectangle((72, height - 116, 72 + sub_width, height - 58), radius=18, fill=(4, 10, 20, 220), outline=(255, 255, 255, 70), width=2)
        draw.text((96, height - 101), _fit_text(subline, sub_font, sub_width - 48), font=sub_font, fill=(236, 255, 248, 255))

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out_path, optimize=True)
    return {"path": str(out_path), "width": width, "height": height}


def render_youtube_banner(
    out_path: Path,
    *,
    title: str = "Final Whistle",
    subtitle: str = "With Split & Peel",
    background_path: Optional[Path] = None,
    brand_lockup_path: Optional[Path] = DEFAULT_BRAND_LOCKUP,
    show_safe_area: bool = False,
) -> dict[str, Any]:
    image = _base_canvas(BANNER_SIZE, background_path)
    draw = ImageDraw.Draw(image)
    width, height = BANNER_SIZE
    safe_w, safe_h = BANNER_SAFE_SIZE
    safe_left = (width - safe_w) // 2
    safe_top = (height - safe_h) // 2
    safe_right = safe_left + safe_w
    safe_bottom = safe_top + safe_h

    draw.rectangle((0, 0, width, height), fill=(4, 8, 18, 116))
    _draw_field_texture(draw, width, height)
    draw.rectangle((0, safe_top, width, safe_bottom), fill=(4, 10, 20, 88))

    lockup_box = (safe_left + 380, safe_top + 42, safe_right - 96, safe_bottom - 34)
    pasted = _paste_contained(image, brand_lockup_path, lockup_box)
    if not pasted:
        draw.text((safe_left + 470, safe_top + 82), title.upper(), font=_font(110), fill=(255, 222, 80, 255), stroke_width=5, stroke_fill=(0, 58, 42, 255))
        draw.text((safe_left + 485, safe_top + 210), subtitle.upper(), font=_font(62), fill=(236, 255, 248, 255), stroke_width=3, stroke_fill=(0, 58, 42, 255))

    draw.text((safe_left + 78, safe_top + 126), _clean_text(title).upper(), font=_font(58), fill=(255, 255, 255, 245), stroke_width=2, stroke_fill=(0, 34, 28, 255))
    draw.text((safe_left + 82, safe_top + 198), _clean_text(subtitle).upper(), font=_font(35), fill=(157, 235, 211, 245))
    draw.text((safe_left + 84, safe_bottom - 86), "FOOTBALL TAKES AFTER THE WHISTLE", font=_font(30), fill=(255, 222, 80, 245))

    if show_safe_area:
        draw.rectangle((safe_left, safe_top, safe_right, safe_bottom), outline=(72, 180, 255, 255), width=4)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.convert("RGB").save(out_path, optimize=True)
    return {
        "path": str(out_path),
        "width": width,
        "height": height,
        "safe_area": {"x": safe_left, "y": safe_top, "width": safe_w, "height": safe_h},
    }


def _base_canvas(size: tuple[int, int], background_path: Optional[Path]) -> Image.Image:
    if background_path and background_path.exists():
        try:
            background = Image.open(background_path).convert("RGB")
            return _cover(background, size).filter(ImageFilter.GaussianBlur(radius=1.2)).convert("RGBA")
        except OSError:
            pass
    width, height = size
    image = Image.new("RGBA", size, (4, 8, 18, 255))
    draw = ImageDraw.Draw(image)
    for y in range(height):
        green = int(70 + 48 * (y / height))
        blue = int(42 + 18 * (1 - y / height))
        draw.line((0, y, width, y), fill=(8, green, blue, 255))
    return image


def _cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    width, height = size
    scale = max(width / image.width, height / image.height)
    resized = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    left = (resized.width - width) // 2
    top = (resized.height - height) // 2
    return resized.crop((left, top, left + width, top + height))


def _draw_pitch_lines(draw: ImageDraw.ImageDraw, width: int, height: int, *, alpha: int) -> None:
    line = (255, 255, 255, alpha)
    draw.rectangle((80, 62, width - 80, height - 62), outline=line, width=3)
    draw.line((width // 2, 62, width // 2, height - 62), fill=line, width=3)
    draw.ellipse((width // 2 - 118, height // 2 - 118, width // 2 + 118, height // 2 + 118), outline=line, width=3)
    draw.rectangle((80, height // 2 - 145, 260, height // 2 + 145), outline=line, width=3)
    draw.rectangle((width - 260, height // 2 - 145, width - 80, height // 2 + 145), outline=line, width=3)


def _draw_field_texture(draw: ImageDraw.ImageDraw, width: int, height: int) -> None:
    for x in range(0, width, 160):
        fill = (5, 40, 30, 255) if (x // 160) % 2 == 0 else (4, 30, 25, 255)
        draw.rectangle((x, 0, min(width, x + 80), height), fill=fill)
    for y in range(0, height, 120):
        draw.line((0, y, width, y), fill=(16, 72, 52, 255), width=2)


def _draw_team_strip(image: Image.Image, draw: ImageDraw.ImageDraw, match_context: Optional[dict[str, Any]], *, top: int) -> None:
    match = (match_context or {}).get("match") or {}
    teams = match.get("teams") or []
    if len(teams) < 2:
        return
    left, right = teams[0], teams[1]
    draw.rounded_rectangle((640, top, 1210, top + 86), radius=22, fill=(4, 10, 20, 220), outline=(255, 255, 255, 64), width=2)
    _paste_logo(image, left.get("localLogo"), 666, top + 13, 60)
    _paste_logo(image, right.get("localLogo"), 1130, top + 13, 60)
    draw.text((742, top + 24), _team_abbrev(left), font=_font(34), fill=(255, 255, 255, 255))
    draw.text((960, top + 24), "v", font=_font(34), fill=(255, 222, 80, 255))
    draw.text((1010, top + 24), _team_abbrev(right), font=_font(34), fill=(255, 255, 255, 255))


def _paste_logo(image: Image.Image, logo_path: Any, x: int, y: int, size: int) -> None:
    if not logo_path:
        return
    path = Path(str(logo_path)).expanduser()
    if not path.exists():
        return
    try:
        logo = Image.open(path).convert("RGBA")
    except OSError:
        return
    logo.thumbnail((size, size), Image.LANCZOS)
    image.alpha_composite(logo, (x + (size - logo.width) // 2, y + (size - logo.height) // 2))


def _paste_contained(image: Image.Image, source_path: Optional[Path], box: tuple[int, int, int, int]) -> bool:
    if not source_path:
        return False
    path = Path(source_path).expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.exists():
        return False
    try:
        source = Image.open(path).convert("RGBA")
    except OSError:
        return False
    left, top, right, bottom = box
    max_width = right - left
    max_height = bottom - top
    scale = min(max_width / source.width, max_height / source.height)
    resized = source.resize((int(source.width * scale), int(source.height * scale)), Image.LANCZOS)
    image.alpha_composite(resized, (left + (max_width - resized.width) // 2, top + (max_height - resized.height) // 2))
    return True


def _match_subtitle(match_context: Optional[dict[str, Any]]) -> str:
    match = (match_context or {}).get("match") or {}
    status = match.get("status") or {}
    return _clean_text(
        str(match.get("shortName") or match.get("name") or "")
        or str(status.get("shortDetail") or status.get("detail") or "")
    )


def _team_abbrev(team: dict[str, Any]) -> str:
    return _fit_text(str(team.get("abbreviation") or team.get("shortName") or team.get("name") or "TEAM"), _font(34), 190)


def _wrap_lines(text: str, font: ImageFont.ImageFont, *, max_width: int, max_lines: int) -> list[str]:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if _text_width(draw, candidate, font) <= max_width:
            current = candidate
            continue
        if current:
            lines.append(current)
        current = word
        if len(lines) == max_lines - 1:
            break
    if current and len(lines) < max_lines:
        lines.append(current)
    if len(lines) == max_lines and " ".join(lines) != text:
        lines[-1] = _fit_text(lines[-1], font, max_width - 48).rstrip(".") + "..."
    return lines or [textwrap.shorten(text, width=24, placeholder="...")]


def _fit_text(text: str, font: ImageFont.ImageFont, max_width: int) -> str:
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    if _text_width(draw, text, font) <= max_width:
        return text
    value = text
    while value and _text_width(draw, f"{value}...", font) > max_width:
        value = value[:-1].rstrip()
    return f"{value}..." if value else "..."


def _text_width(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _clean_text(value: Any) -> str:
    return " ".join(str(value or "").split())


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for font_path in (
        "/System/Library/Fonts/SFNSMono.ttf",
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/Library/Fonts/Arial Bold.ttf",
    ):
        try:
            return ImageFont.truetype(font_path, size)
        except OSError:
            continue
    return ImageFont.load_default()
