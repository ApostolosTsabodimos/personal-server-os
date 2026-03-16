# Installation Guide

Complete installation instructions for PSO (Personal Server OS)

---

## Table of Contents

1. [System Requirements](#system-requirements)
2. [Pre-Installation](#pre-installation)
3. [Installation Methods](#installation-methods)
4. [Post-Installation](#post-installation)
5. [Troubleshooting](#troubleshooting)
6. [Uninstallation](#uninstallation)

---

## System Requirements

### Minimum Requirements

- **Operating System**: Linux (64-bit)
  - Arch Linux / Manjaro
  - Ubuntu 20.04+
  - Debian 11+
  - Fedora 35+
  - Other systemd-based distributions
- **Python**: 3.10 or higher
- **Docker**: 20.10 or higher
- **RAM**: 2GB (4GB+ recommended)
- **Disk Space**: 20GB free (more for service data)
- **CPU**: x86_64 or ARM64

### Recommended Setup

- **RAM**: 8GB+ (for running multiple services)
- **Disk**: 100GB+ SSD
- **CPU**: 4+ cores
- **Network**: Static IP or DDNS for remote access

### Supported Platforms

**Tested & Supported**:
- Arch Linux / Manjaro
- Ubuntu 22.04 LTS

**Should Work** (untested):
- Debian 11/12
- Fedora 35+
- CentOS Stream 9
- Other systemd-based Linux distributions

**I have no idea**:
- Windows (WSL2 might work but untested)
- macOS (Docker Desktop required, untested)
- Raspberry Pi OS (32-bit)

---

## Pre-Installation

### 1. Install Docker

#### Arch/Manjaro
```bash
sudo pacman -S docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

#### Ubuntu/Debian
```bash
# Remove old versions
sudo apt remove docker docker-engine docker.io containerd runc

# Install dependencies
sudo apt update
sudo apt install ca-certificates curl gnupg lsb-release

# Add Docker's official GPG key
sudo mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg

# Set up repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker
sudo apt update
sudo apt install docker-ce docker-ce-cli containerd.io docker-compose-plugin

# Add your user to docker group
sudo usermod -aG docker $USER
```

#### Fedora
```bash
sudo dnf install docker docker-compose
sudo systemctl enable --now docker
sudo usermod -aG docker $USER
```

**Important**: After adding yourself to the docker group, **log out and log back in** for changes to take effect.

### 2. Verify Docker Installation

```bash
# Check Docker version
docker --version
# Should show: Docker version 20.10+ or higher

# Test Docker (without sudo)
docker run hello-world
# Should download and run successfully

# If you get permission denied, you need to log out and back in
```

### 3. Install Python 3.10+

#### Arch/Manjaro
```bash
sudo pacman -S python python-pip
```

#### Ubuntu 22.04+
```bash
sudo apt update
sudo apt install python3 python3-pip python3-venv
```

#### Ubuntu 20.04 (requires PPA)
```bash
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv python3-pip
```

### 4. Install Git If You Haven't

```bash
# Arch/Manjaro
sudo pacman -S git

# Ubuntu/Debian
sudo apt install git

# Fedora
sudo dnf install git
```

---

## Installation Methods

### Method 1: Quick Install (Recommended)

```bash
# 1. Clone the repository
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os

# 2. Run the installer
./pso install

# 3. Start PSO
./pso start
```

The installer will:
- Create necessary directories (`~/.pso_dev/`)
- Set up the database
- Install Python dependencies
- Create default admin user
- Generate encryption keys
- Start the dashboard

### Method 2: Manual Installation

```bash
# 1. Clone the repository
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os

# 2. Create data directory
mkdir -p ~/.pso_dev/services

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Initialize database
python3 -m core.database

# 5. Create admin user
python3 -m core.auth register admin adminpassword --admin

# 6. Start the dashboard
./pso start
```

### Method 3: Development Install

For whoever wants to contribute:

```bash
# 1. Clone your fork
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os

# 2. Install development dependencies
pip install -r requirements-dev.txt

# 3. Run installer
./pso install

# 4. Run tests
./pso-check

# 5. Start in development mode
./pso start --dev
```

---

## Post-Installation

### 1. Access the Dashboard

Open your web browser and navigate to:

```
http://localhost:5000
```

### 2. First Login

Default credentials:
- **Username**: `admin`
- **Password**: `admin`

**IMPORTANT**: Change the default password immediately!

```bash
# Change password via CLI
./pso auth change-password admin
```

Or change it through the web dashboard:
1. Click your username (top right)
2. Select "Change Password"
3. Enter new password

### 3. Install Your First Service (If I manage to get it to work)

#### Via Web Dashboard
1. Go to Services tab
2. Find a service (e.g., "Jellyfin")
3. Click "Install"
4. Wait for installation to complete
5. Click "Start" to run the service
6. Click the port link to access the service

#### Via CLI
```bash
# List available services
./pso services list

# Install a service
./pso services install jellyfin

# Start the service
./pso services start jellyfin

# Check status
./pso services status jellyfin

# Access the service
# Open browser to http://localhost:8096 (or check service port)
```

### 4. Understanding Security Tiers (The Way of the Onion)

Every service in PSO has a security tier that controls network access. Think of it like layers of an onion - each layer adds more exposure but also more convenience.

**Tier 0 - Internal Only (DEFAULT)** 🟢
- Accessible only from localhost
- Most secure, use this by default
- Access via SSH tunnel: `ssh -L 8080:localhost:8080 your-server`
- Example: Databases, password managers, internal tools

**Tier 1 - LAN Only** 🟡
- Accessible from your home network
- Good for family services
- Your phone/laptop on home WiFi can access
- Example: Jellyfin (media), Nextcloud (files), Home Assistant

**Tier 2 - VPN Access** 🔵
- Accessible via VPN (Tailscale/WireGuard)
- Remote access while traveling
- Still secured behind VPN authentication
- Example: All services when you're away from home

**Tier 3 - Internet Exposed** 🔴
- PUBLIC internet access
- Use ONLY when absolutely necessary
- Requires explicit confirmation
- Should have additional authentication
- Example: Public blog, webhook endpoints, public API

**Changing Tiers:**

```bash
# Check current tier
python -m core.firewall_manager status jellyfin

# Promote to LAN access (for family)
sudo python -m core.firewall_manager set jellyfin 1
./pso restart jellyfin

# Promote to VPN access (when traveling)
sudo python -m core.firewall_manager set vaultwarden 2
./pso restart vaultwarden
```

**Best Practices:**
- Start everything at Tier 0 (default)
- Only promote to higher tiers when needed
- Keep sensitive services (passwords, admin panels) at Tier 0 or 2
- Use Tier 3 sparingly and only with strong authentication

### 5. Configure System Settings

```bash
# View current configuration
./pso config show

# Set notification email
./pso notifications config set --email your@email.com

# Configure backup retention (days)
./pso config set backup.retention 30

# Enable auto-updates
./pso config set updates.auto_check true
```

### 6. Enable Automatic Startup (Optional)

To start PSO automatically on boot:

```bash
# Create systemd service
./pso install-systemd

# Enable auto-start
sudo systemctl enable pso-dashboard

# Check status
sudo systemctl status pso-dashboard
```

---

## Verification

### Check Installation

```bash
# Run system check
./pso-check

# This will verify:
# - Python version
# - Docker availability
# - Database integrity
# - All core modules
# - Security configuration
```

### Check Dashboard Status

```bash
# Check if dashboard is running
./pso status

# View dashboard logs
./pso logs

# View system metrics
./pso metrics
```

### Test Service Installation

```bash
# Install a lightweight service for testing
./pso services install homer

# Start it
./pso services start homer

# Check if it's running
docker ps | grep pso-homer

# Access it
curl http://localhost:8080
```

---

## Troubleshooting

### Docker Permission Denied

**Problem**: `permission denied while trying to connect to Docker daemon`

**Solution**:
```bash
# Add yourself to docker group
sudo usermod -aG docker $USER

# Log out and log back in, then verify:
groups | grep docker

# If still not working, restart Docker
sudo systemctl restart docker
```

### Port Already in Use

**Problem**: `Address already in use: Port 5000`

**Solution**:
```bash
# Find what's using port 5000
sudo lsof -i :5000

# Kill the process (replace PID)
kill <PID>

# Or use a different port
./pso start --port 5001
```

### Python Version Issues

**Problem**: `Python 3.10+ required`

**Solution**:
```bash
# Check your Python version
python3 --version

# If < 3.10, install from source or PPA (Ubuntu)
sudo add-apt-repository ppa:deadsnakes/ppa
sudo apt update
sudo apt install python3.10 python3.10-venv

# Update alternatives
sudo update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.10 1
```

### Database Errors

**Problem**: Database locked or corrupted

**Solution**:
```bash
# Stop PSO
./pso stop

# Backup database
cp ~/.pso_dev/pso.db ~/.pso_dev/pso.db.backup

# Reinitialize database
python3 -m core.database --reset

# Recreate admin user
python3 -m core.auth register admin newpassword --admin

# Restart
./pso start
```

### Service Won't Start

**Problem**: Service fails to start

**Solution**:
```bash
# Check service logs
./pso services logs <service-name>

# Check Docker logs
docker logs pso-<service-name>

# Check port conflicts
./pso services check-ports

# Try reinstalling
./pso services uninstall <service-name>
./pso services install <service-name>
```

### Dashboard Not Accessible

**Problem**: Can't access http://localhost:5000

**Solution**:
```bash
# Check if PSO is running
./pso status

# Check firewall
sudo ufw status
sudo ufw allow 5000/tcp

# Check if port is listening
sudo netstat -tlnp | grep 5000

# Check logs for errors
./pso logs

# Try restarting
./pso restart
```

---

## Uninstallation

### Complete Removal

```bash
# 1. Stop all services
./pso services stop-all

# 2. Uninstall all services
./pso services uninstall-all

# 3. Stop PSO dashboard
./pso stop

# 4. Remove systemd service (if installed)
./pso uninstall-systemd

# 5. Remove data directory
rm -rf ~/.pso_dev

# 6. Remove repository
cd ..
rm -rf personal-server-os
```

### Keep Data, Remove PSO

```bash
# Stop PSO
./pso stop

# Keep ~/.pso_dev but remove PSO code
cd ..
rm -rf personal-server-os
```

### Reinstall

```bash
# If you kept data, just re-clone and run
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os
./pso start

# If you removed data, do full install
./pso install
```

---

## Next Steps

After installation:

1. **Read the User Guide**: [USER_GUIDE.md](USER_GUIDE.md)
2. **Explore Services**: Browse the service catalog
3. **Configure Backups**: Set up automated backups
4. **Harden Security**: Review [Security Settings](USER_GUIDE.md#security-settings) and [Firewall & Tiers](USER_GUIDE.md#firewall--network-tiers)
5. **Join Community**: When we set it up (lol)

---

## Getting Help

- **Documentation**: [docs/](../)
- **FAQ**: [USER_GUIDE.md](USER_GUIDE.md#faq)

