"""LLM triage. Supports stub (offline), GitHub Models, and Groq."""
import difflib
import json
import os
import re
import urllib.request
from pathlib import Path

SYSTEM_PROMPT = """You are a senior security engineer reviewing a SAST finding.
Given a vulnerability finding and the surrounding source code, return STRICT JSON:
{
  "severity": "critical" | "high" | "medium" | "low" | "noise",
  "is_reachable": true | false,
  "fix_diff": "<unified diff applying to the file, or empty string>",
  "rationale": "<two short sentences explaining the fix>"
}

Rules:
- Only suggest fix_diff if confidence is high; otherwise return empty string.
- Severity "noise" means a false positive that should be ignored.
- The diff MUST be a valid unified diff with --- a/<path> and +++ b/<path>
  headers, using the exact path provided in the finding, and contain three
  lines of context above and below each change.
- Do NOT include markdown fences. Return only the JSON object.
"""

# (rule_substr, message_substr) -> (old_substr, new_substr)
CANNED_FIXES: list[tuple[tuple[str, str], tuple[str, str]]] = [
    (("tainted-sql", "sql"),
     ('query = "SELECT * FROM users WHERE username = \'" + name + "\'"\n    cur.execute(query)',
      'query = "SELECT * FROM users WHERE username = ?"\n    cur.execute(query, (name,))')),
    (("subprocess", "subprocess"),
     ('result = subprocess.check_output("ping -c 1 " + host, shell=True)',
      'result = subprocess.check_output(["ping", "-c", "1", host], shell=False)')),
    (("hardcoded", "password"),
     ('DB_PASSWORD = "admin123"  # hardcoded secret',
      'DB_PASSWORD = os.environ["DB_PASSWORD"]')),
]

CANNED_RATIONALES = {
    "tainted-sql": ("high",
        "Replaces string concatenation with sqlite3 positional bind parameters, eliminating SQL injection while preserving query semantics."),
    "subprocess": ("high",
        "Replaces shell=True string concatenation with a list argv and shell=False, preventing command injection via crafted host values."),
    "hardcoded": ("medium",
        "Removes the hardcoded secret and reads DB_PASSWORD from the environment instead. Operators must export DB_PASSWORD before launch."),
}


def _make_diff(path: str, old_content: str, new_content: str) -> str:
    """difflib-generated unified diff with `patch -p1` compatible headers."""
    diff = difflib.unified_diff(
        old_content.splitlines(keepends=True),
        new_content.splitlines(keepends=True),
        fromfile=f"a/{path}",
        tofile=f"b/{path}",
        n=3,
    )
    return "".join(diff)


def _stub_response(finding: dict, full_file: str) -> dict:
    rule_id = (finding.get("ruleId") or "").lower()
    msg = (finding.get("message") or "").lower()
    path = finding.get("path", "")

    for (rk, mk), (old, new) in CANNED_FIXES:
        if rk in rule_id or mk in msg:
            if old not in full_file:
                # Already patched on a previous finding — return noise.
                return {
                    "severity": "noise",
                    "is_reachable": False,
                    "fix_diff": "",
                    "rationale": "Identical fix was applied earlier in this run; this finding is now resolved.",
                }
            new_file = full_file.replace(old, new, 1)
            sev, why = next(((s, w) for k, (s, w) in CANNED_RATIONALES.items() if k in rk), ("high", ""))
            return {
                "severity": sev,
                "is_reachable": True,
                "fix_diff": _make_diff(path, full_file, new_file),
                "rationale": why,
            }

    return {
        "severity": "low",
        "is_reachable": False,
        "fix_diff": "",
        "rationale": "Stub triage: no canned fix for this rule. Wire up a real LLM (--llm github-models) for full coverage.",
    }


def _call_github_models(finding: dict, code: str, token: str) -> dict:
    body = {
        "model": "openai/gpt-4o-mini",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"finding": finding, "code": code})},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://models.github.ai/inference/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    return _parse_json(payload["choices"][0]["message"]["content"])


def _call_groq(finding: dict, code: str, key: str) -> dict:
    body = {
        "model": "llama-3.3-70b-versatile",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": json.dumps({"finding": finding, "code": code})},
        ],
        "temperature": 0,
        "response_format": {"type": "json_object"},
    }
    req = urllib.request.Request(
        "https://api.groq.com/openai/v1/chat/completions",
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read())
    return _parse_json(payload["choices"][0]["message"]["content"])


def _parse_json(raw: str) -> dict:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def triage(finding: dict, code: str, backend: str = "stub", target_root: Path | None = None) -> dict:
    if backend == "stub":
        full = ""
        if target_root is not None and finding.get("path"):
            p = target_root / finding["path"]
            if p.exists():
                full = p.read_text(errors="replace")
        return _stub_response(finding, full)
    if backend == "github-models":
        token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
        if not token:
            raise RuntimeError("GITHUB_TOKEN not set for github-models backend")
        return _call_github_models(finding, code, token)
    if backend == "groq":
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            raise RuntimeError("GROQ_API_KEY not set for groq backend")
        return _call_groq(finding, code, key)
    raise ValueError(f"Unknown backend: {backend}")
