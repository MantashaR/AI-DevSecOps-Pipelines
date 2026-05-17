"""Apply a unified diff to the working tree (in-place, dry-run safe)."""
import subprocess
import tempfile
from pathlib import Path


def apply_diff(repo_root: Path, diff: str, dry_run: bool = False) -> tuple[bool, str]:
    if not diff.strip():
        return False, "empty diff"

    with tempfile.NamedTemporaryFile("w", suffix=".patch", delete=False) as fh:
        fh.write(diff)
        patch_path = fh.name

    cmd_check = ["patch", "-p1", "--dry-run", "--fuzz=3", "-i", patch_path]
    res = subprocess.run(cmd_check, cwd=repo_root, capture_output=True, text=True)
    if res.returncode != 0:
        return False, f"dry-run failed: {res.stdout}\n{res.stderr}"

    if dry_run:
        return True, "dry-run OK"

    cmd_apply = ["patch", "-p1", "--fuzz=3", "-i", patch_path]
    res = subprocess.run(cmd_apply, cwd=repo_root, capture_output=True, text=True)
    if res.returncode != 0:
        return False, f"apply failed: {res.stdout}\n{res.stderr}"
    return True, "applied"
