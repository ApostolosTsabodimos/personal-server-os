#!/usr/bin/env bash
# =============================================================================
# PSO — Personal Server OS
# Web Installer  |  https://your-site/install.sh
#
# Usage:
#   curl -fsSL https://your-site/install.sh | bash
#
# What this does:
#   1. Detects your OS
#   2. Installs missing dependencies (git, Python 3.9+, Docker)
#   3. Clones the PSO repository
#   4. Creates a Python virtualenv and installs dependencies
#   5. Installs the `pso` and `pso-check` CLIs onto your PATH
#   6. Runs pso-check to verify everything is working
#   7. Prints next steps
#
# Supported platforms:
#   Ubuntu / Debian, Arch Linux, macOS (Homebrew)
#
# Requirements:
#   curl or wget, bash 4+
# =============================================================================

set -euo pipefail

# ─── Colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# ─── Config ───────────────────────────────────────────────────────────────────
PSO_REPO="https://github.com/ApostolosTsampodimos/personal-server-os.git"
PSO_INSTALL_DIR="${PSO_INSTALL_DIR:-$HOME/.pso}"
PSO_DATA_DIR="${PSO_DATA_DIR:-$HOME/.pso_dev}"
PSO_BIN_DIR="$HOME/.local/bin"
REQUIRED_PYTHON_MAJOR=3
REQUIRED_PYTHON_MINOR=9

# ─── Helpers ──────────────────────────────────────────────────────────────────
print_header() {
    echo ""
    echo -e "${BOLD}${CYAN}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${CYAN}║         PSO — Personal Server OS             ║${RESET}"
    echo -e "${BOLD}${CYAN}║              Web Installer                   ║${RESET}"
    echo -e "${BOLD}${CYAN}╚══════════════════════════════════════════════╝${RESET}"
    echo ""
}

info()    { echo -e "${CYAN}[PSO]${RESET}  $*"; }
success() { echo -e "${GREEN}[PSO]${RESET}  ✓ $*"; }
warn()    { echo -e "${YELLOW}[PSO]${RESET}  ⚠ $*"; }
error()   { echo -e "${RED}[PSO]${RESET}  ✗ $*" >&2; }
die()     { error "$*"; exit 1; }

step() {
    echo ""
    echo -e "${BOLD}── $* ${RESET}"
}

command_exists() { command -v "$1" &>/dev/null; }

# ─── OS Detection ─────────────────────────────────────────────────────────────
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        return
    fi

    if [[ ! -f /etc/os-release ]]; then
        die "Cannot detect OS. /etc/os-release not found. Manual installation required."
    fi

    # shellcheck source=/dev/null
    source /etc/os-release
    case "${ID:-}" in
        ubuntu|debian|linuxmint|pop)
            OS="debian"
            ;;
        arch|manjaro|endeavouros)
            OS="arch"
            ;;
        *)
            # Best-effort: check for apt or pacman
            if command_exists apt-get; then
                OS="debian"
            elif command_exists pacman; then
                OS="arch"
            else
                die "Unsupported OS: '${ID:-unknown}'. PSO currently supports Ubuntu/Debian, Arch, and macOS."
            fi
            ;;
    esac
}

# ─── Privilege helpers ────────────────────────────────────────────────────────
# We avoid requiring sudo where possible. When we do need it, we tell the user why.

maybe_sudo() {
    if [[ $EUID -eq 0 ]]; then
        "$@"
    else
        sudo "$@"
    fi
}

check_sudo() {
    if [[ $EUID -ne 0 ]] && ! command_exists sudo; then
        die "This installer needs sudo to install system packages. Please install sudo or run as root."
    fi
}

# ─── Package managers ─────────────────────────────────────────────────────────
pkg_install_debian() {
    info "Installing: $*"
    maybe_sudo apt-get update -qq
    maybe_sudo apt-get install -y -qq "$@"
}

pkg_install_arch() {
    info "Installing: $*"
    maybe_sudo pacman -Sy --noconfirm --needed "$@"
}

pkg_install_macos() {
    if ! command_exists brew; then
        info "Homebrew not found — installing Homebrew first..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
    fi
    info "Installing: $*"
    brew install "$@"
}

pkg_install() {
    case "$OS" in
        debian) pkg_install_debian "$@" ;;
        arch)   pkg_install_arch   "$@" ;;
        macos)  pkg_install_macos  "$@" ;;
    esac
}

# ─── Dependency: git ──────────────────────────────────────────────────────────
ensure_git() {
    step "Checking git"
    if command_exists git; then
        success "git found: $(git --version)"
        return
    fi
    warn "git not found — installing..."
    check_sudo
    case "$OS" in
        debian) pkg_install git ;;
        arch)   pkg_install git ;;
        macos)  pkg_install git ;;
    esac
    command_exists git || die "git installation failed."
    success "git installed: $(git --version)"
}

# ─── Dependency: Python 3.9+ ──────────────────────────────────────────────────
find_python() {
    # Return the first python3 binary that meets the version requirement
    for candidate in python3 python3.13 python3.12 python3.11 python3.10 python3.9; do
        if command_exists "$candidate"; then
            local ver
            ver=$("$candidate" -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
            local major
            major=$("$candidate" -c "import sys; print(sys.version_info.major)" 2>/dev/null || echo 0)
            if [[ "$major" -eq "$REQUIRED_PYTHON_MAJOR" && "$ver" -ge "$REQUIRED_PYTHON_MINOR" ]]; then
                echo "$candidate"
                return 0
            fi
        fi
    done
    return 1
}

ensure_python() {
    step "Checking Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+"

    if PYTHON=$(find_python); then
        success "Python found: $PYTHON ($($PYTHON --version))"
        return
    fi

    warn "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ not found — installing..."
    check_sudo
    case "$OS" in
        debian)
            pkg_install python3 python3-venv python3-pip
            ;;
        arch)
            pkg_install python python-pip
            ;;
        macos)
            pkg_install python@3.12
            # Ensure the newly installed python is on PATH
            # shellcheck disable=SC2155
            export PATH="$(brew --prefix)/opt/python@3.12/bin:$PATH"
            ;;
    esac

    if PYTHON=$(find_python); then
        success "Python installed: $PYTHON ($($PYTHON --version))"
    else
        die "Python ${REQUIRED_PYTHON_MAJOR}.${REQUIRED_PYTHON_MINOR}+ installation failed. Please install it manually."
    fi
}

ensure_python_venv() {
    # On some Debian/Ubuntu systems python3-venv is a separate package
    if [[ "$OS" == "debian" ]]; then
        if ! $PYTHON -m venv --help &>/dev/null; then
            warn "python3-venv missing — installing..."
            pkg_install python3-venv
        fi
    fi
}

# ─── Dependency: Docker ───────────────────────────────────────────────────────
ensure_docker() {
    step "Checking Docker"

    if command_exists docker && docker info &>/dev/null 2>&1; then
        success "Docker running: $(docker --version)"
        return
    fi

    if command_exists docker; then
        warn "Docker is installed but not running."
        if [[ "$OS" == "macos" ]]; then
            warn "Please start Docker Desktop, then re-run the installer."
            warn "  open -a Docker"
            DOCKER_MISSING=1
            return
        fi
        warn "Attempting to start Docker daemon..."
        maybe_sudo systemctl start docker 2>/dev/null || true
        sleep 3
        if docker info &>/dev/null 2>&1; then
            success "Docker is now running."
            return
        fi
        warn "Docker still not accessible. PSO will install but some features require Docker."
        DOCKER_MISSING=1
        return
    fi

    warn "Docker not found — installing..."
    check_sudo

    case "$OS" in
        debian)
            # Official Docker convenience script
            if command_exists curl; then
                curl -fsSL https://get.docker.com | maybe_sudo bash
            else
                pkg_install ca-certificates curl gnupg lsb-release
                maybe_sudo mkdir -p /etc/apt/keyrings
                curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
                    | maybe_sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
                echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
                    | maybe_sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
                pkg_install docker-ce docker-ce-cli containerd.io docker-compose-plugin
            fi
            # Allow current user to use docker without sudo
            maybe_sudo usermod -aG docker "$USER" 2>/dev/null || true
            maybe_sudo systemctl enable docker --now
            ;;
        arch)
            pkg_install docker docker-compose
            maybe_sudo systemctl enable docker --now
            maybe_sudo usermod -aG docker "$USER" 2>/dev/null || true
            ;;
        macos)
            warn "Docker Desktop for Mac must be installed manually."
            warn "  https://docs.docker.com/desktop/install/mac-install/"
            DOCKER_MISSING=1
            return
            ;;
    esac

    if docker info &>/dev/null 2>&1; then
        success "Docker installed and running: $(docker --version)"
    else
        warn "Docker installed but not yet accessible."
        warn "  You may need to log out and back in for group membership to take effect."
        warn "  Or run: newgrp docker"
        DOCKER_MISSING=1
    fi
}

# ─── Clone / Update repo ──────────────────────────────────────────────────────
install_pso_repo() {
    step "Installing PSO"

    if [[ -d "$PSO_INSTALL_DIR/.git" ]]; then
        info "PSO already cloned at $PSO_INSTALL_DIR — updating..."
        git -C "$PSO_INSTALL_DIR" pull --ff-only || {
            warn "git pull failed (local changes?). Skipping update."
        }
        success "Repository up to date."
    else
        info "Cloning PSO to $PSO_INSTALL_DIR ..."
        mkdir -p "$(dirname "$PSO_INSTALL_DIR")"
        git clone --depth=1 "$PSO_REPO" "$PSO_INSTALL_DIR"
        success "Repository cloned."
    fi
}

# ─── Python virtualenv + deps ─────────────────────────────────────────────────
setup_venv() {
    step "Setting up Python environment"

    local venv_dir="$PSO_INSTALL_DIR/.venv"

    if [[ ! -d "$venv_dir" ]]; then
        info "Creating virtualenv at $venv_dir ..."
        $PYTHON -m venv "$venv_dir"
    else
        info "Virtualenv already exists at $venv_dir"
    fi

    # Upgrade pip silently
    "$venv_dir/bin/pip" install --quiet --upgrade pip

    local req_file="$PSO_INSTALL_DIR/requirements.txt"
    if [[ -f "$req_file" ]]; then
        info "Installing Python dependencies..."
        "$venv_dir/bin/pip" install --quiet -r "$req_file"
        success "Python dependencies installed."
    else
        warn "requirements.txt not found — skipping Python dep install."
    fi
}

# ─── Install CLIs onto PATH ───────────────────────────────────────────────────
install_bins() {
    step "Installing pso and pso-check to $PSO_BIN_DIR"

    mkdir -p "$PSO_BIN_DIR"

    # Write a launcher wrapper for `pso` that activates the venv first
    cat > "$PSO_BIN_DIR/pso" <<EOF
#!/usr/bin/env bash
# PSO launcher — activates the venv then delegates to the real CLI
source "$PSO_INSTALL_DIR/.venv/bin/activate"
exec "$PSO_INSTALL_DIR/pso" "\$@"
EOF
    chmod +x "$PSO_BIN_DIR/pso"

    # Same for pso-check
    cat > "$PSO_BIN_DIR/pso-check" <<EOF
#!/usr/bin/env bash
source "$PSO_INSTALL_DIR/.venv/bin/activate"
exec "$PSO_INSTALL_DIR/pso-check" "\$@"
EOF
    chmod +x "$PSO_BIN_DIR/pso-check"

    success "Launchers written."

    # Ensure ~/.local/bin is on PATH (add to shell RC if missing)
    ensure_path_entry
}

ensure_path_entry() {
    local path_line='export PATH="$HOME/.local/bin:$PATH"'

    # Detect which RC files to update
    local rc_files=()
    [[ -f "$HOME/.bashrc" ]]  && rc_files+=("$HOME/.bashrc")
    [[ -f "$HOME/.zshrc" ]]   && rc_files+=("$HOME/.zshrc")
    [[ -f "$HOME/.profile" ]] && rc_files+=("$HOME/.profile")

    # macOS zsh default
    if [[ "$OS" == "macos" && ${#rc_files[@]} -eq 0 ]]; then
        rc_files+=("$HOME/.zprofile")
    fi

    for rc in "${rc_files[@]}"; do
        if ! grep -qF '.local/bin' "$rc" 2>/dev/null; then
            echo "" >> "$rc"
            echo "# Added by PSO installer" >> "$rc"
            echo "$path_line" >> "$rc"
            info "Added ~/.local/bin to PATH in $rc"
        fi
    done

    # Also export for current shell session
    export PATH="$HOME/.local/bin:$PATH"
}

# ─── Data directory ───────────────────────────────────────────────────────────
setup_data_dir() {
    step "Setting up PSO data directory"
    mkdir -p \
        "$PSO_DATA_DIR/configs" \
        "$PSO_DATA_DIR/backups" \
        "$PSO_DATA_DIR/services" \
        "$PSO_DATA_DIR/proxy" \
        "$PSO_DATA_DIR/logs"
    success "Data directory ready: $PSO_DATA_DIR"
}

# ─── Run pso-check ────────────────────────────────────────────────────────────
run_pso_check() {
    step "Running pso-check"

    local pso_check="$PSO_INSTALL_DIR/pso-check"
    if [[ ! -x "$pso_check" ]]; then
        warn "pso-check not found or not executable at $pso_check — skipping."
        return
    fi

    source "$PSO_INSTALL_DIR/.venv/bin/activate" 2>/dev/null || true

    if "$pso_check"; then
        success "pso-check passed — environment is healthy."
    else
        warn "pso-check reported issues (see above). PSO may still work."
        warn "Run 'pso-check' manually after fixing any reported problems."
    fi
}

# ─── Print next steps ─────────────────────────────────────────────────────────
print_next_steps() {
    local docker_note=""
    if [[ "${DOCKER_MISSING:-0}" -eq 1 ]]; then
        docker_note="
  ${YELLOW}⚠  Docker is not running. Some PSO features require Docker.${RESET}
     Install/start Docker, then run: ${BOLD}pso-check${RESET}
"
    fi

    echo ""
    echo -e "${BOLD}${GREEN}╔══════════════════════════════════════════════╗${RESET}"
    echo -e "${BOLD}${GREEN}║        PSO installed successfully! 🎉        ║${RESET}"
    echo -e "${BOLD}${GREEN}╚══════════════════════════════════════════════╝${RESET}"
    echo ""
    echo -e "${docker_note}"
    echo -e "  ${BOLD}Reload your shell:${RESET}"
    echo -e "    source ~/.bashrc        ${CYAN}# bash${RESET}"
    echo -e "    source ~/.zshrc         ${CYAN}# zsh${RESET}"
    echo ""
    echo -e "  ${BOLD}Verify the installation:${RESET}"
    echo -e "    pso-check"
    echo ""
    echo -e "  ${BOLD}Get started:${RESET}"
    echo -e "    pso help                ${CYAN}# show all commands${RESET}"
    echo -e "    pso service list        ${CYAN}# list available services${RESET}"
    echo -e "    pso service install <name>"
    echo ""
    echo -e "  ${BOLD}Data stored at:${RESET}  $PSO_DATA_DIR"
    echo -e "  ${BOLD}PSO installed at:${RESET} $PSO_INSTALL_DIR"
    echo ""
}

# ─── Main ─────────────────────────────────────────────────────────────────────
main() {
    print_header

    DOCKER_MISSING=0

    detect_os
    info "Detected OS: ${BOLD}$OS${RESET}"

    ensure_git
    ensure_python
    ensure_python_venv
    ensure_docker
    install_pso_repo
    setup_venv
    setup_data_dir
    install_bins
    run_pso_check
    print_next_steps
}

main "$@"