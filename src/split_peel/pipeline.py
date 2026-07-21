from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from split_peel.characters import DEFAULT_CHARACTERS_PATH, load_characters
from split_peel.espn import (
    DEFAULT_ESPN_LEAGUE,
    build_scoreboard_overlays,
    download_match_logos,
    fetch_scoreboard,
    normalize_scoreboard,
    scoreboard_url_for_league,
)
from split_peel.feed import DEFAULT_FOOTBALL_FEED_URL, fetch_feed, write_json
from split_peel.memory import DEFAULT_MEMORY_DIR, load_episode_memory, save_episode_memory
from split_peel.overlays import build_pfp_overlays, load_overlay_manifest
from split_peel.package import build_show, inspect_package, unpack_package
from split_peel.scriptwriter import draft_script


class PipelineError(RuntimeError):
    pass


@dataclass
class PipelineConfig:
    episode_slug: str
    template_path: Path
    run_dir: Path
    output_bs: Path
    output_bannyshow: Path
    output_movie: Path
    duration_sec: int = 60
    background_gain: Optional[float] = None
    feed_url: str = DEFAULT_FOOTBALL_FEED_URL
    espn_league: str = DEFAULT_ESPN_LEAGUE
    scoreboard_url: Optional[str] = None
    match_id: Optional[str] = None
    no_espn: bool = False
    overlays_path: Optional[Path] = None
    characters_path: Path = DEFAULT_CHARACTERS_PATH
    instructions: Optional[str] = None
    instructions_file: Optional[Path] = None
    script_provider: Optional[str] = None
    memory_dir: Path = DEFAULT_MEMORY_DIR
    no_memory: bool = False
    overwrite_script: bool = False


def load_pipeline_config(path: Path) -> PipelineConfig:
    payload = json.loads(path.read_text(encoding="utf-8"))
    base_dir = Path.cwd()

    slug = _required_str(payload, "episode_slug")
    run_dir = _path(payload.get("run_dir") or f"runs/{slug}", base_dir)
    output_bs = _path(payload.get("output_bs") or f"outputs/{slug}.bs", base_dir)
    output_bannyshow = _path(payload.get("output_bannyshow") or f"outputs/{slug}.bannyshow", base_dir)
    output_movie = _path(payload.get("output_movie") or f"outputs/{slug}.mp4", base_dir)

    return PipelineConfig(
        episode_slug=slug,
        template_path=_path(_required_str(payload, "template_path"), base_dir),
        run_dir=run_dir,
        output_bs=output_bs,
        output_bannyshow=output_bannyshow,
        output_movie=output_movie,
        duration_sec=int(payload.get("duration_sec") or 60),
        background_gain=_optional_float(payload.get("background_gain")),
        feed_url=str(payload.get("feed_url") or DEFAULT_FOOTBALL_FEED_URL),
        espn_league=str(payload.get("espn_league") or DEFAULT_ESPN_LEAGUE),
        scoreboard_url=payload.get("scoreboard_url"),
        match_id=payload.get("match_id"),
        no_espn=bool(payload.get("no_espn", False)),
        overlays_path=_optional_path(payload.get("overlays_path"), base_dir),
        characters_path=_path(payload.get("characters_path") or DEFAULT_CHARACTERS_PATH, base_dir),
        instructions=payload.get("instructions"),
        instructions_file=_optional_path(payload.get("instructions_file"), base_dir),
        script_provider=payload.get("script_provider"),
        memory_dir=_path(payload.get("memory_dir") or DEFAULT_MEMORY_DIR, base_dir),
        no_memory=bool(payload.get("no_memory", False)),
        overwrite_script=bool(payload.get("overwrite_script", False)),
    )


def write_pipeline_config_template(path: Path) -> None:
    payload = {
        "episode_slug": "pipeline-smoke",
        "template_path": "outputs/openai-voiced.bs",
        "run_dir": "runs/pipeline-smoke",
        "output_bs": "outputs/pipeline-smoke.bs",
        "output_bannyshow": "outputs/pipeline-smoke.bannyshow",
        "output_movie": "outputs/pipeline-smoke.mp4",
        "duration_sec": 60,
        "background_gain": 0.22,
        "feed_url": DEFAULT_FOOTBALL_FEED_URL,
        "espn_league": DEFAULT_ESPN_LEAGUE,
        "match_id": None,
        "no_espn": False,
        "overlays_path": None,
        "characters_path": str(DEFAULT_CHARACTERS_PATH),
        "instructions": "Build a tight Banny and Peel studio commentary episode.",
        "instructions_file": None,
        "script_provider": "template",
        "memory_dir": str(DEFAULT_MEMORY_DIR),
        "no_memory": False,
        "overwrite_script": False,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def build_pipeline_plan(config: PipelineConfig) -> dict[str, Any]:
    artifacts = {
        "feed": str(config.run_dir / "feed.json"),
        "script": str(config.run_dir / "script.json"),
        "manifest": str(config.run_dir / "pipeline-manifest.json"),
        "qa_checklist": str(config.run_dir / "studio-qa-checklist.md"),
        "movie_handoff": str(config.run_dir / "movie-export-handoff.md"),
        "output_bs": str(config.output_bs),
        "output_bannyshow": str(config.output_bannyshow),
        "output_movie": str(config.output_movie),
    }
    if not config.no_espn:
        artifacts.update(
            {
                "scoreboard": str(config.run_dir / "scoreboard.json"),
                "match_context": str(config.run_dir / "match_context.json"),
                "espn_overlays": str(config.run_dir / "espn-overlays.json"),
            }
        )
    if config.overlays_path:
        artifacts["input_overlays"] = str(config.overlays_path)

    return {
        "episode_slug": config.episode_slug,
        "template_path": str(config.template_path),
        "duration_sec": config.duration_sec,
        "background_gain": config.background_gain,
        "feed_url": config.feed_url,
        "espn_league": None if config.no_espn else config.espn_league,
        "overwrite_script": config.overwrite_script,
        "stages": [
            "inspect-template",
            "fetch-feed",
            *([] if config.no_espn else ["fetch-scoreboard", "normalize-match-context", "build-espn-overlays"]),
            "draft-script",
            "build-show",
            "unpack",
            "write-movie-export-handoff",
            "write-studio-qa-checklist",
            "write-pipeline-manifest",
        ],
        "artifacts": artifacts,
    }


def run_studio_pipeline(config: PipelineConfig, dry_run: bool = False) -> dict[str, Any]:
    plan = build_pipeline_plan(config)
    if dry_run:
        return plan

    config.run_dir.mkdir(parents=True, exist_ok=True)
    config.output_bs.parent.mkdir(parents=True, exist_ok=True)
    config.output_bannyshow.parent.mkdir(parents=True, exist_ok=True)

    feed_path = config.run_dir / "feed.json"
    script_path = config.run_dir / "script.json"
    _ensure_script_output(script_path, config.overwrite_script)
    template_inspection = inspect_package(config.template_path)
    overlays_path = config.overlays_path
    match_context = None

    feed = fetch_feed(config.feed_url)
    write_json(feed_path, feed)

    if not config.no_espn:
        scoreboard_url = config.scoreboard_url or scoreboard_url_for_league(config.espn_league)
        scoreboard_path = config.run_dir / "scoreboard.json"
        match_context_path = config.run_dir / "match_context.json"
        espn_overlays_path = config.run_dir / "espn-overlays.json"

        scoreboard = fetch_scoreboard(scoreboard_url)
        write_json(scoreboard_path, scoreboard)
        match_context = normalize_scoreboard(scoreboard, match_id=config.match_id)
        download_match_logos(match_context, config.run_dir / "espn-assets")
        write_json(match_context_path, match_context)
        write_json(espn_overlays_path, _merge_overlay_dicts(load_overlay_manifest(overlays_path), build_scoreboard_overlays(match_context)))
        overlays_path = espn_overlays_path

    characters = load_characters(config.characters_path)
    memory = [] if config.no_memory else load_episode_memory(config.memory_dir)
    script = draft_script(
        feed,
        duration_sec=config.duration_sec,
        match_context=match_context,
        characters=characters,
        episode_memory=memory,
        instructions=_instructions(config.instructions, config.instructions_file),
        script_provider=config.script_provider,
    )
    write_json(script_path, script)

    pfp_overlays = build_pfp_overlays(script, config.run_dir / "pfp-assets")
    if (pfp_overlays.get("overlays") or []) or overlays_path:
        pfp_overlays_path = config.run_dir / "pfp-overlays.json"
        write_json(pfp_overlays_path, _merge_overlay_dicts(load_overlay_manifest(overlays_path), pfp_overlays))
        overlays_path = pfp_overlays_path

    memory_path = None if config.no_memory else save_episode_memory(script, config.memory_dir)
    build_show(
        config.template_path,
        script_path,
        config.output_bs,
        background_gain=config.background_gain,
        overlays=overlays_path,
        characters=characters,
    )
    unpack_package(config.output_bs, config.output_bannyshow, overwrite=True)

    qa_path = config.run_dir / "studio-qa-checklist.md"
    handoff_path = config.run_dir / "movie-export-handoff.md"
    write_studio_qa_checklist(config, qa_path)
    write_movie_export_handoff(config, handoff_path)

    manifest = {
        **plan,
        "template_inspection": template_inspection,
        "memory_path": str(memory_path) if memory_path else None,
        "final_overlays": str(overlays_path) if overlays_path else None,
        "movie_export_path": str(config.output_movie),
        "delivery_status": "awaiting-studio-export",
        "status": "ready-for-studio-qa",
    }
    write_json(config.run_dir / "pipeline-manifest.json", manifest)
    return manifest


def write_studio_qa_checklist(config: PipelineConfig, path: Path) -> None:
    lines = [
        f"# Studio QA Checklist: {config.episode_slug}",
        "",
        f"- Input package: `{config.output_bs}`",
        f"- Unpacked package: `{config.output_bannyshow}`",
        f"- Target movie export: `{config.output_movie}`",
        f"- Run directory: `{config.run_dir}`",
        "",
        "## Import",
        "",
        "- [ ] Open the generated `.bs` in Banny Studio.",
        "- [ ] Confirm characters remain dressed and staged.",
        "- [ ] Confirm backgrounds, lights, and persistent props loaded.",
        "",
        "## Preview",
        "",
        "- [ ] Dialogue is audible.",
        "- [ ] Background gain is acceptable.",
        "- [ ] Mouth and motion events line up with speech.",
        "- [ ] ESPN or other generated overlays are visible when expected.",
        "- [ ] Farcaster PFP overlays are visible when expected.",
        "- [ ] Highlight or PiP overlays are visible and timed correctly.",
        "",
        "## Export",
        "",
        "- [ ] Export range covers the full episode.",
        f"- [ ] Export movie to `{config.output_movie}`.",
        "- [ ] Final video plays without missing media.",
        "- [ ] Re-opened `.bannyshow` still works.",
        "",
        "## Notes",
        "",
        "- Decision:",
        "- Needed rebuild changes:",
        "- Final export path:",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def write_movie_export_handoff(config: PipelineConfig, path: Path) -> None:
    lines = [
        f"# Movie Export Handoff: {config.episode_slug}",
        "",
        "This handoff is the bridge between the generated package pipeline and the final movie file.",
        "The repo prepares the package; Banny Studio performs the visual preview and movie export.",
        "",
        "## Inputs",
        "",
        f"- Generated package: `{config.output_bs}`",
        f"- Unpacked show folder: `{config.output_bannyshow}`",
        f"- Pipeline manifest: `{config.run_dir / 'pipeline-manifest.json'}`",
        f"- Studio QA checklist: `{config.run_dir / 'studio-qa-checklist.md'}`",
        "",
        "## Target Output",
        "",
        f"- Final movie: `{config.output_movie}`",
        "",
        "## Export Steps",
        "",
        "1. Open the generated `.bs` package in Banny Studio.",
        "2. Preview the full timeline from the beginning.",
        "3. Confirm dialogue, motion, overlays, and background audio are acceptable.",
        "4. Export the full range to the target movie path.",
        "5. Reopen or play the final movie file and check for missing media.",
        "6. Record any needed rebuild in the Studio QA checklist.",
        "",
        "## Completion Criteria",
        "",
        "- The final movie file exists at the target output path.",
        "- The movie plays start to finish without missing media.",
        "- The corresponding `.bs` and `.bannyshow` artifacts remain available for rebuilds.",
        "- QA notes include the final export decision.",
        "",
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _required_str(payload: dict[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise PipelineError(f"pipeline config missing required string: {key}")
    return value


def _ensure_script_output(path: Path, overwrite: bool) -> None:
    if not path.exists():
        return
    if not overwrite:
        raise PipelineError(f"{path} already exists; edit it and run build-show, or set overwrite_script=true")
    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def _path(value: Any, base_dir: Path) -> Path:
    path = Path(str(value))
    return path if path.is_absolute() else base_dir / path


def _optional_path(value: Any, base_dir: Path) -> Optional[Path]:
    if value in (None, ""):
        return None
    return _path(value, base_dir)


def _optional_float(value: Any) -> Optional[float]:
    if value in (None, ""):
        return None
    return float(value)


def _instructions(inline: Optional[str], path: Optional[Path]) -> Optional[str]:
    pieces = []
    if inline:
        pieces.append(inline)
    if path:
        pieces.append(path.read_text(encoding="utf-8").strip())
    return "\n".join(piece for piece in pieces if piece).strip() or None


def _merge_overlay_dicts(existing_overlays: list[dict], generated_overlays: dict) -> dict:
    overlays = []
    overlays.extend(existing_overlays)
    overlays.extend(generated_overlays.get("overlays") or [])
    return {"overlays": overlays}
