#!/usr/bin/env bash
# =============================================================================
# PSO installer test harness
# Runs install.sh inside Docker containers to verify it works on each platform.
#
# Usage:
#   chmod +x test_installer.sh
#   ./test_installer.sh
#
# Requirements:
#   Docker running locally
#   install.sh in the same directory as this script (or PSO_REPO reachable)
#
# What it tests:
#   - Ubuntu 22.04 (Debian family)
#   - Debian 12
#   - Arch Linux
#   Each container runs the installer end-to-end and checks the exit code.
# =============================================================================

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INSTALL_SH="$SCRIPT_DIR/install.sh"
PASS=0
FAIL=0

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BOLD='\033[1m'
RESET='\033[0m'

# ─── Helpers ──────────────────────────────────────────────────────────────────
pass() { echo -e "${GREEN}[PASS]${RESET} $*"; ((PASS++)); }
fail() { echo -e "${RED}[FAIL]${RESET} $*"; ((FAIL++)); }
info() { echo -e "${YELLOW}[INFO]${RESET} $*"; }

# ─── Check prereqs ────────────────────────────────────────────────────────────
if ! command -v docker &>/dev/null || ! docker info &>/dev/null 2>&1; then
    echo -e "${RED}Docker is not running. Please start Docker and try again.${RESET}"
    exit 1
fi

if [[ ! -f "$INSTALL_SH" ]]; then
    echo -e "${RED}install.sh not found at $INSTALL_SH${RESET}"
    exit 1
fi

# ─── Test runner ──────────────────────────────────────────────────────────────
# Mounts install.sh read-only into the container and runs it as a non-root user
# (to match real-world usage — sudo will be invoked for apt/pacman).
#
# We skip the actual git clone and Docker install inside the container
# to keep tests fast and offline-friendly — instead we inject a mock repo
# and stub out the docker check.

run_test() {
    local name="$1"
    local image="$2"
    local setup_cmd="${3:-}"   # optional: pre-install command (e.g. install sudo)

    info "Testing on $name ($image)..."

    # Build an inline Dockerfile that:
    # 1. Starts from the base image
    # 2. Installs sudo if needed
    # 3. Creates a non-root user 'tester'
    # 4. Injects a minimal fake PSO repo so we don't need network access
    local dockerfile
    dockerfile=$(cat <<DOCKERFILE
FROM $image

# ── Install sudo + curl if not present ───────────────────────────────────────
$(if [[ -n "$setup_cmd" ]]; then echo "RUN $setup_cmd"; fi)

# ── Create non-root user ──────────────────────────────────────────────────────
RUN id tester 2>/dev/null || useradd -m -s /bin/bash tester && \
    echo 'tester ALL=(ALL) NOPASSWD:ALL' >> /etc/sudoers

# ── Inject a minimal fake PSO repo at /fake-pso-repo ─────────────────────────
# This avoids a real git clone during tests.
RUN mkdir -p /fake-pso-repo && \
    cd /fake-pso-repo && git init && \
    touch requirements.txt && \
    printf '#!/usr/bin/env bash\necho "pso-check: all phases passing"\nexit 0\n' > pso-check && \
    chmod +x pso-check && \
    printf '#!/usr/bin/env bash\necho "pso: PSO CLI"\n' > pso && \
    chmod +x pso && \
    git config user.email "test@test.com" && \
    git config user.name "Test" && \
    git add -A && git commit -m "init"

# ── Copy install.sh ───────────────────────────────────────────────────────────
COPY install.sh /install.sh
RUN chmod +x /install.sh

# ── Patch install.sh for testing ─────────────────────────────────────────────
# Override PSO_REPO to point at our local fake repo.
# Override ensure_docker to be a no-op (Docker-in-Docker is out of scope).
RUN sed -i \
    's|PSO_REPO=.*|PSO_REPO="file:///fake-pso-repo"|' \
    /install.sh && \
    sed -i \
    's|ensure_docker$|: # ensure_docker stubbed for testing|' \
    /install.sh

USER tester
WORKDIR /home/tester

CMD ["/install.sh"]
DOCKERFILE
)

    local tag="pso-test-$(echo "$name" | tr '[:upper:]/ ' '[:lower:]--')"

    # Build
    if ! echo "$dockerfile" | docker build -t "$tag" -f - "$SCRIPT_DIR" \
            --quiet 2>&1; then
        fail "$name — Docker build failed"
        return
    fi

    # Run
    local output exit_code
    output=$(docker run --rm "$tag" 2>&1) && exit_code=0 || exit_code=$?

    if [[ $exit_code -eq 0 ]]; then
        # Spot-check the output for key success markers
        if echo "$output" | grep -q "PSO installed successfully"; then
            pass "$name — installer completed successfully"
        else
            fail "$name — exited 0 but success message not found"
            echo "$output" | tail -30
        fi
    else
        fail "$name — installer exited with code $exit_code"
        echo "$output" | tail -40
    fi

    # Clean up image
    docker rmi "$tag" --force &>/dev/null || true
}

# ─── Tests ────────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}PSO Installer Test Suite${RESET}"
echo "────────────────────────────────────────"

run_test "Ubuntu 22.04" "ubuntu:22.04" \
    "apt-get update -qq && apt-get install -y -qq sudo curl git"

run_test "Debian 12" "debian:12" \
    "apt-get update -qq && apt-get install -y -qq sudo curl git"

run_test "Arch Linux" "archlinux:latest" \
    "pacman -Sy --noconfirm sudo git curl"

# ─── Summary ──────────────────────────────────────────────────────────────────
echo ""
echo "────────────────────────────────────────"
TOTAL=$((PASS + FAIL))
echo -e "Results: ${GREEN}${PASS} passed${RESET} / ${RED}${FAIL} failed${RESET} / ${TOTAL} total"

if [[ $FAIL -gt 0 ]]; then
    exit 1
fi