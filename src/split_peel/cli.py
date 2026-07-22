from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path
from typing import Optional

from split_peel.characters import DEFAULT_CHARACTERS_PATH, load_characters
from split_peel.config import load_dotenv
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
from split_peel.package import build_show, inspect_package, retime_mouth_events, roundtrip_package, unpack_package
from split_peel.pipeline import (
    load_pipeline_config,
    run_studio_pipeline,
    write_pipeline_config_template,
)
from split_peel.scriptwriter import EPISODE_TYPE_CHOICES, draft_script
from split_peel.youtube import YouTubeUploadMetadata, upload_video


def main(argv: Optional[list[str]] = None) -> int:
    load_dotenv()

    parser = argparse.ArgumentParser(prog="split-peel")
    subparsers = parser.add_subparsers(dest="command", required=True)

    fetch_parser = subparsers.add_parser("fetch-feed", help="Fetch and cache the Farcaster feed.")
    fetch_parser.add_argument("--feed-url", default=DEFAULT_FOOTBALL_FEED_URL)
    fetch_parser.add_argument("--out", type=Path, required=True)

    scoreboard_parser = subparsers.add_parser("fetch-scoreboard", help="Fetch and normalize an ESPN scoreboard.")
    scoreboard_parser.add_argument("--espn-league", default=DEFAULT_ESPN_LEAGUE)
    scoreboard_parser.add_argument("--scoreboard-url")
    scoreboard_parser.add_argument("--match-id")
    scoreboard_parser.add_argument("--out", type=Path, required=True)
    scoreboard_parser.add_argument("--match-context-out", type=Path)

    characters_parser = subparsers.add_parser("characters", help="Print the active character profiles.")
    characters_parser.add_argument("--characters", type=Path, default=DEFAULT_CHARACTERS_PATH)

    draft_parser = subparsers.add_parser("draft-script", help="Draft a structured two-commentator script.")
    draft_parser.add_argument("--feed", type=Path, required=True)
    draft_parser.add_argument("--out", type=Path, required=True)
    draft_parser.add_argument("--duration-sec", type=int, default=60)
    draft_parser.add_argument("--episode-title")
    draft_parser.add_argument("--episode-type", default="match-event", choices=EPISODE_TYPE_CHOICES)
    draft_parser.add_argument("--show-name", default="Final Whistle with Split & Peel")
    draft_parser.add_argument("--tagline", default="The whistle goes, the takes stay loud.")
    draft_parser.add_argument("--match-context", type=Path)
    draft_parser.add_argument("--characters", type=Path, default=DEFAULT_CHARACTERS_PATH)
    draft_parser.add_argument("--instructions")
    draft_parser.add_argument("--instructions-file", type=Path)
    draft_parser.add_argument("--script-provider", choices=["template", "local", "openai"])
    draft_parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    draft_parser.add_argument("--no-memory", action="store_true")
    draft_parser.add_argument("--overwrite-script", action="store_true")

    inspect_parser = subparsers.add_parser("inspect-template", help="Inspect a Banny .bs template.")
    inspect_parser.add_argument("--template", type=Path, required=True)

    roundtrip_parser = subparsers.add_parser("roundtrip", help="Unpack and repackage a .bs file unchanged.")
    roundtrip_parser.add_argument("--template", type=Path, required=True)
    roundtrip_parser.add_argument("--out", type=Path, required=True)

    unpack_parser = subparsers.add_parser("unpack", help="Extract a .bs package to a .bannyshow folder.")
    unpack_parser.add_argument("--template", type=Path, required=True)
    unpack_parser.add_argument("--out", type=Path, required=True)
    unpack_parser.add_argument("--overwrite", action="store_true")

    retime_mouth_parser = subparsers.add_parser("retime-mouth", help="Rebuild mouth events from existing dialogue WAV files.")
    retime_mouth_parser.add_argument("--template", type=Path, required=True)
    retime_mouth_parser.add_argument("--out", type=Path, required=True)
    retime_mouth_parser.add_argument("--overwrite", action="store_true")

    build_parser = subparsers.add_parser("build-show", help="Build a .bs show from a template and script.")
    build_parser.add_argument("--template", type=Path, required=True)
    build_parser.add_argument("--script", type=Path)
    build_parser.add_argument("--out", type=Path, required=True)
    build_parser.add_argument("--background-gain", type=float)
    build_parser.add_argument("--overlays", type=Path)
    build_parser.add_argument("--characters", type=Path, default=DEFAULT_CHARACTERS_PATH)
    build_parser.add_argument("--reuse-audio-from", type=Path)
    build_parser.add_argument("--skip-voice", action="store_true")

    make_parser = subparsers.add_parser("make", help="Run the first end-to-end smoke pipeline.")
    make_parser.add_argument("--template", type=Path, required=True)
    make_parser.add_argument("--feed-url", default=DEFAULT_FOOTBALL_FEED_URL)
    make_parser.add_argument("--espn-league", default=DEFAULT_ESPN_LEAGUE)
    make_parser.add_argument("--scoreboard-url")
    make_parser.add_argument("--match-id")
    make_parser.add_argument("--no-espn", action="store_true")
    make_parser.add_argument("--run-dir", type=Path, default=Path("runs/latest"))
    make_parser.add_argument("--out", type=Path, required=True)
    make_parser.add_argument("--duration-sec", type=int, default=60)
    make_parser.add_argument("--episode-title")
    make_parser.add_argument("--episode-type", default="match-event", choices=EPISODE_TYPE_CHOICES)
    make_parser.add_argument("--show-name", default="Final Whistle with Split & Peel")
    make_parser.add_argument("--tagline", default="The whistle goes, the takes stay loud.")
    make_parser.add_argument("--background-gain", type=float)
    make_parser.add_argument("--overlays", type=Path)
    make_parser.add_argument("--characters", type=Path, default=DEFAULT_CHARACTERS_PATH)
    make_parser.add_argument("--instructions")
    make_parser.add_argument("--instructions-file", type=Path)
    make_parser.add_argument("--script-provider", choices=["template", "local", "openai"])
    make_parser.add_argument("--memory-dir", type=Path, default=DEFAULT_MEMORY_DIR)
    make_parser.add_argument("--no-memory", action="store_true")
    make_parser.add_argument("--overwrite-script", action="store_true")
    make_parser.add_argument("--draft-only", "--no-build", dest="draft_only", action="store_true")
    make_parser.add_argument("--reuse-audio-from", type=Path)
    make_parser.add_argument("--skip-voice", action="store_true")

    pipeline_parser = subparsers.add_parser("studio-pipeline", help="Run a config-driven Banny Studio development pipeline.")
    pipeline_parser.add_argument("--config", type=Path, required=True)
    pipeline_parser.add_argument("--dry-run", action="store_true")
    pipeline_parser.add_argument("--init-config", action="store_true")

    youtube_parser = subparsers.add_parser("upload-youtube", help="Upload a finished movie to YouTube.")
    youtube_parser.add_argument("--file", type=Path, required=True)
    youtube_parser.add_argument("--title", required=True)
    youtube_parser.add_argument("--description", default="")
    youtube_parser.add_argument("--description-file", type=Path)
    youtube_parser.add_argument("--tags", default="")
    youtube_parser.add_argument("--category-id", default="17")
    youtube_parser.add_argument("--privacy-status", default="private", choices=["private", "public", "unlisted"])
    youtube_parser.add_argument("--notify-subscribers", action="store_true")
    youtube_parser.add_argument("--made-for-kids", action="store_true")
    youtube_parser.add_argument("--contains-synthetic-media", action="store_true")
    youtube_parser.add_argument("--credentials", type=Path)
    youtube_parser.add_argument("--token", type=Path)
    youtube_parser.add_argument("--thumbnail", type=Path)
    youtube_parser.add_argument("--out", type=Path)
    youtube_parser.add_argument("--dry-run", action="store_true")

    args = parser.parse_args(argv)

    if args.command == "fetch-feed":
        payload = fetch_feed(args.feed_url)
        write_json(args.out, payload)
        print(f"wrote {args.out}")
        return 0

    if args.command == "fetch-scoreboard":
        scoreboard_url = _scoreboard_url(args.scoreboard_url, args.espn_league)
        payload = fetch_scoreboard(scoreboard_url)
        write_json(args.out, payload)
        print(f"wrote {args.out}")
        if args.match_context_out:
            context = normalize_scoreboard(payload, match_id=args.match_id)
            write_json(args.match_context_out, context)
            print(f"wrote {args.match_context_out}")
        return 0

    if args.command == "characters":
        print(json.dumps(load_characters(args.characters), indent=2))
        return 0

    if args.command == "draft-script":
        _ensure_script_output(args.out, args.overwrite_script)
        feed = _read_json(args.feed)
        match_context = _read_json(args.match_context) if args.match_context else None
        characters = load_characters(args.characters)
        memory = [] if args.no_memory else load_episode_memory(args.memory_dir)
        instructions = _instructions(args.instructions, args.instructions_file)
        script = draft_script(
            feed,
            duration_sec=args.duration_sec,
            match_context=match_context,
            characters=characters,
            episode_memory=memory,
            instructions=instructions,
            script_provider=args.script_provider,
            episode_title=args.episode_title,
            episode_type=args.episode_type,
            show_name=args.show_name,
            tagline=args.tagline,
        )
        write_json(args.out, script)
        print(f"wrote {args.out}")
        return 0

    if args.command == "inspect-template":
        print(json.dumps(inspect_package(args.template), indent=2))
        return 0

    if args.command == "roundtrip":
        roundtrip_package(args.template, args.out)
        print(f"wrote {args.out}")
        return 0

    if args.command == "unpack":
        unpack_package(args.template, args.out, overwrite=args.overwrite)
        print(f"wrote {args.out}")
        return 0

    if args.command == "retime-mouth":
        retime_mouth_events(args.template, args.out, overwrite=args.overwrite)
        print(f"wrote {args.out}")
        return 0

    if args.command == "build-show":
        characters = load_characters(args.characters)
        build_show(
            args.template,
            args.script,
            args.out,
            background_gain=args.background_gain,
            overlays=args.overlays,
            characters=characters,
            reuse_audio_from=args.reuse_audio_from,
            skip_voice=args.skip_voice,
        )
        print(f"wrote {args.out}")
        return 0

    if args.command == "make":
        feed_path = args.run_dir / "feed.json"
        script_path = args.run_dir / "script.json"
        _ensure_script_output(script_path, args.overwrite_script)
        match_context = None
        overlays_path = args.overlays
        characters = load_characters(args.characters)
        memory = [] if args.no_memory else load_episode_memory(args.memory_dir)
        instructions = _instructions(args.instructions, args.instructions_file)
        feed = fetch_feed(args.feed_url)
        write_json(feed_path, feed)

        if not args.no_espn:
            scoreboard_path = args.run_dir / "scoreboard.json"
            match_context_path = args.run_dir / "match_context.json"
            espn_overlays_path = args.run_dir / "espn-overlays.json"
            scoreboard_url = _scoreboard_url(args.scoreboard_url, args.espn_league)
            scoreboard = fetch_scoreboard(scoreboard_url)
            write_json(scoreboard_path, scoreboard)
            match_context = normalize_scoreboard(scoreboard, match_id=args.match_id)
            download_match_logos(match_context, args.run_dir / "espn-assets")
            write_json(match_context_path, match_context)
            overlays = _merged_overlays(args.overlays, build_scoreboard_overlays(match_context, episode_type=args.episode_type))
            write_json(espn_overlays_path, overlays)
            overlays_path = espn_overlays_path

        script = draft_script(
            feed,
            duration_sec=args.duration_sec,
            match_context=match_context,
            characters=characters,
            episode_memory=memory,
            instructions=instructions,
            script_provider=args.script_provider,
            episode_title=args.episode_title,
            episode_type=args.episode_type,
            show_name=args.show_name,
            tagline=args.tagline,
        )
        write_json(script_path, script)
        pfp_overlays = build_pfp_overlays(script, args.run_dir / "pfp-assets")
        key_moment_overlays = build_key_moment_takeover_overlays(script, args.run_dir / "key-moment-assets")
        generated_overlay_count = len(pfp_overlays.get("overlays") or []) + len(key_moment_overlays.get("overlays") or [])
        if generated_overlay_count or overlays_path:
            pfp_overlays_path = args.run_dir / "pfp-overlays.json"
            overlays = _merged_overlay_dicts(
                load_overlay_manifest(overlays_path),
                _merged_overlay_dicts(pfp_overlays.get("overlays") or [], key_moment_overlays),
            )
            write_json(pfp_overlays_path, overlays)
            overlays_path = pfp_overlays_path

        if args.draft_only:
            print(f"wrote {feed_path}")
            if not args.no_espn:
                print(f"wrote {args.run_dir / 'scoreboard.json'}")
                print(f"wrote {args.run_dir / 'match_context.json'}")
                print(f"wrote {args.run_dir / 'espn-overlays.json'}")
            if overlays_path == args.run_dir / "pfp-overlays.json":
                print(f"wrote {overlays_path}")
            print(f"wrote {script_path}")
            print("skipped build-show (--draft-only)")
            return 0

        memory_path = None if args.no_memory else save_episode_memory(script, args.memory_dir)
        build_show(
            args.template,
            script_path,
            args.out,
            background_gain=args.background_gain,
            overlays=overlays_path,
            characters=characters,
            reuse_audio_from=args.reuse_audio_from,
            skip_voice=args.skip_voice,
        )
        print(f"wrote {feed_path}")
        if not args.no_espn:
            print(f"wrote {args.run_dir / 'scoreboard.json'}")
            print(f"wrote {args.run_dir / 'match_context.json'}")
            print(f"wrote {args.run_dir / 'espn-overlays.json'}")
        if overlays_path == args.run_dir / "pfp-overlays.json":
            print(f"wrote {overlays_path}")
        print(f"wrote {script_path}")
        if memory_path:
            print(f"wrote {memory_path}")
        print(f"wrote {args.out}")
        return 0

    if args.command == "studio-pipeline":
        if args.init_config:
            write_pipeline_config_template(args.config)
            print(f"wrote {args.config}")
            return 0

        manifest = run_studio_pipeline(load_pipeline_config(args.config), dry_run=args.dry_run)
        print(json.dumps(manifest, indent=2))
        return 0

    if args.command == "upload-youtube":
        description = _instructions(args.description, args.description_file) or ""
        result = upload_video(
            args.file,
            YouTubeUploadMetadata(
                title=args.title,
                description=description,
                tags=_tags(args.tags),
                category_id=args.category_id,
                privacy_status=args.privacy_status,
                notify_subscribers=args.notify_subscribers,
                made_for_kids=args.made_for_kids,
                contains_synthetic_media=True if args.contains_synthetic_media else None,
            ),
            credentials_path=args.credentials,
            token_path=args.token,
            thumbnail_path=args.thumbnail,
            out_path=args.out,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, indent=2))
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2


def _read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _ensure_script_output(path: Path, overwrite: bool) -> None:
    if not path.exists():
        return
    if not overwrite:
        raise SystemExit(f"{path} already exists; edit it and run build-show, or pass --overwrite-script to replace it")
    shutil.copy2(path, path.with_suffix(path.suffix + ".bak"))


def _instructions(inline: Optional[str], path: Optional[Path]) -> Optional[str]:
    pieces = []
    if inline:
        pieces.append(inline)
    if path:
        pieces.append(path.read_text(encoding="utf-8").strip())
    return "\n".join(piece for piece in pieces if piece).strip() or None


def _scoreboard_url(scoreboard_url: Optional[str], espn_league: str) -> str:
    return scoreboard_url or scoreboard_url_for_league(espn_league)


def _merged_overlays(user_overlay_path: Optional[Path], generated_overlays: dict) -> dict:
    overlays = []
    overlays.extend(load_overlay_manifest(user_overlay_path))
    overlays.extend(generated_overlays.get("overlays") or [])
    return {"overlays": overlays}


def _merged_overlay_dicts(existing_overlays: list[dict], generated_overlays: dict) -> dict:
    overlays = []
    overlays.extend(existing_overlays)
    overlays.extend(generated_overlays.get("overlays") or [])
    return {"overlays": overlays}


def _tags(value: str) -> tuple[str, ...]:
    return tuple(tag.strip() for tag in value.split(",") if tag.strip())


if __name__ == "__main__":
    raise SystemExit(main())
