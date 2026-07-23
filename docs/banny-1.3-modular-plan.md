# Banny Studio 1.3 Modular Build Plan

## Goal

Move split-peel from a template-first build into a modular Studio-native pipeline where expensive voice generation is an explicit artifact and visual/performance passes can iterate without spending voice credits.

## Constraints

- No backward compatibility requirement for older build conventions.
- Voice generation is the expensive boundary.
- Reactions, shots, background changes, image timing, and character placement must be cheap to iterate after voice is locked.
- Banny Studio remains the visual authoring tool for character placement, reusable reactions, camera grammar, and reusable media.

## Target Artifacts

```text
runs/<episode>/script.json
runs/<episode>/voice/audio/*.wav
runs/<episode>/voice-manifest.json
runs/<episode>/performance-plan.json
runs/<episode>/visual-plan.json
outputs/<episode>.bannyshow
outputs/<episode>.bs
```

## Pipeline Shape

1. Draft or hand-edit `script.json`.
2. Build `voice-manifest.json` from script dialogue and cached/generated WAV files.
3. Build a performance plan from script anchors and voice clip timings.
4. Build a visual plan from reusable scene, reaction, shot, and media presets.
5. Compose a fresh Studio package from assets, voice manifest, performance plan, and visual plan.
6. Validate, preview, and ship through the Banny CLI.

## First Implementation Slice

The first slice introduces the voice boundary without trying to solve every reusable asset at once:

- Add a `voice-manifest.json` writer.
- Add a `build-voice` CLI command.
- Make `make` and `studio-pipeline` generate `voice-manifest.json`.
- Make package build consume `voice-manifest.json` instead of synthesizing during package mutation.
- Preserve enough direct `build-show` behavior for local tests and manual use while moving production paths to the manifest.

Implemented commands:

```bash
split-peel build-voice --script runs/<episode>/script.json --out runs/<episode>/voice-manifest.json
split-peel build-show --template templates/instudio.bannyshow --script runs/<episode>/script.json --voice-manifest runs/<episode>/voice-manifest.json --out outputs/<episode>.bs
```

The reusable reaction and shot slice adds script-anchored visual beats:

```bash
split-peel build-show \
  --template templates/instudio.bannyshow \
  --script runs/<episode>/script.json \
  --voice-manifest runs/<episode>/voice-manifest.json \
  --performance-plan templates/final-whistle/performance-plan.json \
  --out outputs/<episode>.bs
```

The asset-first slice adds registry extraction and fresh composition:

```bash
split-peel extract-studio-assets --source templates/instudio.bannyshow --out templates/final-whistle/registry.json
split-peel compose-show --registry templates/final-whistle/registry.json --scene-preset default --script runs/<episode>/script.json --voice-manifest runs/<episode>/voice-manifest.json --out outputs/<episode>.bannyshow
```

## Next Tickets

- SP13-001: Voice manifest boundary.
- SP13-002: Studio-native package source support.
- SP13-003: Script-anchored reaction and shot plans.
- SP13-004: Studio asset registry extraction.
- SP13-005: Fresh document composition from assets.
