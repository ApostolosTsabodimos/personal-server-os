# PSO Setup Guides

Complete setup instructions for all major features.

---

## Table of Contents

1. [Authentication](#authentication)
2. [Firewall & Tiers](#firewall--tiers)
3. [Health Monitoring](#health-monitoring)
4. [Backup System](#backup-system)
5. [Update Manager](#update-manager)
6. [Reverse Proxy](#reverse-proxy)
7. [Rate Limiting](#rate-limiting)
8. [Notifications](#notifications)

---

## Authentication

### Setup

**1. Default credentials:**
- Username: `admin`
- Password: `pso-admin-2026`

**2. Change password (IMPORTANT):**
```bash
python3 << 'EOF'
from core.database import Database
from core.auth import Auth

db = Database()
auth = Auth(db)

# Login as admin
result = auth.login('admin', 'pso-admin-2026')
if result:
    auth.change_password(result['user']['id'], 'pso-admin-2026', 'YOUR_NEW_SECURE_PASSWORD')
    print("✓ Password changed successfully")
EOF
```

**3. Create additional users:**
```bash
python -m core.auth register username password123
python -m core.auth register adminuser secret123 --admin
```

### Usage

**Login:** http://localhost:5000/login

**Sessions:**
- Regular login: 24 hours
- "Remember me": 30 days

**CLI management:**
```bash
python -m core.auth list           # List users
python -m core.auth cleanup        # Remove expired sessions
```

---

## Firewall & Tiers

### Setup

**1. Install iptables:**
```bash
# Manjaro/Arch
sudo pacman -S iptables
sudo systemctl enable iptables

# Ubuntu/Debian
sudo apt install iptables-persistent
```

**2. Verify installation:**
```bash
python -m core.firewall_manager tiers    # Show tier definitions
python -m core.firewall_manager list     # List all service tiers
```

### Usage

**View service tier:**
```bash
python -m core.firewall_manager status <service>
```

**Change tier:**
```bash
# Promote to LAN access (Tier 1)
sudo python -m core.firewall_manager set nginx 1

# Restart service to apply
./pso restart nginx
```

**Emergency lockdown:**
```bash
python -m core.firewall_manager reset-all
# Type 'RESET' to confirm - sets all services to Tier 0
```

**View tier history:**
```bash
python -m core.firewall_manager history <service>
```

### Tier Recommendations

| Service Type | Recommended Tier | Notes |
|--------------|------------------|-------|
| Databases | Tier 0 | Never expose directly |
| Family media | Tier 1 | LAN access for household |
| Remote access | Tier 2 | Use VPN |
| Public website | Tier 3 | Only if absolutely necessary |

---

## Health Monitoring

### Setup

**1. Already running with API:**
Health monitor starts automatically when you run `python web/api.py`

**2. Optional: Run as systemd service:**
```bash
# Copy service file
sudo cp pso-health-monitor.service /etc/systemd/system/

# Edit to set correct paths
sudo nano /etc/systemd/system/pso-health-monitor.service

# Enable and start
sudo systemctl enable pso-health-monitor
sudo systemctl start pso-health-monitor

# Check status
sudo systemctl status pso-health-monitor
```

### Usage

**Manual health check:**
```bash
python -m core.health_monitor check <service>
python -m core.health_monitor status
```

**View health history:**
```bash
python -m core.health_monitor history <service>
```

**Dashboard:**
- Service cards show health status (✓ Healthy / ✗ Unhealthy)
- Click "Advanced" button for detailed logs
- System overview shows healthy service count

### Configuration

Edit health check settings in service manifests:
```json
"health_check": {
  "type": "http",
  "endpoint": "http://localhost:8080/health",
  "interval": 30,
  "timeout": 5,
  "retries": 3
}
```

---

## Backup System

### Setup

No setup required - works immediately.

**Backup location:** `/var/pso/backups/`

### Usage

**Create backup:**
```bash
./pso backup create <service>
./pso backup create <service> --note "Before update"
```

**List backups:**
```bash
./pso backup list
./pso backup list <service>
```

**Restore backup:**
```bash
./pso backup restore <service> <backup-id>
```

**Verify integrity:**
```bash
./pso backup verify <backup-id>
```

**Prune old backups:**
```bash
./pso backup prune <service> --keep 7
```

**View backup info:**
```bash
./pso backup info <backup-id>
```

### Automatic Backups

**Schedule with cron:**
```bash
crontab -e

# Add daily backups at 2 AM
0 2 * * * cd ~/personal-server-os && ./pso backup create nginx
0 2 * * * cd ~/personal-server-os && ./pso backup create jellyfin

# Weekly pruning on Sunday at 3 AM
0 3 * * 0 cd ~/personal-server-os && ./pso backup prune nginx --keep 7
```

### Dashboard Usage

1. Click "Backups" button on service card
2. View all backups
3. Click "Create Backup" to make new backup
4. Click "Restore" to restore from backup

---

## Update Manager

### Setup

No setup required - works immediately.

### Usage

**Check for updates:**
```bash
python -m core.update_manager check            # All services
python -m core.update_manager check <service>  # Specific service
```

**Update service:**
```bash
python -m core.update_manager update <service>
```

**Update all:**
```bash
python -m core.update_manager update-all
```

**View update history:**
```bash
python -m core.update_manager history
python -m core.update_manager history <service>
```

### Dashboard Usage

1. Click "Updates" button on service card
2. View current vs. latest version
3. Click "Update" to apply update (auto-backs up first)
4. View update history

### Features

- Automatic backup before update
- Rollback on failure
- Update history tracking
- Dry-run mode for testing

---

## Reverse Proxy

### Setup

**1. Install Caddy:**
```bash
# Automatic
sudo python -m core.reverse_proxy install

# Or manual (Arch)
sudo pacman -S caddy
sudo systemctl enable caddy

# Or manual (Ubuntu/Debian)
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
echo "deb [signed-by=/usr/share/keyrings/caddy-stable-archive-keyring.gpg] https://dl.cloudsmith.io/public/caddy/stable/deb/debian any-version main" | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update
sudo apt install caddy
```

**2. Create log directory:**
```bash
sudo mkdir -p /var/log/pso/proxy
sudo chown -R caddy:caddy /var/log/pso/proxy
```

### Usage

**Generate configuration:**
```bash
# For local network
python -m core.reverse_proxy generate

# For public domain with SSL
python -m core.reverse_proxy generate \
    --domain example.com \
    --email admin@example.com
```

**Validate configuration:**
```bash
python -m core.reverse_proxy validate
```

**Reload Caddy:**
```bash
sudo python -m core.reverse_proxy reload
```

**Check status:**
```bash
python -m core.reverse_proxy status
python -m core.reverse_proxy list
```

### DNS Setup

**For public domain:**
```
A    @              your.server.ip
A    *.example.com  your.server.ip
```

**For local network:**
Add to `/etc/hosts` on client devices:
```
192.168.1.100  nginx.local
192.168.1.100  jellyfin.local
```

### Workflow

```bash
# 1. Install services
./pso install nginx
./pso install jellyfin

# 2. Set tiers (only Tier 1+ are proxied)
sudo python -m core.firewall_manager set nginx 1
sudo python -m core.firewall_manager set jellyfin 1

# 3. Restart services
./pso restart nginx
./pso restart jellyfin

# 4. Generate proxy config
python -m core.reverse_proxy generate --domain myserver.com --email me@example.com

# 5. Validate and reload
python -m core.reverse_proxy validate
sudo python -m core.reverse_proxy reload

# 6. Test
curl https://nginx.myserver.com
curl https://jellyfin.myserver.com
```

---

## Rate Limiting

### Setup

No setup required - works immediately.

### Usage

**Blacklist IP:**
```bash
python -m core.rate_limiter blacklist 1.2.3.4 --reason "Brute force attack"
```

**Whitelist IP:**
```bash
python -m core.rate_limiter whitelist 192.168.1.100 --reason "My home IP"
```

**View lists:**
```bash
python -m core.rate_limiter list-blacklist
python -m core.rate_limiter list-whitelist
python -m core.rate_limiter list-bans
```

**View violations:**
```bash
python -m core.rate_limiter violations
python -m core.rate_limiter violations --limit 100
```

**Statistics:**
```bash
python -m core.rate_limiter stats
```

**Cleanup expired bans:**
```bash
python -m core.rate_limiter cleanup
```

### Integration in Code

```python
from core.rate_limiter import RateLimiter, RateLimitError

limiter = RateLimiter()

try:
    limiter.check_rate_limit(
        ip_address="1.2.3.4",
        service_id="nginx",
        endpoint="/api/login",
        max_requests=5,      # 5 requests
        window_seconds=60    # per minute
    )
    # Request allowed
except RateLimitError:
    # Rate limit exceeded
    return "Too many requests", 429
```

### Tier-Based Limits

```python
tier_limits = {
    0: None,           # Internal - no limits
    1: (1000, 60),     # LAN - 1000/min
    2: (500, 60),      # VPN - 500/min
    3: (100, 60),      # Internet - 100/min (strict)
}
```

---

## Notifications

### Setup

**Linux:**
```bash
sudo apt install libnotify-bin  # Ubuntu/Debian
sudo pacman -S libnotify        # Arch
```

**macOS/Windows:** Built-in support, no installation needed.

### Usage

**Test notification:**
```bash
python -m core.notifications test
python -m core.notifications test --title "Hello" --message "Test"
```

**View history:**
```bash
python -m core.notifications history
python -m core.notifications history --limit 50
```

**Clear history:**
```bash
python -m core.notifications clear
```

### Integration in Code

```python
from core.notifications import NotificationManager, NotificationLevel

notif = NotificationManager()

# Send notification
notif.send(
    title="Service Started",
    message="nginx is now running",
    level=NotificationLevel.SUCCESS
)

# Convenience methods
notif.notify_health_failure("nginx", "Connection refused")
notif.notify_backup_complete("jellyfin", "backup_20260203_143022")
notif.notify_update_available("gitea")
notif.notify_tier_change("nginx", old_tier=0, new_tier=1)
```

### Automatic Notifications

Notifications are automatically sent for:
- Health check failures
- Successful updates
- Backup completion
- Security tier changes

Configure in each component's code.

---

## Quick Reference

| Feature | Command | Location |
|---------|---------|----------|
| Auth | `python -m core.auth` | `core/auth.py` |
| Firewall | `python -m core.firewall_manager` | `core/firewall_manager.py` |
| Health | `python -m core.health_monitor` | `core/health_monitor.py` |
| Backup | `./pso backup` | `core/backup_manager.py` |
| Updates | `python -m core.update_manager` | `core/update_manager.py` |
| Proxy | `python -m core.reverse_proxy` | `core/reverse_proxy.py` |
| Rate Limit | `python -m core.rate_limiter` | `core/rate_limiter.py` |
| Notifications | `python -m core.notifications` | `core/notifications.py` |

---

**All features are production-ready and tested.**