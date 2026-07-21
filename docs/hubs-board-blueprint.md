# Hubs Board Blueprint

This board turns the `split-peel` repo into a manually controllable episode factory. Hubs cards should carry context, decisions, inputs, and approvals; the repo remains the execution engine that fetches data, drafts scripts, mutates Banny packages, and writes outputs.

## Board Name

`Banny Studio Episode Build`

## Operating Model

Each episode is one parent card. Supporting cards attach to or link from that episode card:

- Context cards: ESPN league/match, Farcaster posts, manual story notes, sponsor/brand constraints.
- Creative cards: script direction, jokes to use/avoid, character notes, highlight/PiP assets.
- Build cards: template selection, overlay manifest, generated script, generated package, export review.
- Refinement cards: requested changes, Banny Studio manual edits, regenerated builds, final export notes.

Hubs should be the source of intent and review state. The filesystem remains the source of generated artifacts.

## Recommended Lanes

1. `Inbox`
   Raw cards added manually during ideation: links, match notes, highlight clips, sponsor requirements, bits, constraints.

2. `Episode Brief`
   Curated cards that define what this episode is about.

3. `Context Ready`
   Cards with normalized inputs ready for the CLI: ESPN league/match, Farcaster feed, manual instructions, character profile, template path.

4. `Script Draft`
   Cards for generated `runs/<episode>/script.json`, script review, dialogue edits, and tone changes.

5. `Build Package`
   Cards for `split-peel make`, overlay manifests, generated `.bs`, unpacked `.bannyshow`, and Banny Studio import checks.

6. `Studio Review`
   Manual Banny Studio inspection: character staging, overlay placement, media timing, mouth/motion quality, preview/export checks.

7. `Refine`
   Concrete change requests that should trigger another script/build pass.

8. `Final`
   Approved exported video, final `.bannyshow`, source cards used, and memory notes for future episodes.

## Card Types

### Episode

Use one parent card per generated show.

Fields:

- `episode_slug`: filesystem-safe name, for example `arg-esp-shining-hotel`
- `template_path`: source `.bs` or `.bannyshow` template
- `run_dir`: usually `runs/<episode_slug>`
- `output_bs`: usually `outputs/<episode_slug>.bs`
- `output_bannyshow`: usually `outputs/<episode_slug>.bannyshow`
- `duration_sec`: target runtime
- `status`: one of the board lanes
- `approved_export`: final video path or URL

Checklist:

- Template chosen
- Context cards attached
- Script drafted
- Build generated
- Banny Studio opened and checked
- Refinements complete
- Final export approved

### ESPN Context

Fields:

- `espn_league`: examples: `eng.1`, `fifa.world`, `fra.1`
- `scoreboard_url`: optional explicit ESPN API URL
- `featured_match`: normalized match name
- `match_context_path`: `runs/<episode_slug>/match_context.json`
- `logo_overlay_path`: `runs/<episode_slug>/espn-overlays.json`

Commands:

```bash
split-peel fetch-scoreboard \
  --espn-league eng.1 \
  --out runs/<episode_slug>/scoreboard.json \
  --match-context-out runs/<episode_slug>/match_context.json
```

### Farcaster Context

Fields:

- `feed_url`
- `feed_path`: `runs/<episode_slug>/feed.json`
- `must_use_casts`
- `avoid_casts`
- `fallback_notes`

Command:

```bash
split-peel fetch-feed \
  --out runs/<episode_slug>/feed.json
```

### Manual Creative Direction

Fields:

- `instructions`
- `instructions_file`: optional prompt file path
- `targets`
- `avoid`
- `required_lines`
- `callback_to_previous_episode`

This card should be passed through `--instructions` or written into an instructions file and passed through `--instructions-file`.

### Template And Scene Setup

Fields:

- `template_path`
- `characters_dressed`: yes/no
- `background_scene_ready`: yes/no
- `base_props_ready`: yes/no
- `notes`

Rule: keep templates lean. A template should contain reusable staging, dressed characters, backgrounds, lights, and persistent props. It should not contain every possible episode asset.

### Overlay Asset

Fields:

- `asset_path`
- `kind`: `image`, `video`, `poster`
- `overlay_manifest_path`
- `start`
- `dur`
- `x`
- `y`
- `scale`
- `rendered_in_banny`: yes/no

Manifest shape:

```json
{
  "overlays": [
    {
      "name": "highlight-replay",
      "file": "examples/assets/highlight-poster.png",
      "start": 0,
      "dur": "full",
      "x": 0.78,
      "y": 0.24,
      "scale": 0.28
    }
  ]
}
```

### Script Draft

Fields:

- `script_path`: `runs/<episode_slug>/script.json`
- `duration_sec`
- `characters_path`
- `review_notes`
- `approved`: yes/no

Command:

```bash
split-peel draft-script \
  --feed runs/<episode_slug>/feed.json \
  --match-context runs/<episode_slug>/match_context.json \
  --out runs/<episode_slug>/script.json \
  --duration-sec 60 \
  --instructions-file runs/<episode_slug>/instructions.txt
```

### Build

Fields:

- `template_path`
- `script_path`
- `overlays_path`
- `background_gain`
- `output_bs`
- `output_bannyshow`
- `build_log`

Command:

```bash
split-peel build-show \
  --template <template_path> \
  --script runs/<episode_slug>/script.json \
  --out outputs/<episode_slug>.bs \
  --background-gain 0.22 \
  --overlays runs/<episode_slug>/pfp-overlays.json

split-peel unpack \
  --template outputs/<episode_slug>.bs \
  --out outputs/<episode_slug>.bannyshow \
  --overwrite
```

End-to-end command:

```bash
split-peel make \
  --template <template_path> \
  --run-dir runs/<episode_slug> \
  --out outputs/<episode_slug>.bs \
  --espn-league eng.1 \
  --duration-sec 60 \
  --background-gain 0.22 \
  --instructions-file runs/<episode_slug>/instructions.txt
```

### Studio Review

Fields:

- `bannyshow_path`
- `preview_timecode`
- `issue`
- `screenshot_path`
- `decision`
- `needs_rebuild`: yes/no

Checklist:

- Dialogue audible
- Background gain acceptable
- Mouth events line up
- Characters remain dressed
- ESPN logos or lower-third visible
- Farcaster PFP overlays visible
- Highlight/PiP cue visible and timed correctly
- Export range correct

### Refinement Request

Fields:

- `change_type`: `script`, `voice`, `timing`, `overlay`, `template`, `export`
- `requested_change`
- `files_to_update`
- `accepted_when`

Examples:

- Move highlight overlay from upper-right to lower-left.
- Make Peel less mean about a fan cast.
- Use `fifa.world` instead of `eng.1`.
- Start highlight at `25.7s` and run for `12s`.

## Build Flow From Hubs

1. Create an `Episode` card in `Inbox`.
2. Attach or create context cards: ESPN, Farcaster, manual creative direction, overlay assets.
3. Move the parent card to `Episode Brief` once the story is clear.
4. Move to `Context Ready` after feed, scoreboard, template, and instructions are set.
5. Run `split-peel make` or the staged commands.
6. Attach generated paths to the parent card.
7. Move to `Studio Review`.
8. Add refinement cards for any requested changes.
9. Rebuild until the review card is approved.
10. Move the parent card to `Final` with the final export path.

## Suggested First Board Seed Cards

### Episode: Shining Hotel Zoom Test

- `episode_slug`: `shining-hotel-zoom-test`
- `template_path`: `outputs/openai-voiced.bannyshow` or the next manually dressed template
- `run_dir`: `runs/shining-hotel-zoom-test`
- `output_bs`: `outputs/shining-hotel-zoom-test.bs`
- `output_bannyshow`: `outputs/shining-hotel-zoom-test.bannyshow`
- `duration_sec`: `60`

### Overlay Asset: Shining Hotel Zoom

- `asset_path`: `/Users/kmm/.codex/visualizations/2026/07/20/019f807a-8ef4-7302-bba4-9d46c01e8e1d/highlight.mp4`
- `kind`: `video`
- `fallback_poster`: `examples/assets/highlight-poster.png`
- `x`: `0.78`
- `y`: `0.24`
- `scale`: `0.28`
- `start`: `0`
- `dur`: `full`

### Template And Scene Setup: Base Football Commentary Room

- dressed Banny characters
- chosen background scene
- reusable lights
- persistent desk or props only
- no episode-specific feed, logos, PFPs, or highlight assets

## Automation Boundaries

Good Hubs controls:

- Manual context capture
- Creative approvals
- Episode status
- Refinement requests
- Generated artifact links
- Review screenshots and notes

Good repo controls:

- Fetching ESPN/Farcaster data
- Drafting script JSON
- Generating voices
- Mutating `show.json`
- Copying assets
- Building `.bs`
- Unpacking `.bannyshow`
- Running tests

Do not make Hubs the generated-artifact store. Use it as the operational board that points at files and decisions.
