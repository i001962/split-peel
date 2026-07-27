# Production Learnings

This is the small memory layer for Split & Peel production. Keep it concrete:
capture what changed the work, promote repeated lessons into defaults, and avoid
turning this into a filing system.

## Defaults Worth Keeping

- Create the episode first; organize only when the work exposes a repeated need.
- Keep episode learnings in `runs/<episode>/reflection.md`.
- Promote a lesson into this file only when it changes future prompts, templates,
  build commands, or publishing defaults.
- Build comparison variants instead of overwriting an approved package.
- Use Banny Studio for edit/review, Banny CLI for deterministic rendering, and
  the repo YouTube CLI for private upload.

## Banny Studio 1.4 / Schema 4

- Treat schema v4 as the active package contract for new work.
- The App Store Banny Studio 1.4 YouTube publish sheet exists, but it needs a
  Google OAuth client ID embedded in the app release configuration.
- For this repo, the practical upload path is still `split-peel upload-youtube`
  with `.secrets/youtube-client.json` and `.secrets/youtube-token.json`.
- Render fresh MP4 files after media changes; do not assume older MP4 exports
  reflect the current `.bannyshow`.
- Render fresh MP4 files after Studio positional edits too. If the unpacked
  `.bannyshow/show.json` is newer than the MP4, validate and ship from the
  edited `.bannyshow` before uploading.

## Voice And Comedy Direction

- Between-line timing helps, but it does not replace intra-line performance.
- ElevenLabs does better with concise performance text and punctuation inside
  the spoken line than with long bracketed actor directions.
- Long inline actor directions can make ElevenLabs stretch short lines into
  unusable reads.
- Good comedy directions define relationship and moment status: who is baiting,
  who is suspicious, who is interrupting, who lands the button.
- Useful line-level patterns:
  - suspicious pause: `VAR... who?`
  - dry delay: `Are you... done now?`
  - quick escalation: `Exactly. Bad actor. Method actor.`
  - final button: land the phrase cleanly and stop.
- For interruption feel, generate natural lines first, then adjust manifest start
  times or small overlaps after generation.

## Media And Callouts

- Keep advertiser/callout media as rectangular 16:9 assets when readability
  matters in Banny Studio.
- When rebuilding from an already-integrated package, avoid reapplying the same
  overlay manifest unless duplicate assets/tracks/cues are expected and cleaned.
- Validate after packaging; duplicate asset, track, and cue IDs are easy to
  introduce during iterative rebuilds.

## Publishing

- First YouTube upload should stay `private`.
- Run `upload-youtube --dry-run` before real upload when metadata or file paths
  changed.
- Always run the upload command from repo root, not from the Banny Studio source
  checkout.
- When ElevenLabs or another synthetic voice provider is used, set YouTube's
  `containsSyntheticMedia` declaration on upload.

## Final Whistle Desk Builds

- When the brief calls for the Falsenine set, build from
  `outputs/falsenine-roast-desk.bannyshow`; it contains the intended gantry
  desk, two-shot, and close-up source assets. Do not substitute the generic
  stadium background.
- Banny schema v4 allows exactly one `Scenes` background track. Speaker cuts
  must become adjacent camera cues on that track, not a second camera
  background track.
- If a macOS app picker rejects an otherwise valid Banny MP4, make a
  compatibility copy with `avconvert --preset Preset1920x1080` and clear a
  stale `com.apple.quarantine` attribute before concluding the export is bad.

## Reflection Template

```md
# Episode Reflection: <title>

Date:
Package:
MP4:
Published:

## Production Timing

Brainstorm started:
First draft saved:
Script locked:
Private upload completed:
Brainstorm to upload:

If the original brainstorm timestamp is unavailable, use the earliest reliable
run artifact and label the result as an artifact-based proxy. The four required
milestones are brainstorm start, first draft, script lock, and private upload.

## What Shipped

## What Worked

## What Felt Weak

## Surprises

## Viewer Or Audience Signals

## Promote To Defaults

## Avoid Next Time

## Next Experiment
```
