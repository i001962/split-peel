"""Publication receipts shared by every harness. Unknown outcomes never auto-retry."""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from split_peel.artifacts import atomic_json, digest, identity, job_lock, read_json, require_approval


def publish_once(receipt: Path, request: dict, submit: Callable, prepare: Callable = lambda: None) -> dict:
    key = identity(request)
    with job_lock(receipt.with_suffix(receipt.suffix + ".lock")):
        if receipt.exists():
            previous = read_json(receipt)
            if previous.get("request_hash") != key:
                raise ValueError(f"Receipt belongs to different content: {receipt}; use a new release revision")
            if previous.get("status") == "complete":
                return previous["result"]
            raise ValueError(f"Publication outcome needs reconciliation: {receipt}; inspect the platform before retrying")
        prepare()
        record = {"version": 1, "status": "submitting", "request_hash": key, "request": request}
        atomic_json(receipt, record)
        try:
            result = submit()
        except Exception as error:
            atomic_json(receipt, {**record, "status": "unknown", "error_type": type(error).__name__})
            raise
        atomic_json(receipt, {**result, **record, "status": "complete", "result": result})
        return result


def reconcile_publication(receipt: Path, result: dict) -> dict:
    """Record the verified remote result of an interrupted request, without resubmitting."""
    with job_lock(receipt.with_suffix(receipt.suffix + ".lock")):
        previous = read_json(receipt)
        if previous.get("status") == "complete":
            raise ValueError("publication is already complete")
        if not result.get("url") or not any(result.get(k) for k in ("video_id", "post_id", "cast_hash")):
            raise ValueError("reconciliation requires a verified platform identifier and URL")
        atomic_json(receipt, {**result, **previous, "status": "complete", "result": result})
    return result


def publish_x_file(path: Path, receipt: Path, approval: Path, expected_mentions=(), dry_run=False) -> dict:
    from split_peel.x_posting import post_x
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise ValueError("X post is empty")
    for mention in expected_mentions:
        if text.count("@" + mention.lstrip("@")) != 1:
            raise ValueError(f"Expected exactly one mention of {mention}")
    require_approval(path, approval, "publish")
    request = {"platform": "x", "text": text, "sha256": digest(path)}
    if dry_run:
        return {"dry_run": True, "request": request}
    def submit():
        response = post_x(text)
        post_id = str((response.get("data") or {}).get("id") or "")
        if not post_id:
            raise ValueError("X did not return a post ID")
        return {"post_id": post_id, "url": f"https://x.com/i/status/{post_id}", "response": response}
    return publish_once(receipt, request, submit)


def distribution_receipt(receipts: list[Path], out: Path) -> dict:
    releases = [read_json(path) for path in receipts]
    if any(r.get("status") != "complete" for r in releases):
        raise ValueError("all platform receipts must be complete")
    result = {"version": 1, "status": "complete", "publications": releases}
    atomic_json(out, result)
    return result
