"""AutoPatch entry point.

Usage:
    python src/autopatch.py \
        --sarif <path>... \
        --repo-root <path> \
        --target-root <path> \
        --llm stub|github-models|groq \
        [--dry-run] [--max-fixes N]
"""
import argparse
import json
import sys
from pathlib import Path

import patch as patch_mod
import sarif as sarif_mod
import store
import triage


def _read_snippet(target_root: Path, finding: dict, ctx: int = 6) -> str:
    p = target_root / finding["path"]
    if not p.exists():
        return ""
    lines = p.read_text(errors="replace").splitlines()
    start = max(0, finding["startLine"] - ctx - 1)
    end = min(len(lines), finding["endLine"] + ctx)
    return "\n".join(f"{i + 1}: {ln}" for i, ln in enumerate(lines[start:end], start=start))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sarif", nargs="+", required=True, type=Path)
    ap.add_argument("--repo-root", type=Path, required=True,
                    help="Where .autopatch/ history + cache live")
    ap.add_argument("--target-root", type=Path, required=True,
                    help="The codebase being scanned (where patches apply)")
    ap.add_argument("--llm", default="stub", choices=["stub", "github-models", "groq"])
    ap.add_argument("--dry-run", action="store_true",
                    help="Verify diffs apply but do not modify files")
    ap.add_argument("--max-fixes", type=int, default=10)
    args = ap.parse_args()

    findings: list[dict] = []
    for s in args.sarif:
        findings.extend(sarif_mod.load(s))

    cache = store.load_cache(args.repo_root)
    fixed_locations: set[tuple[str, int]] = set()

    summary = {
        "total_findings": len(findings),
        "fixes_applied": 0,
        "fixes_skipped_no_diff": 0,
        "fixes_skipped_low_severity": 0,
        "cache_hits": 0,
        "llm_calls": 0,
        "by_severity": {"critical": 0, "high": 0, "medium": 0, "low": 0, "noise": 0},
        "by_tool": {},
        "fixes": [],
        "llm_backend": args.llm,
        "dry_run": args.dry_run,
    }

    for finding in findings:
        summary["by_tool"][finding["tool"]] = summary["by_tool"].get(finding["tool"], 0) + 1
        h = store.finding_hash(finding)
        if h in cache:
            verdict = cache[h]
            summary["cache_hits"] += 1
        else:
            snippet = _read_snippet(args.target_root, finding)
            try:
                verdict = triage.triage(
                    finding, snippet, backend=args.llm, target_root=args.target_root
                )
            except Exception as exc:
                verdict = {
                    "severity": "low",
                    "is_reachable": False,
                    "fix_diff": "",
                    "rationale": f"triage error: {exc}",
                }
            cache[h] = verdict
            summary["llm_calls"] += 1

        sev = verdict.get("severity", "low")
        summary["by_severity"][sev] = summary["by_severity"].get(sev, 0) + 1

        if sev not in ("critical", "high"):
            summary["fixes_skipped_low_severity"] += 1
            continue
        diff = verdict.get("fix_diff", "")
        if not diff:
            summary["fixes_skipped_no_diff"] += 1
            continue
        loc_key = (finding["path"], finding["startLine"])
        if loc_key in fixed_locations:
            summary["fixes_skipped_no_diff"] += 1
            continue
        if summary["fixes_applied"] >= args.max_fixes:
            continue

        ok, msg = patch_mod.apply_diff(args.target_root, diff, dry_run=args.dry_run)
        summary["fixes"].append({
            "hash": h,
            "rule": finding["ruleId"],
            "path": finding["path"],
            "line": finding["startLine"],
            "severity": sev,
            "applied": ok,
            "rationale": verdict.get("rationale", ""),
            "message": msg,
        })
        if ok:
            summary["fixes_applied"] += 1
            fixed_locations.add(loc_key)

    store.save_cache(args.repo_root, cache)
    store.append_run(args.repo_root, summary)

    json.dump(summary, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
