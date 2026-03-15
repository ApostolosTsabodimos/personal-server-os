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
8. [CLI Reference](#cli-reference)
9. [FAQ](#faq)
10. [Troubleshooting](#troubleshooting)

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

⚠️ **Warning**: This overwrites current service data!

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

---

## User Management

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

```bash
# Enable rate limiting
./pso config set security.rate_limit.enabled true

# Max requests per minute
./pso config set security.rate_limit.max_requests 60

# Ban duration (minutes)
./pso config set security.rate_limit.ban_duration 15
```

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

## CLI Reference

For full interactive help, run: `./pso --help` or `./pso-menu`

### Quick Start

```bash
./pso init                           # Initialize database
./pso install <service>              # Install a service
./pso list                           # List installed services
./pso dashboard start                # Start web UI at :5000
```

### Service Catalog

Browse available services:

```bash
./pso catalog                        # Browse all available services
./pso catalog info <service>         # Get details about a service
./pso catalog search <query>         # Search by name/category/tag
```

### Service Management

```bash
# Installation
./pso install <service> [--dry-run]  # Install service
./pso uninstall <service>            # Remove service and data

# Control
./pso start <service>                # Start a service
./pso stop <service>                 # Stop a service
./pso restart <service>              # Restart a service
./pso start-all                      # Start all installed services
./pso stop-all                       # Stop all running services

# Power management
./pso pause                          # Stop all services + dashboard (e.g., closing laptop)
./pso resume                         # Start dashboard + all services (coming back)

# Information
./pso status <service>               # Service details and health
./pso logs <service> [lines]         # View logs (default: 100 lines)
./pso list                           # List all installed services
```

### Security

#### RBAC (Role-Based Access Control)

```bash
./pso rbac status                    # Overview of roles and users
./pso rbac role list                 # List all roles
./pso rbac role create <role>        # Create new role
./pso rbac role delete <role>        # Delete role
./pso rbac role perms <role>         # Show role permissions
./pso rbac user assign <user> <role> # Assign role to user
./pso rbac user revoke <user> <role> # Revoke role from user
./pso rbac check <user> <permission> # Test if user has permission
```

#### Secrets Management

```bash
./pso secrets list                   # List all stored secrets (names only)
./pso secrets set <name> <value> [service]  # Store encrypted secret
./pso secrets get <name>             # Retrieve and decrypt secret
./pso secrets delete <name>          # Remove secret
./pso secrets export                 # Export all secrets to JSON (backup)
```

#### Audit Trail

```bash
./pso audit show                     # View full audit trail
./pso audit show --event <type>      # Filter by event type
./pso audit show --user <username>   # Filter by user
./pso audit show --warn              # Show warnings only
./pso audit stats                    # Summary and top events
```

#### Rate Limiting

```bash
./pso rate-limit status              # Show stats: violations, bans, blacklist counts
./pso rate-limit blacklist <ip> --reason "X"    # Permanent IP block + iptables
./pso rate-limit unblacklist <ip>    # Remove from permanent blacklist
./pso rate-limit whitelist <ip> --reason "X"    # Whitelist IP (bypass rate limits)
./pso rate-limit bans                # Show active temporary bans
./pso rate-limit violations          # Show recent violations log
./pso rate-limit cleanup             # Remove expired bans
```

### Network Tier System

Control service exposure (0=Internal, 1=LAN, 2=VPN, 3=Public):

```bash
./pso tier list                      # Show all service tiers
./pso tier status <service>          # Check one service's tier
./pso tier set <service> <0-3>       # Change tier (may need sudo)
./pso tier history <service>         # Audit log of tier changes
./pso tier info                      # Explain the tier system
```

**Tier Levels**:
- **Tier 0 (Internal)**: Localhost only (127.0.0.1)
- **Tier 1 (LAN)**: Local network only (192.168.x.x)
- **Tier 2 (VPN)**: VPN clients only
- **Tier 3 (Public)**: Internet-facing (0.0.0.0)

### Service Discovery

```bash
./pso discover list                  # Directory of all services + URLs
./pso discover sync                  # Refresh registry from installed services
./pso discover info <service>        # Show address, port, status, history
./pso discover search <query>        # Search service registry
./pso discover server                # Show host IP and hostname
```

### Dependencies

```bash
./pso deps                           # Full dependency graph (all services)
./pso deps <service>                 # Show what service needs and what needs it
```

### Migration & Import

Import existing Docker setups:

```bash
./pso migrate status                 # Show managed vs unmanaged containers
./pso migrate compose <file> [--dry-run]  # Import from docker-compose.yml
./pso migrate adopt [--all] [<name>]      # Adopt running Docker containers
./pso migrate export [file]          # Export PSO registry to JSON
./pso migrate import <file> [--dry-run]   # Import PSO registry from JSON
```

### Backups

```bash
./pso backup create <service> [--note "text"]  # Create backup
./pso backup restore <service> <id>  # Restore from backup
./pso backup list [service]          # List backups
./pso backup verify <id>             # Check backup integrity
./pso backup prune <service> [--keep N]  # Delete old backups (default: keep 5)
```

### Updates

```bash
./pso update check [service]         # Check for available updates
./pso update apply <service>         # Update service (auto-backup first)
./pso update history [service]       # Show update log
```

### Health Monitoring

```bash
./pso health check <service>         # Run health check now
./pso health status [service]        # Show current health status
./pso health history <service>       # Show health check history
./pso health config <service>        # Show health check configuration
```

### Logs Aggregation

```bash
./pso logs-agg tail                  # Live stream all service logs
./pso logs-agg search <query>        # Search across all logs
./pso logs-agg errors                # Show recent errors from all services
./pso logs-agg stats                 # Log volume and error count per service
./pso logs-agg start                 # Start background collection daemon
```

### Notifications

```bash
./pso notifications status           # Show configured channels and recent alerts
./pso notifications test email       # Send test email notification
./pso notifications test webhook     # Send test webhook notification
./pso notifications config set [options]  # Configure email/webhook/desktop
./pso notifications history          # View alert history
```

### Resource Management

Control CPU, memory, and disk limits:

```bash
# Profiles
./pso resources profiles             # List all profiles (tiny/small/medium/large/unlimited)
./pso resources get <service>        # Show current resource limits

# Set limits
./pso resources set <service> --profile <tiny|small|medium|large|unlimited>
./pso resources set <service> --cpu <cores> --memory <MB>
./pso resources set <service> --disk <MB> --restart <policy>
./pso resources apply <service>      # Apply limits to container
./pso resources stats <service>      # Live CPU/memory/disk usage
```

**Resource Profiles**:
- **tiny**: 0.5 CPU cores, 512MB RAM
- **small**: 1 CPU core, 1GB RAM
- **medium**: 2 CPU cores, 2GB RAM
- **large**: 4 CPU cores, 4GB RAM
- **unlimited**: No limits

### Metrics

```bash
./pso metrics show                   # Display all latest metric values
./pso metrics collect                # Run one-time collection
./pso metrics query <metric> [service]  # Query stored metric history
./pso metrics export [service]       # Export in Prometheus format
./pso metrics start                  # Start background metrics collector
```

### Grafana Integration

```bash
./pso grafana status                 # Check Grafana reachability
./pso grafana provision              # Push PSO dashboard and datasource to Grafana
./pso grafana serve-metrics          # Start /metrics endpoint on :9090
./pso grafana install                # Install Grafana via PSO
```

### User Management

```bash
./pso user list                      # List all users
./pso user add <user> <pass>         # Create regular user
./pso user add-admin <user> <pass>   # Create admin user
./pso user cleanup                   # Remove expired sessions
```

### Port Management

```bash
./pso ports                          # Show all port allocations
./pso ports available                # List free ports
./pso ports check <port>             # Check if specific port is free
```

### Dashboard Commands

```bash
./pso dashboard start                # Start web UI
./pso dashboard stop                 # Stop web UI
./pso dashboard status               # Check dashboard status
./pso dashboard restart              # Restart dashboard
./pso dashboard logs                 # View dashboard logs
```

### System Commands

```bash
./pso init                           # Initialize PSO database
./pso doctor                         # Run system diagnostics
./pso fix-blockers                   # Auto-fix common issues
./pso version                        # Show PSO version and development progress
./pso dev scan                       # Scan development progress
./pso dev tree                       # Show development component tree
./pso dev status                     # Show development status
```

### Testing & Validation

```bash
./pso-check                          # Full automated test suite
./pso-check --quick                  # Structural checks only
./pso-check --functional             # Functional tests only
./pso-check --cli-only               # CLI command tests only
./pso-check --manifests              # Manifest and asset checks only
./pso-check --tests                  # Run existing test suite only
```

### Common Workflows

**Pause everything (closing laptop)**:
```bash
./pso pause                          # Stop all services + dashboard
./pso resume                         # Bring everything back up
```

**Install and configure**:
```bash
./pso install jellyfin
sudo ./pso tier set jellyfin 1       # Make accessible on LAN
./pso resources set jellyfin --profile medium
./pso discover info jellyfin
```

**Backup, update, verify**:
```bash
./pso backup create nginx --note "pre-update"
./pso update apply nginx
./pso health check nginx
```

**Monitor performance**:
```bash
./pso resources stats nginx
./pso metrics query service_cpu_percent nginx
./pso logs nginx 200
```

**Troubleshoot**:
```bash
./pso status nginx
./pso logs nginx 500
./pso health history nginx
./pso restart nginx
```

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
   - Install Nginx service
   - Configure domain and SSL
   - See [SETUP_GUIDES.md](SETUP_GUIDES.md) for details

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

