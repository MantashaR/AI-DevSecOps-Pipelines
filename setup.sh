#!/usr/bin/env bash
# AutoPatch — one-shot dependency installer for macOS and Linux.
# Idempotent: safe to re-run. Prints a clear PASS/FAIL at the end.

set -euo pipefail

GREEN=$'\033[0;32m'; RED=$'\033[0;31m'; YEL=$'\033[1;33m'; OFF=$'\033[0m'
ok()   { echo "${GREEN}[OK]${OFF}   $*"; }
warn() { echo "${YEL}[WARN]${OFF} $*"; }
die()  { echo "${RED}[FAIL]${OFF} $*"; exit 1; }

OS="$(uname -s)"
echo "AutoPatch setup — detected OS: ${OS}"

# 1. Python 3.10+
if ! command -v python3 >/dev/null 2>&1; then
  die "python3 not found. Install Python 3.10+ from https://www.python.org/downloads/"
fi
PY_VER=$(python3 -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")')
PY_OK=$(python3 -c 'import sys; print(int(sys.version_info >= (3,10)))')
if [ "$PY_OK" != "1" ]; then
  die "Python ${PY_VER} found, but 3.10+ required. Upgrade: https://www.python.org/downloads/"
fi
ok "Python ${PY_VER}"

# 2. patch CLI
command -v patch >/dev/null 2>&1 || die "patch CLI missing. macOS: built-in. Debian/Ubuntu: 'sudo apt install patch'."
ok "patch ($(patch --version | head -1))"

# 3. git + curl
command -v git  >/dev/null 2>&1 || die "git missing"
command -v curl >/dev/null 2>&1 || die "curl missing"
ok "git, curl"

# 4. Semgrep (via pip — works everywhere)
if ! command -v semgrep >/dev/null 2>&1; then
  echo "Installing semgrep via pip..."
  if pip3 install --quiet semgrep 2>/dev/null \
     || pip3 install --quiet --user semgrep 2>/dev/null \
     || pip3 install --quiet --break-system-packages semgrep 2>/dev/null; then
    :
  else
    die "Could not install semgrep via pip. Try: pip3 install --user semgrep"
  fi
fi
ok "semgrep $(semgrep --version)"

# 5. Trivy
if ! command -v trivy >/dev/null 2>&1; then
  echo "Installing trivy..."
  case "$OS" in
    Darwin)
      command -v brew >/dev/null 2>&1 || die "Homebrew not installed (https://brew.sh). Then: brew install trivy"
      brew install trivy
      ;;
    Linux)
      INSTALL_DIR="${HOME}/.local/bin"
      mkdir -p "$INSTALL_DIR"
      curl -sSfL https://raw.githubusercontent.com/aquasecurity/trivy/main/contrib/install.sh \
        | sh -s -- -b "$INSTALL_DIR" v0.70.0
      case ":$PATH:" in
        *":$INSTALL_DIR:"*) : ;;
        *) warn "Add ${INSTALL_DIR} to your PATH:  echo 'export PATH=\"\$HOME/.local/bin:\$PATH\"' >> ~/.bashrc" ;;
      esac
      export PATH="$INSTALL_DIR:$PATH"
      ;;
    *) die "Unsupported OS for auto-install: ${OS}. Install trivy manually: https://aquasecurity.github.io/trivy/" ;;
  esac
fi
ok "trivy $(trivy --version 2>/dev/null | head -1)"

echo
echo "${GREEN}====================================${OFF}"
echo "${GREEN} Setup complete. Next: ./verify.sh ${OFF}"
echo "${GREEN}====================================${OFF}"
