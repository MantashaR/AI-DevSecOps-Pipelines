#!/usr/bin/env bash
# AutoPatch — self-test. Asserts the pipeline produces the expected outputs
# end-to-end. Prints clear PASS/FAIL with line-level diffs on mismatch.

set -euo pipefail

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; OFF=$'\033[0m'
pass() { echo "${GREEN}[PASS]${OFF} $*"; }
fail() { echo "${RED}[FAIL]${OFF} $*"; exit 1; }

cd "$(dirname "$0")"

echo "=== AutoPatch self-test ==="

# Restore vulnerable demo target if a previous run left it patched
if ! grep -q '"admin123"' target-app/app.py; then
  fail "target-app/app.py is not in the expected vulnerable state. Restore it via git checkout."
fi
grep -q 'shell=True' target-app/app.py || fail "target-app/app.py missing shell=True (expected vuln)"
grep -q "name + " target-app/app.py    || fail "target-app/app.py missing SQLi pattern (expected vuln)"
pass "demo target is in vulnerable baseline"

# Clean any prior run artefacts
rm -rf .autopatch dashboard/history.json semgrep*.sarif trivy.sarif

# 1. Run scanners
echo "--- running scanners ---"
( cd target-app && \
    semgrep --config p/python --config p/security-audit --sarif --output ../semgrep.sarif . >/dev/null 2>&1 && \
    trivy fs --format sarif --output ../trivy.sarif --quiet . )
[ -s semgrep.sarif ] || fail "semgrep.sarif not produced"
[ -s trivy.sarif ]   || fail "trivy.sarif not produced"
SAST_BEFORE=$(python3 -c "import json; print(sum(len(r['results']) for r in json.load(open('semgrep.sarif'))['runs']))")
SCA_BEFORE=$(python3  -c "import json; print(sum(len(r['results']) for r in json.load(open('trivy.sarif'))['runs']))")
pass "scanners produced ${SAST_BEFORE} SAST + ${SCA_BEFORE} SCA findings"
[ "$SAST_BEFORE" -ge 4 ] || fail "expected >=4 Semgrep findings, got ${SAST_BEFORE}"
[ "$SCA_BEFORE"  -ge 5 ] || fail "expected >=5 Trivy findings, got ${SCA_BEFORE}"

# 2. Dry-run AutoPatch
echo "--- AutoPatch dry-run (stub LLM) ---"
DRY_OUT=$(python3 src/autopatch.py --sarif semgrep.sarif trivy.sarif \
            --repo-root . --target-root target-app --llm stub --dry-run)
DRY_APPLIED=$(echo "$DRY_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['fixes_applied'])")
[ "$DRY_APPLIED" = "2" ] || fail "dry-run expected 2 fixes, got ${DRY_APPLIED}"
pass "dry-run applied ${DRY_APPLIED} fixes (verified to apply, file untouched)"

# Confirm file is still vulnerable after dry-run
grep -q 'shell=True' target-app/app.py || fail "dry-run mutated the file (it must not!)"
pass "dry-run left target file untouched"

# 3. Real run — actually patch
echo "--- AutoPatch real run ---"
REAL_OUT=$(python3 src/autopatch.py --sarif semgrep.sarif trivy.sarif \
             --repo-root . --target-root target-app --llm stub)
REAL_APPLIED=$(echo "$REAL_OUT" | python3 -c "import json,sys; print(json.load(sys.stdin)['fixes_applied'])")
[ "$REAL_APPLIED" = "2" ] || fail "real run expected 2 fixes, got ${REAL_APPLIED}"
pass "real run applied ${REAL_APPLIED} patches"

# 4. Confirm patches landed correctly
grep -q 'execute(query, (name,))' target-app/app.py     || fail "SQLi patch did not land"
grep -q '"ping", "-c", "1", host' target-app/app.py     || fail "command-injection patch did not land"
grep -q 'shell=True' target-app/app.py                  && fail "shell=True is still present after patching"
pass "both patches present in target-app/app.py"

# 5. Self-validation re-scan
echo "--- self-validation re-scan ---"
( cd target-app && \
    semgrep --config p/python --config p/security-audit --sarif --output ../semgrep.after.sarif . >/dev/null 2>&1 )
SAST_AFTER=$(python3 -c "import json; print(sum(len(r['results']) for r in json.load(open('semgrep.after.sarif'))['runs']))")
[ "$SAST_AFTER" = "0" ] || fail "expected 0 Semgrep findings after patch, got ${SAST_AFTER}"
pass "self-validation: ${SAST_BEFORE} findings -> 0 (all SAST vulns closed)"

# 6. Dashboard mirror
[ -f dashboard/history.json ] || fail "dashboard/history.json was not mirrored"
RUNS=$(python3 -c "import json; print(len(json.load(open('dashboard/history.json'))))")
[ "$RUNS" -ge 1 ] || fail "dashboard/history.json is empty"
pass "dashboard/history.json has ${RUNS} run(s)"

# 7. Restore vuln state for demo
if [ -d .git ] && git ls-files --error-unmatch target-app/app.py >/dev/null 2>&1; then
  git checkout -- target-app/app.py
else
  python3 - <<'PY'
import re, pathlib
p = pathlib.Path('target-app/app.py')
src = p.read_text()
src = src.replace('query = "SELECT * FROM users WHERE username = ?"',
                  'query = "SELECT * FROM users WHERE username = \'" + name + "\'"')
src = src.replace('cur.execute(query, (name,))', 'cur.execute(query)')
src = src.replace('subprocess.check_output(["ping", "-c", "1", host], shell=False)',
                  'subprocess.check_output("ping -c 1 " + host, shell=True)')
p.write_text(src)
PY
fi
rm -f semgrep*.sarif trivy.sarif

echo
echo "${GREEN}=========================================${OFF}"
echo "${GREEN} ALL CHECKS PASSED — project is healthy ${OFF}"
echo "${GREEN}=========================================${OFF}"
echo
echo "Next:"
echo "  make demo        # safe dry-run, file unchanged"
echo "  make patch       # real run (mutates target-app/app.py)"
echo "  make dashboard   # http://localhost:8000"
