# PSO Architecture

System architecture and design documentation.

---

## Overview

PSO (Personal Server OS) is a **tier-based service management platform - The way of the onion** that makes self-hosting secure by default while allowing controlled access when needed.

**Core Principle:** "Secure by Default, Explicit by Choice"

---

## Current System Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                         User Interfaces                      │
├──────────────┬──────────────────┬──────────────────────────┤
│  CLI (pso)   │  Menu (pso-menu) │  Dashboard (web/React)  │
└──────┬───────┴────────┬─────────┴────────────┬─────────────┘
       │                │                      │
       └────────────────┼──────────────────────┘
                        │
         ┌──────────────▼──────────────┐
         │      Flask API (web/api.py)  │
         │    - REST endpoints          │
         │    - JWT authentication      │
         │    - CORS enabled            │
         └──────────────┬──────────────┘
                        │
         ┌──────────────▼──────────────────────────┐
         │           Core Modules (core/)          │
         ├─────────────────────────────────────────┤
         │  Service Management │  Security         │
         │  - installer        │  - auth           │
         │  - service_manager  │  - firewall_mgr   │
         │  - manifest         │  - rate_limiter   │
         │  - dependency       │                   │
         │                     │                   │
         │  Data & Config      │  Monitoring       │
         │  - database         │  - health_monitor │
         │  - port_manager     │  - notifications  │
         │  - config_manager   │                   │
         │  - backup_manager   │                   │
         │  - update_manager   │                   │
         │                     │                   │
         │  Infrastructure     │                   │
         │  - reverse_proxy    │                   │
         └─────────┬───────────┴───────────────────┘
                   │
         ┌─────────▼──────────────┐
         │   SQLite Database      │
         │   (/var/pso/pso.db)    │
         └─────────┬──────────────┘
                   │
         ┌─────────▼──────────────────────────┐
         │      External Systems              │
         ├────────────────────────────────────┤
         │  Docker Engine  │  iptables        │
         │  Caddy Proxy    │  File System     │
         │  systemd        │  Notification    │
         └────────────────────────────────────┘
```

---

## Tier-Based Security System

### Architecture

```
Service Installation
       │
       ▼
Default: Tier 0 (127.0.0.1) ◄─── MOST SECURE?
       │
       ▼ User promotes tier
       │
Tier 1: LAN (0.0.0.0 + firewall)
       │
       ▼ User promotes tier
       │
Tier 2: VPN (0.0.0.0 + VPN firewall)
       │
       ▼ User confirms (explicit)
       │
Tier 3: Internet (0.0.0.0 + rate limiting)
```

### Implementation

**1. Service Installation:**
```python
# installer.py
def install(service_id):
    manifest = loader.load(service_id)
    # Install Docker container at 127.0.0.1 (Tier 0)
    # Record in database with tier=0
    firewall_mgr.set_service_tier(service_id, 0)
```

**2. Tier Promotion:**
```python
# firewall_manager.py
def set_service_tier(service_id, tier):
    # 1. Validate tier
    # 2. Get service ports
    # 3. Apply iptables rules
    # 4. Update database
    # 5. Log change to audit trail
    # 6. Trigger service restart (rebind ports)
```

**3. Firewall Rules:**
```bash
# Tier 0: No rules (127.0.0.1 not network-accessible)

# Tier 1: LAN only
iptables -A PSO_nginx_8080 -s 192.168.0.0/16 -p tcp --dport 8080 -j ACCEPT
iptables -A PSO_nginx_8080 -p tcp --dport 8080 -j DROP

# Tier 2: VPN only
iptables -A PSO_jellyfin_8096 -i tailscale0 -p tcp --dport 8096 -j ACCEPT
iptables -A PSO_jellyfin_8096 -p tcp --dport 8096 -j DROP

# Tier 3: Rate-limited internet
iptables -A PSO_web_80 -m recent --set
iptables -A PSO_web_80 -m recent --update --seconds 60 --hitcount 100 -j DROP
iptables -A PSO_web_80 -j ACCEPT
```

---

## Service Lifecycle

```
┌──────────────┐
│   Manifest   │  service_id/manifest.json
│  Definition  │  - Docker image, ports, volumes
└──────┬───────┘  - Health check, dependencies
       │          - Tier recommendations
       ▼
┌──────────────┐
│ Dependency   │  dependency_resolver.py
│  Resolution  │  - Check required services
└──────┬───────┘  - Detect conflicts
       │          - Plan install order
       ▼
┌──────────────┐
│ Installation │  installer.py
│   Process    │  - Pull Docker image
└──────┬───────┘  - Create volumes/networks
       │          - Set environment
       │          - Bind to 127.0.0.1 (Tier 0)
       │          - Record to database
       ▼
┌──────────────┐
│   Running    │  service_manager.py
│   Service    │  - Start/stop/restart
└──────┬───────┘  - View logs
       │          - Check status
       │
       ├──────────────────────────────┐
       │                              │
       ▼                              ▼
┌──────────────┐              ┌──────────────┐
│    Health    │              │  Tier-Based  │
│  Monitoring  │              │   Access     │
└──────┬───────┘              └──────┬───────┘
       │                             │
       │ health_monitor.py           │ firewall_manager.py
       │ - HTTP/TCP checks           │ - iptables rules
       │ - Auto-restart              │ - Port binding
       │ - Uptime tracking           │ - Audit logging
       │                             │
       ▼                             ▼
┌──────────────┐              ┌──────────────┐
│  Backups &   │              │   Reverse    │
│   Updates    │              │    Proxy     │
└──────┬───────┘              └──────┬───────┘
       │                             │
       │ backup_manager.py           │ reverse_proxy.py
       │ update_manager.py           │ - Caddy config
       │                             │ - SSL/TLS
       │                             │ - Subdomain routing
       ▼
┌──────────────┐
│ Uninstall    │  installer.py
│   Process    │  - Stop service
└──────────────┘  - Remove container
                  - Clean volumes
                  - Update database
                  - Remove firewall rules
```

---

## Database Design

### Entity Relationships

```
┌──────────────────┐
│ installed_       │
│   services       │◄───────┐
└────────┬─────────┘        │
         │                  │
         │ 1:N              │
         │                  │ FOREIGN KEY
    ┌────▼─────┬────────────┴─────┬───────────┬──────────────┐
    │          │                  │           │              │
┌───▼────┐  ┌──▼─────┐  ┌────────▼─────┐  ┌──▼────┐  ┌─────▼──────┐
│service_│  │service_│  │installation_ │  │service│  │   backups  │
│ ports  │  │volumes │  │   history    │  │_tiers │  │            │
└────────┘  └────────┘  └──────────────┘  └───┬───┘  └────────────┘
                                              │
                                              │ 1:N
                                              │
                                         ┌────▼─────────┐
                                         │tier_change_  │
                                         │     log      │
                                         └──────────────┘

┌──────────┐
│  users   │◄───────┐
└────┬─────┘        │
     │              │ FOREIGN KEY
     │ 1:N          │
     │              │
  ┌──▼──────┐  ┌────┴─────┐
  │sessions │  │tier_     │
  │         │  │change_log│
  └─────────┘  └──────────┘

┌──────────────┐
│ service_     │
│   health     │
└──────┬───────┘
       │
       │ 1:N
       │
  ┌────▼────────────┬─────────────┐
  │                 │             │
┌─▼────────┐  ┌─────▼────────┐  ┌─▼─────────┐
│health_   │  │uptime_       │  │           │
│checks    │  │tracking      │  │           │
└──────────┘  └──────────────┘  └───────────┘
```

### Normalization

- **Services:** Core entity, referenced by all other tables
- **Ports/Volumes:** 1:N relationship with services
- **History:** Temporal data, append-only logs
- **Health:** Time-series data, periodic cleanup
- **Tiers:** Current state + audit trail

---

## Component Interactions

### Installation Flow

```
User: ./pso install nginx
       │
       ▼
CLI: pso (bash)
       │ Calls Python
       ▼
Dependency Resolver
       │ Checks manifest
       │ Resolves dependencies
       ▼
Installer
       │ Validates
       │ Pulls image
       │ Creates container
       │ Binds to 127.0.0.1
       ▼
Database
       │ Records installation
       │ Tracks ports
       ▼
Firewall Manager
       │ Sets tier to 0
       │ (No rules needed)
       ▼
Service Manager
       │ Starts service
       ▼
Health Monitor
       │ Registers for checks
       │ Starts monitoring
       ▼
Done 
```

### Tier Change Flow

```
User: firewall_manager set nginx 1
       │
       ▼
Firewall Manager
       │ Validates tier
       │ Checks if Tier 3 → confirm
       ▼
Database
       │ Log tier change
       │ Update current_tier
       ▼
iptables
       │ Create chain PSO_nginx_8080
       │ Add LAN accept rule
       │ Add drop rule
       │ Jump from INPUT
       ▼
Service Manager
       │ Restart service
       │ Rebind to 0.0.0.0
       ▼
Notification
       │ Desktop popup
       │ "Tier changed to LAN"
       ▼
Done
```

### Health Check Flow

```
Health Monitor (background thread)
       │ Every 30 seconds
       ▼
For each installed service:
       │
       ▼
Check Docker status
       │ docker ps
       ▼
Check HTTP endpoint (if configured)
       │ curl health endpoint
       ▼
Record result
       │ Database: health_checks
       │ Update: service_health
       ▼
If unhealthy (3+ failures):
       │
       ▼
Auto-restart (if enabled)
       │ service_manager.restart()
       ▼
Notification
       │ Desktop popup
       │ "Service restarted"
       ▼
Continue monitoring
```

---

## API Architecture

### Request Flow

```
Browser/CLI
    │ HTTP Request
    │ Authorization: Bearer <token>
    ▼
Flask API (api.py)
    │
    ▼
@app.before_request
    │ Extract token
    │ Validate JWT
    │ Check expiration
    │ Load user
    ▼
Route Handler
    │ /api/services/<id>/start
    ▼
Core Module
    │ service_manager.start(id)
    ▼
Docker
    │ docker start pso-<id>
    ▼
Database
    │ Update status
    ▼
Response
    │ {"success": true}
    ▼
Browser/CLI
```

### Authentication Flow

```
Login Page
    │ POST /api/auth/login
    │ {username, password, remember_me}
    ▼
Auth Module
    │ Hash password
    │ Compare with stored hash
    ▼
JWT Generation
    │ Create token with user ID
    │ Set expiration (24h or 30d)
    │ Sign with secret key
    ▼
Session Record
    │ Store in sessions table
    │ For revocation
    ▼
Response
    │ {user: {...}, token: "...", expires_at: "..."}
    ▼
Browser
    │ Store in localStorage
    │ Add to all requests
```

---

## File System Layout

```
/var/pso/
├── pso.db                      # SQLite database
├── services/                   # Service data
│   ├── nginx/
│   │   ├── config/
│   │   └── data/
│   └── jellyfin/
│       ├── config/
│       ├── cache/
│       └── media/
├── backups/                    # Compressed backups
│   ├── nginx_20260203_143022.tar.gz
│   ├── nginx_20260203_143022.json  # Metadata
│   └── jellyfin_20260202_020000.tar.gz
├── proxy/                      # Reverse proxy config
│   ├── Caddyfile
│   └── Caddyfile.backup
└── logs/                       # PSO logs
    └── proxy/
        ├── nginx.log
        └── jellyfin.log
```

---

## Security Design - The way of the onion

### Defense in Depth

**Layer 1: Default Deny**
- All services start at Tier 0 (127.0.0.1)
- Not network-accessible by default

**Layer 2: Explicit Promotion**
- User must actively promote tier
- Tier 3 requires confirmation

**Layer 3: Firewall Rules**
- iptables enforces access control
- Default DROP policy

**Layer 4: Rate Limiting**
- Per-IP request limits
- Automatic banning

**Layer 5: Authentication**
- JWT tokens for API
- Password hashing (bcrypt)
- Session tracking

**Layer 6: Audit Logging**
- All tier changes logged
- Rate limit violations tracked
- Installation history

---

## Scalability Considerations

### Current Design (Single Server)
- SQLite database (sufficient for single user)
- Local file storage
- In-process health monitoring
- Single API instance

### Future Extensions

**Multi-user:**
- Add RBAC tables to database
- User-specific service access
- Shared vs. private services

**Multi-server:**
- PostgreSQL instead of SQLite
- Distributed health monitoring
- Service orchestration (Kubernetes)
- Centralized logging?

**High Availability:**
- Load balancer
- Multiple API instances
- Replicated database
- Shared storage (NFS/S3)

---

## Performance Characteristics

### Response Times
- API endpoints: <100ms
- Service start/stop: 1-3 seconds
- Health checks: <1 second
- Database queries: <10ms

### Resource Usage
- API memory: ~50MB
- Database size: ~5MB (typical)
- Health monitor: ~20MB
- Per service: Varies by service

### Concurrency
- API: 5-10 concurrent requests (Flask dev server)
- Health monitor: Sequential checks (one at a time)
- Database: SQLite handles multiple readers

---

## Design Decisions

### Why SQLite?
- Single user system
- No client-server overhead
- Built-in to Python
- File-based (easy backup)
- Sufficient for <100 services

### Why Flask?
- Lightweight
- Easy to extend
- Good for prototyping
- Simple deployment

### Why Docker?
- Isolation
- Portability
- Easy updates
- Large ecosystem

### Why iptables?
- Built-in to Linux
- Low-level control
- No additional dependencies
- Standard tool

### Why JWT?
- Stateless authentication
- Easy to validate
- Industry standard
- Works with any client

---

## Extension Points

### Adding New Features

**1. New service type:**
- Create manifest
- Add installation method to installer.py
- Test

**2. New security tier:**
- Update firewall_manager.py
- Add tier definition
- Update database schema

**3. New monitoring type:**
- Extend health_monitor.py
- Add health check type to manifest
- Update UI

**4. New API endpoint:**
- Add route to api.py
- Implement in core module
- Add authentication if needed
- Update API docs

---
