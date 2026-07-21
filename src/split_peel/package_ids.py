from __future__ import annotations

import hashlib


def make_id(value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:14]
    return f"sp{digest}"
