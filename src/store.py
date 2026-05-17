"""Repo-local JSON storage for cache and history."""
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def _ensure(path: Path, default):
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(json.dumps(default))


def finding_hash(finding: dict) -> str:
    key = f"{finding.get('ruleId')}|{finding.get('path')}|{finding.get('startLine')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def load_cache(repo_root: Path) -> dict:
    p = repo_root / ".autopatch" / "cache.json"
    _ensure(p, {})
    return json.loads(p.read_text())


def save_cache(repo_root: Path, cache: dict) -> None:
    p = repo_root / ".autopatch" / "cache.json"
    p.write_text(json.dumps(cache, indent=2, sort_keys=True))


def append_run(repo_root: Path, summary: dict) -> None:
    p = repo_root / ".autopatch" / "history.json"
    _ensure(p, [])
    history = json.loads(p.read_text())
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()
    history.append(summary)
    payload = json.dumps(history, indent=2)
    p.write_text(payload)
    mirror = repo_root / "dashboard" / "history.json"
    if mirror.parent.exists():
        mirror.write_text(payload)
