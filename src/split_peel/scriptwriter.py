from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.request
from typing import Any, Optional

from split_peel.characters import DEFAULT_CHARACTERS, character_ids, character_map
from split_peel.feed import RankedCast, rank_match_relevant_casts


SHOW_NAME = "Match Replies"


def draft_script(
    feed: dict[str, Any],
    duration_sec: int = 60,
    match_context: Optional[dict[str, Any]] = None,
    characters: Optional[dict[str, Any]] = None,
    episode_memory: Optional[list[dict[str, Any]]] = None,
    instructions: Optional[str] = None,
    script_provider: Optional[str] = None,
) -> dict[str, Any]:
    ranked = rank_match_relevant_casts(feed, match_context)
    characters = characters or DEFAULT_CHARACTERS
    episode_memory = episode_memory or []
    beats = _extract_beats(ranked, match_context, instructions)
    provider = _script_provider(script_provider)
    if provider == "openai":
        dialogue = _draft_dialogue_openai(
            ranked,
            duration_sec=duration_sec,
            match_context=match_context,
            characters=characters,
            episode_memory=episode_memory,
            instructions=instructions,
        )
    elif provider in {"template", "local"}:
        dialogue = _draft_dialogue(ranked, match_context, characters, episode_memory, instructions)
    else:
        raise RuntimeError(f"unknown script provider: {provider}")
    dialogue = _add_house_lines(dialogue, match_context, characters)

    return {
        "title": _title_from_beats(beats, match_context),
        "durationSec": duration_sec,
        "beats": beats,
        "instructions": instructions,
        "characters": [
            {
                "id": character.get("id"),
                "displayName": character.get("displayName"),
                "personality": character.get("personality"),
                "preferences": character.get("preferences"),
            }
            for character in characters.get("characters") or []
        ],
        "memoryUsed": [
            {
                "title": episode.get("title"),
                "createdAt": episode.get("createdAt"),
                "beats": episode.get("beats"),
            }
            for episode in episode_memory
        ],
        "match": (match_context or {}).get("match"),
        "sourceCasts": _source_casts(ranked, match_context),
        "fallbackCasts": _fallback_casts(ranked, match_context),
        "dialogue": dialogue,
    }


def _script_provider(script_provider: Optional[str]) -> str:
    return (script_provider or os.environ.get("SPLIT_PEEL_SCRIPT_PROVIDER") or "template").strip().lower()


def _cast_payload(cast: RankedCast) -> dict[str, Any]:
    return {
        "username": cast.username,
        "timestamp": cast.timestamp,
        "score": cast.score,
        "matchHits": cast.match_hits,
        "likes": cast.likes,
        "replies": cast.replies,
        "text": cast.text,
        "hash": cast.hash,
        "pfpUrl": cast.pfp_url,
    }


def _source_casts(casts: list[RankedCast], match_context: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if (match_context or {}).get("match"):
        return [_cast_payload(cast) for cast in casts if cast.match_hits > 0][:8]
    return [_cast_payload(cast) for cast in casts[:8]]


def _fallback_casts(casts: list[RankedCast], match_context: Optional[dict[str, Any]]) -> list[dict[str, Any]]:
    if not (match_context or {}).get("match"):
        return []
    return [_cast_payload(cast) for cast in casts if cast.match_hits == 0][:8]


def _extract_beats(
    casts: list[RankedCast],
    match_context: Optional[dict[str, Any]] = None,
    instructions: Optional[str] = None,
) -> list[str]:
    relevant_casts = [cast for cast in casts if cast.match_hits > 0] if (match_context or {}).get("match") else casts
    text = " ".join(cast.text.lower() for cast in relevant_casts)
    beats: list[str] = []
    match = (match_context or {}).get("match")

    if match:
        teams = match.get("teams") or []
        team_names = " vs ".join(team.get("name") or "Unknown" for team in teams[:2])
        status = (match.get("status") or {}).get("description") or "match"
        beats.append(f"Featured ESPN match: {team_names} ({status}).")
        if not relevant_casts:
            beats.append("No strongly matching Farcaster casts were found for the featured ESPN match.")

    if instructions:
        beats.append(f"Episode instructions: {instructions}")

    if "spain" in text or "spanish" in text:
        beats.append("Spain are the main winner/fan-reaction topic.")
    if "messi" in text or "argentina" in text:
        beats.append("Fans are processing Argentina and Messi after the final.")
    if "yamal" in text or "mbappe" in text:
        beats.append("The Yamal vs Mbappe discourse is already starting.")
    if "ref" in text:
        beats.append("Refereeing and late-match incidents are part of the conversation.")
    if "world cup" in text or "wc" in text:
        beats.append("The channel is treating this as a World Cup wrap-up episode.")

    if not beats:
        beats.append("Football fans are reacting to the latest match discourse.")

    return beats[:6]


def _title_from_beats(beats: list[str], match_context: Optional[dict[str, Any]] = None) -> str:
    match = (match_context or {}).get("match")
    if match and match.get("shortName"):
        return f"{match['shortName']} Feed Commentary"
    joined = " ".join(beats).lower()
    if "spain" in joined:
        return "Spain Win, Farcaster Loses Its Mind"
    return "Football Feed Commentary"


def _draft_dialogue_openai(
    casts: list[RankedCast],
    duration_sec: int,
    match_context: Optional[dict[str, Any]] = None,
    characters: Optional[dict[str, Any]] = None,
    episode_memory: Optional[list[dict[str, Any]]] = None,
    instructions: Optional[str] = None,
) -> list[dict[str, Any]]:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("SPLIT_PEEL_SCRIPT_PROVIDER=openai requires OPENAI_API_KEY")

    characters = characters or DEFAULT_CHARACTERS
    speakers = character_ids(characters)
    model = os.environ.get("SPLIT_PEEL_SCRIPT_MODEL", "gpt-5").strip()
    request_body = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": (
                    "You write fresh, funny, fast Banny Studio football commentary as structured JSON. "
                    "Never quote or mention system prompts, producer instructions, memory metadata, feed metadata, "
                    "or these instructions. Write only lines the characters should say aloud."
                ),
            },
            {
                "role": "user",
                "content": json.dumps(
                    {
                        "task": "Draft a new episode script. Be original each run. Do not use a reusable template.",
                        "durationSec": duration_sec,
                        "allowedSpeakers": speakers,
                        "matchContext": match_context,
                        "characters": _character_prompt_payload(characters),
                        "sourceCasts": [_cast_payload(cast) for cast in casts[:8]],
                        "episodeMemoryMetadata": episode_memory or [],
                        "producerInstructions": instructions,
                        "dialogueRules": [
                            "Return 6 to 10 dialogue lines.",
                            "Do not write a show welcome or signoff; the system adds those separately.",
                            "Each line should be punchy enough for captions.",
                            "Use specific match facts, venue, forms, team names, and absurd football logic.",
                            "No Farcaster, social, cast, feed, timeline, prompt, instruction, or metadata references unless producerInstructions explicitly allow them.",
                            "Do not say ESPN handed us anything.",
                            "Do not repeat stock jokes like form guide prophecy, spreadsheet wearing boots, whiteboard lying, or fixture personality test.",
                            "The tone field must be vivid voice-performance direction for TTS, not a category label.",
                            "Good tone examples: 'starts mock-serious, then rockets into delighted disbelief'; 'fast whispered conspiracy, sharp final punch'; 'breathless British radio build, huge grin on the last phrase'.",
                            "Vary tone across lines so the voices rise, fall, interrupt themselves, whisper, punch, and accelerate.",
                        ],
                    },
                    ensure_ascii=False,
                ),
            },
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": "banny_episode_dialogue",
                "description": "Structured Banny Studio dialogue lines.",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "dialogue": {
                            "type": "array",
                            "minItems": 6,
                            "maxItems": 10,
                            "items": {
                                "type": "object",
                                "properties": {
                                    "speaker": {"type": "string", "enum": speakers},
                                    "line": {"type": "string"},
                                    "tone": {"type": "string"},
                                },
                                "required": ["speaker", "line", "tone"],
                                "additionalProperties": False,
                            },
                        }
                    },
                    "required": ["dialogue"],
                    "additionalProperties": False,
                },
            }
        },
    }

    request = urllib.request.Request(
        "https://api.openai.com/v1/responses",
        data=json.dumps(request_body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response:
            response_body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenAI script generation failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise RuntimeError(f"OpenAI script generation failed: {error}") from error

    payload = json.loads(_response_text(response_body))
    return _normalize_ai_dialogue(payload.get("dialogue"), speakers)


def _character_prompt_payload(characters: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "id": character.get("id"),
            "displayName": character.get("displayName"),
            "voiceDirection": character.get("voiceDirection"),
            "personality": character.get("personality"),
            "preferences": character.get("preferences"),
            "catchphrases": character.get("catchphrases"),
        }
        for character in characters.get("characters") or []
    ]


def _response_text(response_body: dict[str, Any]) -> str:
    if response_body.get("output_text"):
        return str(response_body["output_text"])
    pieces: list[str] = []
    for item in response_body.get("output") or []:
        for content in item.get("content") or []:
            if content.get("text"):
                pieces.append(str(content["text"]))
    text = "".join(pieces).strip()
    if not text:
        raise RuntimeError("OpenAI script generation returned no text")
    return text


def _normalize_ai_dialogue(dialogue: Any, speakers: list[str]) -> list[dict[str, Any]]:
    if not isinstance(dialogue, list):
        raise RuntimeError("OpenAI script generation returned invalid dialogue")
    normalized: list[dict[str, Any]] = []
    start = 0.5
    for index, item in enumerate(dialogue):
        if not isinstance(item, dict):
            continue
        speaker = str(item.get("speaker") or speakers[index % len(speakers)]).lower()
        if speaker not in speakers:
            speaker = speakers[index % len(speakers)]
        line = _clean_spoken_line(str(item.get("line") or ""))
        if not line:
            continue
        normalized.append(
            {
                "speaker": speaker,
                "line": line,
                "tone": str(item.get("tone") or "banter"),
                "start": round(start, 2),
            }
        )
        start += max(3.0, len(line.split()) * 0.38)

    if len(normalized) < 2:
        raise RuntimeError("OpenAI script generation returned too few usable dialogue lines")
    return normalized


def _add_house_lines(
    dialogue: list[dict[str, Any]],
    match_context: Optional[dict[str, Any]],
    characters: dict[str, Any],
) -> list[dict[str, Any]]:
    speakers = character_ids(characters)
    if not dialogue or len(speakers) < 2:
        return dialogue
    match = (match_context or {}).get("match") or {}
    intro_line = _house_intro(match, characters, speakers)
    signoff_line = _house_signoff(match, speakers)
    wrapped = [
        {"speaker": speakers[0], "line": intro_line, "tone": "bright show open, crisp host energy, playful lift on Peel's description"},
        *dialogue,
        {"speaker": speakers[1], "line": signoff_line, "tone": "classic creator signoff, cheeky grin, punch the final phrase"},
    ]
    return _retime_dialogue(wrapped)


def _house_intro(match: dict[str, Any], characters: dict[str, Any], speakers: list[str]) -> str:
    show_name = _show_name(match)
    character_names = character_map(characters)
    host_name = character_names.get(speakers[0], {}).get("displayName") or speakers[0].title()
    cohost_name = character_names.get(speakers[1], {}).get("displayName") or speakers[1].title()
    descriptor = _peel_descriptor(match)
    return f"Welcome to {show_name}. I'm {host_name}, and as always I'm joined by {descriptor}, {cohost_name}."


def _house_signoff(match: dict[str, Any], speakers: list[str]) -> str:
    variants = [
        "Leave it in the match replies, tap the little banana, and share this before stoppage time finds us.",
        "Like, subscribe, and tell the comments which tactical fruit had the better read.",
        "Drop your verdict in the match replies, ring the peel bell, and send this to one dangerously confident fan.",
        "If your group chat survived that, like, share, and subscribe before the replay changes its mind.",
    ]
    return variants[_variant_index(match, "house-signoff", len(variants))] if match else variants[0]


def _show_name(match: dict[str, Any]) -> str:
    return SHOW_NAME


def _peel_descriptor(match: dict[str, Any]) -> str:
    variants = [
        "a co-commentator with a whistle, a spreadsheet, and no emotional brakes",
        "the only analyst legally allowed to call xG a haunted number",
        "a tiny yellow pundit currently arguing with the fixture computer",
        "the booth's leading expert in panic, vibes, and late flags",
    ]
    return variants[_variant_index(match, "peel-descriptor", len(variants))] if match else variants[0]


def _retime_dialogue(dialogue: list[dict[str, Any]]) -> list[dict[str, Any]]:
    start = 0.5
    retimed: list[dict[str, Any]] = []
    for item in dialogue:
        line = str(item.get("line") or "").strip()
        if not line:
            continue
        updated = {**item, "start": round(start, 2)}
        retimed.append(updated)
        start += max(3.0, len(line.split()) * 0.38)
    return retimed


def _clean_spoken_line(line: str) -> str:
    line = " ".join(line.split()).strip()
    blocked_fragments = (
        "producer instruction",
        "producerinstructions",
        "system prompt",
        "prompt says",
        "metadata",
        "episode memory",
    )
    lowered = line.lower()
    if any(fragment in lowered for fragment in blocked_fragments):
        return ""
    return line


def _draft_dialogue(
    casts: list[RankedCast],
    match_context: Optional[dict[str, Any]] = None,
    characters: Optional[dict[str, Any]] = None,
    episode_memory: Optional[list[dict[str, Any]]] = None,
    instructions: Optional[str] = None,
) -> list[dict[str, Any]]:
    characters = characters or DEFAULT_CHARACTERS
    speakers = character_ids(characters)
    lines = _opening_lines(match_context, speakers, characters)
    match = (match_context or {}).get("match")
    match_relevant_casts = [cast for cast in casts if cast.match_hits > 0] if match else casts
    social_allowed = _social_references_allowed(instructions)

    if match and not match_relevant_casts:
        lines.extend(_no_relevant_cast_lines(match, speakers, social_allowed))

    seen_paraphrases: set[str] = set()
    for cast in match_relevant_casts:
        paraphrase = _paraphrase_cast(cast, match_context)
        paraphrase_key = _paraphrase_key(paraphrase)
        if paraphrase_key in seen_paraphrases:
            continue
        seen_paraphrases.add(paraphrase_key)
        lines.append((speakers[len(lines) % len(speakers)], paraphrase, "banter", cast.username))
        if len(seen_paraphrases) >= 5:
            break

    lines.extend(_closing_lines(match, speakers, social_allowed))

    start = 0.5
    dialogue: list[dict[str, Any]] = []
    for line_tuple in lines:
        speaker, line, tone = line_tuple[:3]
        item = {"speaker": speaker, "line": line, "tone": tone, "start": round(start, 2)}
        if len(line_tuple) > 3:
            item["sourceUsername"] = line_tuple[3]
        dialogue.append(item)
        start += max(3.0, len(line.split()) * 0.38)

    return dialogue


def _social_references_allowed(instructions: Optional[str]) -> bool:
    if not instructions:
        return True
    lowered = instructions.lower()
    blocked_terms = ("no farcaster", "do not reference farcaster", "do not reference social", "no social")
    return not any(term in lowered for term in blocked_terms)


def _no_relevant_cast_lines(match: dict[str, Any], speakers: list[str], social_allowed: bool) -> list[tuple[str, str, str]]:
    if social_allowed:
        return [
            (
                speakers[0],
                "The football channel is not giving this fixture much direct chatter yet, which is suspiciously calm behavior for the internet.",
                "dry",
            ),
            (
                speakers[1 % len(speakers)],
                "So we are treating ESPN as the adult in the room and the social feed as background noise until someone starts shouting about the actual match.",
                "banter",
            ),
        ]

    teams = match.get("teams") or []
    if len(teams) >= 2:
        first, second = teams[0], teams[1]
        first_name = _team_name(first, "the home side")
        second_name = _team_name(second, "the visitors")
        first_form = _team_form(first)
        second_form = _team_form(second)
        variants = [
            [
                (
                    speakers[0],
                    f"{first_name} walk in carrying {first_form}, which looks confident until football starts asking follow-up questions.",
                    "analysis",
                ),
                (
                    speakers[1 % len(speakers)],
                    f"{second_name} answer with {second_form}, a form line that feels like a suitcase packed during a fire alarm.",
                    "banter",
                ),
            ],
            [
                (
                    speakers[0],
                    f"The form guide says {first_name}: {first_form}. I say that is five tiny plot twists wearing club tracksuits.",
                    "analysis",
                ),
                (
                    speakers[1 % len(speakers)],
                    f"And {second_name} show up with {second_form}, which is less a record and more a weather warning with studs.",
                    "banter",
                ),
            ],
            [
                (
                    speakers[0],
                    f"{first_name}'s recent run reads {first_form}, so the confidence meter is making noises the warranty did not cover.",
                    "analysis",
                ),
                (
                    speakers[1 % len(speakers)],
                    f"{second_name} bring {second_form}; somewhere, a tactics board just developed stage fright.",
                    "banter",
                ),
            ],
            [
                (
                    speakers[0],
                    f"{first_name} have {first_form} behind them, which is enough evidence for optimism and at least three bad predictions.",
                    "analysis",
                ),
                (
                    speakers[1 % len(speakers)],
                    f"{second_name}'s {second_form} says this could be composed, chaotic, or both before the first throw-in.",
                    "banter",
                ),
            ],
        ]
        return variants[_variant_index(match, "no-social-middle", len(variants))]

    return [
        (
            speakers[0],
            "The match card is light on chaos but heavy on opportunity, which is exactly when football starts rearranging furniture.",
            "analysis",
        )
    ]


def _closing_lines(
    match: Optional[dict[str, Any]],
    speakers: list[str],
    social_allowed: bool,
) -> list[tuple[str, str, str]]:
    if match and not social_allowed:
        teams = match.get("teams") or []
        if len(teams) >= 2:
            first_name = _team_name(teams[0], "one side")
            second_name = _team_name(teams[1], "the other")
            variants = [
                [
                    (
                        speakers[0],
                        f"My read: {first_name} need clean possession, {second_name} need one ugly transition, and the first mistake gets a marching band.",
                        "deadpan",
                    ),
                    (
                        speakers[1 % len(speakers)],
                        "That is our whistle. Somebody lock the tactics board before it starts giving interviews.",
                        "button",
                    ),
                ],
                [
                    (
                        speakers[0],
                        f"If {first_name} control the tempo, this gets sensible. If {second_name} break the rhythm, we are eating popcorn with both hands.",
                        "deadpan",
                    ),
                    (
                        speakers[1 % len(speakers)],
                        "File it under: normal fixture on paper, suspicious little thundercloud in boots.",
                        "button",
                    ),
                ],
                [
                    (
                        speakers[0],
                        f"The whole thing may hinge on whether {first_name} turn pressure into chances before {second_name} turn patience into a trapdoor.",
                        "deadpan",
                    ),
                    (
                        speakers[1 % len(speakers)],
                        "Wonderful. I came for analysis and left holding a tiny tactical fire extinguisher.",
                        "button",
                    ),
                ],
                [
                    (
                        speakers[0],
                        f"{first_name} need the match to behave; {second_name} need it to get weird. Football traditionally votes for weird.",
                        "deadpan",
                    ),
                    (
                        speakers[1 % len(speakers)],
                        "Back after the break, unless the fixture list escapes and starts chewing the furniture.",
                        "button",
                    ),
                ],
            ]
            return variants[_variant_index(match, "no-social-close", len(variants))]

    return [
        (
            speakers[0],
            "My analysis is simple: football happened, the internet overreacted, and somehow both sides believe this proves their old argument.",
            "deadpan",
        ),
        (
            speakers[1 % len(speakers)],
            "Join us next time, when one misplaced pass becomes a national identity crisis with thumbnails.",
            "button",
        ),
    ]


def _opening_lines(
    match_context: Optional[dict[str, Any]] = None,
    speakers: Optional[list[str]] = None,
    characters: Optional[dict[str, Any]] = None,
) -> list[tuple[str, str, str]]:
    speakers = speakers or ["split", "peel"]
    match = (match_context or {}).get("match")
    character_names = character_map(characters or DEFAULT_CHARACTERS)
    speaker_one_name = character_names.get(speakers[0], {}).get("displayName") or speakers[0]
    speaker_two_name = character_names.get(speakers[1 % len(speakers)], {}).get("displayName") or speakers[1 % len(speakers)]
    if not match:
        return [
            (
                speakers[0],
                f"{speaker_one_name} has opened the football channel and the timeline is already wearing a scarf indoors.",
                "dry open",
            ),
            (
                speakers[1 % len(speakers)],
                f"{speaker_two_name} can confirm: nobody is calm, everyone has a tactical theory, and at least one person is typing through tears.",
                "mock-serious",
            ),
        ]

    teams = match.get("teams") or []
    team_names = " versus ".join(team.get("name") or "Unknown" for team in teams[:2])
    status = match.get("status") or {}
    detail = status.get("detail") or status.get("description") or "on the board"
    venue = (match.get("venue") or {}).get("name")
    venue_line = f" at {venue}" if venue else ""
    variants = [
        [
            (
                speakers[0],
                f"Tonight's very serious banana desk opens on {team_names}{venue_line}, with the board saying {detail}.",
                "dry open",
            ),
            (
                speakers[1 % len(speakers)],
                "Excellent. Two crests, one stadium, and a suspicious amount of destiny pretending to be scheduling.",
                "mock-serious",
            ),
        ],
        [
            (
                speakers[0],
                f"{team_names}{venue_line}: that is the card, {detail}, and already the form guide is sweating through its blazer.",
                "dry open",
            ),
            (
                speakers[1 % len(speakers)],
                "I can hear the pre-match music trying to act calm, which frankly makes it more suspicious.",
                "mock-serious",
            ),
        ],
        [
            (
                speakers[0],
                f"We are pointed at {team_names}{venue_line}, officially marked {detail}, which is code for ninety minutes of emotional paperwork.",
                "dry open",
            ),
            (
                speakers[1 % len(speakers)],
                "Bring me the clipboard, the tiny whistle, and one unreasonable theory before kickoff.",
                "mock-serious",
            ),
        ],
        [
            (
                speakers[0],
                f"The fixture machine has produced {team_names}{venue_line}, stamped {detail}, and asked us to behave professionally.",
                "dry open",
            ),
            (
                speakers[1 % len(speakers)],
                "A bold request. I have already emotionally overcommitted to the first misplaced pass.",
                "mock-serious",
            ),
        ],
    ]
    return variants[_variant_index(match, "opening", len(variants))]


def _team_name(team: dict[str, Any], fallback: str) -> str:
    return str(team.get("name") or team.get("shortName") or team.get("abbreviation") or fallback)


def _team_form(team: dict[str, Any]) -> str:
    return str(team.get("form") or team.get("record") or "a very official-looking form guide")


def _variant_index(match: dict[str, Any], salt: str, count: int) -> int:
    teams = match.get("teams") or []
    team_seed = "|".join(
        f"{team.get('name') or ''}:{team.get('abbreviation') or ''}:{team.get('form') or ''}:{team.get('record') or ''}"
        for team in teams
    )
    venue = (match.get("venue") or {}).get("name") or ""
    seed = "|".join(
        [
            str(match.get("id") or ""),
            str(match.get("shortName") or ""),
            str(match.get("date") or ""),
            str(venue),
            team_seed,
            salt,
        ]
    )
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % count


def _paraphrase_cast(cast: RankedCast, match_context: Optional[dict[str, Any]] = None) -> str:
    text = cast.text.lower()
    prefix = f"@{cast.username} is basically saying"
    match = (match_context or {}).get("match") or {}
    teams = match.get("teams") or []
    for index, team in enumerate(teams):
        name = str(team.get("name") or "")
        abbreviation = str(team.get("abbreviation") or "")
        variants = [
            "the {team} fans have entered the chat with their usual emotional support spreadsheet.",
            "{team} supporters are treating one post like it just passed a fitness test.",
            "the {team} corner of the timeline is already rehearsing its victory speech in the tunnel.",
            "{team} fans are doing that thing where hope puts on a blazer and calls itself analysis.",
        ]
        if name and name.lower() in text:
            return f"{prefix} {variants[(cast.score + index) % len(variants)].format(team=name)}"
        if abbreviation and abbreviation.lower() in text:
            return f"{prefix} {variants[(cast.score + index + 1) % len(variants)].format(team=abbreviation)}"

    if "spain" in text and ("won" in text or "champ" in text or "cup" in text):
        return f"{prefix} Spain did not just win, they made the group chat stand up and applaud."
    if "messi" in text:
        return f"{prefix} even Messi discourse has entered the post-match courtroom."
    if "ref" in text:
        return f"{prefix} the referee had a rare episode of everyone not immediately demanding a public inquiry."
    if "yamal" in text or "mbappe" in text:
        return f"{prefix} the next superstar argument has already kicked off before the confetti got swept up."
    if "argentina" in text:
        return f"{prefix} Argentina were looking for a comeback and found Spain holding the clipboard."

    return f"{prefix} the vibes are dramatic, specific, and possibly typed at full sprint."


def _paraphrase_key(line: str) -> str:
    if " is basically saying " in line:
        return line.split(" is basically saying ", 1)[1]
    return line
