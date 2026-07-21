# Banny Studio Development Pipeline

The `studio-pipeline` command turns a Hubs capability card into a reproducible local build run. It wraps the existing `split-peel` stages, writes all generated artifacts into a run directory, unpacks the generated package for Banny Studio review, and emits a QA checklist plus manifest that can be linked back to Hubs.

## Start A Config

```bash
split-peel studio-pipeline --init-config --config runs/pipeline-smoke/pipeline.json
```

Edit the generated JSON with the episode slug, template path, target outputs, instructions, overlays, and ESPN settings.
Keep `overwrite_script` set to `false` when you plan to manually edit `runs/<episode_slug>/script.json`.

## Preview The Plan

```bash
split-peel studio-pipeline --config examples/studio-pipeline.json --dry-run
```

The dry run prints the stages and artifact paths without fetching feeds, generating voices, or mutating packages.

Set `"no_feed": true` for ESPN-only episodes. The pipeline writes an empty `feed.json`, skips Farcaster fetching, and drafts from ESPN match context plus producer instructions.

## Run The Pipeline

```bash
split-peel studio-pipeline --config examples/studio-pipeline.json
```

The command writes:

- `runs/<episode_slug>/feed.json`
- `runs/<episode_slug>/scoreboard.json`
- `runs/<episode_slug>/match_context.json`
- `runs/<episode_slug>/script.json`
- `runs/<episode_slug>/pfp-overlays.json` when generated
- `runs/<episode_slug>/pipeline-manifest.json`
- `runs/<episode_slug>/studio-qa-checklist.md`
- `runs/<episode_slug>/movie-export-handoff.md`
- `outputs/<episode_slug>.bs`
- `outputs/<episode_slug>.bannyshow`
- `runs/<episode_slug>/banny-validate.json` when Banny CLI integration is enabled
- `runs/<episode_slug>/banny-info.json` when Banny CLI integration is enabled
- `runs/<episode_slug>/preview-*.png` for configured Banny preview frames
- `outputs/<episode_slug>.mp4` when `banny_ship` is enabled

If `runs/<episode_slug>/script.json` already exists, the pipeline stops before redrafting unless `overwrite_script` is set to `true`.

## Manual Script Editing

Use this two-phase flow when the dialogue needs review before audio generation:

```bash
split-peel draft-script \
  --feed runs/<episode_slug>/feed.json \
  --match-context runs/<episode_slug>/match_context.json \
  --out runs/<episode_slug>/script.json \
  --duration-sec 60 \
  --characters characters/default.json \
  --no-memory
```

Edit `runs/<episode_slug>/script.json`, then build from that edited file:

```bash
split-peel build-show \
  --template <template.bs> \
  --script runs/<episode_slug>/script.json \
  --out outputs/<episode_slug>.bs \
  --background-gain 0.22 \
  --overlays runs/<episode_slug>/pfp-overlays.json \
  --characters characters/default.json
```

Only pass `--overwrite-script` to `draft-script` or `make` when replacing a manually edited script is intentional.

## Banny CLI Validation And Render

The pipeline can use the Banny CLI after package generation as the source of truth for validation, metadata, preview frames, and headless movie export.

Config fields:

```json
{
  "banny_enabled": true,
  "banny_bin": null,
  "banny_checkout_path": null,
  "banny_render_size": "720",
  "banny_preview_times": [2, 8, 14],
  "banny_ship": true
}
```

Resolution order:

1. `banny_bin`
2. `BANNY_BIN`
3. `banny` on `PATH`
4. `banny_checkout_path`
5. `BANNY_STUDIO_CHECKOUT`

Use an installed `banny` or a stable local checkout. Do not clone or pull `mejango/banny-studio` on every pipeline run; update that checkout only during setup or intentional CLI upgrades.

When enabled, the post-build sequence is:

```bash
banny validate outputs/<episode_slug>.bs --json
banny info outputs/<episode_slug>.bs --json
banny preview outputs/<episode_slug>.bs runs/<episode_slug>/preview-02-000.png --t 2
banny ship outputs/<episode_slug>.bs outputs/<episode_slug>.mp4 --720
```

Validation errors stop the pipeline. Preview frames and exported movies are added to the manifest and QA checklist.

## Hubs Review Loop

1. Link the config file from the Hubs capability card.
2. Run `--dry-run` and attach the printed plan if the stage boundaries need review.
3. Run the full pipeline.
4. Attach `pipeline-manifest.json`, `studio-qa-checklist.md`, and `movie-export-handoff.md` to the Studio QA card.
5. Open the generated `.bs` or `.bannyshow` in Banny Studio.
6. Export the final movie to the configured `output_movie` path.
7. Record manual issues in the QA checklist or as Hubs refinement cards.
8. Update the config or source files, rerun the pipeline, and replace the manifest/checklist links.

Hubs owns intent and review state. The repo owns configs, generated artifacts, tests, and package mutation logic.
