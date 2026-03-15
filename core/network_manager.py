#!/usr/bin/env python3
"""
PSO Network Manager
Manages Docker networks for PSO services.

Networks:
  pso-internal  — isolated, no internet, services talk to each other by name
  pso-external  — internet access for services that need it (Tier 3/4)

Tier assignment (from firewall_manager):
  Internal (1) → pso-internal only
  LAN      (2) → pso-internal only
  VPN      (3) → pso-internal + pso-external
  Internet (4) → pso-internal + pso-external

CLI: pso network status | create | list | assign <service> <network> | inspect <service>
"""

import json
import sqlite3
import subprocess
import sys
from pathlib import Path

DB_PATH = Path.home() / ".pso_dev" / "pso.db"

PSO_INTERNAL = "pso-internal"
PSO_EXTERNAL = "pso-external"

# Tiers that get internet access
INTERNET_TIERS = {3, 4}  # VPN, Internet


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_networks (
                service_id TEXT NOT NULL,
                network_name TEXT NOT NULL,
                assigned_at TEXT DEFAULT (datetime('now')),
                PRIMARY KEY (service_id, network_name)
            )
        """)
        # Extend installed_services with network_id if not present
        try:
            conn.execute("ALTER TABLE installed_services ADD COLUMN primary_network TEXT DEFAULT 'pso-internal'")
        except sqlite3.OperationalError:
            pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sn_service ON service_networks(service_id)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Docker helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _docker_network_exists(name: str) -> bool:
    try:
        result = _run(["docker", "network", "ls", "--filter", f"name=^{name}$", "--format", "{{.Name}}"], check=False)
        return name in result.stdout.strip().split("\n")
    except Exception:
        return False


def _docker_network_inspect(name: str) -> dict:
    try:
        result = _run(["docker", "network", "inspect", name], check=False)
        if result.returncode == 0:
            data = json.loads(result.stdout)
            return data[0] if data else {}
    except Exception:
        pass
    return {}


def _docker_container_exists(name: str) -> bool:
    try:
        result = _run(["docker", "inspect", name], check=False)
        return result.returncode == 0
    except Exception:
        return False


def _get_service_tier(service_id: str) -> int:
    """Get the firewall tier for a service from the DB."""
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute(
            "SELECT tier FROM installed_services WHERE id=?", (service_id,)
        ).fetchone()
        conn.close()
        return int(row[0]) if row and row[0] else 1
    except Exception:
        return 1


def _get_all_services() -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, status, tier, primary_network FROM installed_services"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


# ---------------------------------------------------------------------------
# Core operations
# ---------------------------------------------------------------------------

def create_networks() -> bool:
    """Create pso-internal and pso-external Docker networks if they don't exist."""
    ok = True

    # pso-internal: isolated bridge, no internet
    if not _docker_network_exists(PSO_INTERNAL):
        try:
            _run([
                "docker", "network", "create",
                "--driver", "bridge",
                "--internal",  # no external connectivity
                "--label", "pso.managed=true",
                "--label", "pso.network=internal",
                PSO_INTERNAL,
            ])
            print(f"  ✓ Created network: {PSO_INTERNAL} (isolated)")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to create {PSO_INTERNAL}: {e.stderr}")
            ok = False
    else:
        print(f"  – {PSO_INTERNAL} already exists")

    # pso-external: standard bridge with internet access
    if not _docker_network_exists(PSO_EXTERNAL):
        try:
            _run([
                "docker", "network", "create",
                "--driver", "bridge",
                "--label", "pso.managed=true",
                "--label", "pso.network=external",
                PSO_EXTERNAL,
            ])
            print(f"  ✓ Created network: {PSO_EXTERNAL} (internet access)")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to create {PSO_EXTERNAL}: {e.stderr}")
            ok = False
    else:
        print(f"  – {PSO_EXTERNAL} already exists")

    return ok


def assign_service(service_id: str, network: str, disconnect_others: bool = False) -> bool:
    """Connect a service container to a network."""
    if not _docker_container_exists(service_id):
        print(f"  ✗ Container not found: {service_id}")
        return False

    if not _docker_network_exists(network):
        print(f"  ✗ Network not found: {network}. Run: pso network create")
        return False

    try:
        # Check if already connected
        info = _docker_network_inspect(network)
        containers = info.get("Containers", {})
        already_connected = any(
            c.get("Name") == service_id for c in containers.values()
        )

        if already_connected:
            print(f"  – {service_id} already on {network}")
            return True

        _run(["docker", "network", "connect", network, service_id])
        print(f"  ✓ Connected {service_id} → {network}")

        # Record in DB
        _ensure_schema()
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "INSERT OR REPLACE INTO service_networks (service_id, network_name) VALUES (?, ?)",
            (service_id, network)
        )
        conn.commit()
        conn.close()
        return True

    except subprocess.CalledProcessError as e:
        print(f"  ✗ Failed: {e.stderr}")
        return False


def assign_service_by_tier(service_id: str) -> bool:
    """Assign a service to the correct networks based on its tier."""
    tier = _get_service_tier(service_id)
    ok = True

    # All services get internal network
    ok = assign_service(service_id, PSO_INTERNAL) and ok

    # Tier 3+ get external network too
    if tier in INTERNET_TIERS:
        ok = assign_service(service_id, PSO_EXTERNAL) and ok
    else:
        # Make sure it's NOT on external if tier dropped
        _disconnect_if_connected(service_id, PSO_EXTERNAL)

    return ok


def _disconnect_if_connected(service_id: str, network: str):
    try:
        info = _docker_network_inspect(network)
        containers = info.get("Containers", {})
        connected = any(c.get("Name") == service_id for c in containers.values())
        if connected:
            _run(["docker", "network", "disconnect", network, service_id], check=False)
            print(f"  – Disconnected {service_id} from {network} (tier too low)")
    except Exception:
        pass


def sync_all_services():
    """Assign all installed services to correct networks based on their tier."""
    _ensure_schema()
    if not create_networks():
        return

    services = _get_all_services()
    if not services:
        print("  No services installed.")
        return

    for svc in services:
        print(f"  {svc['id']} (tier {svc.get('tier', 1)}):")
        assign_service_by_tier(svc["id"])


# ---------------------------------------------------------------------------
# Status display
# ---------------------------------------------------------------------------

def cmd_status():
    _ensure_schema()

    print("\n  PSO Network Status")
    print(f"  {'─'*50}")

    for net_name in [PSO_INTERNAL, PSO_EXTERNAL]:
        exists = _docker_network_exists(net_name)
        if not exists:
            print(f"  ✗ {net_name:<20} NOT CREATED")
            continue

        info = _docker_network_inspect(net_name)
        driver = info.get("Driver", "?")
        internal = info.get("Internal", False)
        containers = info.get("Containers", {})
        label = "(isolated)" if internal else "(internet)"

        print(f"\n  ✓ {net_name} [{driver}] {label}")
        print(f"    Containers: {len(containers)}")
        for c in containers.values():
            print(f"      • {c.get('Name', '?'):<25} {c.get('IPv4Address', '?')}")

    # DB records
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT service_id, network_name, assigned_at FROM service_networks ORDER BY service_id"
    ).fetchall()
    conn.close()

    if rows:
        print(f"\n  {'SERVICE':<25} {'NETWORK':<20} ASSIGNED")
        print(f"  {'─'*25} {'─'*19} {'─'*20}")
        for row in rows:
            ts = row["assigned_at"][:19] if row["assigned_at"] else "?"
            print(f"  {row['service_id']:<25} {row['network_name']:<20} {ts}")
    print()


def cmd_list():
    """List all Docker networks (not just PSO-managed ones)."""
    try:
        result = _run(["docker", "network", "ls", "--format",
                       "table {{.ID}}\t{{.Name}}\t{{.Driver}}\t{{.Scope}}"], check=False)
        print(result.stdout)
    except Exception as e:
        print(f"  ✗ docker network ls failed: {e}")


def cmd_inspect(service_id: str):
    """Show which networks a service container is connected to."""
    if not _docker_container_exists(service_id):
        print(f"  ✗ Container not found: {service_id}")
        return

    try:
        result = _run(["docker", "inspect", service_id])
        info = json.loads(result.stdout)[0]
        nets = info.get("NetworkSettings", {}).get("Networks", {})
        print(f"\n  Networks for {service_id}:")
        for net_name, net_info in nets.items():
            ip = net_info.get("IPAddress", "?")
            print(f"    • {net_name:<25} {ip}")
        print()
    except Exception as e:
        print(f"  ✗ Inspect failed: {e}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] = None):
    args = args or sys.argv[1:]
    sub = args[0] if args else "status"

    if sub == "status":
        cmd_status()
    elif sub == "create":
        print("Creating PSO networks...")
        create_networks()
    elif sub == "list":
        cmd_list()
    elif sub == "assign" and len(args) >= 3:
        assign_service(args[1], args[2])
    elif sub == "assign-tier" and len(args) >= 2:
        assign_service_by_tier(args[1])
    elif sub == "sync":
        print("Syncing all services to correct networks...")
        sync_all_services()
    elif sub == "inspect" and len(args) >= 2:
        cmd_inspect(args[1])
    else:
        print("Usage: pso network [status|create|list|sync|assign <svc> <net>|inspect <svc>]")


if __name__ == "__main__":
    main()