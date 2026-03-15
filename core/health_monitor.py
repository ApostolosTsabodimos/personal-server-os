#!/usr/bin/env python3
"""
PSO Health Monitor - Component #17

Continuous health checks for all installed services.
Stores results in SQLite, detects outages, triggers recovery.

Usage:
    python3 -m core.health_monitor status
    python3 -m core.health_monitor check <service>
    python3 -m core.health_monitor history <service>
    python3 -m core.health_monitor start          # background daemon
"""

import json
import socket
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

CHECK_INTERVAL = 60       # seconds between checks
OUTAGE_THRESHOLD = 3      # consecutive failures before "down"
HISTORY_KEEP_DAYS = 30


# ─────────────────────────────────────────────────────────────────────────────
# Database schema (appended to PSO's existing SQLite DB)
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_TABLES = {
    "health_checks": """
        CREATE TABLE IF NOT EXISTS health_checks (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id  TEXT    NOT NULL,
            checked_at  TEXT    NOT NULL,
            status      TEXT    NOT NULL,
            latency_ms  REAL,
            detail      TEXT
        )""",
    "health_outages": """
        CREATE TABLE IF NOT EXISTS health_outages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            service_id   TEXT NOT NULL,
            started_at   TEXT NOT NULL,
            resolved_at  TEXT,
            duration_sec REAL,
            detail       TEXT
        )""",
}

SCHEMA_INDEXES = [
    "CREATE INDEX IF NOT EXISTS idx_health_checks_service ON health_checks(service_id, checked_at DESC)",
]

# Required columns per table — used for migration when table already exists
REQUIRED_COLUMNS = {
    "health_checks": {
        "service_id": "TEXT NOT NULL DEFAULT ''",
        "checked_at": "TEXT NOT NULL DEFAULT ''",
        "status":     "TEXT NOT NULL DEFAULT 'unknown'",
        "latency_ms": "REAL",
        "detail":     "TEXT",
    },
    "health_outages": {
        "service_id":   "TEXT NOT NULL DEFAULT ''",
        "started_at":   "TEXT NOT NULL DEFAULT ''",
        "resolved_at":  "TEXT",
        "duration_sec": "REAL",
        "detail":       "TEXT",
    },
}


def _ensure_schema(db_path):
    """
    Create tables if missing, add any missing columns if table already exists.
    Opens its OWN raw connection — never called inside _get_connection().
    """
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")

        # Step 1: create tables if missing
        for table, ddl in SCHEMA_TABLES.items():
            conn.execute(ddl)

        # Step 2: migrate — add missing columns BEFORE creating indexes that use them
        for table, cols in REQUIRED_COLUMNS.items():
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table})")}
            for col_name, col_def in cols.items():
                if col_name not in existing:
                    try:
                        conn.execute(f"ALTER TABLE {table} ADD COLUMN {col_name} {col_def}")
                    except Exception as e:
                        print(f"[health monitor] check error: {e}", file=sys.stderr)

        # Step 3: indexes (all columns guaranteed to exist now)
        for idx in SCHEMA_INDEXES:
            try:
                conn.execute(idx)
            except Exception as e:
                print(f"[health monitor] check error: {e}", file=sys.stderr)

        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Core checker
# ─────────────────────────────────────────────────────────────────────────────

class HealthChecker:
    """
    Checks a single service by probing its Docker container and,
    if a port is known, making a TCP connection.
    """

    def check(self, service_id: str, service_data: Dict) -> Dict[str, Any]:
        """
        Run a health check and return a result dict.

        Returns:
            {
                service_id, status, latency_ms, detail, checked_at
            }
        """
        result = {
            "service_id": service_id,
            "status":     "unknown",
            "latency_ms": None,
            "detail":     "",
            "checked_at": datetime.now().isoformat(),
        }

        # 1. Docker container check
        container_status = self._check_container(service_id)
        if container_status == "not_found":
            result["status"] = "unreachable"
            result["detail"] = "Container not found"
            return result
        if container_status != "running":
            result["status"] = "unhealthy"
            result["detail"] = f"Container status: {container_status}"
            return result

        # 2. TCP port probe (if port known)
        ports = service_data.get("ports", {})
        if ports:
            port = next(iter(ports.values()))
            ok, latency, err = self._probe_port("127.0.0.1", port, service_id=service_id)
            result["latency_ms"] = round(latency * 1000, 2) if latency else None
            if ok:
                result["status"] = "healthy"
                result["detail"] = f"Responding on :{port}"
            else:
                result["status"] = "unhealthy"
                result["detail"] = f"Port {port} unreachable: {err}"
        else:
            # Container running, no port to probe → assume healthy
            result["status"] = "healthy"
            result["detail"] = "Container running (no port configured)"

        return result

    def _check_container(self, service_id: str) -> str:
        """Return Docker container status string, or 'not_found'."""
        try:
            import docker
            client = docker.from_env()
            container = client.containers.get(f"pso-{service_id}")
            return container.status          # running / exited / paused / ...
        except Exception:
            return "not_found"

    def _probe_port(self, host: str, port: int, timeout: float = 3.0,
                    service_id: str = None):
        """
        TCP probe. Tries docker exec first (avoids host iptables issues),
        falls back to direct TCP connect if container not found.
        """
        start = time.monotonic()

        # Try via docker exec — reliable even when host bridge traffic is blocked
        if service_id:
            try:
                import docker as _docker
                client = _docker.from_env()
                container = client.containers.get(f"pso-{service_id}")
                result = container.exec_run(
                    ['sh', '-c', f'nc -z -w {int(timeout)} 127.0.0.1 {port}'],
                    demux=False
                )
                latency = time.monotonic() - start
                if result.exit_code == 0:
                    return True, latency, None
                else:
                    return False, None, f"Port {port} not responding inside container"
            except Exception:
                pass  # fall through to direct TCP

        # Fallback: direct TCP from host
        try:
            with socket.create_connection((host, port), timeout=timeout):
                return True, time.monotonic() - start, None
        except OSError as e:
            return False, None, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Health Monitor — stores results, tracks outages
# ─────────────────────────────────────────────────────────────────────────────

class HealthMonitor:
    """
    Orchestrates health checks for all services.
    Keeps running failure counts to detect outages and auto-resolve them.
    """

    def __init__(self, db=None, service_manager=None):
        from core.database import Database
        self.db = db or Database()
        self.service_manager = service_manager
        self.checker = HealthChecker()
        self._failure_counts: Dict[str, int] = {}
        self._open_outages: Dict[str, str] = {}     # service_id → started_at
        _ensure_schema(self.db.db_path)   # safe: opens its own raw connection

    def _ensure_schema(self):
        pass  # kept for compat, real work done in __init__

    # ── Public API ────────────────────────────────────────────────────────────

    def check_service(self, service_id: str) -> Dict[str, Any]:
        """Run a single check, store result, update outage tracking."""
        service = self.db.get_service(service_id)
        if not service:
            return {"service_id": service_id, "status": "unknown",
                    "detail": "Not found in PSO database"}

        result = self.checker.check(service_id, service)
        self._store_result(result)
        self._update_outage_tracking(service_id, result["status"])
        return result

    def check_all(self) -> List[Dict[str, Any]]:
        """Check every installed service."""
        services = self.db.list_services()
        return [self.check_service(s["service_id"]) for s in services]

    def get_status(self) -> List[Dict[str, Any]]:
        """Return latest health result for every service."""
        services = self.db.list_services()
        results = []
        for s in services:
            last = self._get_last_result(s["service_id"])
            results.append(last or {
                "service_id": s["service_id"],
                "status":     "never_checked",
                "detail":     "Run 'pso health check <service>'",
                "checked_at": None,
                "latency_ms": None,
            })
        return results

    def get_history(self, service_id: str, limit: int = 50) -> List[Dict]:
        """Return recent check history for one service."""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT service_id, checked_at, status, latency_ms, detail
                FROM health_checks
                WHERE service_id = ?
                ORDER BY checked_at DESC
                LIMIT ?
            """, (service_id, limit)).fetchall()
        return [dict(r) for r in rows]

    def get_outages(self, service_id: Optional[str] = None) -> List[Dict]:
        """Return outage records, optionally filtered by service."""
        with self.db._get_connection() as conn:
            if service_id:
                rows = conn.execute("""
                    SELECT * FROM health_outages
                    WHERE service_id = ?
                    ORDER BY started_at DESC LIMIT 20
                """, (service_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM health_outages
                    ORDER BY started_at DESC LIMIT 50
                """).fetchall()
        return [dict(r) for r in rows]

    def start_daemon(self):
        """Start background health check loop in a daemon thread."""
        import threading
        def _loop():
            while True:
                try:
                    self.check_all()
                    self._prune_old_records()
                except Exception as e:
                    print(f"[health monitor] error: {e}", file=sys.stderr)
                time.sleep(CHECK_INTERVAL)
        t = threading.Thread(target=_loop, daemon=True)
        t.start()

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _store_result(self, result: Dict):
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT INTO health_checks (service_id, checked_at, status, latency_ms, detail)
                VALUES (?, ?, ?, ?, ?)
            """, (result["service_id"], result["checked_at"], result["status"],
                  result.get("latency_ms"), result.get("detail", "")))
            conn.commit()

    def _get_last_result(self, service_id: str) -> Optional[Dict]:
        with self.db._get_connection() as conn:
            row = conn.execute("""
                SELECT service_id, checked_at, status, latency_ms, detail
                FROM health_checks
                WHERE service_id = ?
                ORDER BY checked_at DESC LIMIT 1
            """, (service_id,)).fetchone()
        return dict(row) if row else None

    def _update_outage_tracking(self, service_id: str, status: str):
        """Track consecutive failures; open/close outage records."""
        if status == "healthy":
            self._failure_counts[service_id] = 0
            # Resolve any open outage
            if service_id in self._open_outages:
                started = self._open_outages.pop(service_id)
                now = datetime.now().isoformat()
                started_dt = datetime.fromisoformat(started)
                duration = (datetime.now() - started_dt).total_seconds()
                with self.db._get_connection() as conn:
                    conn.execute("""
                        UPDATE health_outages
                        SET resolved_at = ?, duration_sec = ?
                        WHERE service_id = ? AND started_at = ?
                    """, (now, duration, service_id, started))
                    conn.commit()
        else:
            count = self._failure_counts.get(service_id, 0) + 1
            self._failure_counts[service_id] = count
            if count >= OUTAGE_THRESHOLD and service_id not in self._open_outages:
                started = datetime.now().isoformat()
                self._open_outages[service_id] = started
                with self.db._get_connection() as conn:
                    conn.execute("""
                        INSERT INTO health_outages (service_id, started_at, detail)
                        VALUES (?, ?, ?)
                    """, (service_id, started, f"Status: {status}"))
                    conn.commit()

    def _prune_old_records(self):
        cutoff = (datetime.now() - timedelta(days=HISTORY_KEEP_DAYS)).isoformat()
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM health_checks WHERE checked_at < ?", (cutoff,))
            conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
GREEN = "\033[0;32m"
RED   = "\033[0;31m"
YELLOW= "\033[1;33m"
CYAN  = "\033[1;36m"
DIM   = "\033[2m"
RESET = "\033[0m"

STATUS_COLOR = {
    "healthy":      GREEN,
    "unhealthy":    RED,
    "unreachable":  RED,
    "never_checked":YELLOW,
    "unknown":      DIM,
}
STATUS_ICON = {
    "healthy":      "✓",
    "unhealthy":    "✗",
    "unreachable":  "✗",
    "never_checked":"?",
    "unknown":      "?",
}


def cmd_status(_args):
    """pso health status"""
    hm = HealthMonitor()
    results = hm.get_status()
    if not results:
        print("\n  No services installed.\n")
        return
    W = 64
    print()
    print(f"{BOLD}  PSO Health Status{RESET}")
    print("  " + "─" * W)
    print(f"  {'Service':<24} {'Status':<14} {'Latency':>9}  {'Last checked'}")
    print("  " + "─" * W)
    for r in sorted(results, key=lambda x: x["service_id"]):
        svc   = r["service_id"]
        st    = r["status"]
        col   = STATUS_COLOR.get(st, DIM)
        icon  = STATUS_ICON.get(st, "?")
        lat   = f"{r['latency_ms']:.0f} ms" if r.get("latency_ms") else "—"
        when  = r["checked_at"][:16].replace("T", " ") if r.get("checked_at") else "never"
        print(f"  {col}{icon}{RESET} {svc:<24} {col}{st:<13}{RESET}  {lat:>9}  {DIM}{when}{RESET}")
    print()
    outages = hm.get_outages()
    open_out = [o for o in outages if not o.get("resolved_at")]
    if open_out:
        print(f"  {RED}Active outages: {len(open_out)}{RESET}")
        for o in open_out:
            print(f"    {o['service_id']}  since {o['started_at'][:16].replace('T',' ')}")
        print()


def cmd_check(args):
    """pso health check <service>"""
    if not args:
        print("\n  Usage: pso health check <service>\n")
        return
    svc = args[0]
    print(f"\n  Checking {svc}...")
    hm = HealthMonitor()
    r  = hm.check_service(svc)
    st  = r["status"]
    col = STATUS_COLOR.get(st, DIM)
    icon = STATUS_ICON.get(st, "?")
    print(f"\n  {col}{icon} {st.upper()}{RESET}  —  {svc}")
    if r.get("latency_ms"):
        print(f"  Latency:  {r['latency_ms']:.1f} ms")
    if r.get("detail"):
        print(f"  Detail:   {r['detail']}")
    print(f"  Checked:  {r['checked_at'][:19].replace('T', ' ')}")
    print()


def cmd_history(args):
    """pso health history <service>"""
    if not args:
        print("\n  Usage: pso health history <service>\n")
        return
    svc = args[0]
    hm  = HealthMonitor()
    rows = hm.get_history(svc, limit=20)
    if not rows:
        print(f"\n  No health history for '{svc}'.\n")
        print(f"  Run: pso health check {svc}\n")
        return
    print(f"\n  {BOLD}Health history: {svc}{RESET}  (last {len(rows)} checks)")
    print("  " + "─" * 56)
    for r in rows:
        st   = r["status"]
        col  = STATUS_COLOR.get(st, DIM)
        icon = STATUS_ICON.get(st, "?")
        lat  = f"{r['latency_ms']:.0f}ms" if r.get("latency_ms") else "  — "
        when = r["checked_at"][:19].replace("T", " ")
        print(f"  {col}{icon}{RESET} {when}  {col}{st:<12}{RESET}  {lat:>6}")
    print()


def cmd_start(_args):
    """pso health start — run background daemon"""
    hm = HealthMonitor()
    hm.start_daemon()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"
    rest = args[1:]
    dispatch = {
        "status":  cmd_status,
        "check":   cmd_check,
        "history": cmd_history,
        "start":   cmd_start,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown command: {cmd}")
        print(f"  Use: status | check <svc> | history <svc> | start\n")


if __name__ == "__main__":
    main()