# PSO Quickstart Guide

**Get PSO running in 15 minutes**

---

## Prerequisites

- Linux system (Manjaro/Arch/Ubuntu/Debian)
- Docker installed
- Python 3.8+
- sudo access

---

## Installation

### 1. Clone and Setup

```bash
cd ~
git clone <your-repo> personal-server-os
cd personal-server-os

# Make scripts executable
chmod +x pso pso-menu pso.py
```

### 2. Install Dependencies

```bash
# Python dependencies
pip install flask flask-cors docker PyJWT bcrypt jsonschema --break-system-packages

# System packages (Manjaro/Arch)
sudo pacman -S docker iptables

# System packages (Ubuntu/Debian)
sudo apt install docker.io docker-compose iptables

# Enable Docker
sudo systemctl enable docker
sudo systemctl start docker
```

### 3. Initialize Database

```bash
python3 << 'EOF'
from core.database import Database
from core.port_manager import PortManager
from core.auth import Auth

# Initialize
db = Database()
pm = PortManager()
auth = Auth(db)

print("✓ Database initialized")
print("✓ Default user: admin / pso-admin-2026")
EOF
```

---

## First Steps

### Start the Dashboard

```bash
cd ~/personal-server-os/web
python api.py
```

**Access:** http://localhost:5000  
**Login:** admin / pso-admin-2026

### Install Your First Service

**Option A: Using CLI**
```bash
./pso install portainer
./pso start portainer
./pso status portainer
```

**Option B: Using Menu**
```bash
./pso-menu
# Navigate: 1 (Service Management) → 3 (Install) → Enter: portainer
```

**Option C: Using Dashboard**
- Open http://localhost:5000
- Login
- Click "Install" on Portainer card

---

## Essential Commands

### Service Management
```bash
./pso install <service>    # Install service
./pso start <service>      # Start service
./pso stop <service>       # Stop service
./pso restart <service>    # Restart service
./pso list                 # List all services
./pso status <service>     # Check status
```

### Service Discovery
```bash
./pso catalog              # Browse available services
./pso catalog search web   # Search for services
```

### Interactive Menu
```bash
./pso-menu                 # Full interactive interface
```

---

## Understanding Tiers (Security Levels)

Every service has a security tier that controls network access:

**Tier 0 - Internal Only (DEFAULT)** 🟢
- Accessible only from localhost
- Most secure, use this by default
- Example: Databases, internal tools

**Tier 1 - LAN Only** 🟡
- Accessible from your home network
- Good for family services
- Example: Jellyfin, Nextcloud

**Tier 2 - VPN Access** 🔵
- Accessible via VPN (Tailscale/WireGuard)
- Remote access while traveling
- Example: All services when away from home

**Tier 3 - Internet Exposed** 🔴
- PUBLIC internet access
- Use ONLY when necessary
- Requires explicit confirmation
- Example: Public blog, API

### Change Tier

**Using CLI:**
```bash
# Check current tier
python -m core.firewall_manager status nginx

# Promote to LAN access
sudo python -m core.firewall_manager set nginx 1

# Restart service to apply
./pso restart nginx
```

**Using Menu:**
```bash
./pso-menu
# Navigate: 3 (Firewall & Tiers) → 4 (Promote service tier)
```

---

## Common Workflows

### Media Server Setup
```bash
# 1. Install Jellyfin
./pso install jellyfin

# 2. Promote to LAN access (family can use it)
sudo python -m core.firewall_manager set jellyfin 1
./pso restart jellyfin

# 3. Access from any device on your network
# http://your-server-ip:8200
```

### Password Manager Setup
```bash
# 1. Install Vaultwarden
./pso install vaultwarden

# 2. Keep at Tier 0 (most secure)
# Access only via SSH tunnel or promote to Tier 2 with VPN

# 3. For VPN access when traveling
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

## Dashboard Features

### Service Cards
Each installed service shows:
- Status indicator (running/stopped)
- Health status (healthy/unhealthy)
- Quick action buttons:
  - **Stop/Start** - Control service
  - **Logs** - View recent logs
  - **Advanced** - Enhanced log viewer with filters
  - **Updates** - Check for updates
  - **Backups** - Backup/restore
  - **Security** - Change tier

### System Overview
Top of dashboard shows 4 cards:
- **Services Running** - Active service count
- **Healthy** - Services passing health checks
- **Uptime** - System uptime
- **Disk Used** - Storage usage

---

## Backup & Updates

### Create Backup
```bash
# Using CLI
./pso backup create <service> --note "Before update"

# Using Dashboard
# Click "Backups" button → "Create Backup"
```

### Check for Updates
```bash
# Using CLI
python -m core.update_manager check <service>

# Using Dashboard
# Click "Updates" button → "Check for Updates"
```

---

## Monitoring

### Health Checks
Health monitor runs in background (via API) and checks services every 30 seconds.

**Manual check:**
```bash
python -m core.health_monitor check <service>
python -m core.health_monitor status
```

### Desktop Notifications
Get popup notifications for:
- Service failures
- Successful updates
- Backup completion
- Security tier changes

**Test notification:**
```bash
python -m core.notifications test
```

---

## Troubleshooting

### Dashboard not loading?
```bash
# Check if API is running
ps aux | grep api.py

# Restart API
cd ~/personal-server-os/web
pkill -f api.py
python api.py
```

### Service won't install?
```bash
# Check for port conflicts
sudo netstat -tuln | grep <port>

# Free the port
sudo fuser -k <port>/tcp

# Try again
./pso install <service>
```

### Can't see new dashboard features?
```bash
# Clear browser cache
# Method 1: Use incognito/private window
# Method 2: Hard refresh (Ctrl+Shift+R)
# Method 3: Clear all cache (Ctrl+Shift+Delete)
```

### Database errors?
```bash
# Reinitialize database
python3 << 'EOF'
from core.database import Database
from core.port_manager import PortManager
Database()
PortManager()
print("✓ Database reinitialized")
EOF
```

---

## Next Steps

1. **Install services you need**
   - Browse: `./pso catalog`
   - Install: `./pso install <service>`

2. **Set appropriate security tiers**
   - Keep most services at Tier 0
   - Promote to Tier 1 for family access
   - Use Tier 2 with VPN for remote access

3. **Set up automatic backups**
   - Schedule daily backups in cron
   - Test restore process

4. **Enable health monitoring**
   - Already runs with API
   - Check status regularly

5. **Explore the dashboard**
   - Test all modals (Logs, Updates, Backups)
   - Review system overview
   - Check service metrics

---

## Getting Help

**Check documentation:**
```bash
./pso-menu
# Navigate: 8 (Documentation)
```

**View logs:**
```bash
./pso logs <service>
```

**Check service status:**
```bash
./pso status <service>
```

---

## Security Checklist

- [ ] Change default admin password
- [ ] Review installed services
- [ ] Verify all services at appropriate tier
- [ ] Test backup/restore
- [ ] Enable firewall
- [ ] Set up VPN (if using Tier 2)
- [ ] Configure reverse proxy with SSL (if using Tier 3)

---

**You're ready to go! Start with `./pso-menu` to explore all features.**