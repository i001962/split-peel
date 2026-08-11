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
- ElevenLabs can make fast joke exchanges sound too even or mechanical when
  every line has the same sentence shape and calm tone label. For Peel especially,
  write more audible performance into the line: shorter fragments, self-correction,
  wounded pauses, interruptions, and one clear emotional turn per beat.
- When a script takes several review passes to get funny, treat that as signal
  that the first draft was too generic. Add football-specific names, roles,
  fixture texture, pundit references, kickoff timing, FPL pain, and recurring
  staff bits before voice generation, not after.
- For Farcaster-led episodes, write the channel as a social room, not a topic
  feed. Identify the people in the thread and assign each a moment status:
  proposing, resisting, overbuilding, misunderstanding, table-policing, or
  quietly escalating the bit.
- Plan one or two 12-20 second social bites during scripting. The episode can
  still run longer, but at least one exchange should be self-contained enough
  to trim directly from the final MP4.
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
- During post-show reflection, flag any reusable facial or vocal character tick.
  If it should recur, save it as a Banny reaction definition in the Studio
  source or a performance-plan library, then trigger it from future scripts by
  line id instead of hardcoding absolute seconds.
- Lock character pronouns before script finalization and again before voice
  generation. Split is she/her; Peel is he/him. Pronoun drift is a script
  blocker, not a post-production cleanup item.

## Media And Callouts

- Keep advertiser/callout media as rectangular 16:9 assets when readability
  matters in Banny Studio.
- For outlandish sponsor/callout ideas with a strong physical metaphor, prefer
  a full motif-driven pixel-art set over a flat ad card. Keep the lower center
  open so Split and Peel can sit naturally inside the world; readable background
  signs can carry jokes and exposition without extra spoken lines.
- If a script uses named Farcaster or channel people as texture, collect every
  mentioned account's PFP before packaging. Do not stop at the loudest two
  accounts; scan `sourceCasts`, final dialogue, and subtitles for late mentions.
- Treat PFPs as production identifiers, not decorative stickers. Normalize them
  to a consistent square canvas, use one scale by default, and review any manual
  Studio movement against a same-size reference before final render.
- Time PFP cues to the spoken mention, not just the segment topic. Use subtitle
  start times from the final `.bannyshow/show.json` as the source of truth after
  Studio edits, because script line timings can drift after retiming or manual
  cuts.
- Keep PFP overlays small and conventional: roughly the prior show scale,
  positioned near the upper sides or in a simple three-across callout. They
  should identify the person without becoming a second gag layer.
- When rebuilding from an already-integrated package, avoid reapplying the same
  overlay manifest unless duplicate assets/tracks/cues are expected and cleaned.
- Validate after packaging; duplicate asset, track, and cue IDs are easy to
  introduce during iterative rebuilds.

## Publishing

- First YouTube upload should stay `private`.
- Run `upload-youtube --dry-run` before real upload when metadata or file paths
  changed.
- When a social or YouTube package mentions current products, agents, teams, or
  communities, include platform-specific at-mentions in the handoff and verify
  handles before publishing. Keep hashtags/tags for discovery, but use mentions
  for interested parties.
- Write social post copy, YouTube titles, and YouTube descriptions as teaser
  packaging for a continuing series. Think Netflix episode card: name the hook,
  imply the chaos, and make the viewer want the missing context. Do not explain
  every joke or summarize the full plot in the public copy.
- YouTube descriptions should stay short, public-facing, and curiosity-led:
  one premise paragraph, one show/context paragraph, a short series lockup, and
  only essential credits or synthetic-media disclosure.
- Always run the upload command from repo root, not from the Banny Studio source
  checkout.
- For Banny Studio-edited episodes, copy or export the final MP4 to
  `outputs/<episode-slug>.mp4` before upload. Avoid uploading from loose
  external export paths unless there is also a retained repo copy.
- Final MP4 exports must be visible in Finder. After Banny CLI ship or any
  manual copy, check `ls -lO@ outputs/<episode-slug>.mp4`; if macOS set the
  `hidden` flag, run `chflags nohidden outputs/<episode-slug>.mp4` before
  handoff.
- When ElevenLabs or another synthetic voice provider is used, set YouTube's
  `containsSyntheticMedia` declaration on upload.

## Final Whistle Desk Builds

- Build Final Whistle desk episodes from
  `templates/final-whistle-desk.bannyshow`. It is the lean schema-v4 source for
  the gantry desk, two-shot, close-ups, characters, and persistent stadium bed.
  Do not build from old episode outputs or broad template packages with leftover
  logos, scorebugs, dialogue, or one-off overlays.
- When a script has a strong repeated visual premise, prefer one clear,
  readable overlay prop over complex panning or multiple scene changes. Keep
  harder effects, such as eye ticker reflections, out unless they are essential
  to the joke.
- Use reusable Banny reactions for repeatable character business such as
  Split's deadpan side-eye, Peel's innocent over-explanation, compliance panic,
  and short hot-mic pauses. Reactions should stay short, usually under two
  seconds, so they can attach cleanly to punchlines and listener beats.
- Keep default Split and Peel movement sparse but alive: blinks and small nods
  should read as presence, while reaction instances should be reserved for
  punchlines, listener beats, and clear emotional turns.
- Banny schema v4 allows exactly one `Scenes` background track. Speaker cuts
  must become adjacent camera cues on that track, not a second camera
  background track.
- On set-style desk episodes, do not use character movement events to push the
  hosts back from camera, especially `ArrowUp` / "move away" performance beats.
  Keep the characters planted at the desk and solve headroom/framing with
  camera cue `camFrom` / `camTo` positions.
- Character depth is locked by default. Do not animate Split or Peel front-to-back
  unless the script or producer explicitly asks for a depth move. Repeated depth
  drift makes the hosts shrink across the episode and breaks the desk illusion.
- For desk closeups, retime camera cuts to the final dialogue WAV clip starts
  after ElevenLabs generation or Studio edits. Script line order is not enough:
  final `stage.audioTracks[0].clips[]` start times are the source of truth.
- For Split and Peel desk closeups, pan the camera upward rather than moving the
  characters. The tactical-timeout pass used closeup framing around
  `y: 0.43`, `zoom: 1.82`, with Split near `x: 0.79` and Peel near `x: 0.315`.
- A foreground desk must be a true front-of-cast element. Put the desk track
  after `c-0` and `c-1` in `rowOrder` / `front-of-cast` so it occludes the
  characters' lower bodies and reads like they are sitting behind it.
- If a producer manually adjusts callout/logo placement in Banny Studio, treat
  the edited `.bannyshow` as source of truth. Render and upload from that
  package; do not rebuild from `runs/<episode>/pfp-overlays.json` and overwrite
  the manual placement.
- If a macOS app picker rejects an otherwise valid Banny MP4, make a
  compatibility copy with `avconvert --preset Preset1920x1080` and clear a
  stale `com.apple.quarantine` attribute before concluding the export is bad.
- If Banny CLI rejects a Studio-edited package because of Studio-only fields
  such as `muted`, `visualLayer`, image-track `clips`, or image-track `fx`, make
  a temporary render-only copy and strip only those unsupported fields there.
  Do not rewrite the reviewed `.bannyshow` just to satisfy an older CLI.
- Before rendering a Studio-edited package, remove stale template tracks and
  unresolved asset references from the render copy. Old team logos, scorebugs,
  key-moment takeovers, or show logos can survive as hidden or orphaned tracks
  and still break validation or leak into the export.
- If headless Banny export crashes inside CoreAudio from the sandbox, retry the
  same validated render command with macOS audio access outside the sandbox
  before falling back to manual Studio export.
- For longer Final Whistle episodes, break the show into reviewed scenes first,
  voice/build each scene as a controlled unit when practical, then assemble the
  final episode in post-production. Long single-pass builds make drift, review
  cuts, and render iteration more expensive than they need to be.
- After script review/finalization, do not let package generation or production
  scripting add new spoken content unless that addition goes back through script
  review. The Summer Abyss build picked up extra content between approval and
  production, which lengthened the show and introduced character mistakes.

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
