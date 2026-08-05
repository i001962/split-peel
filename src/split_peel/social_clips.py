from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from split_peel.banny_cli import BannyCliError, resolve_banny_cli
from split_peel.feed import write_json
from split_peel.voice_manifest import load_voice_manifest


class SocialClipError(RuntimeError):
    pass


@dataclass(frozen=True)
class SocialClipSpec:
    slug: str
    title: str
    start: float
    end: float
    line_ids: tuple[str, ...]
    text: str
    speakers: tuple[str, ...]

    @property
    def duration(self) -> float:
        return round(self.end - self.start, 3)


def build_social_clip_specs(
    script_path: Path,
    voice_manifest_path: Path,
    *,
    count: int = 2,
    min_duration: float = 6.0,
    max_duration: float = 22.0,
    padding: float = 0.35,
) -> list[SocialClipSpec]:
    script = json.loads(script_path.read_text(encoding="utf-8"))
    manifest = load_voice_manifest(voice_manifest_path)
    clips = [clip for clip in manifest["clips"] if str(clip.get("text") or "").strip()]
    if not clips:
        raise SocialClipError("voice manifest does not contain timed dialogue clips")

    scored = []
    for index, clip in enumerate(clips):
        scored.append((_funny_score(clip), -index, [clip]))

    if len(clips) >= count * 2:
        for index in range(len(clips) - 1):
            pair = [clips[index], clips[index + 1]]
            pair_duration = _clip_end(pair[-1]) - float(pair[0].get("start") or 0)
            if pair_duration <= max_duration:
                scored.append((_funny_score(pair[0]) + _funny_score(pair[1]) + 1.5, -index, pair))

    chosen: list[list[dict[str, Any]]] = []
    used_line_ids: set[str] = set()
    for _score, _order, candidate in sorted(scored, reverse=True):
        line_ids = {str(item.get("line_id") or "") for item in candidate}
        if used_line_ids.intersection(line_ids):
            continue
        chosen.append(candidate)
        used_line_ids.update(line_ids)
        if len(chosen) >= count:
            break

    if len(chosen) < count:
        raise SocialClipError(f"could only choose {len(chosen)} social clip(s); requested {count}")

    episode_title = str(script.get("title") or script.get("episodeTitle") or "Episode").strip()
    return [
        _spec_from_clips(candidate, index + 1, episode_title, min_duration, max_duration, padding)
        for index, candidate in enumerate(chosen)
    ]


def export_social_clips_with_banny(
    show: Path,
    specs: list[SocialClipSpec],
    out_dir: Path,
    *,
    render_size: str = "720",
    banny_bin: Optional[Path] = None,
    banny_checkout_path: Optional[Path] = None,
) -> dict[str, Any]:
    try:
        cli = resolve_banny_cli(banny_bin, banny_checkout_path)
        outputs = []
        for spec in specs:
            out = out_dir / f"{spec.slug}.mp4"
            cli.ship_range(show, out, render_size, spec.start, spec.end)
            outputs.append(_clip_output(spec, out, "banny-range"))
    except BannyCliError as error:
        raise SocialClipError(str(error)) from error
    return _result(outputs)


def export_social_clips_from_movie(
    movie: Path,
    specs: list[SocialClipSpec],
    out_dir: Path,
    *,
    ffmpeg_bin: Optional[str] = None,
) -> dict[str, Any]:
    if not movie.exists():
        raise SocialClipError(f"source movie does not exist: {movie}")
    ffmpeg = ffmpeg_bin or shutil.which("ffmpeg")
    avconvert = shutil.which("avconvert")
    if not ffmpeg and avconvert:
        return _export_social_clips_with_avconvert(movie, specs, out_dir, avconvert)
    if not ffmpeg:
        raise SocialClipError("ffmpeg or avconvert is required for source-movie social clip export")
    outputs = []
    for spec in specs:
        out = out_dir / f"{spec.slug}.mp4"
        out.parent.mkdir(parents=True, exist_ok=True)
        command = [
            ffmpeg,
            "-y",
            "-ss",
            _seconds(spec.start),
            "-to",
            _seconds(spec.end),
            "-i",
            str(movie),
            "-map",
            "0:v:0",
            "-map",
            "0:a:0?",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-movflags",
            "+faststart",
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            str(out),
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise SocialClipError(_format_ffmpeg_error(command, completed.stderr))
        outputs.append(_clip_output(spec, out, "ffmpeg-trim"))
    return _result(outputs)


def _export_social_clips_with_avconvert(
    movie: Path,
    specs: list[SocialClipSpec],
    out_dir: Path,
    avconvert: str,
) -> dict[str, Any]:
    outputs = []
    for spec in specs:
        out = out_dir / f"{spec.slug}.mp4"
        av_out = out.with_suffix(".m4v")
        out.parent.mkdir(parents=True, exist_ok=True)
        command = [
            avconvert,
            "--source",
            str(movie),
            "--preset",
            "PresetAppleM4V720pHD",
            "--output",
            str(av_out),
            "--replace",
            "--start",
            _seconds(spec.start),
            "--duration",
            _seconds(spec.duration),
            "--disableMetadataFilter",
        ]
        completed = subprocess.run(command, text=True, capture_output=True, check=False)
        if completed.returncode != 0:
            raise SocialClipError(_format_ffmpeg_error(command, completed.stderr))
        if out.exists():
            out.unlink()
        av_out.replace(out)
        outputs.append(_clip_output(spec, out, "avconvert-trim"))
    return _result(outputs)


def write_social_clip_artifacts(result: dict[str, Any], out_dir: Path) -> dict[str, str]:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "social-clips.json"
    handoff_path = out_dir / "social-posts.md"
    write_json(manifest_path, result)
    handoff_path.write_text(_posts_markdown(result), encoding="utf-8")
    return {"manifest": str(manifest_path), "handoff": str(handoff_path)}


def _spec_from_clips(
    clips: list[dict[str, Any]],
    index: int,
    episode_title: str,
    min_duration: float,
    max_duration: float,
    padding: float,
) -> SocialClipSpec:
    raw_start = float(clips[0].get("start") or 0)
    raw_end = _clip_end(clips[-1])
    start = max(0.0, raw_start - padding)
    end = raw_end + padding
    if end - start < min_duration:
        end = start + min_duration
    if end - start > max_duration:
        end = start + max_duration
    text = " ".join(str(clip.get("text") or "").strip() for clip in clips if str(clip.get("text") or "").strip())
    speakers = tuple(dict.fromkeys(str(clip.get("speaker") or "").strip() for clip in clips if clip.get("speaker")))
    title = f"{episode_title} - Sound Bite {index}"
    return SocialClipSpec(
        slug=f"sound-bite-{index:02d}",
        title=title,
        start=round(start, 3),
        end=round(end, 3),
        line_ids=tuple(str(clip.get("line_id") or "") for clip in clips),
        text=text,
        speakers=speakers,
    )


def _funny_score(clip: dict[str, Any]) -> float:
    text = str(clip.get("text") or "")
    tone = str(clip.get("tone") or "").lower()
    lowered = text.lower()
    score = min(len(text), 160) / 80
    score += sum(1 for mark in ("!", "?", "wait", "what", "please", "sir", "mate", "lads") if mark in lowered)
    score += sum(1.5 for word in ("funny", "deadpan", "mock", "panic", "shocked", "breathless", "outraged") if word in tone)
    return score


def _clip_end(clip: dict[str, Any]) -> float:
    return float(clip.get("start") or 0) + float(clip.get("duration") or 0)


def _clip_output(spec: SocialClipSpec, path: Path, method: str) -> dict[str, Any]:
    return {
        "slug": spec.slug,
        "title": spec.title,
        "path": str(path),
        "format": "mp4",
        "method": method,
        "start": spec.start,
        "end": spec.end,
        "duration": spec.duration,
        "line_ids": list(spec.line_ids),
        "speakers": list(spec.speakers),
        "text": spec.text,
        "x_post": _post_text(spec, "x"),
        "farcaster_cast": _post_text(spec, "farcaster"),
    }


def _result(outputs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": 1,
        "clip_count": len(outputs),
        "platforms": ["x", "farcaster"],
        "clips": outputs,
    }


def _post_text(spec: SocialClipSpec, platform: str) -> str:
    suffix = "#FinalWhistle" if platform == "x" else "/football"
    text = spec.text.strip()
    if len(text) > 160:
        text = text[:157].rstrip() + "..."
    return f"{text}\n\n{suffix}"


def _posts_markdown(result: dict[str, Any]) -> str:
    lines = ["# Social Clip Posts", ""]
    for clip in result.get("clips") or []:
        lines.extend(
            [
                f"## {clip['title']}",
                "",
                f"- MP4: `{clip['path']}`",
                f"- Range: `{clip['start']}` to `{clip['end']}` ({clip['duration']} sec)",
                f"- Lines: `{', '.join(clip.get('line_ids') or [])}`",
                "",
                "### X",
                "",
                clip["x_post"],
                "",
                "### Farcaster",
                "",
                clip["farcaster_cast"],
                "",
            ]
        )
    return "\n".join(lines)


def _seconds(value: float) -> str:
    return f"{value:.3f}".rstrip("0").rstrip(".")


def _format_ffmpeg_error(command: list[str], stderr: str) -> str:
    message = f"ffmpeg social clip export failed: {' '.join(command)}"
    if stderr.strip():
        message += f"\nstderr:\n{stderr.strip()}"
    return message
