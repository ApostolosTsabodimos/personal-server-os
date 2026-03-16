# PSO User Guide

Complete guide to using PSO (Personal Server OS)

---

## Table of Contents

1. [Getting Started](#getting-started)
2. [Dashboard Overview](#dashboard-overview)
3. [Managing Services](#managing-services)
4. [System Monitoring](#system-monitoring)
5. [Backups & Recovery](#backups--recovery)
6. [User Management](#user-management)
7. [Security Settings](#security-settings)
8. [Firewall & Network Tiers](#firewall--network-tiers)
9. [Advanced Features](#advanced-features)
10. [FAQ](#faq)
11. [Troubleshooting](#troubleshooting)

---

## Getting Started

### First Login

1. Open your browser to `http://localhost:5000`
2. Log in with default credentials:
   - **Username**: `admin`
   - **Password**: `admin`
3. **Immediately change your password**:
   - Click your username (top right)
   - Select "Change Password"
   - Enter a strong password

### Dashboard Layout

```
┌─────────────────────────────────────────────────┐
│  PSO Control Panel                     [User ▾] │ ← Header
├─────────────────────────────────────────────────┤
│  🎨 Theme  📘 Guide  📊 Metrics  📜 Log  ● Status│ ← Tools
├─────────────────────────────────────────────────┤
│  ◉ Running: 5    ○ Stopped: 3    ⊙ Total: 8    │ ← Stats
├─────────────────────────────────────────────────┤
│  🔍 Search services...        🏷️ All Categories  │ ← Filters
├─────────────────────────────────────────────────┤
│  📦 Start All Stopped    ⏸️  Stop All Running    │ ← Bulk Actions
├─────────────────────────────────────────────────┤
│                                                  │
│  [Service Cards Grid]                           │ ← Services
│                                                  │
└─────────────────────────────────────────────────┘
```

---

## Dashboard Overview

### Header Tools

- **Theme Switcher**: Toggle between dark/light mode
- **Setup Guide**: Interactive tutorial for new users
- **System Metrics**: View CPU, RAM, disk usage
- **Activity Log**: See recent system events
- **Status Badge**: Overall system health indicator
- **User Menu**: Account settings and logout

### Service Stats Bar

Shows a quick overview:
- **Running**: Number of active services
- **Stopped**: Number of inactive services
- **Total**: Total installed services

### Search & Filters

- **Search Box**: Filter services by name or description
- **Category Filter**: Show only specific categories (Media, Network, etc.)
- **Status Filter**: Show only running/stopped services

### Bulk Actions

- **Start All Stopped**: Start all inactive services at once
- **Stop All Running**: Stop all active services at once

### Service Cards

Each service card shows:
- **Category**: Service type (Media, Network, etc.)
- **Logo**: Service icon
- **Name**: Service display name
- **Status**: Running (green) or Stopped (gray)
- **Port Link**: Quick access to service web interface (when running)
- **Action Buttons**: Start/Stop/Restart
- **Menu**: Additional options (Logs, Update, Backup, Uninstall)

---

## Managing Services

### Installing a Service

#### Via Dashboard
1. Find the service you want to install
2. Click the **"Install"** button
3. Review service details (ports, resources, etc.)
4. Click **"Confirm Install"**
5. Wait for installation to complete
6. Service will appear as "Stopped" when ready

#### Via CLI
```bash
# List available services
./pso services list

# Install a service
./pso services install jellyfin

# Install with custom configuration
./pso services install nextcloud --config custom.json
```

### Starting a Service

#### Via Dashboard
1. Find your installed service
2. Click the **"Start"** button
3. Wait for status to change to "Running" (green)
4. Click the port link to access the service

#### Via CLI
```bash
./pso services start jellyfin
```

### Stopping a Service

#### Via Dashboard
1. Find the running service
2. Click the **"Stop"** button
3. Confirm if prompted

#### Via CLI
```bash
./pso services stop jellyfin
```

### Restarting a Service

#### Via Dashboard
1. Click the three-dot menu on the service card
2. Select **"Restart"**

#### Via CLI
```bash
./pso services restart jellyfin
```

### Viewing Logs

#### Via Dashboard
1. Click the three-dot menu
2. Select **"View Logs"**
3. Logs appear in a modal window
4. Use **"Auto-refresh"** to see live logs

#### Via CLI
```bash
# View logs
./pso services logs jellyfin

# Follow logs (live)
./pso services logs jellyfin --follow

# Show last 100 lines
./pso services logs jellyfin --tail 100
```

### Updating a Service

#### Via Dashboard
1. If an update is available, a badge appears
2. Click the three-dot menu
3. Select **"Update"**
4. Review changes
5. Click **"Update Now"**

#### Via CLI
```bash
# Check for updates
./pso services check-updates

# Update a specific service
./pso services update jellyfin

# Update all services
./pso services update-all
```

### Uninstalling a Service

⚠️ **Warning**: This permanently deletes all service data!

#### Via Dashboard
1. Click the three-dot menu
2. Select **"Uninstall"**
3. Type the service name to confirm
4. Click **"Uninstall"**

This removes:
- Docker container
- All volumes and data
- Network configuration
- Database entries
- Service secrets

#### Via CLI
```bash
# Uninstall (removes everything)
./pso services uninstall jellyfin

# Force uninstall (no confirmation)
./pso services uninstall jellyfin --force
```

---

## System Monitoring

### System Metrics

Access via the **"System Metrics"** button in the header.

**Shows**:
- **CPU Usage**: Current and historical
- **RAM Usage**: Used/Total with percentage
- **Disk Usage**: Used/Total per partition
- **Network I/O**: Upload/Download rates
- **Service Count**: Running vs Stopped
- **Uptime**: System and PSO dashboard uptime

### Per-Service Metrics

1. Click three-dot menu on service card
2. Select **"Metrics"**
3. View service-specific stats:
   - CPU usage (% and cores)
   - Memory usage (MB/GB)
   - Network I/O
   - Disk I/O
   - Uptime

### Activity Log

Access via the **"Activity Log"** button in the header.

**Shows**:
- User actions (login, service start/stop, etc.)
- System events (updates, backups, errors)
- Timestamps
- User who performed action
- Event severity (info, warning, error)

**Filters**:
- By user
- By event type
- By date range
- By severity

### Health Checks

Services automatically health-checked every 30 seconds.

**Status Indicators**:
- 🟢 **Healthy**: Service responding normally
- 🟡 **Degraded**: Service responding slowly
- 🔴 **Unhealthy**: Service not responding
- ⚪ **Unknown**: Health check not configured

**Manual health checks:**
```bash
python -m core.health_monitor check <service>
python -m core.health_monitor status
python -m core.health_monitor history <service>
```

**Run as systemd service (optional):**
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

**Configure health checks in service manifests:**
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

## Backups & Recovery

### Automatic Backups

PSO automatically backs up:
- Service data volumes
- Service configurations
- PSO database
- Secrets vault

**Default Schedule**: Daily at 2 AM

### Manual Backup

#### Via Dashboard
1. Click three-dot menu on service
2. Select **"Backup"**
3. Click **"Create Backup Now"**
4. Backup saved to `~/.pso_dev/backups/`

#### Via CLI
```bash
# Backup a specific service
./pso backup create jellyfin

# Backup all services
./pso backup create-all

# List backups
./pso backup list

# List backups for specific service
./pso backup list jellyfin
```

### Restoring from Backup

**Warning**: This overwrites current service data!

#### Via Dashboard
1. Stop the service first
2. Click three-dot menu
3. Select **"Backup"**
4. Choose backup from list
5. Click **"Restore"**
6. Confirm restoration
7. Start the service

#### Via CLI
```bash
# List available backups
./pso backup list jellyfin

# Restore from backup
./pso backup restore jellyfin <backup-id>

# Restore latest backup
./pso backup restore jellyfin --latest
```

### Backup Configuration

```bash
# View backup settings
./pso config show backup

# Set backup retention (days)
./pso config set backup.retention 30

# Set backup schedule (cron format)
./pso config set backup.schedule "0 2 * * *"

# Enable/disable automatic backups
./pso config set backup.enabled true
```

### Backup Location

Backups stored in:
```
~/.pso_dev/backups/
  ├── jellyfin/
  │   ├── backup_2026-03-15_02-00-00.tar.gz
  │   └── backup_2026-03-14_02-00-00.tar.gz
  ├── nextcloud/
  └── pso_system/
      └── database_2026-03-15_02-00-00.db
```

### Backup Verification & Pruning

**Verify backup integrity:**
```bash
./pso backup verify <backup-id>
```

**View backup info:**
```bash
./pso backup info <backup-id>
```

**Prune old backups:**
```bash
# Keep only latest 7 backups
./pso backup prune <service> --keep 7

# Delete backups older than 30 days
./pso backup cleanup --older-than 30
```

### Scheduled Backups with Cron

```bash
crontab -e

# Add daily backups at 2 AM
0 2 * * * cd ~/personal-server-os && ./pso backup create nginx
0 2 * * * cd ~/personal-server-os && ./pso backup create jellyfin

# Weekly pruning on Sunday at 3 AM
0 3 * * 0 cd ~/personal-server-os && ./pso backup prune nginx --keep 7
```

---

## User Management

### Login & Sessions

**Access dashboard:** http://localhost:5000/login

**Session Duration:**
- Regular login: 24 hours
- "Remember me" enabled: 30 days

### Creating Users

```bash
# Create regular user
./pso auth register alice password123

# Create admin user
./pso auth register bob adminpass --admin

# Create user with email
./pso auth register carol pass123 --email carol@example.com
```

### Listing Users

```bash
# List all users
./pso auth list-users

# Show user details
./pso auth show alice
```

### Changing Passwords

```bash
# Change your own password (interactive)
./pso auth change-password alice

# Admin: Reset user password
./pso auth reset-password alice newpassword
```

### Deleting Users

```bash
# Delete user
./pso auth delete alice

# Cannot delete last admin user
```

### Session Management

```bash
# List active sessions
python -m core.auth list

# Remove expired sessions
python -m core.auth cleanup
```

### Roles & Permissions

**Admin Users**:
- Install/uninstall services
- Manage users
- Change system settings
- Access all logs
- Manage backups

**Regular Users**:
- Start/stop services
- View logs
- Create backups
- Change own password

---

## Security Settings

### Changing Admin Password

**Critical**: Do this immediately after installation!

```bash
./pso auth change-password admin
```

### Enabling HTTPS

```bash
# Generate self-signed certificate
./pso ssl generate

# Enable HTTPS
./pso ssl enable

# Dashboard now at: https://localhost:5000
```

For production, use a proper certificate:
```bash
# Use your own certificate
./pso ssl enable --cert /path/to/cert.pem --key /path/to/key.pem
```

### Session Timeout

```bash
# Set session timeout (minutes)
./pso config set security.session_timeout 60

# Disable timeout (not recommended)
./pso config set security.session_timeout 0
```

### Rate Limiting

**Enable/Configure:**
```bash
# Enable rate limiting
./pso config set security.rate_limit.enabled true

# Max requests per minute
./pso config set security.rate_limit.max_requests 60

# Ban duration (minutes)
./pso config set security.rate_limit.ban_duration 15
```

**Manage IP lists:**
```bash
# Blacklist IP
python -m core.rate_limiter blacklist 1.2.3.4 --reason "Brute force attack"

# Whitelist IP
python -m core.rate_limiter whitelist 192.168.1.100 --reason "My home IP"

# View lists
python -m core.rate_limiter list-blacklist
python -m core.rate_limiter list-whitelist
python -m core.rate_limiter list-bans
```

**Monitor violations:**
```bash
# View violations
python -m core.rate_limiter violations
python -m core.rate_limiter violations --limit 100

# Statistics
python -m core.rate_limiter stats

# Cleanup expired bans
python -m core.rate_limiter cleanup
```

**Tier-based limits:**
- Tier 0: No limits (internal only)
- Tier 1: 1000 requests/minute (LAN)
- Tier 2: 500 requests/minute (VPN)
- Tier 3: 100 requests/minute (Internet - strict)

### Audit Logging

All actions are logged by default.

```bash
# View audit log
./pso audit log

# View specific user's actions
./pso audit log --user alice

# Export audit log
./pso audit export audit_log.json
```

---

## Firewall & Network Tiers

### Tier System Overview

PSO uses a tier-based firewall system to control network access to services. Every service starts at Tier 0 (most secure) and can be promoted to higher tiers as needed.

### Setup

**Install iptables (if not already installed):**
```bash
# Manjaro/Arch
sudo pacman -S iptables
sudo systemctl enable iptables

# Ubuntu/Debian
sudo apt install iptables-persistent
```

**Verify installation:**
```bash
python -m core.firewall_manager tiers    # Show tier definitions
python -m core.firewall_manager list     # List all service tiers
```

### Managing Tiers

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

## Advanced Features

### Reverse Proxy Setup

**Install Caddy:**
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

**Generate configuration:**
```bash
# For local network
python -m core.reverse_proxy generate

# For public domain with SSL
python -m core.reverse_proxy generate \
    --domain example.com \
    --email admin@example.com
```

**Manage proxy:**
```bash
# Validate configuration
python -m core.reverse_proxy validate

# Reload Caddy
sudo python -m core.reverse_proxy reload

# Check status
python -m core.reverse_proxy status
python -m core.reverse_proxy list
```

**Complete workflow:**
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

### Notifications

**Setup (Linux):**
```bash
sudo apt install libnotify-bin  # Ubuntu/Debian
sudo pacman -S libnotify        # Arch
```

**macOS/Windows:** Built-in support, no installation needed.

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

**Automatic notifications sent for:**
- Health check failures
- Successful updates
- Backup completion
- Security tier changes

---

## FAQ

### How do I access services remotely?

Services are localhost-only by default. To access remotely:

1. **SSH Tunnel** (Recommended):
   ```bash
   ssh -L 8096:localhost:8096 user@your-server
   # Now access http://localhost:8096 on your local machine
   ```

2. **Reverse Proxy** (Advanced):
   - Install Caddy or Nginx service
   - Configure domain and SSL
   - See [Reverse Proxy Setup](#reverse-proxy-setup) for details

### Can I change service ports?

Yes, but you need to edit the service manifest before installation:

```bash
# Edit manifest
nano services/jellyfin/manifest.json

# Change "http": 8096 to your desired port

# Then install
./pso services install jellyfin
```

For already-installed services, you need to uninstall and reinstall.

### How do I update PSO itself?

```bash
# Pull latest changes
git pull

# Restart dashboard
./pso restart
```

### Where is my data stored?

```
~/.pso_dev/
  ├── pso.db              # PSO database
  ├── .secrets_key        # Encryption key
  ├── services/           # Service data
  │   ├── jellyfin/
  │   ├── nextcloud/
  │   └── ...
  └── backups/            # Backup files
```

### Can I run PSO on a Raspberry Pi?

- **Raspberry Pi 4/5** (64-bit OS): ✅ Yes
- **Raspberry Pi 3** (64-bit OS): ⚠️ Slow but works
- **Raspberry Pi Zero/1/2**: ❌ Not enough RAM

Install Raspberry Pi OS 64-bit for best results.

### How do I free up disk space?

```bash
# Remove unused Docker images
docker system prune -a

# Delete old backups
./pso backup cleanup --older-than 30

# Check disk usage
./pso metrics disk
```

### Can I use this in production?

PSO is currently in **prototype stage** (v0.1.0). It works well but:
- Not all features are complete
- Limited testing on different platforms
- Documentation still being written

**Recommended for**:
- Home labs
- Personal use
- Testing

**Not yet recommended for**:
- Production environments
- Critical services
- Public-facing deployments

### How do I backup everything?

```bash
# Backup all services
./pso backup create-all

# Also backup PSO database
cp ~/.pso_dev/pso.db ~/pso_backup.db

# Backup secrets key (KEEP SAFE!)
cp ~/.pso_dev/.secrets_key ~/secrets_key.backup
```

---

## Troubleshooting

### Service won't start

1. Check logs: `./pso services logs <service-name>`
2. Check port conflicts: `./pso services check-ports`
3. Restart: `./pso services restart <service-name>`
4. Reinstall: `./pso services uninstall <service-name> && ./pso services install <service-name>`

### Dashboard is slow

1. Check system resources: `./pso metrics`
2. Stop unused services: `./pso services stop <name>`
3. Clear Docker cache: `docker system prune`
4. Restart dashboard: `./pso restart`

### Lost admin password

```bash
# Reset admin password
./pso auth reset-password admin newpassword
```

### Service data disappeared

1. Check if service is installed: `./pso services list`
2. Check backups: `./pso backup list <service-name>`
3. Restore from backup: `./pso backup restore <service-name> --latest`

### Port already in use

```bash
# Find what's using the port
sudo lsof -i :8096

# Kill the process or change service port
```

---

## Getting Help

- **Documentation**: Check [docs/](../)
- **GitHub Issues**: Report bugs and request features
- **GitHub Discussions**: Ask questions and share tips
- **Logs**: Always include logs when reporting issues

