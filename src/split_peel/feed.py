from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional
import urllib.parse
import urllib.error
from urllib.request import Request, urlopen


FOOTBALL_PARENT_URL = "chain://eip155:1/erc721:0x7abfe142031532e1ad0e46f971cc0ef7cf4b98b0"
FALSENINE_BOT_FID = "2477947"


def football_feed_url(limit: int = 100) -> str:
    query = urllib.parse.urlencode({"parent_urls": FOOTBALL_PARENT_URL, "limit": limit})
    return f"https://haatz.quilibrium.com/v2/farcaster/feed/parent_urls?{query}"


def farcaster_user_casts_url(fid: str = FALSENINE_BOT_FID, limit: int = 20) -> str:
    query = urllib.parse.urlencode({"fid": fid, "limit": limit})
    return f"https://haatz.quilibrium.com/v2/farcaster/feed/user/casts?{query}"


DEFAULT_FOOTBALL_FEED_URL = football_feed_url()
DEFAULT_FALSENINE_BOT_FEED_URL = farcaster_user_casts_url()
FALLBACK_FOOTBALL_FEED_URLS = ()

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
    research_source_id: str = ""
    research_source_name: str = ""
    fact_check_required: bool = False


def fetch_feed(url: str = DEFAULT_FOOTBALL_FEED_URL, timeout: int = 30) -> dict[str, Any]:
    urls = [url]
    if url == DEFAULT_FOOTBALL_FEED_URL:
        urls.extend(fallback for fallback in FALLBACK_FOOTBALL_FEED_URLS if fallback not in urls)

    last_error: Optional[Exception] = None
    for candidate in urls:
        request = Request(candidate, headers={"User-Agent": "split-peel/0.1"})
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            last_error = error
            if error.code not in {404, 502, 503, 504} or candidate == urls[-1]:
                raise
        except urllib.error.URLError as error:
            last_error = error
            if candidate == urls[-1]:
                raise

    raise RuntimeError(f"failed to fetch football feed: {last_error}")


def fetch_research_feed(
    feed_url: str = DEFAULT_FOOTBALL_FEED_URL,
    *,
    include_falsenine_bot: bool = True,
    falsenine_bot_feed_url: str = DEFAULT_FALSENINE_BOT_FEED_URL,
    timeout: int = 30,
) -> dict[str, Any]:
    sources = [
        {
            "id": "football-channel",
            "name": "Farcaster football channel",
            "kind": "farcaster-parent-url",
            "url": feed_url,
            "factCheckRequired": False,
            "role": "fan-texture",
        }
    ]
    if include_falsenine_bot:
        sources.append(
            {
                "id": "falsenine-bot",
                "name": "Falsenine bot account",
                "kind": "farcaster-user-casts",
                "url": falsenine_bot_feed_url,
                "fid": FALSENINE_BOT_FID,
                "factCheckRequired": True,
                "role": "fact-leads",
            }
        )

    merged_casts: list[dict[str, Any]] = []
    source_metadata = []
    source_errors = []
    seen: set[str] = set()
    for index, source in enumerate(sources):
        try:
            payload = fetch_feed(str(source["url"]), timeout=timeout)
        except Exception as error:
            if index == 0:
                raise
            source_errors.append({"sourceId": source["id"], "error": str(error)})
            continue

        casts = payload.get("casts") or []
        source_metadata.append({**source, "castCount": len(casts)})
        for cast in casts:
            if not isinstance(cast, dict):
                continue
            key = _cast_key(cast)
            if not key or key in seen:
                continue
            seen.add(key)
            merged_casts.append(_with_research_source(cast, source))

    research_graph = _build_research_graph(source_metadata, merged_casts)
    return {
        "casts": merged_casts,
        "researchSources": source_metadata,
        "sourceErrors": source_errors,
        "researchLoop": ["load", "extract", "graph", "index", "query", "memory", "produce-show", "update-learning"],
        "researchGraph": research_graph,
        "researchIndex": _build_research_index(merged_casts),
    }


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
                research_source_id=str(cast.get("researchSourceId") or ""),
                research_source_name=str((cast.get("researchSource") or {}).get("name") or ""),
                fact_check_required=bool(cast.get("factCheckRequired", False)),
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


def _cast_key(cast: dict[str, Any]) -> str:
    return str(cast.get("hash") or "").strip() or _normalize_text(str(cast.get("text") or ""))


def _with_research_source(cast: dict[str, Any], source: dict[str, Any]) -> dict[str, Any]:
    return {
        **cast,
        "researchSourceId": source["id"],
        "researchSource": {
            "id": source["id"],
            "name": source["name"],
            "kind": source["kind"],
            "role": source["role"],
            "url": source["url"],
            **({"fid": source["fid"]} if source.get("fid") else {}),
        },
        "factCheckRequired": bool(source["factCheckRequired"]),
    }


def _build_research_graph(sources: list[dict[str, Any]], casts: list[dict[str, Any]]) -> dict[str, Any]:
    nodes = [
        {
            "id": f"source:{source['id']}",
            "type": "source",
            "label": source["name"],
            "factCheckRequired": bool(source["factCheckRequired"]),
        }
        for source in sources
    ]
    edges = []
    for cast in casts:
        cast_id = f"cast:{_cast_key(cast)}"
        nodes.append(
            {
                "id": cast_id,
                "type": "cast",
                "label": str((cast.get("author") or {}).get("username") or "unknown"),
                "factCheckRequired": bool(cast.get("factCheckRequired", False)),
            }
        )
        edges.append({"from": f"source:{cast.get('researchSourceId')}", "to": cast_id, "type": "published"})
    return {"nodes": nodes, "edges": edges}


def _build_research_index(casts: list[dict[str, Any]]) -> dict[str, Any]:
    terms: dict[str, list[str]] = {}
    for cast in casts:
        cast_id = f"cast:{_cast_key(cast)}"
        for term in _terms_from_value(cast.get("text")):
            terms.setdefault(term, []).append(cast_id)
    return {"terms": {term: sorted(set(ids)) for term, ids in sorted(terms.items())}}
