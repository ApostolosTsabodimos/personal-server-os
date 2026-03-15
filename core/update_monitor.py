#!/usr/bin/env python3
"""
PSO Update Monitor
Polls Docker Hub and GitHub Releases for newer versions of installed services.
Writes findings to the update_checks table — does NOT apply updates.
CLI: pso update-monitor status | start | stop | check-now | history
"""

import json
import sqlite3
import subprocess
import threading
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path


DB_PATH = Path.home() / ".pso_dev" / "pso.db"
PID_FILE = Path.home() / ".pso_dev" / "update_monitor.pid"
LOG_FILE = Path.home() / ".pso_dev" / "update_monitor.log"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS update_checks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT NOT NULL,
                current_version TEXT,
                latest_version TEXT,
                source TEXT,
                update_available INTEGER DEFAULT 0,
                checked_at TEXT NOT NULL,
                error TEXT
            )
        """)
        # Add columns that may be missing from older schema
        for col, typedef in [
            ("source", "TEXT"),
            ("error", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE update_checks ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass  # already exists
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uc_service ON update_checks(service_id)"
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uc_checked ON update_checks(checked_at)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Version fetching
# ---------------------------------------------------------------------------

def _http_get_json(url: str, timeout: int = 10) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "PSO-UpdateMonitor/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def _fetch_dockerhub_latest(image: str) -> str | None:
    """Return the most recent non-latest tag from Docker Hub for an image."""
    # image may be 'nginx', 'library/nginx', or 'user/repo'
    parts = image.split("/")
    if len(parts) == 1:
        repo = f"library/{image}"
    else:
        repo = "/".join(parts)
    url = f"https://hub.docker.com/v2/repositories/{repo}/tags?page_size=10&ordering=last_updated"
    try:
        data = _http_get_json(url)
        tags = [t["name"] for t in data.get("results", []) if t["name"] != "latest"]
        return tags[0] if tags else None
    except Exception:
        return None


def _fetch_github_latest(repo: str) -> str | None:
    """Return the latest release tag from a GitHub repo (owner/repo)."""
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    try:
        data = _http_get_json(url)
        return data.get("tag_name")
    except Exception:
        return None


def _get_installed_services() -> list[dict]:
    """Return list of installed services with their current image/version info."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, name, docker_image, version FROM installed_services WHERE status = 'running'"
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]
    except Exception:
        return []


def _get_manifest_update_source(service_id: str) -> dict | None:
    """Read the service manifest to find update_source config."""
    services_dir = Path.cwd() / "services"
    manifest_path = services_dir / service_id / "manifest.json"
    if not manifest_path.exists():
        return None
    try:
        with open(manifest_path) as f:
            manifest = json.load(f)
        return manifest.get("update_source")  # e.g. {"type": "dockerhub", "image": "nginx"} or {"type": "github", "repo": "owner/repo"}
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Core check logic
# ---------------------------------------------------------------------------

def check_service(service: dict) -> dict:
    """
    Check a single service for updates.
    Returns a result dict suitable for inserting into update_checks.
    """
    service_id = service["id"]
    current_version = service.get("version") or "unknown"
    now = datetime.now(timezone.utc).isoformat()

    result = {
        "service_id": service_id,
        "current_version": current_version,
        "latest_version": None,
        "source": None,
        "update_available": 0,
        "checked_at": now,
        "error": None,
    }

    # Try manifest update_source first
    update_source = _get_manifest_update_source(service_id)

    latest = None
    source_label = None

    if update_source:
        src_type = update_source.get("type", "")
        if src_type == "dockerhub":
            image = update_source.get("image", service_id)
            latest = _fetch_dockerhub_latest(image)
            source_label = f"dockerhub:{image}"
        elif src_type == "github":
            repo = update_source.get("repo", "")
            latest = _fetch_github_latest(repo)
            source_label = f"github:{repo}"
    else:
        # Fall back: try docker image field
        docker_image = service.get("docker_image", "")
        if docker_image:
            image_name = docker_image.split(":")[0]
            latest = _fetch_dockerhub_latest(image_name)
            source_label = f"dockerhub:{image_name}"

    if latest is None:
        result["error"] = "Could not determine latest version"
    else:
        result["latest_version"] = latest
        result["source"] = source_label
        # Simple string comparison — not semver-aware, but good enough for most tags
        if latest != current_version and latest != "latest":
            result["update_available"] = 1

    return result


def check_all_services() -> list[dict]:
    """Check all running services and write results to DB."""
    _ensure_schema()
    services = _get_installed_services()

    if not services:
        _log("No running services found to check.")
        return []

    results = []
    conn = sqlite3.connect(DB_PATH)
    try:
        for service in services:
            _log(f"Checking {service['id']}...")
            result = check_service(service)
            conn.execute(
                """INSERT INTO update_checks
                   (service_id, current_version, latest_version, source, update_available, checked_at, error)
                   VALUES (:service_id, :current_version, :latest_version, :source, :update_available, :checked_at, :error)""",
                result,
            )
            results.append(result)
        conn.commit()
    finally:
        conn.close()

    updates_found = sum(1 for r in results if r["update_available"])
    _log(f"Check complete: {len(results)} services checked, {updates_found} updates available.")
    return results


# ---------------------------------------------------------------------------
# Background daemon
# ---------------------------------------------------------------------------

def _log(msg: str):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{ts}] {msg}"
    print(line)
    try:
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _run_daemon(interval_minutes: int = 60):
    """Background polling loop."""
    _log(f"Update monitor started (interval: {interval_minutes}m)")
    while True:
        try:
            check_all_services()
        except Exception as e:
            _log(f"Error during check: {e}")
        time.sleep(interval_minutes * 60)


def start_daemon(interval_minutes: int = 60):
    """Start the monitor as a background thread and write PID file."""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    PID_FILE.write_text(str(__import__("os").getpid()))
    t = threading.Thread(target=_run_daemon, args=(interval_minutes,), daemon=True)
    t.start()
    return t


# ---------------------------------------------------------------------------
# CLI helpers
# ---------------------------------------------------------------------------

def _format_row(result: dict) -> str:
    avail = "⬆  YES" if result["update_available"] else "   -  "
    current = (result["current_version"] or "?")[:15]
    latest = (result["latest_version"] or "?")[:15]
    err = f"  [!] {result['error']}" if result["error"] else ""
    return f"  {result['service_id']:<20} {current:<16} {latest:<16} {avail}{err}"


def cmd_status():
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # Latest check per service
    rows = conn.execute("""
        SELECT uc.*
        FROM update_checks uc
        INNER JOIN (
            SELECT service_id, MAX(checked_at) AS max_checked
            FROM update_checks
            GROUP BY service_id
        ) latest ON uc.service_id = latest.service_id AND uc.checked_at = latest.max_checked
        ORDER BY uc.service_id
    """).fetchall()
    conn.close()

    if not rows:
        print("  No update checks on record. Run: pso update-monitor check-now")
        return

    print(f"\n  {'SERVICE':<20} {'CURRENT':<16} {'LATEST':<16} UPDATE")
    print(f"  {'─'*20} {'─'*15} {'─'*15} {'─'*10}")
    for row in rows:
        print(_format_row(dict(row)))
    print()


def cmd_check_now():
    print("Checking all services for updates...")
    results = check_all_services()
    if not results:
        print("  No services checked.")
        return
    print(f"\n  {'SERVICE':<20} {'CURRENT':<16} {'LATEST':<16} UPDATE")
    print(f"  {'─'*20} {'─'*15} {'─'*15} {'─'*10}")
    for r in results:
        print(_format_row(r))
    print()


def cmd_history(service_id: str = None, limit: int = 20):
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if service_id:
        rows = conn.execute(
            "SELECT * FROM update_checks WHERE service_id=? ORDER BY checked_at DESC LIMIT ?",
            (service_id, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM update_checks ORDER BY checked_at DESC LIMIT ?", (limit,)
        ).fetchall()
    conn.close()

    if not rows:
        print("  No history found.")
        return

    print(f"\n  {'TIME':<22} {'SERVICE':<20} {'CURRENT':<14} {'LATEST':<14} UPDATE")
    print(f"  {'─'*22} {'─'*19} {'─'*13} {'─'*13} {'─'*6}")
    for row in rows:
        r = dict(row)
        avail = "YES" if r["update_available"] else "-"
        ts = r["checked_at"][:19].replace("T", " ")
        current = (r["current_version"] or "?")[:13]
        latest = (r["latest_version"] or "?")[:13]
        print(f"  {ts:<22} {r['service_id']:<20} {current:<14} {latest:<14} {avail}")
    print()


def cmd_start(interval: int = 60):
    print(f"Starting update monitor daemon (interval: {interval}m)...")
    t = start_daemon(interval)
    print("  Monitor running. Press Ctrl+C to stop.")
    try:
        t.join()
    except KeyboardInterrupt:
        print("\n  Stopped.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main(args: list[str] = None):
    import sys
    args = args or sys.argv[1:]
    sub = args[0] if args else "status"

    if sub == "status":
        cmd_status()
    elif sub == "check-now":
        cmd_check_now()
    elif sub == "history":
        service_id = args[1] if len(args) > 1 else None
        cmd_history(service_id)
    elif sub == "start":
        interval = int(args[1]) if len(args) > 1 else 60
        cmd_start(interval)
    else:
        print(f"Unknown subcommand: {sub}")
        print("Usage: pso update-monitor [status|check-now|history [service]|start [interval_minutes]]")


if __name__ == "__main__":
    main()