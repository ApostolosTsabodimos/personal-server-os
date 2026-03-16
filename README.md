# PSO - Personal Server OS

> **Self-hosted service management platform with one-click Docker deployments**

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)


---

## Features

- Service deployment from web dashboard
- Docker-based containerization for all services
- JWT authentication with encrypted secrets storage
- Resource monitoring (CPU, RAM, disk, network)
- Automatic health checks with configurable intervals
- Automated backup and restore functionality
- Web UI with dark/light theme support
- Comprehensive activity logging
- 20+ pre-configured service manifests

---

## Currently Supported Services

**Media & Entertainment**
- Jellyfin (Media Server)
- Immich (Photo Management)
- Tautulli (Plex Analytics)

**Productivity**
- Nextcloud AIO (File Sync & Office)
- Docmost (Documentation)
- Trilium (Note Taking)
- Firefly III (Finance Manager)

**Network & Infrastructure**
- Pi-hole (Network-wide Ad Blocking)
- Nginx (Web Server)
- Portainer (Docker Management)
- Uptime Kuma (Monitoring)
- Grafana (Metrics & Dashboards)

**Smart Home**
- Home Assistant (Home Automation)
- Zigbee2MQTT (Zigbee Gateway)
- Mosquitto (MQTT Broker)

**Security & Privacy**
- Vaultwarden (Password Manager)
- AirVPN (VPN Client)

**Download Management**
- Prowlarr (Indexer Manager)

**And more...** [View full service catalog](services/)

---

## Quick Start

### Prerequisites

- **OS**: Linux (Arch, Manjaro, Ubuntu, Debian, Fedora, etc.)
- **Python**: 3.10 or higher
- **Docker**: Latest version
- **RAM**: 2GB minimum (4GB+ recommended)
- **Disk**: 20GB+ free space

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os

# 2. Run the installer
./pso install

# 3. Start the dashboard
./pso start

# 4. Open in your browser
# http://localhost:5000
# Default credentials: admin / admin (change immediately!)
```

For detailed installation instructions, see [INSTALL.md](docs/INSTALL.md)

---

## Documentation

- **[Installation Guide](docs/INSTALL.md)** - Step-by-step setup instructions
- **[User Guide](docs/USER_GUIDE.md)** - Complete guide to using PSO
- **[Reference](docs/REFERENCE.md)** - CLI commands, API endpoints, technical details
- **[Architecture](docs/ARCHITECTURE.md)** - System design and components
- **[Roadmap](ROADMAP.md)** - Future features and development plans

---

## Usage

### Managing Services

```bash
# List available services
./pso services list

# Install a service (e.g., Jellyfin)
./pso services install jellyfin

# Start/stop a service
./pso services start jellyfin
./pso services stop jellyfin

# View logs
./pso services logs jellyfin

# Uninstall a service
./pso services uninstall jellyfin
```

### Dashboard Operations

```bash
# Start the web dashboard
./pso start

# Stop the dashboard
./pso stop

# Check system status
./pso status

# View all commands
./pso help
```

### Web Dashboard

Access the dashboard at `http://localhost:5000`

- **Services Tab**: Install, start, stop, and manage services
- **System Metrics**: View CPU, RAM, disk usage
- **Activity Log**: Track system events
- **Backups**: Schedule and manage backups
- **Settings**: Configure authentication, notifications, etc.

---

## Security Tiers

PSO uses a **tier-based firewall system** to control network exposure:

- **Tier 0 (Internal)**: Localhost only - most secure (default)
- **Tier 1 (LAN)**: Local network access - for family services
- **Tier 2 (VPN)**: VPN access only - for remote access
- **Tier 3 (Public)**: Internet-facing - use sparingly

All services start at Tier 0 and can be promoted as needed. See [docs/INSTALL.md](docs/INSTALL.md#understanding-security-tiers-the-way-of-the-onion) for details.

---

## Security

PSO implements multiple security layers:

- **Authentication**: JWT-based with configurable session timeout
- **Secrets Management**: AES-256 encrypted credential storage
- **Audit Logging**: All actions tracked with timestamps
- **Network Isolation**: Services isolated by default (localhost-only)
- **No Root Required**: Runs entirely in user space
- **Regular Updates**: Security patches and dependency updates

**Default Security**:
- All services bind to `127.0.0.1` (localhost only)
- No external network access by default
- Secrets stored encrypted on disk
- Password hashing with bcrypt
- Tier-based firewall system for controlled network exposure

See [Security Settings](docs/USER_GUIDE.md#security-settings) and [Firewall & Tiers](docs/USER_GUIDE.md#firewall--network-tiers) for details

---

## Architecture

```
PSO Architecture
┌─────────────────────────────────────────────────┐
│  Web Dashboard (Flask + React)                  │
│  - Authentication & Authorization               │
│  - Service Management UI                        │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│  Core Engine (Python)                           │
│  - Service Manager  - Health Monitor            │
│  - Docker Manager   - Backup Manager            │
│  - Config Manager   - Update Monitor            │
└─────────────────┬───────────────────────────────┘
                  │
┌─────────────────▼───────────────────────────────┐
│  Docker Engine                                  │
│  - Container Orchestration                      │
│  - Network & Volume Management                  │
└─────────────────────────────────────────────────┘
```

Components:
- **Web Dashboard**: Flask API + React frontend
- **Core Engine**: Python modules for service lifecycle
- **Database**: SQLite for metadata and state
- **Secrets Vault**: Encrypted credential storage
- **Docker**: Container runtime for all services

See [ARCHITECTURE.md](docs/ARCHITECTURE.md) for detailed design.

---

## Roadmap

### Current Status: Phase 1 (Prototype)

**Completed** 
- Service installation and management
- Web dashboard with authentication
- Docker integration
- Health monitoring
- Backup system
- Activity logging

**In Progress** 
- Security hardening (rate limiting, 2FA)
- Real-time WebSocket updates
- Comprehensive documentation
- Cross-platform testing

**Planned** 
- Local AI integration (Ollama?)
- Multi-server federation
- Vite build system migration
- Mobile app
- Plugin system

See [ROADMAP.md](ROADMAP.md) for development timeline.

---

### Development Setup

```bash
# Clone your fork
git clone https://github.com/ApostolosTsampodimos/personal-server-os.git
cd personal-server-os

# Install development dependencies
pip install -r requirements-dev.txt

# Run tests
./pso-check

# Run the dashboard in dev mode
./pso start --dev
```

---

## Project Stats

- **Services**: 20+ pre-configured
- **Active Development**: Yes
- **Status**: Prototype (v0.1.0)

---

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## Acknowledgments

PSO is built on top of open-source projects:

- **Docker** - Container runtime
- **Flask** - Web framework
- **React** - UI library
- **SQLite** - Database
- All the service developers (Jellyfin, Nextcloud, Pi-hole, etc.)

### Development Tools

This project was developed with assistance from **Claude** (Anthropic) for:
- Architecture design and code structure
- Documentation writing and organization
- Security best practices implementation
- Code review and optimization

The core concepts, design decisions, and project vision are entirely original.
