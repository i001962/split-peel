from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from split_peel.banny_cli import BannyCliError, resolve_banny_cli
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
from split_peel.overlays import build_key_moment_takeover_overlays, build_pfp_overlays, load_overlay_manifest
from split_peel.package import build_show, inspect_package, repair_banny_wardrobe, unpack_package
from split_peel.scriptwriter import draft_script
from split_peel.youtube import (
    DEFAULT_YOUTUBE_CATEGORY_ID,
    DEFAULT_YOUTUBE_PRIVACY_STATUS,
    YouTubeUploadError,
    YouTubeUploadMetadata,
    build_youtube_description,
    upload_video,
)


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
    episode_title: Optional[str] = None
    episode_type: str = "match-event"
    show_name: str = "Final Whistle with Split & Peel"
    tagline: str = "The whistle goes, the takes stay loud."
    background_gain: Optional[float] = None
    feed_url: str = DEFAULT_FOOTBALL_FEED_URL
    no_feed: bool = False
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
    draft_only: bool = False
    reuse_audio_from: Optional[Path] = None
    skip_voice: bool = False
    banny_enabled: bool = False
    banny_bin: Optional[Path] = None
    banny_checkout_path: Optional[Path] = None
    banny_render_size: str = "720"
    banny_preview_times: tuple[float, ...] = ()
    banny_ship: bool = False
    youtube_upload_enabled: bool = False
    youtube_credentials: Optional[Path] = None
    youtube_token: Optional[Path] = None
    youtube_title: Optional[str] = None
    youtube_description: Optional[str] = None
    youtube_description_file: Optional[Path] = None
    youtube_tags: tuple[str, ...] = ()
    youtube_category_id: str = DEFAULT_YOUTUBE_CATEGORY_ID
    youtube_privacy_status: str = DEFAULT_YOUTUBE_PRIVACY_STATUS
    youtube_notify_subscribers: bool = False
    youtube_made_for_kids: bool = False
    youtube_contains_synthetic_media: Optional[bool] = None
    youtube_thumbnail: Optional[Path] = None


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
        episode_title=payload.get("episode_title"),
        episode_type=str(payload.get("episode_type") or "match-event"),
        show_name=str(payload.get("show_name") or "Final Whistle with Split & Peel"),
        tagline=str(payload.get("tagline") or "The whistle goes, the takes stay loud."),
        background_gain=_optional_float(payload.get("background_gain")),
        feed_url=str(payload.get("feed_url") or DEFAULT_FOOTBALL_FEED_URL),
        no_feed=bool(payload.get("no_feed", False)),
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
        draft_only=bool(payload.get("draft_only", False) or payload.get("no_build", False)),
        reuse_audio_from=_optional_path(payload.get("reuse_audio_from"), base_dir),
        skip_voice=bool(payload.get("skip_voice", False)),
        banny_enabled=bool(payload.get("banny_enabled", False)),
        banny_bin=_optional_path(payload.get("banny_bin"), base_dir),
        banny_checkout_path=_optional_path(payload.get("banny_checkout_path"), base_dir),
        banny_render_size=_render_size(payload.get("banny_render_size") or "720"),
        banny_preview_times=_preview_times(payload.get("banny_preview_times")),
        banny_ship=bool(payload.get("banny_ship", False)),
        youtube_upload_enabled=bool(payload.get("youtube_upload_enabled", False)),
        youtube_credentials=_optional_path(payload.get("youtube_credentials"), base_dir),
        youtube_token=_optional_path(payload.get("youtube_token"), base_dir),
        youtube_title=payload.get("youtube_title"),
        youtube_description=payload.get("youtube_description"),
        youtube_description_file=_optional_path(payload.get("youtube_description_file"), base_dir),
        youtube_tags=_string_tuple(payload.get("youtube_tags")),
        youtube_category_id=str(payload.get("youtube_category_id") or DEFAULT_YOUTUBE_CATEGORY_ID),
        youtube_privacy_status=_youtube_privacy_status(payload.get("youtube_privacy_status") or DEFAULT_YOUTUBE_PRIVACY_STATUS),
        youtube_notify_subscribers=bool(payload.get("youtube_notify_subscribers", False)),
        youtube_made_for_kids=bool(payload.get("youtube_made_for_kids", False)),
        youtube_contains_synthetic_media=_optional_bool(payload.get("youtube_contains_synthetic_media")),
        youtube_thumbnail=_optional_path(payload.get("youtube_thumbnail"), base_dir),
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
        "episode_title": "ENG1 Matchday Preview",
        "episode_type": "game-week-preview",
        "show_name": "Final Whistle with Split & Peel",
        "tagline": "The whistle goes, the takes stay loud.",
        "background_gain": 0.22,
        "feed_url": DEFAULT_FOOTBALL_FEED_URL,
        "no_feed": False,
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
        "draft_only": False,
        "reuse_audio_from": None,
        "skip_voice": False,
        "banny_enabled": True,
        "banny_bin": None,
        "banny_checkout_path": None,
        "banny_render_size": "720",
        "banny_preview_times": [2, 8, 14],
        "banny_ship": True,
        "youtube_upload_enabled": False,
        "youtube_credentials": None,
        "youtube_token": ".secrets/youtube-token.json",
        "youtube_title": None,
        "youtube_description": None,
        "youtube_description_file": None,
        "youtube_tags": ["football", "final whistle"],
        "youtube_category_id": DEFAULT_YOUTUBE_CATEGORY_ID,
        "youtube_privacy_status": DEFAULT_YOUTUBE_PRIVACY_STATUS,
        "youtube_notify_subscribers": False,
        "youtube_made_for_kids": False,
        "youtube_contains_synthetic_media": None,
        "youtube_thumbnail": None,
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
    if config.banny_enabled:
        artifacts["banny_catalog"] = str(config.run_dir / "banny-catalog.json")
        artifacts["banny_wardrobe_repairs"] = str(config.run_dir / "banny-wardrobe-repairs.json")
        artifacts["banny_validate"] = str(config.run_dir / "banny-validate.json")
        artifacts["banny_info"] = str(config.run_dir / "banny-info.json")
        if config.banny_preview_times:
            artifacts["banny_previews"] = [
                str(_preview_path(config, timestamp)) for timestamp in config.banny_preview_times
            ]
        if config.banny_ship:
            artifacts["output_movie"] = str(config.output_movie)
    if config.youtube_upload_enabled and not config.draft_only:
        artifacts["youtube_upload"] = str(config.run_dir / "youtube-upload.json")

    return {
        "episode_slug": config.episode_slug,
        "template_path": str(config.template_path),
        "duration_sec": config.duration_sec,
        "episode_title": config.episode_title,
        "episode_type": config.episode_type,
        "show_name": config.show_name,
        "tagline": config.tagline,
        "background_gain": config.background_gain,
        "feed_url": config.feed_url,
        "no_feed": config.no_feed,
        "espn_league": None if config.no_espn else config.espn_league,
        "overwrite_script": config.overwrite_script,
        "draft_only": config.draft_only,
        "reuse_audio_from": str(config.reuse_audio_from) if config.reuse_audio_from else None,
        "skip_voice": config.skip_voice,
        "stages": [
            "inspect-template",
            "write-empty-feed" if config.no_feed else "fetch-feed",
            *([] if config.no_espn else ["fetch-scoreboard", "normalize-match-context", "build-espn-overlays"]),
            "draft-script",
            *([] if config.draft_only else ["build-show", "unpack", *_banny_stages(config)]),
            *([] if config.draft_only else ["write-movie-export-handoff", "write-studio-qa-checklist"]),
            *([] if config.draft_only or not config.youtube_upload_enabled else ["youtube-upload"]),
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

    feed = {"casts": []} if config.no_feed else fetch_feed(config.feed_url)
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
        write_json(
            espn_overlays_path,
            _merge_overlay_dicts(
                load_overlay_manifest(overlays_path),
                build_scoreboard_overlays(match_context, episode_type=config.episode_type),
            ),
        )
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
        episode_title=config.episode_title,
        episode_type=config.episode_type,
        show_name=config.show_name,
        tagline=config.tagline,
    )
    write_json(script_path, script)

    pfp_overlays = build_pfp_overlays(script, config.run_dir / "pfp-assets")
    key_moment_overlays = build_key_moment_takeover_overlays(script, config.run_dir / "key-moment-assets")
    generated_overlay_count = len(pfp_overlays.get("overlays") or []) + len(key_moment_overlays.get("overlays") or [])
    if generated_overlay_count or overlays_path:
        pfp_overlays_path = config.run_dir / "pfp-overlays.json"
        write_json(
            pfp_overlays_path,
            _merge_overlay_dicts(
                load_overlay_manifest(overlays_path),
                _merge_overlay_dicts(pfp_overlays.get("overlays") or [], key_moment_overlays),
            ),
        )
        overlays_path = pfp_overlays_path

    if config.draft_only:
        manifest = {
            **plan,
            "template_inspection": template_inspection,
            "memory_path": None,
            "final_overlays": str(overlays_path) if overlays_path else None,
            "movie_export_path": str(config.output_movie),
            "banny": None,
            "delivery_status": "draft-ready",
            "status": "ready-for-script-review",
        }
        write_json(config.run_dir / "pipeline-manifest.json", manifest)
        return manifest

    memory_path = None if config.no_memory else save_episode_memory(script, config.memory_dir)
    build_show(
        config.template_path,
        script_path,
        config.output_bs,
        background_gain=config.background_gain,
        overlays=overlays_path,
        characters=characters,
        reuse_audio_from=config.reuse_audio_from,
        skip_voice=config.skip_voice,
    )
    banny_result = run_banny_post_build(config) if config.banny_enabled else None
    unpack_package(config.output_bs, config.output_bannyshow, overwrite=True)

    qa_path = config.run_dir / "studio-qa-checklist.md"
    handoff_path = config.run_dir / "movie-export-handoff.md"
    write_studio_qa_checklist(config, qa_path, banny_result=banny_result)
    write_movie_export_handoff(config, handoff_path, banny_result=banny_result)
    youtube_result = run_youtube_upload(config, script) if config.youtube_upload_enabled else None

    manifest = {
        **plan,
        "template_inspection": template_inspection,
        "memory_path": str(memory_path) if memory_path else None,
        "final_overlays": str(overlays_path) if overlays_path else None,
        "movie_export_path": str(config.output_movie),
        "banny": banny_result,
        "youtube": youtube_result,
        "delivery_status": _delivery_status(banny_result, youtube_result),
        "status": "ready-for-studio-qa",
    }
    write_json(config.run_dir / "pipeline-manifest.json", manifest)
    return manifest


def run_youtube_upload(config: PipelineConfig, script: dict[str, Any]) -> dict[str, Any]:
    if not config.output_movie.exists():
        raise PipelineError(f"YouTube upload is enabled but movie file does not exist: {config.output_movie}")
    title = _youtube_title(config, script)
    description = _youtube_description(config, script)
    try:
        return upload_video(
            config.output_movie,
            YouTubeUploadMetadata(
                title=title,
                description=description,
                tags=config.youtube_tags,
                category_id=config.youtube_category_id,
                privacy_status=config.youtube_privacy_status,
                notify_subscribers=config.youtube_notify_subscribers,
                made_for_kids=config.youtube_made_for_kids,
                contains_synthetic_media=config.youtube_contains_synthetic_media,
            ),
            credentials_path=config.youtube_credentials,
            token_path=config.youtube_token,
            thumbnail_path=config.youtube_thumbnail,
            out_path=config.run_dir / "youtube-upload.json",
        )
    except YouTubeUploadError as error:
        raise PipelineError(str(error)) from error


def run_banny_post_build(config: PipelineConfig) -> dict[str, Any]:
    try:
        cli = resolve_banny_cli(config.banny_bin, config.banny_checkout_path)
    except BannyCliError as error:
        raise PipelineError(str(error)) from error

    validate_path = config.run_dir / "banny-validate.json"
    info_path = config.run_dir / "banny-info.json"
    catalog_path = config.run_dir / "banny-catalog.json"
    repairs_path = config.run_dir / "banny-wardrobe-repairs.json"
    try:
        catalog = cli.catalog()
        catalog_path.write_text(catalog.stdout, encoding="utf-8")
        repairs = repair_banny_wardrobe(config.output_bs, json.loads(catalog.stdout))
        write_json(repairs_path, repairs)
        validate = cli.validate(config.output_bs)
        info = cli.info(config.output_bs)
        validate_path.write_text(validate.stdout, encoding="utf-8")
        info_path.write_text(info.stdout, encoding="utf-8")

        previews = []
        for timestamp in config.banny_preview_times:
            preview_path = _preview_path(config, timestamp)
            cli.preview(config.output_bs, preview_path, timestamp)
            previews.append({"time": timestamp, "path": str(preview_path)})

        movie = None
        if config.banny_ship:
            cli.ship(config.output_bs, config.output_movie, config.banny_render_size)
            movie = str(config.output_movie)
    except BannyCliError as error:
        raise PipelineError(str(error)) from error

    return {
        "command_prefix": cli.command_prefix,
        "cwd": str(cli.cwd) if cli.cwd else None,
        "catalog": str(catalog_path),
        "wardrobe_repairs": str(repairs_path),
        "wardrobe_repair_count": len(repairs),
        "validate": str(validate_path),
        "info": str(info_path),
        "previews": previews,
        "render_size": config.banny_render_size,
        "movie": movie,
    }


def write_studio_qa_checklist(config: PipelineConfig, path: Path, banny_result: Optional[dict[str, Any]] = None) -> None:
    lines = [
        f"# Studio QA Checklist: {config.episode_slug}",
        "",
        f"- Input package: `{config.output_bs}`",
        f"- Unpacked package: `{config.output_bannyshow}`",
        f"- Target movie export: `{config.output_movie}`",
        f"- Run directory: `{config.run_dir}`",
        "",
        "## Banny CLI",
        "",
        *(_banny_checklist_lines(config, banny_result)),
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


def write_movie_export_handoff(config: PipelineConfig, path: Path, banny_result: Optional[dict[str, Any]] = None) -> None:
    lines = [
        f"# Movie Export Handoff: {config.episode_slug}",
        "",
        "This handoff is the bridge between the generated package pipeline and the final movie file.",
        _handoff_summary(config, banny_result),
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
        *_handoff_steps(config, banny_result),
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


def _optional_bool(value: Any) -> Optional[bool]:
    if value in (None, ""):
        return None
    return bool(value)


def _render_size(value: Any) -> str:
    size = str(value)
    if size not in {"480", "720", "1080", "4k"}:
        raise PipelineError("banny_render_size must be one of: 480, 720, 1080, 4k")
    return size


def _preview_times(value: Any) -> tuple[float, ...]:
    if value in (None, ""):
        return ()
    if not isinstance(value, list):
        raise PipelineError("banny_preview_times must be a list of seconds")
    return tuple(float(item) for item in value)


def _string_tuple(value: Any) -> tuple[str, ...]:
    if value in (None, ""):
        return ()
    if isinstance(value, str):
        return tuple(item.strip() for item in value.split(",") if item.strip())
    if isinstance(value, list):
        return tuple(str(item).strip() for item in value if str(item).strip())
    raise PipelineError("youtube_tags must be a list of strings or comma-separated string")


def _youtube_privacy_status(value: Any) -> str:
    status = str(value)
    if status not in {"private", "public", "unlisted"}:
        raise PipelineError("youtube_privacy_status must be one of: private, public, unlisted")
    return status


def _instructions(inline: Optional[str], path: Optional[Path]) -> Optional[str]:
    pieces = []
    if inline:
        pieces.append(inline)
    if path:
        pieces.append(path.read_text(encoding="utf-8").strip())
    return "\n".join(piece for piece in pieces if piece).strip() or None


def _youtube_title(config: PipelineConfig, script: dict[str, Any]) -> str:
    return (
        (config.youtube_title or "").strip()
        or str(script.get("title") or "").strip()
        or (config.episode_title or "").strip()
        or config.episode_slug
    )


def _youtube_description(config: PipelineConfig, script: dict[str, Any]) -> str:
    configured = _instructions(config.youtube_description, config.youtube_description_file)
    if configured:
        return configured
    return build_youtube_description(script, show_name=config.show_name, tagline=config.tagline)


def _delivery_status(banny_result: Optional[dict[str, Any]], youtube_result: Optional[dict[str, Any]]) -> str:
    if youtube_result and youtube_result.get("video_id"):
        return "uploaded-to-youtube"
    if banny_result and banny_result.get("movie"):
        return "movie-exported"
    return "awaiting-studio-export"


def _merge_overlay_dicts(existing_overlays: list[dict], generated_overlays: dict) -> dict:
    overlays = []
    overlays.extend(existing_overlays)
    overlays.extend(generated_overlays.get("overlays") or [])
    return {"overlays": overlays}


def _banny_stages(config: PipelineConfig) -> list[str]:
    if not config.banny_enabled:
        return []
    stages = ["banny-validate", "banny-info"]
    if config.banny_preview_times:
        stages.append("banny-preview")
    if config.banny_ship:
        stages.append("banny-ship")
    return stages


def _preview_path(config: PipelineConfig, timestamp: float) -> Path:
    return config.run_dir / f"preview-{_preview_slug(timestamp)}.png"


def _preview_slug(timestamp: float) -> str:
    return f"{timestamp:06.3f}".replace(".", "-")


def _banny_checklist_lines(config: PipelineConfig, banny_result: Optional[dict[str, Any]]) -> list[str]:
    if not config.banny_enabled:
        return [
            "- [ ] Banny CLI validation was not enabled for this run.",
            "- [ ] Open and export manually in Banny Studio.",
        ]
    if not banny_result:
        return [
            "- [ ] Banny CLI validation is enabled and will run after package generation.",
            "- [ ] Confirm `banny validate` passes before movie export.",
        ]

    lines = [
        f"- [x] `banny validate` output: `{banny_result['validate']}`",
        f"- [x] `banny info --json` output: `{banny_result['info']}`",
    ]
    previews = banny_result.get("previews") or []
    if previews:
        for preview in previews:
            lines.append(f"- [ ] Review preview frame at {preview['time']}s: `{preview['path']}`")
    else:
        lines.append("- [ ] No Banny preview frames were configured for this run.")

    if banny_result.get("movie"):
        lines.append(f"- [ ] Play exported movie: `{banny_result['movie']}`")
    else:
        lines.append(f"- [ ] Export movie manually to `{config.output_movie}`.")
    return lines


def _handoff_summary(config: PipelineConfig, banny_result: Optional[dict[str, Any]]) -> str:
    if banny_result and banny_result.get("movie"):
        return "The repo prepared the package, validated it with the Banny CLI, and rendered the movie headlessly."
    if config.banny_enabled:
        return "The repo prepares the package and validates/previews it with the Banny CLI; Banny Studio can still perform final manual export."
    return "The repo prepares the package; Banny Studio performs the visual preview and movie export."


def _handoff_steps(config: PipelineConfig, banny_result: Optional[dict[str, Any]]) -> list[str]:
    if banny_result and banny_result.get("movie"):
        return [
            f"1. Play `{banny_result['movie']}` from start to finish.",
            "2. Compare the generated preview frames against the intended episode beats.",
            "3. Open the generated `.bs` package in Banny Studio only if visual or timing fixes are needed.",
            "4. Record any needed rebuild in the Studio QA checklist.",
        ]
    if config.banny_enabled:
        return [
            "1. Review the Banny CLI validation and info artifacts.",
            "2. Review generated preview frames for key moments.",
            "3. Open the generated `.bs` package in Banny Studio.",
            "4. Export the full range to the target movie path.",
            "5. Reopen or play the final movie file and check for missing media.",
            "6. Record any needed rebuild in the Studio QA checklist.",
        ]
    return [
        "1. Open the generated `.bs` package in Banny Studio.",
        "2. Preview the full timeline from the beginning.",
        "3. Confirm dialogue, motion, overlays, and background audio are acceptable.",
        "4. Export the full range to the target movie path.",
        "5. Reopen or play the final movie file and check for missing media.",
        "6. Record any needed rebuild in the Studio QA checklist.",
    ]
