# Latest Banny Studio Engagement Plan

This plan is based on the local Banny Studio version-history notes, the current GitHub `main` checkout, and the current repo bibles for Final Whistle and Proof Patrol.

Local version check on 2026-07-29:

- `/Applications/BannyStudio.app` reports `CFBundleShortVersionString` `1.5.1`.
- `.cache/banny-studio/.build/arm64-apple-macosx/debug/banny --version` reports `banny 1.5.0 (show schema 4)`.
- The screenshot supplied in this task shows app version-history entries labeled through `1.7.0`.
- Treat those numbers as release-note labels that may be misnumbered. For production, use the installed Banny Studio app and the current GitHub `main` checkout as the latest available implementation sources.

Use the capabilities below when they are present in the installed app or current checkout, and validate/export with that same Banny generation.

## Changelog Takeaways

- 1.7.0 adds character-audio mute from the character inspector while animation and visuals continue.
- 1.7.0 calls out visual media placement in front of or behind the cast.
- 1.7.0 adds selected-range timeline tools for keeping or removing content.
- 1.7.0 improves character removal and undo behavior, plus drag-and-drop audio reliability.
- 1.6.0 adds a cleaner focus-first workspace, recordable performances by keyboard/dragging, microphone/import/TTS dialogue, editable voice recipes, automatic editable mouth timing, character flips, rotation pivots, draggable lighting, better motion physics, named markers/sections, stronger audio controls, and safer project handling.
- 1.5.0 adds taller timeline tracks, intuitive rotation anchors for visual assets, a shared media inspector, improved voice selection, and stability refinements.

## Repo Updates

- Overlay manifests now support `layer` or `visualLayer` for `behind-cast` and `front-of-cast` image tracks.
- Overlay manifests can pass through media cue motion fields: `rotation`, `to`, `pivot`, `mask`, `maskRadius`, `appearance`, `playback`, `speed`, and `rotationSpeed`.
- Default sample manifests mark title cards, desks, proof seals, tamper alerts, and version traces with intentional layers.

## Final Whistle Features To Incorporate

1. Layered tactical proof wall

   Put xG maps, fixture slates, form tables, and key-moment timelines behind Split and Peel as if the gantry itself is becoming Split's analysis board. Keep the joke football-specific: the visual should clarify a team, player, fixture, or fan reaction, not become random decoration.

2. Foreground desk interruptions

   Put lower thirds, live-feed cards, yellow/red cards, transfer receipts, and fan-comment callouts in front of the cast. Use this when the studio cannot contain the match: a keeper glove blocks the lens, stoppage-time cards stack on the desk, or a chant shakes the lower-third.

3. Peel vibe objects with rotation pivots

   Give Peel physical props that rotate from a deliberate anchor: the eye-test eyeball, haunted spreadsheet, treasure-map fixture list, pub-law scroll, or confidence balloon. The pivot should express his emotional logic, not just add motion.

4. Split precision overlays

   Use behind-cast diagrams that slide or rotate into place on Split's lines: surgical run lasers, meltdown-stage brackets, or a three-point tactical framework. Her overlays should feel clean, exact, and slightly dangerous.

5. Named sections and range-edit workflow

   Mark each episode as `cold-open`, `setup`, `escalation`, `impossible-visual`, and `button`. Use the new keep/remove range tools in Studio to cut slow patches without disturbing the whole build.

6. Character mute for visual-only review

   During Studio polish, mute Split or Peel from the inspector to judge the other character's mouth, motion, side-eye, and reactions while the full visual track keeps playing. This is especially useful for Peel's accidental double-meaning beats and Split's forensic pauses.

7. Drag-recorded motion pass

   After the generated package is built, record short drag/keyboard performances on top: Peel inflating with confidence, Split leaning into a pause, or both hosts reacting to a late goal. Keep additions sparse so generated timing remains editable.

8. Draggable lighting beats

   Use light cues to make fan feelings literal: derby static, VAR courtroom lighting, stoppage-time dread, or a warm post-match glow. Lighting should support the football emotion rather than becoming a separate gag.

## Proof Patrol Features To Incorporate

1. Behind-cast evidence timelines

   Put version ladders, original-record traces, and archive lightboxes behind Perry and Fauxnana. This keeps the lesson visible while the banter stays first.

2. Foreground proof events

   Put proof seals, tamper alerts, forged receipts, and provenance badges in front of the cast when evidence interrupts a claim. The visual should show what changed, not imply the system proves truth.

3. Fauxnana machine pivots

   Use rotation pivots and light sweeps for Fauxnana's "-inator" machines. Her machines can be stylish and seductive, but the gag must stay about manipulated records, missing context, or version history.

4. Perry silent-audit beats

   Use character mute and visual-only review to refine Perry's dry reaction timing while Fauxnana's pitch continues visually. His comedy depends on precision and restraint.

5. Named sections for proof clarity

   Mark episodes as `fake`, `temptation`, `evidence-problem`, `proof-mechanism`, `reversal`, and `button`. This makes range edits safer and keeps the proof lesson from turning into a lecture.

## Guardrails

- Final Whistle visuals must come from real football specificity and character conflict.
- Proof Patrol visuals must distinguish provenance from truth verification.
- Do not add random motion just because the tool supports it.
- Use foreground layers for interruption and behind-cast layers for context.
- Validate in Banny before shipping, and preview frames around every major layer, camera, light, or reaction change.
