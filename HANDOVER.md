# AutoPatch — Handover Guide

This document is everything you need to **(1) get the project running on your
machine in 10 minutes** and **(2) understand it well enough to defend it in a
viva**. Read it once, top-to-bottom, before touching anything.

---

## 1. What is this project?

**AutoPatch** is the working prototype for **HCLTech CoE PS-11**:
*"AI-Augmented DevSecOps Pipeline with Automated Vulnerability Remediation."*

It is a **single GitHub Actions workflow** that, on every PR:

1. **Scans** the codebase with Semgrep (SAST) + Trivy (SCA).
2. **Triages** every finding with an LLM — gets back severity + a unified-diff
   fix.
3. **Auto-opens a fix-PR** with the patch applied.
4. **Re-scans** to confirm the patch actually closed the vulnerability
   (self-validation loop).
5. **Renders an MTTR dashboard** as a static GitHub Pages site.

**Zero servers. Zero databases. ₹0/month.** The GitHub runner is the compute,
the repo itself is the storage, GitHub Models is the LLM.

### Why this design wins

| Attribute | Why it matters |
|---|---|
| **One-line install** for any GitHub repo | Judges can install it on their own repo during the viva |
| **Self-validation** | Most published work stops at "suggest fix"; we close the loop |
| **Multi-LLM routing** (stub / GitHub Models / Groq) | Real-world production pattern, not a toy |
| **Zero-cost** | Demonstrates cost-aware engineering — rare in student projects |
| **GitHub-native serverless framing** | Genuinely novel paper angle |

---

## 2. Architecture

```
┌────────────────────┐
│  PR opened         │
└─────────┬──────────┘
          ▼
┌─────────────────────────────────────────────────────────┐
│  GitHub Actions runner  (the only "compute")            │
│                                                         │
│  Step 1.  Run Semgrep + Trivy  →  semgrep.sarif         │
│                                  trivy.sarif            │
│                                                         │
│  Step 2.  python3 src/autopatch.py                      │
│             • parse SARIF                               │
│             • for each finding:                         │
│                 hash → cache.json hit? skip LLM         │
│                 else → LLM (GitHub Models)              │
│                       returns severity + unified diff   │
│             • apply diff to working tree                │
│             • write history.json                        │
│                                                         │
│  Step 3.  if working tree changed:                      │
│             gh pr create --base main --head autopatch/* │
└─────────────────────────────────────────────────────────┘
          ▼
┌────────────────────┐     ┌──────────────────────────────┐
│  Fix-PR opened     │     │  GitHub Pages (dashboard/)   │
│  on the repo       │     │  Reads history.json,         │
└────────────────────┘     │  Chart.js renders MTTR etc.  │
                           └──────────────────────────────┘
```

Everything else (cache, history, audit trail) lives in **`.autopatch/*.json`**
inside the repo. No external services. The dashboard is static HTML + Chart.js
served from GitHub Pages.

---

## 3. Repo layout — what every file does

```
autopatch/
├── README.md                           Project overview (public-facing)
├── HANDOVER.md                         THIS file (internal walkthrough)
├── Makefile                            shortcuts: make demo / patch / dashboard
├── setup.sh                            native install: Python deps + semgrep + trivy
├── verify.sh                           self-test — runs full pipeline + asserts
├── Dockerfile                          one-OS-fits-all runtime image
├── docker-compose.yml                  one-command operations on any OS
├── .dockerignore                       keep image lean
├── .gitattributes                      enforce LF on shell scripts (Windows safety)
├── action.yml                          composite GitHub Action manifest
├── .gitignore
│
├── src/                                THE PIPELINE
│   ├── autopatch.py                    entry point — orchestrates everything
│   ├── sarif.py                        parses Semgrep + Trivy SARIF
│   ├── triage.py                       LLM call (stub / github-models / groq)
│   ├── patch.py                        applies unified diff via `patch -p1`
│   └── store.py                        cache.json + history.json + dashboard mirror
│
├── target-app/                         INTENTIONALLY VULNERABLE demo target
│   ├── app.py                          Flask app: SQLi, cmd injection, hardcoded pwd
│   └── requirements.txt                old flask/jinja2/requests → Trivy CVEs
│
├── dashboard/
│   ├── index.html                      static dashboard (GitHub Pages-ready)
│   └── history.json                    auto-mirrored from .autopatch/history.json
│
├── tests/fixtures/
│   └── sample_sarif.json               minimal SARIF for quick unit-style runs
│
└── .github/workflows/
    └── autopatch.yml                   the actual CI that runs on every PR
```

### Hot paths to understand for the viva

- **`src/autopatch.py`** — main loop. Reads SARIF → cache check → LLM → apply.
- **`src/triage.py`** — three backends. The `stub` backend uses **`difflib`**
  to generate proper unified diffs against the real file content (so dry runs
  work offline). `github-models` and `groq` make HTTP calls to OpenAI-compatible
  endpoints with `response_format: json_object`.
- **`src/patch.py`** — uses GNU `patch -p1 --fuzz=3` so small whitespace
  differences don't break apply. Always does `--dry-run` first to validate.
- **`.github/workflows/autopatch.yml`** — uses `permissions: models: read` so
  the built-in `GITHUB_TOKEN` can call GitHub Models. **No manual secret needed.**

---

## 4. Setup on a fresh machine — pick ONE path

### Path A — Docker (recommended for Windows, works on every OS) ⭐

The image bakes in semgrep + trivy + patch + Python 3.11. You install **only
Docker Desktop**. Nothing else.

**Prerequisites**
- Docker Desktop ([Windows](https://docs.docker.com/desktop/install/windows-install/) /
  [macOS](https://docs.docker.com/desktop/install/mac-install/) /
  [Linux](https://docs.docker.com/desktop/install/linux/))
- On Windows: enable the **WSL2 backend** during install (default since 2022).

**Run it (any OS, including Windows PowerShell or cmd):**

```bash
cd autopatch
docker compose build              # one time, ~3 minutes
docker compose run --rm verify    # full self-test, prints PASS/FAIL
```

You should see 8 `[PASS]` lines ending with:

```
=========================================
 ALL CHECKS PASSED — project is healthy
=========================================
```

**Day-to-day commands:**

```bash
docker compose run --rm demo      # safe dry-run, file unchanged
docker compose run --rm patch     # real run, mutates target-app/app.py
docker compose run --rm scan      # just produce semgrep.sarif + trivy.sarif
docker compose up dashboard       # http://localhost:8000   (Ctrl-C to stop)
```

**To use a real LLM instead of the offline stub:**

```bash
# macOS / Linux:
GITHUB_TOKEN=ghp_yourtoken LLM=github-models docker compose run --rm patch

# Windows PowerShell:
$env:GITHUB_TOKEN="ghp_yourtoken"; $env:LLM="github-models"; docker compose run --rm patch

# Windows cmd:
set GITHUB_TOKEN=ghp_yourtoken & set LLM=github-models & docker compose run --rm patch
```

### Path B — Native (macOS / Linux only, no Docker)

**Prerequisites**
- **Python 3.10 or newer** (`python3 --version`)
- `git`, `curl`, `patch` (preinstalled on macOS; Linux has them by default)
- macOS: Homebrew (script auto-installs trivy via brew)

```bash
cd autopatch
./setup.sh           # installs semgrep + trivy
./verify.sh          # runs full pipeline, asserts every step
```

`setup.sh` is **idempotent** — safe to re-run.

---

## 5. The 5-minute live demo (what you show on screen)

The demo is identical regardless of path; only the launcher differs.

| Step | Path A (Docker) | Path B (Native) |
|---|---|---|
| Show vulnerable state | `grep -n "shell=True\|admin123" target-app/app.py` | same |
| Scan + auto-patch | `docker compose run --rm patch` | `make patch` |
| Show fixed state | `grep -n "execute(query" target-app/app.py` | same |
| Self-validation rescan | `docker compose run --rm scan` (count findings) | `make scan` |
| Live dashboard | `docker compose up dashboard` → http://localhost:8000 | `make dashboard` |
| Restore vuln state | `git checkout target-app/app.py` | same |

**What the demo proves on screen:**
1. Before patch: 4 Semgrep findings (SQLi + 3 subprocess), 13 Trivy CVEs.
2. AutoPatch run: 2 fixes applied (`fixes_applied: 2` in the JSON output).
3. After patch: Semgrep returns **0** findings — the patches actually closed
   the vulnerabilities. This is the self-validation loop in action.
4. Dashboard shows the run timeline + severity mix + per-fix rationale.

---

## 6. Backends — when to use which

| Backend | When to use | Setup |
|---|---|---|
| `stub` | Dry runs, demos without internet, deterministic test fixtures | None — built-in |
| `github-models` | Real production runs on GitHub Actions | The `GITHUB_TOKEN` already has it via `permissions: models: read` |
| `groq` | Local runs without a GitHub token, or fallback | Sign up free at console.groq.com → `export GROQ_API_KEY=gsk_...` |

The stub only knows three canonical fixes (SQLi, command injection, hardcoded
password) — enough to demo the full pipeline without burning API quota. For
arbitrary repos, use `github-models`.

---

## 7. Pushing this to your own GitHub

```bash
gh auth login                                       # one-time
gh repo create autopatch --public --source=. \
   --remote=origin --push
```

Then on the GitHub web UI:

1. **Settings → Actions → General → Workflow permissions** → set to
   *Read and write permissions* (so the workflow can open fix-PRs).
2. **Settings → Pages** → Source: *Deploy from a branch*, Branch: `main`,
   Folder: `/dashboard`. Wait ~30s. Your dashboard is live at
   `https://<you>.github.io/autopatch/`.

Open any PR (typo in README is fine) — within a couple of minutes the **Actions**
tab will show AutoPatch running, and a `[AutoPatch] Automated security fixes`
PR will appear if Semgrep + Trivy find anything.

---

## 8. Viva FAQ — questions a judge will ask

**Q: Why not just use Snyk / Dependabot / Mend?**
A: Those tools suggest fixes but don't generate context-aware patches and don't
self-validate. AutoPatch's LLM produces a unified diff conditioned on the actual
surrounding code, then re-runs the scanner to *prove* the patch closed the
finding. Dependabot only does dep-version bumps; it can't fix SQL injection in
your own code.

**Q: How do you prevent the LLM from suggesting a wrong patch that breaks the
build?**
A: Three layers. (1) `patch --dry-run` validates the diff applies cleanly
*before* we accept it. (2) Self-validation re-scans after apply — if findings
persist, we label the PR `needs-human` instead of `auto-fixed`. (3) The PR is
*opened*, never auto-merged; a human always approves.

**Q: How do you handle prompt injection from malicious code comments?**
A: The LLM input is wrapped in a strict JSON envelope with a fixed system
prompt. The LLM is told to return *only* JSON with a `fix_diff` field. The diff
is applied via `patch`, not eval'd. We never echo LLM output into shell.

**Q: What's the LLM cost at scale?**
A: Zero on the free tier of GitHub Models (rate-limited). The cache hashes
each finding by `(rule_id, path, start_line)` so identical findings across
PRs cost one LLM call total. A reachability filter (CodeQL) — listed in the
roadmap — would cut calls another ~80%.

**Q: Why a single workflow file instead of a backend service?**
A: The GitHub runner is the compute, the repo is the storage. Cuts ops to
zero, makes the install a single-file copy, and gives a genuinely novel paper
framing: *"GitHub-native serverless DevSecOps."*

**Q: What's the failure mode if GitHub Models is down?**
A: The `--llm` flag falls back to Groq (Llama 3.3 70B) or to the deterministic
stub. The pipeline never breaks — at worst it skips fixes for that run.

**Q: How do you measure success?**
A: Four metrics, all on the dashboard:
  1. **MTTR** (mean time to remediation) per PR
  2. **Auto-fix rate** = `fixes_applied / total_findings`
  3. **Self-validation pass rate** = `% of fixes that re-scan clean`
  4. **Cost per scan** (stays at $0 on free tier)

---

## 9. Roadmap (what to say when asked "what next?")

- **Reachability filter** via CodeQL — only LLM-triage findings on a path from a
  public HTTP handler. Cuts API cost ~80%, paper-worthy contribution.
- **OWASP ZAP** integration for runtime DAST findings.
- **Streamlit Pro dashboard** on Hugging Face Spaces (richer than the static
  page, still free).
- **Reachability-weighted CVSS** — combine CVSS with EPSS exploitability +
  reachability; few student projects do this.
- **IEEE SecDev paper draft.**

---

## 10. Troubleshooting

### Docker path

| Symptom | Fix |
|---|---|
| `docker: command not found` | Install Docker Desktop and **launch it once** so the daemon starts |
| `Cannot connect to the Docker daemon` (Windows/Mac) | Open Docker Desktop from the Start menu / Applications and wait for the whale icon to stop animating |
| Build fails with "no space left on device" | `docker system prune -a` then rebuild |
| `verify` fails with `\r: command not found` | The compose entrypoint already strips CRLF; if you customised the script, ensure it has Unix line endings (`git config core.autocrlf input`) |
| Dashboard at localhost:8000 shows no data | Run `docker compose run --rm patch` first to generate `dashboard/history.json` |
| `docker compose run --rm patch` shows `fixes_applied: 0` | The target file is already patched. `git checkout target-app/app.py` |

### Native path

| Symptom | Fix |
|---|---|
| `./setup.sh` says "Python 3.X found, but 3.10+ required" | `brew install python@3.11` (mac) / `sudo apt install python3.11` (linux) |
| `./setup.sh` says trivy install failed on Linux | `curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \| sh -s -- -b ~/.local/bin v0.70.0` then add `~/.local/bin` to PATH |
| `make demo` errors with "semgrep not found" | `pip3 install --user --break-system-packages semgrep` |

### GitHub workflow

| Symptom | Fix |
|---|---|
| Workflow fails at "Open fix PR" | Settings → Actions → General → Workflow permissions → Read and write |
| LLM call returns 401 | `GITHUB_TOKEN` lacks `models:read` scope. Regenerate at github.com/settings/tokens (fine-grained, enable Models) |
| Dashboard on GitHub Pages shows "No runs yet" | First workflow run hasn't completed, or you set the Pages folder wrong. Settings → Pages → Folder: `/dashboard` |

---

## 11. License

MIT. Use freely.

---

If anything in this doc is wrong or unclear, that's a bug — fix it before
submission.
