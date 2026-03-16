# PSO Reference Guide

Complete command reference (I think) and technical documentation.

---

## Table of Contents

1. [CLI Commands](#cli-commands)
2. [Port Allocations](#port-allocations)
3. [Database Schema](#database-schema)
4. [API Endpoints](#api-endpoints)
5. [File Structure](#file-structure)
6. [Environment Variables](#environment-variables)

---

## CLI Commands

### Main CLI (`pso`)

**Service Management:**
```bash
pso install <service>           # Install service
pso uninstall <service>         # Uninstall service
pso start <service>             # Start service
pso stop <service>              # Stop service
pso restart <service>           # Restart service
pso list                        # List installed services
pso status <service>            # Check service status
pso logs <service>              # View service logs
```

**Service Catalog:**
```bash
pso catalog                     # Browse all services
pso catalog descriptions        # Show descriptions
pso catalog depends             # Show dependency tree
pso catalog depends <service>   # Show service dependencies
pso catalog search <query>      # Search services
```

**Backup:**
```bash
pso backup create <service> [--note "text"]
pso backup restore <service> <backup-id>
pso backup verify <backup-id>
pso backup list [service]
pso backup prune <service> [--keep N]
pso backup info <backup-id>
```

**Development:**
```bash
pso dev scan                    # Scan and update progress
pso dev tree                    # Show progress tree
pso dev architecture            # Show architecture
pso dev complete <component>    # Mark component complete
```

### Interactive Menu (`pso-menu`)

```bash
pso-menu                        # Launch interactive menu
```

**Menu Structure:**
1. Service Management
2. Service Catalog
3. Firewall & Tiers
4. Health Monitoring
5. User Management
6. Backup Management
7. Development Tools
8. Documentation
9. System Info
0. Exit

### Module CLIs

**Authentication:**
```bash
python -m core.auth list
python -m core.auth register <username> <password> [--admin]
python -m core.auth login <username> <password>
python -m core.auth cleanup
```

**Firewall Manager:**
```bash
python -m core.firewall_manager tiers
python -m core.firewall_manager list
python -m core.firewall_manager status <service>
sudo python -m core.firewall_manager set <service> <tier>
python -m core.firewall_manager history <service>
python -m core.firewall_manager reset-all
```

**Health Monitor:**
```bash
python -m core.health_monitor status
python -m core.health_monitor check <service>
python -m core.health_monitor history <service>
python -m core.health_monitor start
```

**Update Manager:**
```bash
python -m core.update_manager check [service]
python -m core.update_manager update <service> [--no-backup] [--dry-run]
python -m core.update_manager update-all [--dry-run]
python -m core.update_manager history [service] [--limit N]
```

**Reverse Proxy:**
```bash
python -m core.reverse_proxy generate [--domain D] [--email E] [--dry-run]
python -m core.reverse_proxy validate
sudo python -m core.reverse_proxy reload
python -m core.reverse_proxy status
python -m core.reverse_proxy list
python -m core.reverse_proxy install
```

**Rate Limiter:**
```bash
python -m core.rate_limiter blacklist <ip> [--reason "text"]
python -m core.rate_limiter whitelist <ip> [--reason "text"]
python -m core.rate_limiter list-blacklist
python -m core.rate_limiter list-whitelist
python -m core.rate_limiter list-bans
python -m core.rate_limiter violations [--limit N]
python -m core.rate_limiter stats
python -m core.rate_limiter cleanup
```

**Notifications:**
```bash
python -m core.notifications test [--title T] [--message M] [--level L]
python -m core.notifications history [--limit N]
python -m core.notifications clear
```

**Port Manager:**
```bash
python -m core.port_manager                 # Show all allocations
python -m core.port_manager available       # Show available ports
python -m core.port_manager check <port>    # Check specific port
```

**Manifest Validator:**
```bash
python -m core.manifest_validator [service]  # Validate manifest(s)
```

**Dependency Resolver:**
```bash
python -m core.dependency_resolver <service> # Show install plan
```

**Service Recommendations:**
```bash
python -m core.show_recommendations recommended   # Show recommended
python -m core.show_recommendations categories    # By category
python -m core.show_recommendations packs         # Starter packs
python -m core.show_recommendations info <service>
```

---

## Port Allocations

### Port Ranges

| Range | Purpose | Services |
|-------|---------|----------|
| 53 | DNS | pihole |
| 80-443 | Web infrastructure | nginx, caddy, traefik |
| 1883 | MQTT | mosquitto |
| 8000-8099 | Infrastructure | portainer, homer |
| 8100-8199 | Productivity | nextcloud, gitea, paperless-ngx |
| 8200-8299 | Media | jellyfin, immich, prowlarr, tautulli |
| 8300-8399 | Monitoring | grafana, uptime-kuma |
| 8400-8499 | Networking | pihole (web UI) |
| 8500-8599 | Automation | homeassistant, zigbee2mqtt |
| 8086 | Database | influxdb |
| 9000 | Management | portainer |
| 11000+ | High ports | nextcloud-aio |

### Current Allocations

**Infrastructure (80-8099):**
- 80, 443: nginx/caddy/traefik (only one active)
- 8000: portainer (edge agent)
- 8081: homer
- 9000: portainer (main UI)

**Productivity (8100-8199):**
- 8082: firefly-iii
- 8090: nextcloud-aio (admin)
- 8100: gitea
- 8101: memos
- 8102: paperless-ngx
- 11000: nextcloud-aio (main)

**Media (8200-8299):**
- 8200: jellyfin
- 8201: tautulli
- 8202: prowlarr
- 8203: immich

**Monitoring (8300-8399):**
- 8300: grafana
- 8301: uptime-kuma

**Networking (8400-8499):**
- 8400: pihole (web UI)

**Automation (8500-8599):**
- 8123: homeassistant
- 8580: zigbee2mqtt

**Special:**
- 53: pihole (DNS)
- 1883: mosquitto (MQTT)
- 8086: influxdb
- 5000: PSO Dashboard

### Checking Ports

```bash
# Check if port is in use
sudo netstat -tuln | grep <port>
sudo ss -tuln | grep <port>

# Kill process using port
sudo fuser -k <port>/tcp

# Check PSO allocations
python -m core.port_manager
python -m core.port_manager check <port>
```

---

## Database Schema

**Location:** `/var/pso/pso.db` (SQLite)

### Core Tables

**installed_services**
```sql
service_id TEXT PRIMARY KEY
service_name TEXT
status TEXT
installed_at TEXT
version TEXT
```

**service_ports**
```sql
service_id TEXT
port_name TEXT
port_number INTEGER
FOREIGN KEY (service_id) REFERENCES installed_services
```

**service_volumes**
```sql
service_id TEXT
host_path TEXT
container_path TEXT
volume_type TEXT
FOREIGN KEY (service_id) REFERENCES installed_services
```

**service_dependencies**
```sql
service_id TEXT
dependency_id TEXT
dependency_type TEXT
FOREIGN KEY (service_id) REFERENCES installed_services
```

**installation_history**
```sql
id INTEGER PRIMARY KEY
service_id TEXT
action TEXT
timestamp TEXT
status TEXT
error_message TEXT
```

### Auth Tables

**users**
```sql
id INTEGER PRIMARY KEY
username TEXT UNIQUE
password_hash TEXT
email TEXT
full_name TEXT
is_admin INTEGER
created_at TEXT
```

**sessions**
```sql
id INTEGER PRIMARY KEY
user_id INTEGER
token TEXT UNIQUE
created_at TEXT
expires_at TEXT
FOREIGN KEY (user_id) REFERENCES users
```

### Health Tables

**health_checks**
```sql
id INTEGER PRIMARY KEY
service_id TEXT
status TEXT
response_time REAL
error TEXT
timestamp TEXT
```

**service_health**
```sql
service_id TEXT PRIMARY KEY
current_status TEXT
last_check TEXT
consecutive_failures INTEGER
total_checks INTEGER
successful_checks INTEGER
uptime_percentage REAL
```

**uptime_tracking**
```sql
id INTEGER PRIMARY KEY
service_id TEXT
status TEXT
started_at TEXT
ended_at TEXT
duration_seconds INTEGER
```

### Firewall Tables

**service_tiers**
```sql
service_id TEXT PRIMARY KEY
current_tier INTEGER DEFAULT 0
previous_tier INTEGER
changed_at TEXT
changed_by TEXT
FOREIGN KEY (service_id) REFERENCES installed_services
```

**tier_change_log**
```sql
id INTEGER PRIMARY KEY
service_id TEXT
from_tier INTEGER
to_tier INTEGER
changed_at TEXT
changed_by TEXT
reason TEXT
```

### Backup Tables

**backups**
```sql
backup_id TEXT PRIMARY KEY
service_id TEXT
backup_path TEXT
created_at TEXT
size_bytes INTEGER
checksum TEXT
note TEXT
FOREIGN KEY (service_id) REFERENCES installed_services
```

### Rate Limiter Tables

**ip_blacklist**
```sql
ip_address TEXT PRIMARY KEY
reason TEXT
banned_at TEXT
banned_by TEXT DEFAULT 'system'
```

**ip_whitelist**
```sql
ip_address TEXT PRIMARY KEY
reason TEXT
added_at TEXT
added_by TEXT DEFAULT 'system'
```

**temp_bans**
```sql
ip_address TEXT PRIMARY KEY
service_id TEXT
reason TEXT
banned_at TEXT
expires_at TEXT
ban_count INTEGER DEFAULT 1
```

**rate_limit_violations**
```sql
id INTEGER PRIMARY KEY
ip_address TEXT
service_id TEXT
endpoint TEXT
violation_time TEXT
request_count INTEGER
action_taken TEXT
```

---

## API Endpoints

**Base URL:** http://localhost:5000

### Public Endpoints

**POST /api/auth/login**
```json
Request: {"username": "admin", "password": "pass", "remember_me": false}
Response: {"user": {...}, "token": "...", "expires_at": "..."}
```

### Protected Endpoints (Require Authorization Header)

**Header:** `Authorization: Bearer <token>`

**Services:**
```
GET    /api/services                    # List all services
GET    /api/services/<id>               # Get service details
POST   /api/services/<id>/install       # Install service
POST   /api/services/<id>/start         # Start service
POST   /api/services/<id>/stop          # Stop service
POST   /api/services/<id>/restart       # Restart service
POST   /api/services/<id>/uninstall     # Uninstall service
GET    /api/services/<id>/logs          # Get logs (basic)
GET    /api/services/<id>/logs/enhanced # Get filtered logs
```

**Health:**
```
GET    /api/health                      # All service health
GET    /api/health/<id>                 # Service health
GET    /api/health/<id>/history         # Health history
POST   /api/health/<id>/check           # Trigger check
```

**Updates:**
```
GET    /api/services/<id>/check-update  # Check for updates
POST   /api/services/<id>/update        # Apply update
```

**Backups:**
```
GET    /api/services/<id>/backups       # List backups
POST   /api/services/<id>/backup        # Create backup
POST   /api/services/<id>/restore       # Restore backup
```

**Metrics:**
```
GET    /api/services/<id>/metrics       # Service metrics
```

**System:**
```
GET    /api/system/stats                # System statistics
GET    /api/ports                       # Port allocations
```

**Tiers:**
```
GET    /api/tiers                       # All tier definitions
GET    /api/tiers/services              # All service tiers
GET    /api/services/<id>/tier          # Service tier
POST   /api/services/<id>/tier          # Change tier
GET    /api/services/<id>/tier/history  # Tier history
POST   /api/tiers/reset-all             # Emergency reset
```

**Auth:**
```
POST   /api/auth/logout                 # Logout
GET    /api/auth/validate               # Validate token
POST   /api/auth/register               # Register user (admin only)
```

---

## File Structure

```
personal-server-os/
├── pso                          # Main CLI (bash)
├── pso-menu                     # Interactive menu (bash)
├── pso.py                       # Dev tracker (python)
├── requirements.txt             # Python dependencies
├── .gitignore                   # Git ignore patterns
│
├── core/                        # Python modules
│   ├── __init__.py
│   ├── auth.py                  # Authentication (500 lines)
│   ├── backup_manager.py        # Backups (600 lines)
│   ├── config_manager.py        # Config management (500 lines)
│   ├── database.py              # Database layer (450 lines)
│   ├── dependency_resolver.py   # Dependencies (250 lines)
│   ├── firewall_manager.py      # Firewall/tiers (650 lines)
│   ├── health_monitor.py        # Health checks (450 lines)
│   ├── installer.py             # Installation (480 lines)
│   ├── manifest.py              # Manifest loader (350 lines)
│   ├── manifest_validator.py    # Validation (150 lines)
│   ├── notifications.py         # Notifications (500 lines)
│   ├── port_manager.py          # Port allocation (250 lines)
│   ├── rate_limiter.py          # Rate limiting (600 lines)
│   ├── reverse_proxy.py         # Proxy manager (500 lines)
│   ├── service_manager.py       # Service control (460 lines)
│   ├── service_recommendations.py # Recommendations (250 lines)
│   ├── show_recommendations.py  # CLI wrapper (150 lines)
│   ├── update_manager.py        # Updates (550 lines)
│   └── schemas/
│       └── manifest_v1.schema.json
│
├── web/                         # Dashboard
│   ├── api.py                   # Flask API (961 lines)
│   ├── requirements-web.txt     # Web dependencies
│   └── static/
│       ├── index.html           # Dashboard UI
│       ├── app.js               # React app (1611 lines)
│       ├── styles.css           # Styles (1706 lines)
│       └── login.html           # Login page
│
├── services/                    # Service manifests
│   ├── nginx/manifest.json
│   ├── jellyfin/manifest.json
│   └── ... (21 services)
│
├── systemd/                     # Service files
│   └── pso-health-monitor.service
│
└── docs/                        # Documentation
    ├── INSTALL.md
    ├── USER_GUIDE.md
    ├── REFERENCE.md
    └── ARCHITECTURE.md
```

---

## Environment Variables

### PSO Configuration

```bash
# Database location (default: /var/pso/pso.db)
export PSO_DB_PATH="/custom/path/pso.db"

# Services directory (default: ./services)
export PSO_SERVICES_DIR="/custom/services"

# Backup directory (default: /var/pso/backups)
export PSO_BACKUP_DIR="/custom/backups"

# Log level (default: INFO)
export PSO_LOG_LEVEL="DEBUG"
```

### API Configuration

```bash
# API host (default: 0.0.0.0)
export PSO_API_HOST="127.0.0.1"

# API port (default: 5000)
export PSO_API_PORT="8080"

# JWT secret key
export PSO_JWT_SECRET="your-secret-key"
```

### Service-Specific

Set in service manifest `environment` section:
```json
"environment": {
  "TZ": "America/New_York",
  "PUID": "1000",
  "PGID": "1000"
}
```

---

## Security Tiers and Onions

| Tier | Name | Binding | Access | Risk |
|------|------|---------|--------|------|
| 0 | Internal Only | 127.0.0.1 | Localhost | 🟢 Minimal |
| 1 | LAN Only | 0.0.0.0 | Home network | 🟡 Low |
| 2 | VPN Access | 0.0.0.0 | VPN clients | 🔵 Medium |
| 3 | Internet Exposed | 0.0.0.0 | Public internet | 🔴 High |

**Firewall Rules:**
- Tier 0: No rules (not network-accessible)
- Tier 1: ACCEPT from LAN subnet, DROP others
- Tier 2: ACCEPT from VPN interface, DROP others
- Tier 3: Rate-limited ACCEPT (100 req/min per IP)

---

## Service Categories

- **infrastructure:** nginx, portainer, homer
- **productivity:** nextcloud, gitea, paperless-ngx, filebrowser
- **media:** jellyfin, immich, prowlarr, tautulli
- **security:** vaultwarden
- **monitoring:** grafana, uptime-kuma, influxdb
- **networking:** pihole
- **automation:** homeassistant, zigbee2mqtt, mosquitto

---

## Dependencies

**Python (requirements.txt):**
```
flask
flask-cors
docker
PyJWT
bcrypt
jsonschema
```

**System:**
- Docker & Docker Compose
- Python 3.8+
- iptables
- SQLite (built-in)
- libnotify (Linux, for notifications)

---

## File Locations

```
/var/pso/                        # PSO data directory
├── pso.db                       # SQLite database
├── backups/                     # Service backups
├── services/                    # Service data
│   ├── nginx/
│   └── jellyfin/
├── proxy/                       # Reverse proxy config
│   └── Caddyfile
└── logs/                        # PSO logs

~/.pso_dev/                      # Development tracking
└── data.json

~/personal-server-os/            # Project directory
```
