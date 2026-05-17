"""SARIF -> normalised findings."""
import json
from pathlib import Path


def load(sarif_path: Path) -> list[dict]:
    data = json.loads(sarif_path.read_text())
    findings: list[dict] = []
    for run in data.get("runs", []):
        tool = run.get("tool", {}).get("driver", {}).get("name", "unknown")
        rules = {r["id"]: r for r in run.get("tool", {}).get("driver", {}).get("rules", [])}
        for r in run.get("results", []):
            rule_id = r.get("ruleId", "")
            rule = rules.get(rule_id, {})
            locs = r.get("locations", [])
            phys = locs[0].get("physicalLocation", {}) if locs else {}
            artifact = phys.get("artifactLocation", {})
            region = phys.get("region", {})
            findings.append({
                "tool": tool,
                "ruleId": rule_id,
                "message": (r.get("message") or {}).get("text", ""),
                "level": r.get("level", rule.get("defaultConfiguration", {}).get("level", "warning")),
                "path": artifact.get("uri", ""),
                "startLine": region.get("startLine", 0),
                "endLine": region.get("endLine", region.get("startLine", 0)),
                "cwe": _extract_cwe(rule),
            })
    return findings


def _extract_cwe(rule: dict) -> str:
    tags = rule.get("properties", {}).get("tags", []) or []
    for t in tags:
        if isinstance(t, str) and t.lower().startswith("cwe"):
            return t
    return ""
