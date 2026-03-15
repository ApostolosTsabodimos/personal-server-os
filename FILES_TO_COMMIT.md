# Files to Commit to GitHub

## WILL BE COMMITTED (Project Files)

### Core Application
- `pso` - Main CLI script
- `pso.py` - Python entry point
- `install.sh` - Installation script
- `requirements.txt` - Python dependencies
- `requirements-dev.txt` - Development dependencies
- `LICENSE` - MIT License
- `.gitignore` - Git ignore rules

### Documentation
- `README.md` - Main project readme
- `ROADMAP.md` - Development roadmap
- `GITHUB_CHECKLIST.md` - Publication checklist
- `GITHUB_READINESS.md` - GitHub preparation guide
- `SECURITY_AUDIT_REPORT.md` - Security audit results
- `docs/INSTALL.md` - Installation guide
- `docs/USER_GUIDE.md` - User manual
- `docs/ARCHITECTURE.md` - System architecture
- `docs/REFERENCE.md` - API reference
- `docs/SETUP_GUIDES.md` - Setup guides
- `docs/HANDOFF.md` - Development handoff
- `docs/PROJECT_STATUS.md` - Project status
- `docs/QUICKSTART.md` - Quick start guide

### Core Python Modules (~30 files)
- `core/*.py` - All core modules
- `core/schemas/*.json` - JSON schemas

### Web Dashboard
- `web/api.py` - Flask API backend
- `web/static/app.js` - React frontend
- `web/static/styles.css` - Stylesheets
- `web/static/logos/*.svg` - Service logos

### Services (20+ services)
- `services/*/manifest.json` - Service manifests for:
  - airvpn, docmost, filebrowser, firefly-iii
  - grafana, homeassistant, homer, immich
  - influxdb, jellyfin, mosquitto, nextcloud-aio
  - nginx, pihole, portainer, prowlarr
  - tautulli, trilium, uptime-kuma, vaultwarden
  - zigbee2mqtt

### Scripts
- `scripts/prepare_for_github.sh` - GitHub preparation
- `scripts/update_manifests.py` - Manifest updater
- `scripts/generate_launchd_plist.py` - macOS service

### Tests
- `tests/*.py` - Test files
- `pso-check` - System verification script

---

## WILL NOT BE COMMITTED (Gitignored)

### User Data
- `~/.pso_dev/` - User data directory
- `*.db` - SQLite databases
- `.secrets_key` - Encryption key
- `backups/` - Backup files

### Python
- `__pycache__/` - Python cache
- `*.pyc`, `*.pyo` - Compiled Python
- `.venv/`, `venv/` - Virtual environments
- `web/.venv/` - Web venv

### Logs & Reports
- `*.log` - Log files
- `dashboard.log` - Dashboard logs
- `*_report.txt` - Generated reports
- `pso-check-report.txt` - Check reports

### Temporary Files
- `*.tmp`, `*.temp` - Temporary files
- `*.backup`, `*.old` - Backup files
- `.cache/` - Cache directory
- `.pso_check_tmp/` - Temporary check files

### Environment & Secrets
- `.env`, `.env.local`, `*.env` - Environment files
- `*.pem`, `*.key` - Keys and certificates

### IDE & OS
- `.vscode/`, `.idea/` - IDE settings
- `.DS_Store` - macOS files
- `*.swp`, `*.swo` - Vim swap files

### Claude Code
- `.claude/` - Claude Code settings

---

## File Count Summary

- **Python files**: ~35
- **JSON files**: ~25 (service manifests + schemas)
- **Documentation**: ~15 markdown files
- **Scripts**: ~5 shell/Python scripts
- **Web assets**: 3 (app.js, styles.css, api.py) + logos

**Total files to commit**: ~85-90 files
**Total size**: ~2-3 MB (mostly text)

---

## How to Add Files

```bash
# Add all project files (excluding gitignored)
git add .

# Or add specific categories:
git add core/ services/ web/ docs/
git add README.md LICENSE ROADMAP.md
git add requirements.txt install.sh pso pso.py
git add scripts/ tests/

# Check what will be committed
git status

# Verify no sensitive files
git status | grep -E "(\.env|\.log|\.db|_report\.txt|\.venv)"
# Should return nothing

# Commit
git commit -m "Initial public release - PSO v0.1.0"
```

---

## Before Committing

**Run final check**:
```bash
./scripts/prepare_for_github.sh -o final_check.txt
cat final_check.txt
```

**Verify gitignore**:
```bash
git status --ignored | head -20
# Should show .venv/, *.log, *.db, etc.
```

**Check for secrets**:
```bash
git diff --cached | grep -iE "(password|secret|api_key|token)" || echo "No obvious secrets"
```
