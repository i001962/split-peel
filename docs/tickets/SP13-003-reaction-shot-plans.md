# SP13-003: Script-Anchored Reaction And Shot Plans

## Problem

Reusable facial reactions and camera cuts should ride on script and voice timing, not hardcoded absolute seconds.

## Scope

- Add `performance-plan.json` with anchors like line id, start/end/midpoint, and offset.
- Add reusable reaction references by id.
- Add reusable shot/camera references by id.
- Resolve anchors against `voice-manifest.json`.
- Insert Banny `reactionLibrary` instances and camera cues during package composition.

## Acceptance Criteria

- [x] A reaction can be attached to `line_id=end-0.25`.
- [x] A close-up can be attached to the same anchor.
- [x] Visual-only rebuilds do not regenerate voice.
