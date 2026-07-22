---
name: split-peel
description: Build, validate, preview, and render Banny Studio football commentary episodes with the split-peel repo. Use when Codex needs to generate or modify Banny Studio `.bs`, `.bannyshow`, or mp4 outputs from Farcaster football feeds, ESPN match context, two-commentator scripts, character voice profiles, mouth/motion timing, foreground overlays, Banny CLI wardrobe/catalog checks, or the config-driven Studio pipeline.
---

# Split Peel

Use this repo as the execution engine for Banny Studio episode builds. Prefer the `split-peel` CLI over hand-editing package JSON unless the user asks for a narrow inspection or patch.

## Orient

1. Check the working tree before editing: `git status --short`.
2. Read [README.md](README.md) for setup, environment variables, command examples, script shape, character configuration, overlays, and package mutation notes.
3. Read [docs/studio-development-pipeline.md](docs/studio-development-pipeline.md) when the user wants a repeatable episode build, dry run, QA checklist, movie handoff, or Hubs-linked workflow.
4. Read [docs/hubs-board-blueprint.md](docs/hubs-board-blueprint.md) only when the user asks to plan or operate the Hubs board flow.
5. Read [references/banny-cli.md](references/banny-cli.md) when the task involves Banny CLI setup, wardrobe/catalog choices, validation, preview frames, headless mp4 render, or `.bs` format details beyond this repo's pipeline.

## Setup

Install locally when `split-peel` is unavailable:

```bash
python -m pip install -e ".[dev]"
```

Run validation after code or behavior changes:

```bash
python -m pytest
```

Do not commit `.env`, `runs/`, `outputs/`, `memory/`, or large local Banny templates unless the user explicitly asks. These are ignored generated or local assets.

For Banny CLI validation/rendering, prefer an installed `banny` on `PATH` or `BANNY_BIN`. Use a local `banny-studio` checkout through `BANNY_STUDIO_CHECKOUT` only as a setup fallback. Do not clone or pull `mejango/banny-studio` during every episode run.

## Common Workflows

Inspect an existing Banny template:

```bash
split-peel inspect-template --template /path/to/template.bs
```

Fetch context and draft a structured script:

```bash
split-peel fetch-feed --out runs/<episode_slug>/feed.json
split-peel fetch-scoreboard --espn-league eng.1 --out runs/<episode_slug>/scoreboard.json --match-context-out runs/<episode_slug>/match_context.json
split-peel draft-script --feed runs/<episode_slug>/feed.json --match-context runs/<episode_slug>/match_context.json --out runs/<episode_slug>/script.json --duration-sec 60
```

Build a show from a reviewed script:

```bash
split-peel build-show --template <template.bs> --script runs/<episode_slug>/script.json --out outputs/<episode_slug>.bs --background-gain 0.22
split-peel unpack --template outputs/<episode_slug>.bs --out outputs/<episode_slug>.bannyshow --overwrite
```

Run the end-to-end episode flow:

```bash
split-peel make --template <template.bs> --run-dir runs/<episode_slug> --out outputs/<episode_slug>.bs --duration-sec 60
```

Prefer the two-phase flow for creative iteration:

1. Draft and edit `runs/<episode_slug>/script.json`.
2. Review or adjust overlay manifests and generated PNGs.
3. Run `build-show` only after dialogue is locked.

`build-show` and `make` synthesize dialogue audio. With the default ElevenLabs provider, rerunning either command can spend money and regenerate every dialogue clip. Do not rerun them for script wording, title card placement, ESPN context, or overlay-only experiments unless the user explicitly wants a fresh voiced package.

Use the audio-safety flags when iterating:

```bash
split-peel make ... --draft-only
split-peel build-show ... --reuse-audio-from outputs/<episode_slug>.bs --skip-voice
```

`--draft-only` writes run artifacts and `script.json` but skips package build, memory write, and hosted voice generation. `--reuse-audio-from` can point at an existing `.bs` or `.bannyshow`. `--skip-voice` must be used for visual-only rebuilds when spending new voice credits is not allowed; missing reusable audio should fail the build.

Dialogue WAVs are cached in `.cache/split-peel/audio/` by default. The cache key includes provider, voice settings, speaker, spoken text, and tone. Do not delete or bypass the cache during repeated episode builds unless the user asks for fresh voice generation.

Use `retime-mouth` when the existing voice audio is acceptable and only mouth/eye timing needs repair:

```bash
split-peel retime-mouth --template outputs/<episode_slug>.bs --out outputs/<episode_slug>-retimed.bs --overwrite
```

Run the config-driven Studio pipeline:

```bash
split-peel studio-pipeline --init-config --config runs/<episode_slug>/pipeline.json
split-peel studio-pipeline --config runs/<episode_slug>/pipeline.json --dry-run
split-peel studio-pipeline --config runs/<episode_slug>/pipeline.json
```

When `banny_enabled` is true in the pipeline config, the pipeline validates the generated package with `banny validate`, writes `banny info --json`, creates configured preview frames, and can ship the mp4 with `banny ship`.

## Episode Rules

- Preserve the source template's reusable staging, characters, lights, and persistent props.
- Mutate only episode-specific timeline data unless the user explicitly asks for template changes: dialogue clips, mouth events, character motion events, background cues, foreground overlays, captions, and generated assets.
- Keep generated dialogue in the structured script shape documented in `README.md`.
- Prefer manual review between `draft-script` and `build-show` when the user is iterating on jokes, tone, or character direction.
- Pass `--overwrite-script` only when replacing an existing reviewed script is intentional.
- Treat `runs/<episode_slug>/script.json` as the handoff file before voice generation. It contains the script, episode metadata, preroll/cold-open data, and outro effect instructions.
- Treat `outputs/<episode_slug>.bs` and `outputs/<episode_slug>.bannyshow` as the Studio handoff after voice generation. Creator touch-ups in Studio should not require rerunning hosted TTS unless the spoken lines change.
- Use `characters/default.json` unless the user provides another character file.
- Use `--no-memory` for isolated tests or one-off builds where callbacks to prior episodes would be undesirable.
- Use `examples/overlays.final-whistle-gantry.json` for the Final Whistle stadium background and title lockup defaults. Overlay entries can use `includeEpisodeTypes` or `excludeEpisodeTypes`; the title lockup is excluded for `outtake`.
- Run `banny catalog --json` before choosing Banny wardrobe names or outfit slots. Never guess outfit names.
- Run `banny validate` before `banny ship`; validation errors block delivery.
- Preview at least one key frame per major episode beat before treating an mp4 render as final.

## Provider Notes

- Local voice generation uses macOS `say` and `afconvert`; check their availability before relying on local audio output.
- OpenAI script or TTS generation requires `OPENAI_API_KEY` and the `SPLIT_PEEL_*` environment variables documented in `README.md`.
- ElevenLabs voice generation requires `ELEVENLABS_API_KEY` and per-character voice IDs.
- Network-backed context fetching or hosted generation can fail without credentials or network access; surface that clearly and fall back to deterministic/local flows when useful.
