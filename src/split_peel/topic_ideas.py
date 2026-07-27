from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any, Optional

from split_peel.feed import RankedCast, match_terms_from_context, rank_match_relevant_casts, rank_casts
from split_peel.x_trends import XTrend, normalize_x_trends


FOOTBALL_IDEA_TERMS = {
    "arsenal",
    "bayern",
    "bundesliga",
    "chelsea",
    "city",
    "cup",
    "england",
    "final",
    "football",
    "goal",
    "injury",
    "league",
    "liverpool",
    "manager",
    "manchester",
    "match",
    "messi",
    "munich",
    "penalty",
    "premier",
    "psg",
    "real madrid",
    "ref",
    "referee",
    "soccer",
    "spain",
    "stuttgart",
    "transfer",
    "ucl",
    "united",
    "world cup",
    "xg",
}

DEFAULT_GUIDED_SEEDS = (
    "transfer news",
    "injury news",
    "manager pressure",
    "referee controversy",
    "VAR",
    "xG",
)


def generate_topic_ideas(
    *,
    x_trends_payload: dict[str, Any],
    feed: dict[str, Any],
    match_context: Optional[dict[str, Any]] = None,
    memory: Optional[list[dict[str, Any]]] = None,
    limit: int = 10,
    seed_terms: Optional[list[str]] = None,
) -> dict[str, Any]:
    trends = normalize_x_trends(x_trends_payload)
    ranked_casts = rank_match_relevant_casts(feed, match_context, limit=40)
    fallback_casts = rank_casts(feed, limit=40, match_context=match_context, require_match_context=False)
    memory = memory or []
    match_terms = match_terms_from_context(match_context)
    memory_terms = _memory_terms(memory)

    ideas = []
    seen_titles: set[str] = set()
    guided_terms = _guided_terms(seed_terms, match_context, memory_terms)
    candidates = [(trend, False) for trend in trends]
    candidates.extend((XTrend(name=term), True) for term in guided_terms)
    for trend, guided in candidates:
        trend_terms = _terms(trend.name)
        overlap_casts = _overlapping_casts(trend_terms, ranked_casts or fallback_casts)
        match_overlap = sorted(trend_terms & match_terms)
        memory_overlap = sorted(trend_terms & memory_terms)
        football_overlap = sorted(trend_terms & FOOTBALL_IDEA_TERMS)
        if not guided and not _is_candidate(trend, trend_terms, overlap_casts, match_overlap, memory_overlap, football_overlap):
            continue

        title = _idea_title(trend, match_context)
        if title.lower() in seen_titles:
            continue
        seen_titles.add(title.lower())
        score = _idea_score(trend, overlap_casts, match_overlap, memory_overlap, football_overlap)
        if guided:
            score += 5
        else:
            score += 100
        ideas.append(
            {
                "title": title,
                "topic": trend.name,
                "source": "guided-probe" if guided else "x-trend",
                "angle": _angle(trend, match_context, overlap_casts, memory_overlap),
                "whyNow": _why_now(trend, match_overlap, football_overlap, guided=guided),
                "farcasterHooks": _farcaster_hooks(overlap_casts),
                "memoryHooks": _memory_hooks(memory, trend_terms),
                "suggestedEpisodeType": _episode_type(trend_terms, match_context),
                "searchTerms": sorted(trend_terms | set(match_overlap))[:10],
                "score": score,
                "ttsReady": False,
            }
        )

    ideas.sort(key=lambda item: item["score"], reverse=True)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "purpose": "idea-generator",
        "ttsReady": False,
        "inputs": {
            "xTrendCount": len(trends),
            "farcasterCastCount": len(feed.get("casts") or []),
            "memoryCount": len(memory),
            "hasMatchContext": bool((match_context or {}).get("match")),
            "guidedSeedCount": len(guided_terms),
        },
        "ideas": ideas[:limit],
    }


def _is_candidate(
    trend: XTrend,
    trend_terms: set[str],
    overlap_casts: list[RankedCast],
    match_overlap: list[str],
    memory_overlap: list[str],
    football_overlap: list[str],
) -> bool:
    if overlap_casts or match_overlap or memory_overlap or football_overlap:
        return True
    return trend.tweet_count >= 100000 and any(term.startswith("#") for term in trend_terms)


def _idea_score(
    trend: XTrend,
    overlap_casts: list[RankedCast],
    match_overlap: list[str],
    memory_overlap: list[str],
    football_overlap: list[str],
) -> int:
    count_score = min(trend.tweet_count // 5000, 25) if trend.tweet_count else 0
    return count_score + len(overlap_casts) * 18 + len(match_overlap) * 16 + len(memory_overlap) * 10 + len(football_overlap) * 8


def _idea_title(trend: XTrend, match_context: Optional[dict[str, Any]]) -> str:
    match = (match_context or {}).get("match") or {}
    short_name = str(match.get("shortName") or "").strip()
    clean_trend = trend.name.strip()
    if short_name and any(term in _terms(clean_trend) for term in match_terms_from_context(match_context)):
        return f"{short_name}: {clean_trend} Is Already A Bit"
    if _contains_any(clean_trend, {"transfer", "signing", "rumor", "rumour"}):
        return f"The Transfer Rumor That Ate {clean_trend}"
    return f"{clean_trend} Needs A Split & Peel Take"


def _angle(
    trend: XTrend,
    match_context: Optional[dict[str, Any]],
    overlap_casts: list[RankedCast],
    memory_overlap: list[str],
) -> str:
    match = (match_context or {}).get("match") or {}
    teams = [team.get("shortName") or team.get("name") for team in match.get("teams") or [] if team.get("shortName") or team.get("name")]
    if teams and overlap_casts:
        return f"X is surfacing {trend.name}, and Farcaster has enough chatter to turn {', '.join(teams[:2])} into a recurring studio argument."
    if teams:
        return f"Use {trend.name} as the zeitgeist hook, then bend it toward the {', '.join(teams[:2])} match without pretending the trend is proof."
    if overlap_casts:
        return f"X says {trend.name} is hot; Farcaster gives us named people to call out and build comedy around."
    if memory_overlap:
        return f"Revive an existing Split/Peel bit through the current {trend.name} trend."
    return f"Use {trend.name} as a quick monologue premise, then test whether Farcaster has better local texture before scripting."


def _why_now(trend: XTrend, match_overlap: list[str], football_overlap: list[str], *, guided: bool = False) -> list[str]:
    reasons = [f"Guided probe: {trend.name}" if guided else f"X trend: {trend.name}"]
    if trend.tweet_count:
        reasons.append(f"X volume: {trend.tweet_count:,} posts")
    if football_overlap:
        reasons.append(f"Football overlap: {', '.join(football_overlap[:4])}")
    if match_overlap:
        reasons.append(f"Match overlap: {', '.join(match_overlap[:4])}")
    return reasons


def _guided_terms(seed_terms: Optional[list[str]], match_context: Optional[dict[str, Any]], memory_terms: set[str]) -> list[str]:
    seeds = [term.strip() for term in (seed_terms or DEFAULT_GUIDED_SEEDS) if term and term.strip()]
    match = (match_context or {}).get("match") or {}
    team_names = []
    for team in match.get("teams") or []:
        for key in ("name", "shortName"):
            value = str(team.get(key) or "").strip()
            if value:
                team_names.append(value)
    team_names = _dedupe_contained_names(team_names)
    if len(team_names) >= 2:
        seeds.append(f"{team_names[0]} vs {team_names[1]}")
    for team_name in team_names:
        seeds.extend(
            [
                f"{team_name} transfer news",
                f"{team_name} injury news",
                f"{team_name} manager pressure",
            ]
        )
    seen: set[str] = set()
    deduped = []
    for seed in seeds:
        key = seed.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(seed)
    return deduped


def _dedupe_contained_names(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in values:
        lower = value.lower()
        if any(lower == existing.lower() for existing in deduped):
            continue
        if any(lower in existing.lower().split() for existing in deduped):
            continue
        deduped = [existing for existing in deduped if existing.lower() not in lower.split()]
        deduped.append(value)
    return deduped


def _farcaster_hooks(casts: list[RankedCast]) -> list[dict[str, Any]]:
    hooks = []
    for cast in casts[:4]:
        hooks.append(
            {
                "username": cast.username,
                "reason": (
                    "Falsenine bot fact lead overlaps with the X trend; verify before scripting."
                    if cast.fact_check_required
                    else "Recent Farcaster post overlaps with the X trend."
                ),
                "likes": cast.likes,
                "replies": cast.replies,
                "text": _shorten(cast.text, 180),
                "researchSourceId": cast.research_source_id,
                "researchSourceName": cast.research_source_name,
                "factCheckRequired": cast.fact_check_required,
            }
        )
    return hooks


def _memory_hooks(memory: list[dict[str, Any]], trend_terms: set[str]) -> list[str]:
    hooks = []
    for episode in memory:
        title = str(episode.get("title") or "").strip()
        text = " ".join(
            [
                title,
                " ".join(str(beat) for beat in episode.get("beats") or []),
                " ".join(str(user) for user in episode.get("sourceCastUsers") or []),
                " ".join(str(line.get("line") or "") for line in episode.get("dialogue") or [] if isinstance(line, dict)),
            ]
        )
        if trend_terms & _terms(text):
            hooks.append(title or "Prior episode memory")
    return hooks[:4]


def _episode_type(trend_terms: set[str], match_context: Optional[dict[str, Any]]) -> str:
    if _contains_term(trend_terms, {"final", "won", "win", "lost", "loss", "recap"}):
        return "recap"
    if _contains_term(trend_terms, {"transfer", "rumor", "rumour", "manager", "injury"}):
        return "general"
    if (match_context or {}).get("match"):
        return "match-event"
    return "general"


def _overlapping_casts(terms: set[str], casts: list[RankedCast]) -> list[RankedCast]:
    overlaps = []
    for cast in casts:
        if terms & _terms(cast.text):
            overlaps.append(cast)
    return overlaps[:6]


def _memory_terms(memory: list[dict[str, Any]]) -> set[str]:
    terms: set[str] = set()
    for episode in memory:
        terms.update(_terms(str(episode.get("title") or "")))
        for beat in episode.get("beats") or []:
            terms.update(_terms(str(beat)))
        for user in episode.get("sourceCastUsers") or []:
            terms.update(_terms(str(user)))
    return terms


def _terms(value: str) -> set[str]:
    text = value.lower()
    terms = {text.strip()} if text.strip() else set()
    terms.update(part for part in re.split(r"[^a-z0-9#]+", text) if len(part) >= 3)
    return {term.lstrip("#") for term in terms if term}


def _contains_any(value: str, needles: set[str]) -> bool:
    terms = _terms(value)
    return _contains_term(terms, needles)


def _contains_term(terms: set[str], needles: set[str]) -> bool:
    return bool(terms & needles)


def _shorten(value: str, limit: int) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."
