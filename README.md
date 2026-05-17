# AutoPatch

**AI-augmented DevSecOps pipeline with automated vulnerability remediation.**
HCLTech CoE PS-11 · Mini Project Compendium 2026.

AutoPatch is a single GitHub Actions workflow that:

1. Scans every PR with **Semgrep** (SAST) and **Trivy** (SCA).
2. Triages each finding with an **LLM** (severity, reachability, code-level fix).
3. Auto-opens a fix-PR with the patch applied.
4. **Re-scans** to confirm the fix actually closes the finding (self-validation loop).
5. Renders an **MTTR dashboard** as a static GitHub Pages site.

Zero servers, zero databases, zero monthly cost. The runner is the compute, the
repo is the storage, GitHub Models is the LLM.

---

## Why this design

Most published DevSecOps + LLM work stops at "suggest a fix". AutoPatch closes
the loop:

| Capability | AutoPatch |
|---|---|
| Multi-tool scanning | Semgrep + Trivy (ZAP optional) |
| Context-aware severity | LLM triage with reachability hint |
| Code-level fix | Unified diff applied as a fix-PR |
| **Self-validation** | Re-scan after patch; only mark `auto-fixed` if finding is gone |
| **Cost-aware** | DynamoDB-style cache via `.autopatch/cache.json`; deterministic stub for dry runs |
| Deployment | One workflow file. No infra. |

---

## Quick start

### Docker (any OS — Windows / macOS / Linux)

Only prerequisite: **Docker Desktop**.

```bash
git clone <your-fork>
cd autopatch
docker compose build              # one time
docker compose run --rm verify    # full self-test, prints PASS/FAIL
docker compose run --rm demo      # safe dry-run
docker compose run --rm patch     # real run (mutates target-app/app.py)
docker compose up dashboard       # http://localhost:8000
```

### Native (macOS / Linux only)

```bash
cd autopatch
./setup.sh           # installs semgrep + trivy
./verify.sh          # full self-test
make demo | patch | dashboard
```

The **stub backend** uses deterministic canned fixes for the demo target. To
process arbitrary repos, swap to a real LLM:

```bash
export GITHUB_TOKEN=ghp_...               # personal token, scope: models:read
python3 src/autopatch.py ... --llm github-models

# OR
export GROQ_API_KEY=gsk_...               # free at console.groq.com
python3 src/autopatch.py ... --llm groq
```

---

## Install on your own repo (one workflow file)

Copy `.github/workflows/autopatch.yml` into your repo and set
`target-root` to the directory you want scanned. The workflow uses the built-in
`GITHUB_TOKEN` with `models: read` permission — no extra secrets needed.

---

## Repo layout

```
src/                      Python pipeline (sarif parser, triage, patch, store)
target-app/               Intentionally vulnerable Flask app (the demo victim)
dashboard/                Static dashboard (GitHub Pages-ready)
.github/workflows/        AutoPatch CI workflow
action.yml                Composite action — for use as `uses: rishabh/autopatch@v1`
tests/fixtures/           Sample SARIF for unit-style runs
```

`.autopatch/` is created at runtime and holds:
- `cache.json` — finding-hash → verdict (avoids redundant LLM calls)
- `history.json` — append-only run summaries (read by the dashboard)

---

## End-to-end demo (5 minutes, all local)

```bash
# Vulnerable state
grep -nE "shell=True|cur.execute|name \+|admin123" target-app/app.py
#   9:DB_PASSWORD = "admin123"
#  17:query = "SELECT * FROM users WHERE username = '" + name + "'"
#  25:subprocess.check_output("ping -c 1 " + host, shell=True)

# Scan + auto-patch
cd target-app && semgrep --config p/python --config p/security-audit --sarif -o ../semgrep.sarif . && trivy fs --format sarif -o ../trivy.sarif --quiet . && cd ..
python3 src/autopatch.py --sarif semgrep.sarif trivy.sarif --repo-root . --target-root target-app --llm stub

# Verify the file is now safe
grep -nE "shell=True|cur.execute|name \+" target-app/app.py
# (only the parameterised execute(query, (name,)) and shell=False remain)

# Self-validation: re-scan
cd target-app && semgrep --config p/python --config p/security-audit --sarif -o ../semgrep.after.sarif . && cd ..
# 4 findings -> 0 findings. The patches actually closed the vulnerabilities.
```

Verified outputs from the dry-run above:

| Stage | Findings | Auto-fixed | Remaining |
|---|---|---|---|
| Semgrep before | 4 | — | — |
| AutoPatch run | 17 (4 sast + 13 sca) | **2** | 15 (low-severity SCA, need version-bump LLM) |
| Semgrep after | 0 | — | **all 4 SAST findings closed** |

---

## Roadmap

- [x] SARIF parsing for Semgrep + Trivy
- [x] LLM triage (stub, GitHub Models, Groq)
- [x] Unified-diff patch apply with `--fuzz=3`
- [x] Repo-local cache + history
- [x] Static dashboard with Chart.js
- [x] Self-validation rescan
- [ ] Reachability filter via CodeQL data flow
- [ ] OWASP ZAP DAST integration
- [ ] Streamlit Pro dashboard on Hugging Face Spaces
- [ ] Paper draft (IEEE SecDev format)

---

## License

MIT.
