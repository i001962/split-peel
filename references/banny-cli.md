# Banny CLI Integration

Use Banny's Swift CLI as the authority for package validation, wardrobe choices, preview frames, and headless mp4 export. Keep `split-peel` responsible for football context, script generation, voice/audio, overlays, and package mutation.

## Setup Policy

Resolve the CLI in this order:

1. `banny_bin` from the pipeline config.
2. `BANNY_BIN` environment variable.
3. `banny` on `PATH`.
4. `banny_checkout_path` from the pipeline config.
5. `BANNY_STUDIO_CHECKOUT` environment variable.

When using a checkout, run `swift run banny` from that checkout. Do not clone or pull `mejango/banny-studio` inside every episode run. Clone or update only during setup, debugging, or when the user explicitly asks for a newer Banny CLI.

Current source repo:

```bash
git clone https://github.com/mejango/banny-studio
cd banny-studio
swift run banny
```

## Commands

```bash
banny catalog --json
banny validate show.bs --json
banny info show.bs --json
banny preview show.bs runs/<episode>/preview-002.png --t 2
banny ship show.bs outputs/<episode>.mp4 --720
banny pack show.bs shareable.bs
banny unpack shareable.bs editable.bs
banny skill print
banny skill install
```

Use `catalog --json` before assigning wardrobe names. Use `validate --json` before previewing or shipping. Use `preview` for key beats and `ship` for final movie output.

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
