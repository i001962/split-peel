# Final Whistle Writers Room Process

Use this process whenever the task is to brainstorm show ideas, generate episode premises, or turn live football data into scripts. The goal is to preserve creative memory while keeping the room focused on football truth, character engines, and cartoon escalation.

## Source Stack

Collect only the sources needed for the current episode type.

| Source | Use For | Output |
|---|---|---|
| ESPN match context | fixtures, score, status, teams, key moments | football facts and visual overlays |
| Farcaster football feed | fan texture, jokes to react to, community language | paraphrased social hooks |
| X trends | why-now topics and broader zeitgeist | idea seeds |
| Episode memory | callbacks, avoided repeats, prior bits | continuity hooks |
| Character bible | voice, flaws, relationships, guardrails | character-specific premises |
| Production learnings | what worked or failed in prior builds | default improvements |

## Brainstorming Order

### 1. Establish The Football Truth

Write a short factual brief before jokes:

- What happened or is about to happen?
- Which teams, players, managers, moments, or fanbases matter?
- What is the honest supporter emotion?
- What uncertainty should the show avoid overstating?

If the available data is weak, say so and pitch from the uncertainty instead of inventing certainty.

### 2. Choose The Emotional Spine

Pick one sentence:

```text
This episode is really about <emotion> caused by <football situation>.
```

Examples:

- This episode is really about hope becoming reckless because a fanbase saw one good preseason clip.
- This episode is really about dread caused by a fixture list that looks personally hostile.
- This episode is really about old-school romance fighting spreadsheet evidence after a weird goal.

### 3. Run The Character Engines

Ask what Split and Peel would each do with the truth.

Split prompts:

- What pattern does she see before everyone else?
- What bad take is she too precise to ignore?
- Where does her tactical brain become emotionally compromised?
- What does she explain cleanly while the room catches fire?

Peel prompts:

- What does his eye test insist is true?
- What normal event does he turn into folklore?
- What chart, rule, or stat personally offends him?
- What warm, ridiculous principle does he defend?

Relationship prompts:

- Where does Split let Peel run because it is funnier?
- Where does Peel accidentally reveal the emotional truth?
- What does Split refuse to say directly but clearly feels?
- What does Peel need Split to translate?

### 4. Cartoon The Feeling

Generate visual escalation from the emotional spine.

Use this ladder:

```text
real detail -> exaggerated interpretation -> impossible object/event -> public studio consequence -> clean button
```

Examples:

- Transfer rumor -> Peel calls it gravity -> every loose object orbits a fake signing graphic -> Split calculates the orbit -> button about the rumor still not completing a medical.
- VAR delay -> Split says time has lost shape -> the desk clock grows extra stoppage-time hands -> Peel starts aging into pundit form -> button about the check still being "almost done."
- Derby nerves -> fan tension becomes static -> scarves stick to the monitor -> Split uses it as a pressure map -> Peel declares the scarf man of the match.

### 5. Build A Premise Card

Every brainstormed idea should fit this shape:

```md
## <Title>

Type:
Football truth:
Emotional spine:
Split engine:
Peel engine:
Cartoon escalation:
Fan honor:
Data hooks:
Memory hooks:
Risks/guardrails:
Best button:
```

Do not move an idea into scripting until the football truth, emotional spine, and cartoon escalation are all clear.

### 6. Pick Winners

Score ideas on five criteria, 1 to 5:

- Football specificity
- Character specificity
- Visual escalation
- Emotional honesty
- Freshness against memory

Prioritize the idea with the highest total, unless production constraints make another idea easier to execute today.

## Memory Workflow

### Before Brainstorming

Read recent memory and production learnings for:

- repeated jokes to avoid
- callbacks worth reviving
- characters or bits that felt strong
- weak patterns that need retirement
- audience or creator signals

### During Brainstorming

Capture:

- rejected ideas with the reason
- winning premise cards
- new running bits
- guardrail decisions
- visual gag ideas that may be useful later

### After The Episode

Write or update `runs/<episode>/reflection.md`, then promote only durable lessons to `docs/production-learnings.md`.

Useful reflection fields:

- What shipped
- What worked
- What felt weak
- Best character moment
- Best visual gag
- Best fan-honor moment
- Joke or trope to avoid next time
- Callback to keep alive
- Data source that mattered
- Next experiment

## Brainstorming Modes

### Wide Room

Goal: generate many ideas.

Rules:

- 10 to 20 premise cards.
- No scripting yet.
- Each idea must name a football truth and cartoon feeling.
- At least half should be playable without needing expensive new assets.

### Punch-Up Room

Goal: improve an existing premise or script.

Rules:

- Preserve the football facts.
- Strengthen character-specific lines.
- Add sharper reversals, pauses, and buttons.
- Replace generic jokes with match-specific jokes.
- Add visual gag opportunities for the Banny timeline.

### Continuity Room

Goal: build longer arcs and lovable character history.

Rules:

- Track what Split and Peel believe now that they did not believe before.
- Let recurring bits evolve.
- Give fans rituals and callbacks.
- Let consequences return in cartoon ways.
- Keep arcs modular so short episodes still work alone.

## Longer Story Arcs

Short episodes can still build deeper story if they leave small marks.

Arc types:

- Split's precision gets challenged by one recurring player, club, or trend she cannot neatly explain.
- Peel starts learning one modern football concept, badly but sincerely.
- A fan-made chant, scarf, or superstition becomes a recurring studio object.
- The desk develops traditions around derby day, transfer deadline day, finals, or international breaks.
- A recurring rival pundit, mascot, producer, or anonymous fan account pushes Split and Peel into bigger choices.

Continuity rule: every arc must be understandable in one line for new viewers.

## Data-To-Idea Template

Use this when raw sources are available:

```md
# Idea Input Brief

Episode type:
Target length:
Required teams/match:

## Facts

## Fan Texture

## Trends

## Memory Hooks

## Guardrails

## Premise Cards

## Recommended Winner
```

## Script Handoff Rules

Before moving to `runs/<episode>/script.json`, confirm:

- The premise card has a clear emotional spine.
- The dialogue can be spoken in 6 to 10 punchy lines unless the user requests longer.
- Team names and weekdays are spoken in full.
- Source posts are paraphrased, not quoted.
- The idea does not depend on unverified claims.
- Any outrageous cartoon event expresses a real football feeling.
- The episode leaves fans feeling seen, not mocked.

