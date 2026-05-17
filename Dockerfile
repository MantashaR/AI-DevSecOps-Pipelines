# AutoPatch — runtime image with all scanners baked in.
# Works identically on macOS, Linux, and Windows (via Docker Desktop + WSL2).
FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# OS deps: patch (apply diffs), git (semgrep needs it for tracked-files mode),
# curl + ca-certificates (trivy installer), bash (verify.sh), tini (clean PID 1).
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
        patch git curl ca-certificates bash tini \
 && rm -rf /var/lib/apt/lists/*

# Trivy 0.70.0 — pinned for reproducible scan output across machines.
RUN curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
      | sh -s -- -b /usr/local/bin v0.70.0

# Semgrep — installs the CLI plus its bundled rule packs.
RUN pip install --no-cache-dir semgrep==1.161.0

# Pre-warm semgrep's rule cache so the first scan inside a container is fast.
RUN semgrep --version >/dev/null

# Project source. Mounted at runtime via -v "$PWD:/work" so patches write back
# to the host repo. Sources here are only used when running without a mount.
WORKDIR /work
COPY src/   /app/src/
COPY tests/ /app/tests/

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python3", "/app/src/autopatch.py", "--help"]
