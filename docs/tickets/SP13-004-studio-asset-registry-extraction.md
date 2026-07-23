# SP13-004: Studio Asset Registry Extraction

## Problem

Banny Studio should be the visual authoring tool, but split-peel needs reusable JSON descriptions for builds.

## Scope

- Add an extraction command that reads a Studio-authored `.bannyshow`.
- Extract named assets, character tracks, reaction definitions, shot/camera presets, and scene presets into a registry.
- Keep media files in package-compatible `assets/` locations.

## Acceptance Criteria

- [x] A Studio-authored in-studio setup can be extracted into registry JSON.
- [x] Character placement and reusable reaction definitions survive round trip.
