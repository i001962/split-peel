from __future__ import annotations

import json
import os
import urllib.error
from dataclasses import dataclass
from typing import Any, Optional
from urllib.request import Request, urlopen


X_TRENDS_BASE_URL = "https://api.x.com/2/trends/by/woeid"
DEFAULT_X_WOEID = "1"


class XTrendsError(RuntimeError):
    pass


@dataclass(frozen=True)
class XTrend:
    name: str
    tweet_count: int = 0
    url: str = ""


def x_trends_url(woeid: str | int = DEFAULT_X_WOEID) -> str:
    return f"{X_TRENDS_BASE_URL}/{str(woeid).strip()}"


def fetch_x_trends(
    woeid: str | int = DEFAULT_X_WOEID,
    *,
    bearer_token: Optional[str] = None,
    timeout: int = 30,
) -> dict[str, Any]:
    token = (bearer_token or os.environ.get("X_BEARER_TOKEN") or "").strip()
    if not token:
        raise XTrendsError("X trends require X_BEARER_TOKEN or --x-bearer-token")

    request = Request(
        x_trends_url(woeid),
        headers={
            "Authorization": f"Bearer {token}",
            "User-Agent": "split-peel/0.1",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = error.read().decode("utf-8", errors="replace")
        raise XTrendsError(f"X trends request failed ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise XTrendsError(f"X trends request failed: {error}") from error


def normalize_x_trends(payload: dict[str, Any], limit: int = 50) -> list[XTrend]:
    trends: list[XTrend] = []
    for raw in payload.get("data") or []:
        if not isinstance(raw, dict):
            continue
        name = str(raw.get("trend_name") or raw.get("name") or "").strip()
        if not name:
            continue
        trends.append(
            XTrend(
                name=name,
                tweet_count=_int_or_zero(raw.get("tweet_count") or raw.get("post_count")),
                url=str(raw.get("url") or ""),
            )
        )
    return trends[:limit]


def _int_or_zero(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
