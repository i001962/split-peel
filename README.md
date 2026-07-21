# split-peel

A production pipeline for generating short Banny Studio football commentary episodes from Farcaster football-channel activity.

The goal is to turn a live football conversation feed into a complete `.bs` show package with:

- a generated two-commentator scene script
- character voice audio
- mouth-open events synced to the voice audio
- light idle/reaction movement for natural character performance
- background image or video assets
- optional music bed
- a rewritten `show.json` packaged back into a Banny Studio `.bs` file

## Why This Exists

Banny Studio show files are zip-style packages. A show package usually contains:

```text
show.json
audio/*.mp3
assets/*.png
assets/*.mp4
```

This project treats an existing `.bs` file as a reusable template, then programmatically replaces the episode-specific parts: script, audio clips, background cues, and character timeline events.

## Target Flow

```text
Farcaster football feed
  -> topic extraction
  -> two-commentator comedy script
  -> voice generation
  -> mouth timing from audio
  -> idle/reaction movement
  -> show.json mutation
  -> packaged .bs output
```

## CLI

End-to-end local voice command:

```bash
split-peel make \
  --template /path/to/WorldCupAll.bs \
  --feed-url "https://haatz.quilibrium.com/v2/farcaster/feed/parent_urls?parent_urls=chain://eip155:1/erc721:0x7abfe142031532e1ad0e46f971cc0ef7cf4b98b0&limit=100" \
  --out outputs/voiced.bs
```

Then unpack the package for Banny Studio:

```bash
split-peel unpack --template outputs/voiced.bs --out outputs/voiced.bannyshow --overwrite
```

Available subcommands:

```bash
split-peel fetch-feed --out runs/latest/feed.json
split-peel fetch-scoreboard --espn-league eng.1 --out runs/latest/scoreboard.json --match-context-out runs/latest/match_context.json
split-peel draft-script --feed runs/latest/feed.json --out runs/latest/script.json
split-peel inspect-template --template /path/to/WorldCupAll.bs
split-peel roundtrip --template /path/to/WorldCupAll.bs --out outputs/roundtrip.bs
split-peel unpack --template outputs/smoke.bs --out outputs/smoke.bannyshow
split-peel build-show --template templates/WorldCupAll.bs --script runs/latest/script.json --out outputs/episode.bs
```

Add foreground media such as a desk, lower-third, or team logos with an overlay manifest:

```bash
split-peel make \
  --template /path/to/WorldCupAll.bs \
  --out outputs/openai-voiced-overlays.bs \
  --background-gain 0.16 \
  --overlays examples/overlays.desk-and-logos.json

split-peel unpack \
  --template outputs/openai-voiced-overlays.bs \
  --out outputs/openai-voiced-overlays.bannyshow \
  --overwrite
```

By default, `split-peel make` also fetches the ESPN Premier League scoreboard, normalizes one featured match, downloads team logos, and generates ESPN logo overlays. Use `--no-espn` to disable that source.

When a generated dialogue line calls out a Farcaster user from `sourceCasts`, the pipeline downloads that user's `pfp_url` and adds it as a timed foreground overlay near the line where they are mentioned.

Set the ESPN soccer competition with `--espn-league`:

```bash
split-peel make \
  --template /path/to/WorldCupAll.bs \
  --out outputs/world-cup.bs \
  --espn-league fifa.world \
  --instructions "Call out overconfident Spain fans, but keep it playful."
```

Examples:

```text
eng.1         English Premier League
fifa.world    FIFA World Cup
fra.1         French Ligue 1
usa.1         Major League Soccer
```

Use `--scoreboard-url` when you want to pass the full ESPN API URL directly.

When a league scoreboard has many matches, inspect the event IDs and select one explicitly:

```bash
split-peel fetch-scoreboard \
  --espn-league usa.1 \
  --out runs/usa1/scoreboard.json

jq '.events[] | {id, name, shortName, date, state:.status.type.state, detail:.status.type.detail}' runs/usa1/scoreboard.json

split-peel make \
  --template /path/to/WorldCupAll.bs \
  --espn-league usa.1 \
  --match-id 401876489 \
  --run-dir runs/usa1 \
  --out outputs/usa1.bs
```

Run without ESPN match context:

```bash
split-peel make \
  --template /path/to/WorldCupAll.bs \
  --out outputs/social-only.bs \
  --no-espn \
  --instructions "Make this a general football-channel banter episode."
```

## Episode Inputs

The Farcaster feed endpoint returns `casts[]` with fields such as:

- `text`
- `timestamp`
- `author.username`
- `reactions.likes_count`
- `replies.count`
- `embeds`
- `mentioned_profiles`

The pipeline should rank casts by match relevance, recency, engagement, and comedic usefulness. Generated dialogue should paraphrase or react to fan casts rather than copy them wholesale.

When ESPN match context is enabled, ESPN takes precedence. Farcaster casts must mention the selected match, team names, or team abbreviations to become `sourceCasts`. Unmatched social posts are kept as `fallbackCasts` metadata and should not drive the episode script.

The ESPN scoreboard input provides match facts and team logo assets:

- `events[].name`, `shortName`, `date`, `status`
- venue name/city/country
- team names, abbreviations, score, form, record, colors
- team logo URLs

For completed matches, the ESPN overlay manifest also renders a center score PNG between the team logos.

Generated run artifacts:

```text
runs/latest/scoreboard.json
runs/latest/match_context.json
runs/latest/espn-overlays.json
runs/latest/espn-assets/*-logo.png
runs/latest/pfp-overlays.json
runs/latest/pfp-assets/*-pfp.png
runs/latest/script.json
memory/*.json
```

## Script Shape

A generated script should be structured, not just plain text:

```json
{
  "title": "Spain Win, Farcaster Loses Its Mind",
  "durationSec": 60,
  "beats": [
    "Spain win the final",
    "Fans argue about Messi and Argentina",
    "Yamal vs Mbappe discourse starts immediately"
  ],
  "dialogue": [
    {
      "speaker": "split",
      "line": "Spain did not just control midfield. They put it in a spreadsheet.",
      "tone": "dry",
      "start": 0.5
    },
    {
      "speaker": "peel",
      "line": "Argentina were looking for a comeback and found a locked door with Spanish paperwork on it.",
      "tone": "mock-serious",
      "start": 4.2
    }
  ]
}
```

Script drafting wraps the generated commentary with a house-format intro and signoff. The show name is locked as `Match Replies`. The intro welcomes viewers, introduces Split, and gives Peel a fresh funny descriptor. The signoff riffs on creator calls to like, subscribe, share, or leave a take in the match replies.

## Overlay Assets

Foreground media uses Banny's media cue shape. The generator copies image files into `assets/`, registers them in `assets[]`, then appends a media track under `stage.audioTracks[]` with `cues[]`.

Manifest format:

```json
{
  "overlays": [
    {
      "name": "commentary-desk",
      "file": "assets/desk.png",
      "start": 0,
      "dur": "full",
      "x": 0.5,
      "y": 0.82,
      "scale": 0.6
    }
  ]
}
```

Use transparent PNGs for desks and logos. Coordinates are normalized Banny stage positions; `x: 0.5`, `y: 0.5` is centered.

## Characters And Memory

Character profiles live in `characters/default.json`. Each character can define:

- `id`: speaker ID used in scripts and Banny audio generation
- `displayName`
- `voice.openai`
- `voice.local`
- `voiceDirection`
- `personality`
- `preferences.targets`
- `preferences.avoid`
- `catchphrases`

Use `voiceDirection` for explicit TTS delivery notes such as cartoonish banana energy, pace, pitch impression, and performance style. `personality` controls the character's writing stance; `voiceDirection` controls how the line should sound.

Inspect the active profile:

```bash
split-peel characters --characters characters/default.json
```

Use a custom character file:

```bash
split-peel make \
  --template /path/to/WorldCupAll.bs \
  --out outputs/custom-cast.bs \
  --characters characters/default.json
```

Each generated episode writes memory to `memory/` by default. Future builds load recent memory so the commentators can refer to prior episodes and avoid repeating the same bit.

Controls:

```bash
--memory-dir memory
--no-memory
--instructions "Call out fans of the teams mentioned in the social feed."
--instructions-file prompts/episode.txt
```

## Banny Show Mutation Notes

From the current template inspection, the important `show.json` areas are:

- `assets[]`: registered asset files and IDs
- `stage.backgroundTracks[].cues[]`: background image/video timing
- `stage.audioTracks[].clips[]`: timed voice/music clips
- `stage.audioTracks[].cues[]`: foreground media/image cues
- `stage.characters[].events[]`: timestamped character controls

Observed character event codes in the template include:

- `KeyM`: mouth open/close
- `Period`: blink
- arrow keys: small movement
- `KeyT`: tilt
- `KeyJ` / `KeyB`: expressive movement controls to verify against Banny Studio behavior

The safest first implementation should preserve the template's character definitions and only replace timed clips, cues, and events.

## Suggested Repo Layout

```text
split-peel/
  README.md
  pyproject.toml
  .env.example
  templates/
    WorldCupAll.bs
  outputs/
  runs/
  src/
    split_peel/
      __init__.py
      cli.py
      feed.py
      scriptwriter.py
      voices.py
      audio_analysis.py
      motion.py
      package.py
```

Generated files in `outputs/` and `runs/` should usually stay out of git.

## Setup

Python setup:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

Then run:

```bash
split-peel --help
```

## Environment

Create a `.env` file for provider credentials. The exact keys depend on the selected generation services.

```bash
OPENAI_API_KEY=
VOICE_PROVIDER_API_KEY=
```

Do not commit `.env`.

The current local voice path does not require `.env`. It uses macOS `say` and `afconvert` to generate WAV dialogue clips. Provider keys become necessary when the project switches to higher-quality hosted voice, LLM script generation, generated music, or generated imagery.

For OpenAI voice generation, use:

```bash
OPENAI_API_KEY=your_key_here
SPLIT_PEEL_SCRIPT_PROVIDER=openai
SPLIT_PEEL_SCRIPT_MODEL=gpt-5
SPLIT_PEEL_VOICE_PROVIDER=openai
SPLIT_PEEL_OPENAI_TTS_MODEL=gpt-4o-mini-tts
SPLIT_PEEL_SPLIT_VOICE=onyx
SPLIT_PEEL_PEEL_VOICE=verse
SPLIT_PEEL_OPENAI_TTS_SPEED=1.15
SPLIT_PEEL_SPLIT_SPEED=1.25
SPLIT_PEEL_PEEL_SPEED=1.18
SPLIT_PEEL_MOUTH_LEAD_SEC=0.06
SPLIT_PEEL_MOUTH_MAX_OPEN_SEC=0.12
SPLIT_PEEL_MOUTH_MIN_CLOSED_SEC=0.04
SPLIT_PEEL_CAPTION_MAX_CHARS=42
SPLIT_PEEL_BACKGROUND_GAIN=0.22
```

When `SPLIT_PEEL_VOICE_PROVIDER=openai` is set, the CLI will fail if `OPENAI_API_KEY` is missing instead of silently falling back to local Mac voices.

For ElevenLabs voice generation, use one voice ID per character:

```bash
ELEVENLABS_API_KEY=your_key_here
SPLIT_PEEL_VOICE_PROVIDER=elevenlabs
SPLIT_PEEL_ELEVENLABS_MODEL=eleven_v3
SPLIT_PEEL_ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
SPLIT_PEEL_SPLIT_ELEVENLABS_VOICE_ID=your_split_voice_id
SPLIT_PEEL_PEEL_ELEVENLABS_VOICE_ID=your_peel_voice_id
```

You can also put the voice IDs in a character file:

```json
{
  "id": "peel",
  "voice": {
    "elevenlabs": "your_peel_voice_id"
  }
}
```

The build uses ElevenLabs Text-to-Speech per dialogue line, then converts the returned audio to WAV for Banny timing, mouth events, and captions. `dialogue[].tone` is prepended as an ElevenLabs-style delivery tag, for example `[breathless British radio build, huge grin on the last phrase]`.

Script drafting defaults to the local template writer. Use `--script-provider openai` or `SPLIT_PEEL_SCRIPT_PROVIDER=openai` to have OpenAI generate fresh structured dialogue from the ESPN/Farcaster context and character profiles. `SPLIT_PEEL_SCRIPT_MODEL` defaults to `gpt-5`.

When OpenAI script generation is used, each `dialogue[].tone` should be treated as per-line TTS performance direction. `build-show` passes that tone into OpenAI TTS instructions so the same character voice can whisper, accelerate, punch a final phrase, or build into disbelief line by line.

OpenAI TTS speed accepts `0.25` to `4.0`; `1.0` is normal speed. Use `voice.openaiSpeed` in `characters/default.json` for per-character defaults, or the `SPLIT_PEEL_*_SPEED` environment variables for quick local tuning.

Mouth events are generated from voice audio amplitude. `SPLIT_PEEL_MOUTH_LEAD_SEC` starts the mouth slightly before the waveform, `SPLIT_PEEL_MOUTH_MAX_OPEN_SEC` prevents long held-open bars, and `SPLIT_PEEL_MOUTH_MIN_CLOSED_SEC` controls how quickly the mouth can reopen.

Subtitles are split into shorter timed captions with `SPLIT_PEEL_CAPTION_MAX_CHARS`. The default is `42`, clamped between `16` and `72`, so Banny's single-line caption display does not run off screen.

Use `SPLIT_PEEL_BACKGROUND_GAIN` or `--background-gain` to control stadium/music bed volume. `1.0` is full volume, `0.22` is the default for generated shows, and `0` mutes background audio.

## First Milestones

1. Create a CLI skeleton with `fetch-feed`, `draft-script`, `build-show`, and `make`.
2. Fetch and cache the Farcaster feed as JSON.
3. Generate a structured two-commentator script from the feed.
4. Unpack a template `.bs`, read `show.json`, and repackage it unchanged as a smoke test.
5. Replace background and audio clips in `show.json`.
6. Generate `KeyM` mouth events from voice audio amplitude.
7. Add sparse blink, tilt, and reaction movement events.
8. Produce a complete `.bs` file that opens in Banny Studio.

## Current Status

Milestone one is implemented:

- installable Python package
- `split-peel` CLI
- Farcaster feed fetch/cache
- deterministic structured script draft
- Banny `.bs` inspection
- Banny `.bs` round-trip packaging smoke test
- `.bs` unpacking to `.bannyshow` folders
- local macOS voice synthesis for dialogue clips
- OpenAI TTS voice synthesis for dialogue clips
- amplitude-based `KeyM` mouth event generation
- procedural blink, tilt, and listener reaction events
- foreground overlay media from JSON manifests
- ESPN scoreboard match context and team logo overlays
- unit tests for script drafting and package round-tripping

The next useful step is to build a real scoreboard/lower-third PNG from `match_context.json`, not just floating team logos.
