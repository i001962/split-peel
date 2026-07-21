from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
from urllib.request import Request, urlopen


DEFAULT_FOOTBALL_FEED_URL = (
    "https://haatz.quilibrium.com/v2/farcaster/feed/parent_urls"
    "?parent_urls=chain://eip155:1/erc721:0x7abfe142031532e1ad0e46f971cc0ef7cf4b98b0"
    "&limit=100"
)

FOOTBALL_TERMS = {
    "argentina",
    "cup",
    "final",
    "football",
    "france",
    "goal",
    "messi",
    "mbappe",
    "ref",
    "referee",
    "spain",
    "spanish",
    "wc",
    "world cup",
    "yamal",
}


@dataclass(frozen=True)
class RankedCast:
    score: int
    timestamp: str
    username: str
    text: str
    likes: int
    replies: int
    match_hits: int = 0
    hash: str = ""
    pfp_url: str = ""


def fetch_feed(url: str = DEFAULT_FOOTBALL_FEED_URL, timeout: int = 30) -> dict[str, Any]:
    request = Request(url, headers={"User-Agent": "split-peel/0.1"})
    with urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def rank_casts(
    feed: dict[str, Any],
    limit: int = 12,
    match_context: Optional[dict[str, Any]] = None,
    require_match_context: bool = True,
) -> list[RankedCast]:
    match_terms = match_terms_from_context(match_context)
    ranked: list[RankedCast] = []
    seen_texts: set[str] = set()
    for cast in feed.get("casts", []):
        text = str(cast.get("text") or "").strip()
        if not text:
            continue
        normalized_text = _normalize_text(text)
        if normalized_text in seen_texts:
            continue
        seen_texts.add(normalized_text)

        text_lower = text.lower()
        match_hits = _count_term_hits(text_lower, match_terms)
        if match_terms and require_match_context and match_hits == 0:
            continue

        term_hits = sum(1 for term in FOOTBALL_TERMS if term in text_lower)
        reactions = cast.get("reactions") or {}
        replies = cast.get("replies") or {}
        likes = int(reactions.get("likes_count") or 0)
        reply_count = int(replies.get("count") or 0)

        score = match_hits * 30 + term_hits * 5 + min(likes, 20) + min(reply_count * 2, 12)
        if len(text) > 80:
            score += 2
        if cast.get("embeds"):
            score += 1

        author = cast.get("author") or {}
        ranked.append(
            RankedCast(
                score=score,
                timestamp=str(cast.get("timestamp") or ""),
                username=str(author.get("username") or "unknown"),
                text=text,
                likes=likes,
                replies=reply_count,
                match_hits=match_hits,
                hash=str(cast.get("hash") or ""),
                pfp_url=str(author.get("pfp_url") or ""),
            )
        )

    return sorted(ranked, key=lambda item: (item.score, item.timestamp), reverse=True)[:limit]


def rank_match_relevant_casts(feed: dict[str, Any], match_context: Optional[dict[str, Any]], limit: int = 12) -> list[RankedCast]:
    ranked = rank_casts(feed, limit=limit, match_context=match_context, require_match_context=True)
    if ranked:
        return ranked
    return rank_casts(feed, limit=limit, match_context=match_context, require_match_context=False)


def match_terms_from_context(match_context: Optional[dict[str, Any]]) -> set[str]:
    match = (match_context or {}).get("match")
    if not match:
        return set()

    terms: set[str] = set()
    for value in (match.get("name"), match.get("shortName")):
        terms.update(_terms_from_value(value))

    for team in match.get("teams") or []:
        for key in ("name", "shortName", "abbreviation"):
            terms.update(_terms_from_value(team.get(key)))

    return {term for term in terms if len(term) >= 3}


def _terms_from_value(value: Any) -> set[str]:
    if not value:
        return set()
    text = str(value).lower()
    terms = {text}
    terms.update(part for part in re.split(r"[^a-z0-9]+", text) if len(part) >= 3)
    return terms


def _count_term_hits(text_lower: str, terms: set[str]) -> int:
    hits = 0
    for term in terms:
        if re.search(rf"(?<![a-z0-9]){re.escape(term)}(?![a-z0-9])", text_lower):
            hits += 1
    return hits


def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower()).strip()
