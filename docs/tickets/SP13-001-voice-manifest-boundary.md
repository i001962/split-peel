# SP13-001: Voice Manifest Boundary

## Problem

`build-show` currently synthesizes dialogue audio and mutates the Banny package in one step. That makes visual iteration expensive because changing reactions, camera, or image timing can cross the hosted TTS boundary.

## Scope

- Add `runs/<episode>/voice-manifest.json`.
- Store dialogue clip metadata keyed by stable line id.
- Store generated/reused WAV files outside the package under `runs/<episode>/voice/audio`.
- Make package mutation consume the manifest and copy WAV files into the package.
- Add CLI support via `split-peel build-voice`.
- Add end-to-end tests that prove package rebuilds can use a manifest without calling TTS.

## Acceptance Criteria

- [x] `make` writes `voice-manifest.json` before package build.
- [x] `studio-pipeline` includes `voice-manifest.json` in its artifact plan and manifest.
- [x] `build-show --voice-manifest <path>` builds a package without invoking voice synthesis.
- [x] Tests verify a script, voice manifest, and package can be produced end to end.
