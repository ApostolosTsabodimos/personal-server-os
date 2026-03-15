#!/usr/bin/env python3
"""
PSO Storage Manager
Manages Docker volumes, persistent data paths, and disk usage per service.
Tracks volume sizes, warns on low disk, handles creation on install and cleanup on uninstall.

CLI: pso storage status | list | inspect <service> | prune | warn-threshold <gb>
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(os.environ.get("PSO_DB_PATH", Path.home() / ".pso_dev" / "pso.db"))
DEFAULT_WARN_THRESHOLD_GB = 5.0   # Warn when free disk falls below this


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS service_volumes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT NOT NULL,
                volume_name TEXT NOT NULL,
                mount_path TEXT,
                size_bytes INTEGER DEFAULT 0,
                last_measured_at TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                UNIQUE(service_id, volume_name)
            )
        """)
        for col, typedef in [
            ("volume_name",      "TEXT"),
            ("size_bytes",       "INTEGER DEFAULT 0"),
            ("mount_path",       "TEXT"),
            ("last_measured_at", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE service_volumes ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_sv_service ON service_volumes(service_id)"
        )
        # Storage settings table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS storage_settings (
                key TEXT PRIMARY KEY,
                value TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _run(cmd: list[str], check: bool = True, timeout: int = 30) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _get_setting(key: str, default: str = None) -> str:
    try:
        conn = sqlite3.connect(DB_PATH)
        row = conn.execute("SELECT value FROM storage_settings WHERE key=?", (key,)).fetchone()
        conn.close()
        return row[0] if row else default
    except Exception:
        return default


def _set_setting(key: str, value: str):
    conn = sqlite3.connect(DB_PATH)
    conn.execute("INSERT OR REPLACE INTO storage_settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def _bytes_to_human(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def _human_to_bytes(s: str) -> int:
    """Parse '1.5 GB' → bytes."""
    s = s.strip().upper()
    units = {"B": 1, "KB": 1024, "MB": 1024**2, "GB": 1024**3, "TB": 1024**4}
    for suffix, factor in units.items():
        if s.endswith(suffix):
            return int(float(s[:-len(suffix)].strip()) * factor)
    return int(s)


# ---------------------------------------------------------------------------
# Docker volume helpers
# ---------------------------------------------------------------------------

def _list_docker_volumes() -> list[dict]:
    """List all Docker volumes."""
    try:
        result = _run(["docker", "volume", "ls", "--format", "{{json .}}"], check=False)
        volumes = []
        for line in result.stdout.strip().splitlines():
            if line.strip():
                try:
                    volumes.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
        return volumes
    except Exception:
        return []


def _get_volume_size(volume_name: str) -> int:
    """Get size of a Docker volume in bytes using a temporary Alpine container."""
    try:
        result = _run([
            "docker", "run", "--rm",
            "-v", f"{volume_name}:/data:ro",
            "alpine", "du", "-sb", "/data"
        ], check=False, timeout=30)
        if result.returncode == 0:
            parts = result.stdout.strip().split()
            if parts:
                return int(parts[0])
    except Exception:
        pass
    return 0


def _get_container_volumes(service_id: str) -> list[dict]:
    """Get volumes mounted by a container."""
    try:
        result = _run(["docker", "inspect", service_id], check=False)
        if result.returncode != 0:
            return []
        info = json.loads(result.stdout)
        if not info:
            return []
        mounts = info[0].get("Mounts", [])
        return [
            {
                "volume_name": m.get("Name", ""),
                "mount_path": m.get("Destination", ""),
                "type": m.get("Type", ""),
                "source": m.get("Source", ""),
            }
            for m in mounts
            if m.get("Type") in ("volume", "bind")
        ]
    except Exception:
        return []


def _get_installed_services() -> list[dict]:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute("SELECT id, name, status FROM installed_services").fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _docker_volume_exists(name: str) -> bool:
    try:
        result = _run(["docker", "volume", "inspect", name], check=False)
        return result.returncode == 0
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Disk space
# ---------------------------------------------------------------------------

def get_disk_usage() -> dict:
    """Get disk usage stats for the Docker data root."""
    try:
        info = _run(["docker", "info", "--format", "{{json .DockerRootDir}}"], check=False)
        docker_root = info.stdout.strip().strip('"') if info.returncode == 0 else "/var/lib/docker"
    except Exception:
        docker_root = "/var/lib/docker"

    try:
        usage = shutil.disk_usage(docker_root)
        return {
            "path": docker_root,
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent_used": usage.used / usage.total * 100,
        }
    except Exception:
        # Fall back to root filesystem
        usage = shutil.disk_usage("/")
        return {
            "path": "/",
            "total_bytes": usage.total,
            "used_bytes": usage.used,
            "free_bytes": usage.free,
            "percent_used": usage.used / usage.total * 100,
        }


def check_disk_warning() -> tuple[bool, str]:
    """Returns (warning, message). warning=True if disk is low."""
    threshold_gb = float(_get_setting("warn_threshold_gb", str(DEFAULT_WARN_THRESHOLD_GB)))
    usage = get_disk_usage()
    free_gb = usage["free_bytes"] / 1024**3

    if free_gb < threshold_gb:
        msg = (f"⚠  Low disk space: {_bytes_to_human(usage['free_bytes'])} free "
               f"({usage['percent_used']:.1f}% used). Threshold: {threshold_gb:.1f} GB")
        return True, msg
    return False, ""


# ---------------------------------------------------------------------------
# Volume management
# ---------------------------------------------------------------------------

def create_volume(service_id: str, volume_name: str, mount_path: str = None) -> bool:
    """Create a Docker volume for a service and record it in the DB."""
    _ensure_schema()

    if not _docker_volume_exists(volume_name):
        try:
            _run(["docker", "volume", "create",
                  "--label", f"pso.service={service_id}",
                  "--label", "pso.managed=true",
                  volume_name])
            print(f"  ✓ Created volume: {volume_name}")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Failed to create volume {volume_name}: {e.stderr}")
            return False
    else:
        print(f"  – Volume already exists: {volume_name}")

    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """INSERT OR REPLACE INTO service_volumes
           (service_id, volume_name, mount_path, created_at)
           VALUES (?, ?, ?, ?)""",
        (service_id, volume_name, mount_path, _now())
    )
    conn.commit()
    conn.close()
    return True


def remove_volume(volume_name: str, force: bool = False) -> bool:
    """Remove a Docker volume (only if not in use, unless force=True)."""
    cmd = ["docker", "volume", "rm"]
    if force:
        cmd.append("--force")
    cmd.append(volume_name)

    try:
        _run(cmd)
        conn = sqlite3.connect(DB_PATH)
        conn.execute("DELETE FROM service_volumes WHERE volume_name=?", (volume_name,))
        conn.commit()
        conn.close()
        print(f"  ✓ Removed volume: {volume_name}")
        return True
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Could not remove {volume_name}: {e.stderr.strip()}")
        return False


def scan_service_volumes(service_id: str):
    """Scan a service container for volumes and record/update them in the DB."""
    _ensure_schema()
    mounts = _get_container_volumes(service_id)

    conn = sqlite3.connect(DB_PATH)
    for mount in mounts:
        vol_name = mount["volume_name"] or mount["source"]
        if not vol_name:
            continue
        size = _get_volume_size(vol_name) if mount["type"] == "volume" else 0
        conn.execute(
            """INSERT OR REPLACE INTO service_volumes
               (service_id, volume_name, mount_path, size_bytes, last_measured_at, created_at)
               VALUES (?, ?, ?, ?, ?, COALESCE(
                   (SELECT created_at FROM service_volumes WHERE service_id=? AND volume_name=?),
                   datetime('now')
               ))""",
            (service_id, vol_name, mount["mount_path"], size, _now(), service_id, vol_name)
        )
    conn.commit()
    conn.close()


def measure_all_volumes():
    """Update size measurements for all tracked volumes."""
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute("SELECT DISTINCT volume_name FROM service_volumes").fetchall()
    conn.close()

    for (vol_name,) in rows:
        size = _get_volume_size(vol_name)
        conn = sqlite3.connect(DB_PATH)
        conn.execute(
            "UPDATE service_volumes SET size_bytes=?, last_measured_at=? WHERE volume_name=?",
            (size, _now(), vol_name)
        )
        conn.commit()
        conn.close()


def prune_unused_volumes() -> int:
    """Remove Docker volumes not associated with any container (docker volume prune)."""
    try:
        result = _run(["docker", "volume", "prune", "--force"])
        # Parse count from output like "Total reclaimed space: 1.2GB"
        print(result.stdout.strip())
        return 0
    except subprocess.CalledProcessError as e:
        print(f"  ✗ Prune failed: {e.stderr}")
        return 0


def cleanup_service(service_id: str, remove_volumes: bool = False):
    """Clean up volumes for an uninstalled service."""
    if not remove_volumes:
        return

    conn = sqlite3.connect(DB_PATH)
    rows = conn.execute(
        "SELECT volume_name FROM service_volumes WHERE service_id=?", (service_id,)
    ).fetchall()
    conn.close()

    for (vol_name,) in rows:
        remove_volume(vol_name)


# ---------------------------------------------------------------------------
# CLI display
# ---------------------------------------------------------------------------

def cmd_status():
    _ensure_schema()

    # Disk usage
    usage = get_disk_usage()
    warn, warn_msg = check_disk_warning()

    print(f"\n  Disk Usage ({usage['path']})")
    print(f"  {'─'*50}")
    bar_filled = int(usage["percent_used"] / 100 * 30)
    bar = "█" * bar_filled + "░" * (30 - bar_filled)
    print(f"  Used:  {_bytes_to_human(usage['used_bytes'])} / {_bytes_to_human(usage['total_bytes'])} [{bar}] {usage['percent_used']:.1f}%")
    print(f"  Free:  {_bytes_to_human(usage['free_bytes'])}")
    if warn:
        print(f"\n  {warn_msg}")

    # Volume summary
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        """SELECT service_id, COUNT(*) as count, SUM(size_bytes) as total_bytes
           FROM service_volumes GROUP BY service_id ORDER BY total_bytes DESC"""
    ).fetchall()
    conn.close()

    if rows:
        print(f"\n  {'SERVICE':<25} {'VOLUMES':>8} {'SIZE':>12}")
        print(f"  {'─'*25} {'─'*8} {'─'*12}")
        for row in rows:
            size = _bytes_to_human(row["total_bytes"] or 0)
            print(f"  {row['service_id']:<25} {row['count']:>8} {size:>12}")
    else:
        print("\n  No volumes tracked. Run: pso storage scan")
    print()


def cmd_list():
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM service_volumes ORDER BY service_id, volume_name"
    ).fetchall()
    conn.close()

    if not rows:
        print("  No volumes tracked.")
        return

    print(f"\n  {'SERVICE':<20} {'VOLUME':<30} {'MOUNT':<25} {'SIZE':>10}")
    print(f"  {'─'*20} {'─'*29} {'─'*24} {'─'*10}")
    for row in rows:
        size = _bytes_to_human(row["size_bytes"] or 0)
        mount = (row["mount_path"] or "")[:24]
        print(f"  {row['service_id']:<20} {row['volume_name']:<30} {mount:<25} {size:>10}")
    print()


def cmd_inspect(service_id: str):
    print(f"\n  Scanning volumes for {service_id}...")
    scan_service_volumes(service_id)
    cmd_list_service(service_id)


def cmd_list_service(service_id: str):
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT * FROM service_volumes WHERE service_id=? ORDER BY volume_name",
        (service_id,)
    ).fetchall()
    conn.close()

    if not rows:
        print(f"  No volumes found for {service_id}")
        return

    for row in rows:
        size = _bytes_to_human(row["size_bytes"] or 0)
        ts = (row["last_measured_at"] or "never")[:19].replace("T", " ")
        print(f"  Volume: {row['volume_name']}")
        print(f"    Mount:    {row['mount_path'] or '?'}")
        print(f"    Size:     {size}  (measured: {ts})")
    print()


def cmd_prune():
    warn, _ = check_disk_warning()
    print("Pruning unused Docker volumes...")
    prune_unused_volumes()
    if warn:
        new_warn, new_msg = check_disk_warning()
        if new_warn:
            print(f"\n  {new_msg}")
        else:
            print("\n  ✓ Disk space warning cleared after prune")


def cmd_scan():
    print("Scanning volumes for all services...")
    services = _get_installed_services()
    for svc in services:
        scan_service_volumes(svc["id"])
        print(f"  ✓ {svc['id']}")
    print("Done.")


def cmd_warn_threshold(args: list[str]):
    if not args:
        current = _get_setting("warn_threshold_gb", str(DEFAULT_WARN_THRESHOLD_GB))
        print(f"  Current warn threshold: {current} GB")
        return
    try:
        gb = float(args[0])
        _set_setting("warn_threshold_gb", str(gb))
        print(f"  ✓ Warn threshold set to {gb} GB")
    except ValueError:
        print(f"  ✗ Invalid value: {args[0]}")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] = None):
    args = args or sys.argv[1:]
    sub = args[0] if args else "status"

    if sub == "status":
        cmd_status()
    elif sub == "list":
        cmd_list()
    elif sub == "inspect" and len(args) >= 2:
        cmd_inspect(args[1])
    elif sub == "scan":
        cmd_scan()
    elif sub == "prune":
        cmd_prune()
    elif sub == "warn-threshold":
        cmd_warn_threshold(args[1:])
    elif sub == "create" and len(args) >= 3:
        create_volume(args[1], args[2], args[3] if len(args) > 3 else None)
    elif sub == "remove" and len(args) >= 2:
        remove_volume(args[1])
    else:
        print("Usage: pso storage [status|list|inspect <svc>|scan|prune|warn-threshold [gb]|create <svc> <vol>|remove <vol>]")


if __name__ == "__main__":
    main()