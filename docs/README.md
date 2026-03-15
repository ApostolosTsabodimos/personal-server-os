# Personal Server OS (PSO)

**Secure, tier-based service management for self-hosting**

> "Secure by Default, Explicit by Choice"

---

## What is PSO?

PSO is a **complete service management platform** that makes self-hosting easy and secure. Install services with a single command, manage them through a beautiful dashboard, and control access with a tier-based security system.

**Core Features:**
- ✅ **One-command installation** - `./pso install jellyfin`
- ✅ **Tier-based security** - Services default to localhost-only
- ✅ **Beautiful dashboard** - React UI with real-time updates
- ✅ **Health monitoring** - Auto-restart failed services
- ✅ **Backup/restore** - One-click backups with integrity checks
- ✅ **Update manager** - Check and apply updates safely
- ✅ **21 services ready** - Media, productivity, security, more

---

## Quick Start

### Install PSO

```bash
# Clone repository
cd ~
git clone <your-repo> personal-server-os
cd personal-server-os

# Install dependencies
pip install flask flask-cors docker PyJWT bcrypt jsonschema --break-system-packages

# Make scripts executable
chmod +x pso pso-menu pso.py

# Initialize database
python3 -c "from core.database import Database; from core.port_manager import PortManager; Database(); PortManager()"
```

### Start Dashboard

```bash
cd web
python api.py

# Open: http://localhost:5000
# Login: admin / pso-admin-2026
```

### Install Your First Service

```bash
# CLI
./pso install portainer

# Or use interactive menu
./pso-menu
```

**That's it!** Your service is running and accessible at localhost.

---

## Security Tiers

PSO uses a **4-tier security model** to prevent accidental exposure:

| Tier | Name | Access | Use Case |
|------|------|--------|----------|
| 🟢 **0** | Internal Only | Localhost | Databases, internal tools (DEFAULT) |
| 🟡 **1** | LAN Only | Home network | Family services (Jellyfin, Nextcloud) |
| 🔵 **2** | VPN Access | VPN clients | Remote access while traveling |
| 🔴 **3** | Internet | Public | Public websites (requires confirmation) |

**All services start at Tier 0** - the most secure. Promote only when needed.

```bash
# Promote Jellyfin to LAN access
sudo python -m core.firewall_manager set jellyfin 1
./pso restart jellyfin

# Now accessible on home network: http://192.168.x.x:8200
```

---

## Available Services (21)

**Infrastructure:**
nginx, portainer, homer

**Productivity:**
nextcloud, gitea, paperless-ngx, filebrowser, docmost, trilium, firefly-iii

**Security:**
vaultwarden

**Media:**
jellyfin, immich, prowlarr, tautulli

**Monitoring:**
grafana, uptime-kuma, influxdb

**Networking:**
pihole

**Automation:**
homeassistant, zigbee2mqtt, mosquitto

---

## Key Features

### Dashboard
- **Service cards** - Visual status for all services
- **Health monitoring** - Real-time health checks
- **Enhanced logs** - Filtered, color-coded log viewer
- **Update manager** - Check and apply updates with auto-backup
- **Backup manager** - Create/restore backups with one click
- **System overview** - Running services, health, uptime, disk usage

### Security
- **Authentication** - JWT-based login system
- **Tier-based firewall** - iptables integration
- **Rate limiting** - DDoS protection and IP banning
- **Audit logging** - Track all security changes

### Automation
- **Health checks** - Background monitoring every 30s
- **Auto-restart** - Restart failed services automatically
- **Desktop notifications** - Popups for events
- **Backup scheduling** - Automated daily backups

---

## Documentation

### Getting Started
- **[QUICKSTART.md](QUICKSTART.md)** - Get running in 15 minutes
- **[PROJECT_STATUS.md](PROJECT_STATUS.md)** - Current state and progress

### Guides
- **[SETUP_GUIDES.md](SETUP_GUIDES.md)** - Complete setup for all features
  - Authentication
  - Firewall & Tiers
  - Health Monitoring
  - Backup System
  - Update Manager
  - Reverse Proxy
  - Rate Limiting
  - Notifications

### Reference
- **[REFERENCE.md](REFERENCE.md)** - Complete command reference
  - All CLI commands
  - Port allocations
  - Database schema
  - API endpoints
  - File structure

### Architecture
- **[ARCHITECTURE.md](ARCHITECTURE.md)** - System design
  - Tier-based security
  - Service lifecycle
  - Component interactions
  - Database design
  - Security model

---

## Common Commands

```bash
# Service management
./pso install <service>     # Install service
./pso start <service>       # Start service
./pso stop <service>        # Stop service
./pso list                  # List all services
./pso status <service>      # Check status

# Interactive menu
./pso-menu                  # Full UI with navigation

# Service discovery
./pso catalog               # Browse available services
./pso catalog search web    # Search for services

# Backups
./pso backup create <service>           # Create backup
./pso backup restore <service> <id>     # Restore backup
./pso backup list <service>             # List backups

# Security tiers
python -m core.firewall_manager list              # Show all tiers
sudo python -m core.firewall_manager set <svc> 1  # Change tier

# Health monitoring
python -m core.health_monitor status              # Check all health
python -m core.health_monitor check <service>     # Check one service
```

---

## Example Workflows

### Media Server Setup

```bash
# 1. Install Jellyfin
./pso install jellyfin

# 2. Promote to LAN for family access
sudo python -m core.firewall_manager set jellyfin 1
./pso restart jellyfin

# 3. Access from any device
# http://your-server-ip:8200

# 4. Set up automatic backups
crontab -e
# Add: 0 2 * * * cd ~/personal-server-os && ./pso backup create jellyfin
```

### Password Manager (Secure)

```bash
# 1. Install Vaultwarden
./pso install vaultwarden

# 2. Keep at Tier 0 (localhost only)
# Access via SSH tunnel: ssh -L 8000:localhost:8000 user@server

# 3. Or promote to VPN access for travel
sudo python -m core.firewall_manager set vaultwarden 2
./pso restart vaultwarden
```

### Home Automation

```bash
# 1. Install Home Assistant
./pso install homeassistant

# 2. LAN access for phones/tablets
sudo python -m core.firewall_manager set homeassistant 1
./pso restart homeassistant

# 3. Access at http://your-server-ip:8123
```

---

## Dashboard Screenshots

**Login:**
- Clean authentication page
- Remember me option
- JWT token-based sessions

**Service Cards:**
- Visual status indicators
- Health status badges
- Tier badges (🟢 🟡 🔵 🔴)
- Quick action buttons (Stop, Restart, Logs, Advanced, Updates, Backups)

**Enhanced Log Viewer:**
- Real-time log streaming
- Filter by level (Error, Warning, Info)
- Auto-scroll
- Color-coded output

**Update Manager:**
- Current vs. latest version
- One-click updates
- Auto-backup before update
- Update history

**Backup Manager:**
- List all backups
- Create backup with notes
- Restore from any backup
- Integrity verification

**System Overview:**
- Services running count
- Healthy services count
- System uptime
- Disk usage

---

## System Requirements

**Minimum:**
- Linux (Manjaro, Arch, Ubuntu, Debian)
- Docker installed
- Python 3.8+
- 1GB RAM
- 10GB disk space

**Recommended:**
- 4GB+ RAM
- 50GB+ disk space
- SSD for better performance

---

## Project Status

**Progress:** 55% (18-19 of 33 components complete)

**Complete:**
- ✅ Core system (installation, management, database)
- ✅ Dashboard (React UI with authentication)
- ✅ Security (tiers, firewall, rate limiting)
- ✅ Monitoring (health checks, notifications)
- ✅ Backup/restore system
- ✅ Update manager

**In Progress:**
- ⏳ Reverse proxy (coded, needs testing)
- ⏳ Metrics collection
- ⏳ RBAC system

**Planned:**
- 📋 AI assistant
- 📋 Mobile app
- 📋 Cloud backup

See [PROJECT_STATUS.md](PROJECT_STATUS.md) for details.

---

## Architecture Highlights

### Tier-Based Security
Services start at Tier 0 (localhost only) and must be explicitly promoted:
```
Tier 0 (127.0.0.1) → Tier 1 (LAN) → Tier 2 (VPN) → Tier 3 (Internet)
```

### Service Lifecycle
```
Manifest → Dependencies → Installation → Running → Monitoring
                                       ↓
                            Firewall Rules (Tier-based)
                                       ↓
                            Health Checks (Auto-restart)
                                       ↓
                            Backups & Updates
```

### Component Interaction
```
CLI/Menu/Dashboard → API (Flask) → Core Modules → Docker/iptables/DB
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for complete design.

---

## Contributing

PSO is designed to be extensible:

**Add a new service:**
1. Create `services/<service>/manifest.json`
2. Define Docker image, ports, volumes
3. Test: `./pso install <service>`

**Add a new feature:**
1. Create module in `core/`
2. Add API endpoint in `web/api.py`
3. Update dashboard UI in `web/static/app.js`

See architecture docs for extension points.

---

## Troubleshooting

**Dashboard not loading?**
```bash
cd web && python api.py
```

**Service won't install?**
```bash
sudo fuser -k <port>/tcp  # Free port
./pso install <service>
```

**Can't see new features?**
- Clear browser cache (Ctrl+Shift+Delete)
- Or use incognito window

**Database errors?**
```bash
python3 -c "from core.database import Database; Database()"
```

See [QUICKSTART.md](QUICKSTART.md) for more.

---

## Security

**Default credentials:**
- Username: `admin`
- Password: `pso-admin-2026`
- **⚠️ CHANGE IMMEDIATELY**

**Security checklist:**
- [ ] Change default password
- [ ] Review service tiers
- [ ] Enable firewall
- [ ] Set up VPN (for Tier 2)
- [ ] Configure SSL (for Tier 3)
- [ ] Enable automatic backups

---

## File Structure

```
personal-server-os/
├── pso                 # Main CLI
├── pso-menu           # Interactive menu
├── core/              # Python modules (19 files)
├── web/               # Dashboard (React + Flask)
├── services/          # Service manifests (21 services)
├── systemd/           # Service files
└── docs/              # Documentation
    ├── QUICKSTART.md
    ├── PROJECT_STATUS.md
    ├── SETUP_GUIDES.md
    ├── REFERENCE.md
    └── ARCHITECTURE.md
```

---

## License

[Your License Here]

---

## Links

- **Documentation:** See docs/ folder
- **Issues:** [Your issue tracker]
- **Discussions:** [Your discussions]

---

**Built with ❤️ for the self-hosting community**

PSO makes self-hosting accessible to everyone while keeping security front and center.