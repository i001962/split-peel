# Banny CLI Integration

Use Banny's Swift CLI as the authority for package validation, wardrobe choices, schema, media import, preview frames, and headless mp4 export. Keep `split-peel` responsible for football context, script generation, voice/audio, overlays, and package mutation.

## Setup Policy

Resolve the CLI in this order:

1. `banny_bin` from the pipeline config.
2. `BANNY_BIN` environment variable.
3. `banny` on `PATH`.
4. `banny_checkout_path` from the pipeline config.
5. `BANNY_STUDIO_CHECKOUT` environment variable.

When using a checkout, run `swift run banny` from that checkout. Do not clone or pull `mejango/banny-studio` inside every episode run. Clone or update only during setup, debugging, or when the user explicitly asks for a newer Banny CLI.

The local debug checkout should stay on a branch that contains the current GitHub `main`. As of the latest review, upstream `main` is `bdec41d` (`feat: add playback speed controls`) and the debug branch adds `9202687` (`Fix start-position lag in event-heavy shows`) on top. Rebuild with `swift build` after fetching so `.build/arm64-apple-macosx/debug/banny` matches the checkout.

Current source repo:

```bash
git clone https://github.com/mejango/banny-studio
cd banny-studio
swift run banny
```

## Commands

```bash
banny catalog --json
banny capabilities --json
banny schema --example
banny schema --compact
banny validate show.bs --json
banny info show.bs --json
banny preview show.bs runs/<episode>/preview-002.png --t 2
banny ship show.bs outputs/<episode>.mp4 --720
banny ship show.bs outputs/social/<episode>/sound-bite-01.mp4 --720 --range 12.5 28.0
banny pack show.bs shareable.bs
banny unpack shareable.bs editable.bs
banny skill print
banny skill install
```

Use `capabilities --json` and `schema --compact` as the authoritative API contract. Use `catalog --json` before assigning wardrobe names. Use `validate --json` before previewing or shipping. Use `preview` for key beats, `ship` for final movie output, and `ship --range FROM TO` for social clip MP4s from the same reviewed show package.

`banny skill print` currently accepts no `--target` argument, despite older help text mentioning targets. If the command shape changes, trust the running binary over this note.

## Current Schema Notes

- Editable packages use schema v4 and should be `.bs` directories; archives are `.bs.zip`.
- `settings.frameW` and `settings.frameH` define the output shape.
- `show[]` is the persistent export range; `ship --range FROM TO` temporarily overrides it.
- Image/audio visual tracks use `visualLayer` values `behindCast` and `inFrontOfCast`.
- Image cues support `playback` with `trimStart`, `trimEnd`, `rate`, `loop`, `reverse`, `freezeAt`, and `phaseOffset`.
- Use `banny media import` for files, `banny tts` for generated speech, `banny lipsync` for imported/microphone takes, and `banny apply` with JSON Patch plus `--if-hash` for structural edits.

## Pipeline Config

Enable Banny post-build checks:

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

`banny_render_size` must be `480`, `720`, `1080`, or `4k`. `banny_ship` controls mp4 export; validation and info still run whenever `banny_enabled` is true.

## Production Loop

1. Generate the episode package with `split-peel`.
2. Run `banny validate <output.bs> --json` and fix errors.
3. Run `banny info <output.bs> --json` for manifest/debug context.
4. Render preview frames at important dialogue or overlay beats.
5. Ship the movie headlessly with `banny ship`, or hand off the validated `.bs` to Banny Studio for manual finishing.

If an agent needs full `.bs` schema and event guidance, run `banny skill print` and use that version-matched guidance rather than copying stale format rules into this repo.
