# GitHub Readiness Checklist

## ✅ Ready / ⚠️ Needs Work / ❌ Not Ready

---

## 1. Code Quality & AI Detection

### Current Status: ⚠️ Needs Minor Cleanup

**What needs fixing:**
- [ ] Remove or improve overly verbose docstrings that look AI-generated
- [ ] Simplify some function names (e.g., `_check_port_availability_with_retry` → `_retry_port_check`)
- [ ] Remove placeholder comments like `# TODO` or `# FIXME` (or complete them)
- [ ] Ensure consistent code style across all files

**What's already good:**
- ✅ Code structure is professional and logical
- ✅ No obvious AI patterns (like excessive comments or unnatural variable names)
- ✅ Functions are well-organized and modular

**Action Items:**
```bash
# 1. Run linters
flake8 core/ web/ --max-line-length=120
black core/ web/ --line-length=120

# 2. Remove debug prints
grep -r "print(" core/ web/ | grep -v "logger" | grep -v "#"

# 3. Clean up TODOs
grep -r "TODO\|FIXME\|XXX\|HACK" core/ web/ services/
```

---

## 2. Personal Information Audit

### Current Status: ⚠️ Needs Checking

**Potential locations of personal info:**
- [ ] Git commit author names/emails
- [ ] Database files (`.db` files should be in `.gitignore`)
- [ ] Log files in `.pso_dev/`
- [ ] API keys or tokens in code
- [ ] Hardcoded paths with `/home/apostolos/`
- [ ] Email addresses in manifests or configs

**Scan commands:**
```bash
# Check for personal paths
grep -r "/home/apostolos" --exclude-dir=.git

# Check for email addresses
grep -rE "[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}" --exclude-dir=.git

# Check for potential secrets
grep -riE "(password|secret|key|token).*=.*['\"]" --exclude-dir=.git

# Check git history for sensitive data
git log --all --full-history --source --pretty=format:"%H" -- "*.env" "*.key" "*.pem"
```

**What to add to `.gitignore`:**
```gitignore
# Personal data
*.db
*.sqlite
*.sqlite3
.pso_dev/
*.log

# Secrets
*.env
*.key
*.pem
secrets/
credentials/

# Development
__pycache__/
*.pyc
.pytest_cache/
.coverage
htmlcov/

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Build artifacts
dist/
build/
*.egg-info/
node_modules/
web/static/dist/
```

---

## 3. Cross-Platform Compatibility

### Current Status: ⚠️ Linux-focused, needs macOS/other distros work

**Current Support:**
- ✅ Works on: Arch-based Linux (Manjaro confirmed)
- ⚠️ Should work on: Ubuntu, Debian, Fedora, CentOS
- ❌ Not tested on: macOS, WSL2, other distros

**Platform-specific issues to fix:**

### A. Path Handling
```python
# ISSUE: Using Path.home() is good, but some paths are hardcoded
# FIX: Use cross-platform paths everywhere

# Before:
data_dir = Path.home() / '.pso_dev'
config_file = '/etc/pso/config.yaml'

# After:
import platformdirs

data_dir = Path(platformdirs.user_data_dir('pso', 'pso-app'))
config_dir = Path(platformdirs.user_config_dir('pso', 'pso-app'))

# Linux: ~/.local/share/pso, ~/.config/pso
# macOS: ~/Library/Application Support/pso, ~/Library/Application Support/pso
# Windows: %LOCALAPPDATA%\pso-app\pso
```

### B. Docker Compatibility
```bash
# ISSUE: Docker socket path differs on macOS
# Current: /var/run/docker.sock
# macOS: /var/run/docker.sock (via Docker Desktop)
# Linux: /var/run/docker.sock

# FIX: Already uses docker.from_env() which handles this ✅
```

### C. Package Manager Dependencies
```markdown
# ISSUE: Installation instructions only cover one method
# FIX: Add multi-distro support

**Installation:**

## Arch/Manjaro:
```bash
sudo pacman -S python docker
```

## Ubuntu/Debian:
```bash
sudo apt update
sudo apt install python3 python3-pip docker.io
```

## Fedora/RHEL:
```bash
sudo dnf install python3 docker
```

## macOS:
```bash
brew install python
# Install Docker Desktop from docker.com
```
```

### D. System Service Management
```python
# ISSUE: Uses systemd which isn't universal
# FIX: Detect init system

def get_init_system():
    if Path('/run/systemd/system').exists():
        return 'systemd'
    elif Path('/sbin/launchd').exists():  # macOS
        return 'launchd'
    elif Path('/sbin/init').exists():
        return 'sysvinit'
    return 'unknown'
```

**Action Items:**
- [ ] Add `platformdirs` to requirements.txt
- [ ] Replace hardcoded paths with platformdirs
- [ ] Test on Ubuntu VM
- [ ] Test on macOS (Docker Desktop)
- [ ] Create platform-specific installation guides

---

## 4. Documentation Requirements

### Current Status: ❌ Needs Comprehensive Documentation

**Essential Documentation:**

### A. README.md
```markdown
# PSO - Personal Server OS

> Self-hosted service management platform with local AI, multi-server federation, and compute marketplace

## Features
- 🐳 Docker service management (install, start, stop, monitor)
- 🔒 Built-in authentication and security
- 📊 Real-time monitoring and health checks
- 💾 Automated backups and restoration
- 🎨 Modern web dashboard
- 🔧 50+ pre-configured services

## Quick Start

### Prerequisites
- Python 3.10+
- Docker 20.10+
- 2GB RAM minimum

### Installation
```bash
git clone https://github.com/ApostolosTsampodimos/pso
cd pso
python3 -m pip install -r requirements.txt
python3 -m core.init  # Initialize database and config
python3 -m web.api    # Start dashboard
```

Visit http://localhost:5000

## Documentation
- [Installation Guide](docs/INSTALL.md)
- [User Guide](docs/USER_GUIDE.md)
- [Architecture](docs/ARCHITECTURE.md)
- [Contributing](CONTRIBUTING.md)

## License
MIT License - see LICENSE file

## Roadmap
See [ROADMAP.md](ROADMAP.md)
```

### B. docs/ARCHITECTURE.md
```markdown
# PSO Architecture

## System Overview

```
┌─────────────────────────────────────────┐
│         Web Dashboard (Flask)           │
│  ┌──────────┐  ┌──────────┐            │
│  │  React   │  │   API    │            │
│  │   UI     │  │ Endpoints│            │
│  └──────────┘  └──────────┘            │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│           Core Modules                   │
│  ┌────────────┐  ┌────────────┐        │
│  │  Installer │  │  Database  │        │
│  ├────────────┤  ├────────────┤        │
│  │Service Mgr │  │Health Check│        │
│  ├────────────┤  ├────────────┤        │
│  │  Secrets   │  │  Backups   │        │
│  └────────────┘  └────────────┘        │
└─────────────┬───────────────────────────┘
              │
┌─────────────▼───────────────────────────┐
│         Docker Engine                    │
│  ┌────────┐ ┌────────┐ ┌────────┐      │
│  │Service1│ │Service2│ │Service3│      │
│  └────────┘ └────────┘ └────────┘      │
└──────────────────────────────────────────┘
```

## Component Breakdown

### 1. Web Layer (`web/`)
- **api.py**: Flask REST API endpoints
- **static/**: Frontend assets (React app)

### 2. Core Layer (`core/`)
- **installer.py**: Service installation logic
- **service_manager.py**: Start/stop/restart services
- **database.py**: SQLite data persistence
- **health_monitor.py**: Health checking
- **secrets_manager.py**: Encrypted secrets storage
- **backup_manager.py**: Backup/restore functionality

### 3. Services (`services/`)
- **manifest.json**: Service definitions
- **docker-compose.yml**: Multi-container configs

### 4. Data Storage
- **SQLite**: Service metadata, configurations
- **Docker Volumes**: Persistent service data
- **Encrypted Files**: Secrets and credentials

## Request Flow

1. User clicks "Install Service" in dashboard
2. Frontend → `POST /api/services/{id}/install`
3. API validates auth token
4. Installer loads manifest from `services/{id}/manifest.json`
5. Creates directories, pulls Docker image
6. Generates secrets, starts container
7. Records installation in database
8. Health monitor begins checking service
9. Status updates sent back to frontend

## Security Model

- JWT-based authentication
- bcrypt password hashing
- AES-256 encrypted secrets
- Docker network isolation
- No root required (user-space Docker)
```

### C. docs/INSTALL.md
```markdown
# Installation Guide

## System Requirements

### Minimum
- 2GB RAM
- 10GB disk space
- Python 3.10+
- Docker 20.10+

### Recommended
- 4GB+ RAM
- 50GB+ disk space
- SSD storage

## Step-by-Step Installation

### 1. Install Dependencies

#### Arch Linux / Manjaro
```bash
sudo pacman -S python docker git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in for group changes
```

#### Ubuntu / Debian
```bash
sudo apt update
sudo apt install python3 python3-pip docker.io git
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
# Log out and back in
```

#### macOS
```bash
# Install Homebrew if not already installed
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

brew install python git

# Install Docker Desktop from:
# https://www.docker.com/products/docker-desktop

# Start Docker Desktop application
```

### 2. Clone Repository
```bash
git clone https://github.com/ApostolosTsampodimos/pso.git
cd pso
```

### 3. Install Python Dependencies
```bash
python3 -m pip install -r requirements.txt
```

### 4. Initialize PSO
```bash
# Creates database, default user, directories
python3 -m core.init
```

Default credentials:
- Username: `admin`
- Password: `pso-admin-2026`

**⚠️ Change this immediately after first login!**

### 5. Start Dashboard
```bash
python3 -m web.api
```

Dashboard available at: http://localhost:5000

### 6. (Optional) Run as System Service

#### Linux (systemd)
```bash
sudo cp scripts/pso.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pso
```

#### macOS (launchd)
```bash
cp scripts/com.pso.dashboard.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.pso.dashboard.plist
```

## Troubleshooting

### Docker Permission Denied
```bash
# Add user to docker group
sudo usermod -aG docker $USER
# Log out and back in
```

### Port 5000 Already in Use
```bash
# Change port in web/api.py or set environment variable
export PSO_PORT=8080
python3 -m web.api
```

### Database Initialization Failed
```bash
# Remove corrupted database and reinitialize
rm ~/.pso_dev/pso.db
python3 -m core.init
```
```

### D. docs/USER_GUIDE.md
```markdown
# User Guide

## Getting Started

### First Login
1. Navigate to http://localhost:5000
2. Log in with default credentials:
   - Username: `admin`
   - Password: `pso-admin-2026`
3. **Immediately change password** in Settings

### Dashboard Overview

#### Header
- **Theme Switcher**: Change color theme (Cyber Green, Neon Blue, etc.)
- **Setup Guide**: Initial setup wizard
- **System Metrics**: Resource usage (CPU, RAM, disk)
- **Activity Log**: Recent system events
- **Status Badge**: Overall system health

#### Stats Bar
- **Installed Services**: Count of installed services
- **Running**: Currently active services
- **Available**: Services available to install

#### Service Cards
Each card shows:
- **Category**: Service type (web, database, productivity, etc.)
- **Port Link**: Click to open service (when running)
- **Service Name**: With status indicator (green=running, gray=stopped)
- **Version**: Current installed version
- **Actions**:
  - **▶ Start / ■ Stop**: Control service
  - **⋯ Menu**: Restart, logs, advanced options
  - **Uninstall**: Remove service completely

## Common Tasks

### Installing a Service

1. Find service in "Available to Install" section
2. Click **Install** button
3. Configure if prompted (ports, passwords, etc.)
4. Wait for installation (progress shown in modal)
5. Service auto-starts after installation

**Example: Installing Nginx**
1. Scroll to "nginx" card
2. Click **Install**
3. Confirm port 8080
4. Wait ~30 seconds
5. Click port link `:8080 ↗` to open

### Starting/Stopping Services

**Single Service:**
- Click **▶ Start** or **■ Stop** on service card

**All Services:**
- Use **▶ Start All Stopped** or **■ Stop All Running** buttons

### Viewing Logs

1. Click **⋯** on service card
2. Select **Logs**
3. View real-time logs in modal
4. Filter by log level (Info, Warning, Error)

### Uninstalling Services

1. Click **Uninstall** on service card
2. Type service name to confirm
3. Wait for complete removal
   - Stops container
   - Removes volumes
   - Deletes database entries
   - Cleans up secrets

**⚠️ This cannot be undone! Data will be lost.**

### Backing Up Services

1. Click **⋯** on service card
2. Select **Backups**
3. Click **Create Backup Now**
4. Backup saved to `~/.pso_dev/backups/`

### Restoring from Backup

1. Click **⋯** on service card
2. Select **Backups**
3. Choose backup from list
4. Click **Restore**
5. Service automatically restarted

## Keyboard Shortcuts

- `Ctrl + /`: Focus search
- `Ctrl + R`: Refresh dashboard
- `Esc`: Close modals

## Tips & Best Practices

1. **Regular Backups**: Enable automated backups for important services
2. **Update Services**: Check for updates weekly
3. **Monitor Resources**: Keep an eye on System Metrics
4. **Read Logs**: Logs help diagnose issues
5. **Separate Data**: Keep service data on separate disk if possible

## Troubleshooting

### Service Won't Start
1. Check logs (⋯ → Logs)
2. Verify port not in use: `sudo netstat -tulpn | grep PORT`
3. Check Docker: `docker ps -a`
4. Restart Docker: `sudo systemctl restart docker`

### Dashboard Not Loading
1. Verify API running: `ps aux | grep api.py`
2. Check port 5000: `curl http://localhost:5000/api/health`
3. View API logs: `tail -f ~/.pso_dev/pso.log`

### Installation Fails
1. Check Docker daemon: `docker info`
2. Verify disk space: `df -h`
3. Check internet connection (for image pulls)
4. Review error message in installation modal
```

### E. CONTRIBUTING.md
```markdown
# Contributing to PSO

## Development Setup

1. Fork repository
2. Clone your fork
3. Create feature branch: `git checkout -b feature-name`
4. Install dev dependencies: `pip install -r requirements-dev.txt`
5. Make changes
6. Run tests: `pytest`
7. Commit: `git commit -m "feat: description"`
8. Push: `git push origin feature-name`
9. Create Pull Request

## Code Style

- Follow PEP 8
- Use Black formatter: `black . --line-length=120`
- Type hints encouraged
- Docstrings for public functions

## Adding New Services

1. Create `services/new-service/manifest.json`
2. Follow manifest schema
3. Test installation
4. Add service logo to `web/static/logos/`
5. Document any special configuration

## Running Tests

```bash
# All tests
pytest

# With coverage
pytest --cov=core --cov=web

# Specific test
pytest tests/test_installer.py::test_docker_install
```

## Commit Message Format

```
<type>: <description>

[optional body]
```

Types: feat, fix, docs, style, refactor, test, chore

Examples:
- `feat: add PostgreSQL service`
- `fix: volume path expansion for macOS`
- `docs: update installation guide`
```

---

## 5. Legal & Licensing

### Current Status: ❌ Needs License

**Recommended: MIT License**
```markdown
MIT License

Copyright (c) 2026 PSO Contributors

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

**Why MIT?**
- ✅ Very permissive
- ✅ Allows commercial use
- ✅ Compatible with future marketplace features
- ✅ Most popular for open source tools

---

## 6. Pre-Release Checklist

### Code Quality
- [ ] Run `black .` formatter
- [ ] Run `flake8` linter
- [ ] Run all tests: `pytest`
- [ ] Remove debug print statements
- [ ] Remove or complete all TODOs

### Security
- [ ] Scan for personal information
- [ ] Verify .gitignore includes sensitive files
- [ ] Change default passwords in docs
- [ ] Audit for hardcoded secrets
- [ ] Run `bandit` security scanner

### Documentation
- [ ] Write README.md
- [ ] Write INSTALL.md
- [ ] Write USER_GUIDE.md
- [ ] Write ARCHITECTURE.md
- [ ] Write CONTRIBUTING.md
- [ ] Add LICENSE file

### Cross-Platform
- [ ] Add platformdirs dependency
- [ ] Replace hardcoded paths
- [ ] Test on Ubuntu
- [ ] Test on macOS (or document as untested)
- [ ] Document platform-specific instructions

### Repository Setup
- [ ] Create .gitignore
- [ ] Add issue templates
- [ ] Add PR template
- [ ] Set up CI/CD (GitHub Actions)
- [ ] Add badges to README (build status, license, etc.)

---

## 7. Recommended Pre-Launch Actions

### Week 1: Code Cleanup
```bash
# 1. Format code
black . --line-length=120

# 2. Lint code
flake8 core/ web/ --max-line-length=120

# 3. Security scan
pip install bandit
bandit -r core/ web/

# 4. Remove personal info
grep -r "/home/apostolos" . --exclude-dir=.git
# Replace with Path.home() or platformdirs

# 5. Clean git history (if needed)
git filter-branch --force --index-filter \
  "git rm --cached --ignore-unmatch *.db *.env" \
  --prune-empty --tag-name-filter cat -- --all
```

### Week 2: Documentation
- Write all essential docs (README, INSTALL, USER_GUIDE)
- Create architecture diagrams
- Record demo video or GIFs

### Week 3: Testing
- Test on clean Ubuntu VM
- Test on macOS if possible
- Fix any platform-specific bugs
- Run full test suite

### Week 4: Polish
- Add GitHub repository description
- Create nice README badges
- Set up GitHub Pages for docs (optional)
- Prepare announcement post

---

## 8. Launch Checklist

### Repository
- [ ] Set repository to public
- [ ] Add topics/tags: `docker`, `self-hosted`, `service-management`, `python`, `flask`
- [ ] Set repository description
- [ ] Add website URL
- [ ] Enable issues
- [ ] Enable discussions (optional)

### Marketing (Optional)
- [ ] Post to r/selfhosted
- [ ] Post to Hacker News Show HN
- [ ] Tweet announcement
- [ ] Post to Product Hunt

---

## Estimated Timeline to Release

- **Minimum (basic release)**: 1-2 weeks
- **Recommended (polished release)**: 3-4 weeks
- **Ideal (thoroughly tested)**: 6-8 weeks

## Current Readiness Score: 6/10

**What you have:**
- ✅ Working core functionality
- ✅ Clean architecture
- ✅ Good feature set
- ✅ Roadmap

**What you need:**
- ⚠️ Documentation (most critical)
- ⚠️ Cross-platform testing
- ⚠️ Security audit
- ⚠️ Code cleanup
