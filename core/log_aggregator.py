#!/usr/bin/env python3
"""
PSO Log Aggregator - Monitoring Component

Centralizes logs from all PSO-managed Docker containers into SQLite.
Supports live tailing, full-text search, level filtering, and export.

Usage:
    python3 -m core.log_aggregator tail                  # tail all services
    python3 -m core.log_aggregator tail nginx            # tail one service
    python3 -m core.log_aggregator search "error"        # search all logs
    python3 -m core.log_aggregator search "timeout" nginx
    python3 -m core.log_aggregator show [service]        # recent logs
    python3 -m core.log_aggregator collect               # one-shot ingest
    python3 -m core.log_aggregator start                 # background daemon
    python3 -m core.log_aggregator stats                 # log volume per service
"""

import json
import re
import subprocess
import sys
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional

COLLECT_INTERVAL  = 15    # seconds between collection passes
RETENTION_DAYS    = 7
MAX_LINES_INGEST  = 500   # lines pulled per service per pass

LEVEL_PATTERNS = [
    (re.compile(r'\b(CRITICAL|FATAL)\b',   re.I), 'critical'),
    (re.compile(r'\b(ERROR|ERR)\b',        re.I), 'error'),
    (re.compile(r'\b(WARN(?:ING)?)\b',     re.I), 'warning'),
    (re.compile(r'\b(INFO)\b',             re.I), 'info'),
    (re.compile(r'\b(DEBUG|TRACE|VERBOSE)\b', re.I), 'debug'),
]

# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA_DDL = """
CREATE TABLE IF NOT EXISTS service_logs (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id  TEXT    NOT NULL,
    level       TEXT    NOT NULL DEFAULT 'info',
    message     TEXT    NOT NULL,
    logged_at   TEXT    NOT NULL,
    ingested_at TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_logs_service  ON service_logs(service_id, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_level    ON service_logs(level, logged_at DESC);
CREATE INDEX IF NOT EXISTS idx_logs_message  ON service_logs(message);
"""

REQUIRED_COLS = {
    "service_id":  "TEXT NOT NULL DEFAULT ''",
    "level":       "TEXT NOT NULL DEFAULT 'info'",
    "message":     "TEXT NOT NULL DEFAULT ''",
    "logged_at":   "TEXT NOT NULL DEFAULT ''",
    "ingested_at": "TEXT NOT NULL DEFAULT ''",
}


def _ensure_schema(db_path):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        # Step 1: tables
        conn.executescript(SCHEMA_DDL)
        # Step 2: migrate missing columns
        existing = {row[1] for row in conn.execute("PRAGMA table_info(service_logs)")}
        for col, defn in REQUIRED_COLS.items():
            if col not in existing:
                try:
                    conn.execute(f"ALTER TABLE service_logs ADD COLUMN {col} {defn}")
                except Exception:
                    pass
        # Step 3: indexes (safe now)
        for stmt in SCHEMA_DDL.splitlines():
            if stmt.strip().startswith("CREATE INDEX"):
                try:
                    conn.execute(stmt.strip())
                except Exception:
                    pass
        conn.commit()
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
# Log ingestion
# ─────────────────────────────────────────────────────────────────────────────

def _detect_level(line: str) -> str:
    for pattern, level in LEVEL_PATTERNS:
        if pattern.search(line):
            return level
    return 'info'


def _parse_timestamp(line: str) -> Optional[str]:
    """Try to pull a timestamp out of the log line."""
    patterns = [
        r'(\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2})',   # ISO-ish
        r'(\d{2}/\w{3}/\d{4}:\d{2}:\d{2}:\d{2})',        # nginx
        r'(\w{3}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})',        # syslog
    ]
    for p in patterns:
        m = re.search(p, line)
        if m:
            return m.group(1)
    return None


class LogCollector:
    """Pulls logs from Docker containers into the database."""

    def collect_service(self, service_id: str, since_minutes: int = 1) -> int:
        """Ingest recent logs for one service. Returns lines written."""
        since = f"{since_minutes}m"
        try:
            result = subprocess.run(
                ["docker", "logs", f"pso-{service_id}",
                 "--since", since, "--tail", str(MAX_LINES_INGEST),
                 "--timestamps"],
                capture_output=True, text=True, timeout=10
            )
            lines = (result.stdout + result.stderr).splitlines()
        except Exception:
            return 0

        if not lines:
            return 0

        now = datetime.now().isoformat()
        rows = []
        for line in lines:
            if not line.strip():
                continue
            ts = _parse_timestamp(line) or now
            # Strip docker's own timestamp prefix if present
            clean = re.sub(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d+Z\s*', '', line)
            rows.append((service_id, _detect_level(clean), clean[:2000], ts, now))

        if not rows:
            return 0

        try:
            from core.database import Database
            db = Database()
            _ensure_schema(db.db_path)
            import sqlite3
            conn = sqlite3.connect(str(db.db_path))
            conn.executemany(
                "INSERT INTO service_logs (service_id, level, message, logged_at, ingested_at) VALUES (?,?,?,?,?)",
                rows
            )
            conn.commit()
            conn.close()
        except Exception:
            return 0

        return len(rows)

    def collect_all(self) -> Dict[str, int]:
        """Collect from all installed services."""
        try:
            from core.database import Database
            services = Database().list_services()
        except Exception:
            return {}
        results = {}
        for svc in services:
            n = self.collect_service(svc['service_id'])
            if n:
                results[svc['service_id']] = n
        return results


# ─────────────────────────────────────────────────────────────────────────────
# Log store — queries
# ─────────────────────────────────────────────────────────────────────────────

class LogStore:

    def __init__(self):
        from core.database import Database
        self.db = Database()
        _ensure_schema(self.db.db_path)

    def _conn(self):
        import sqlite3
        conn = sqlite3.connect(str(self.db.db_path))
        conn.row_factory = sqlite3.Row
        return conn

    def recent(self, service_id: Optional[str] = None,
               level: Optional[str] = None,
               limit: int = 50,
               since_hours: int = 24) -> List[Dict]:
        since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        where = ["logged_at > ?"]
        params = [since]
        if service_id:
            where.append("service_id = ?"); params.append(service_id)
        if level:
            where.append("level = ?"); params.append(level)
        params.append(limit)
        conn = self._conn()
        rows = conn.execute(
            f"SELECT * FROM service_logs WHERE {' AND '.join(where)} "
            f"ORDER BY logged_at DESC LIMIT ?", params
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]

    def search(self, query: str,
               service_id: Optional[str] = None,
               limit: int = 50) -> List[Dict]:
        where = ["lower(message) LIKE ?"]
        params = [f"%{query.lower()}%"]
        if service_id:
            where.append("service_id = ?"); params.append(service_id)
        params.append(limit)
        conn = self._conn()
        rows = conn.execute(
            f"SELECT * FROM service_logs WHERE {' AND '.join(where)} "
            f"ORDER BY logged_at DESC LIMIT ?", params
        ).fetchall()
        conn.close()
        return [dict(r) for r in reversed(rows)]

    def stats(self) -> List[Dict]:
        conn = self._conn()
        rows = conn.execute("""
            SELECT service_id,
                   COUNT(*) as total,
                   SUM(level='error') as errors,
                   SUM(level='warning') as warnings,
                   MAX(logged_at) as last_log
            FROM service_logs
            GROUP BY service_id
            ORDER BY total DESC
        """).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def prune(self):
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat()
        conn = self._conn()
        conn.execute("DELETE FROM service_logs WHERE logged_at < ?", (cutoff,))
        conn.commit()
        conn.close()

    def tail(self, service_id: Optional[str] = None, poll_seconds: float = 2.0):
        """Generator: yields new log rows as they arrive."""
        # Get the latest ID we've seen
        conn = self._conn()
        row = conn.execute("SELECT MAX(id) FROM service_logs").fetchone()
        last_id = row[0] or 0
        conn.close()

        collector = LogCollector()
        while True:
            # Ingest fresh logs first
            if service_id:
                collector.collect_service(service_id, since_minutes=1)
            else:
                collector.collect_all()

            # Yield any new rows
            conn = self._conn()
            where = "id > ?"
            params = [last_id]
            if service_id:
                where += " AND service_id = ?"
                params.append(service_id)
            new_rows = conn.execute(
                f"SELECT * FROM service_logs WHERE {where} ORDER BY id ASC",
                params
            ).fetchall()
            conn.close()

            for row in new_rows:
                last_id = row['id']
                yield dict(row)

            time.sleep(poll_seconds)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

BOLD   = "\033[1m"
RED    = "\033[0;31m"
YELLOW = "\033[1;33m"
CYAN   = "\033[1;36m"
GREEN  = "\033[0;32m"
DIM    = "\033[2m"
RESET  = "\033[0m"

LEVEL_COLOR = {
    'critical': "\033[1;35m",
    'error':    RED,
    'warning':  YELLOW,
    'info':     RESET,
    'debug':    DIM,
}

def _fmt_row(row: Dict) -> str:
    ts    = row.get('logged_at', '')[:19].replace('T', ' ')
    svc   = row.get('service_id', '')
    level = row.get('level', 'info')
    msg   = row.get('message', '')
    col   = LEVEL_COLOR.get(level, RESET)
    lvl_str = f"{col}{level[0].upper()}{RESET}"
    return f"  {DIM}{ts}{RESET}  {CYAN}{svc:<18}{RESET}  {lvl_str}  {col if level in ('error','critical','warning') else ''}{msg}{RESET if level in ('error','critical','warning') else ''}"


def cmd_show(args):
    """pso logs-agg show [service] [--level error] [--lines N]"""
    service_id = None
    level      = None
    limit      = 50
    i = 0
    while i < len(args):
        if args[i] == '--level' and i+1 < len(args):
            level = args[i+1]; i += 2
        elif args[i] == '--lines' and i+1 < len(args):
            limit = int(args[i+1]); i += 2
        elif not args[i].startswith('--'):
            service_id = args[i]; i += 1
        else:
            i += 1

    store = LogStore()
    rows  = store.recent(service_id=service_id, level=level, limit=limit)

    if not rows:
        target = service_id or "any service"
        print(f"\n  No logs for {target}.")
        print(f"  Run 'pso logs-agg collect' to ingest, or 'pso logs <service>' for live Docker logs.\n")
        return

    label = service_id or "all services"
    if level:
        label += f"  [{level}]"
    print(f"\n  {BOLD}{label}{RESET}  (last {len(rows)} lines)")
    print("  " + "─" * 72)
    for row in rows:
        print(_fmt_row(row))
    print()


def cmd_search(args):
    """pso logs-agg search <query> [service]"""
    if not args:
        print("\n  Usage: pso logs-agg search <query> [service]\n")
        return
    query      = args[0]
    service_id = args[1] if len(args) > 1 else None
    store      = LogStore()
    rows       = store.search(query, service_id=service_id)
    if not rows:
        print(f"\n  No logs matching '{query}'\n")
        return
    label = f"'{query}'" + (f" in {service_id}" if service_id else "")
    print(f"\n  {BOLD}Search: {label}{RESET}  ({len(rows)} results)")
    print("  " + "─" * 72)
    for row in rows:
        # Highlight match
        msg = row.get('message', '')
        hi  = re.sub(f"({re.escape(query)})", f"\033[1;33m\\1{RESET}", msg, flags=re.I)
        row['message'] = hi
        print(_fmt_row(row))
    print()


def cmd_tail(args):
    """pso logs-agg tail [service]"""
    service_id = args[0] if args else None
    label      = service_id or "all services"
    print(f"\n  {BOLD}Tailing logs: {label}{RESET}  (Ctrl+C to stop)\n")
    store = LogStore()
    try:
        for row in store.tail(service_id=service_id):
            print(_fmt_row(row))
    except KeyboardInterrupt:
        print(f"\n  Stopped.\n")


def cmd_collect(_args):
    """pso logs-agg collect — one-shot ingest"""
    print("\n  Collecting logs...")
    results = LogCollector().collect_all()
    if results:
        total = sum(results.values())
        print(f"  {GREEN}✓{RESET} {total} lines ingested from {len(results)} service(s)")
        for svc, n in sorted(results.items()):
            print(f"      {svc}: {n} lines")
    else:
        print(f"  {DIM}No new log lines (no running PSO containers found){RESET}")
    print()


def cmd_stats(_args):
    """pso logs-agg stats"""
    store = LogStore()
    rows  = store.stats()
    if not rows:
        print("\n  No log data. Run 'pso logs-agg collect' first.\n")
        return
    print(f"\n  {BOLD}Log Volume by Service{RESET}")
    print("  " + "─" * 60)
    print(f"  {'Service':<22} {'Total':>8}  {'Errors':>8}  {'Warnings':>9}  {'Last log'}")
    print("  " + "─" * 60)
    for r in rows:
        errs  = r['errors'] or 0
        warns = r['warnings'] or 0
        last  = (r['last_log'] or '')[:16].replace('T', ' ')
        ecol  = RED    if errs  else DIM
        wcol  = YELLOW if warns else DIM
        print(f"  {BOLD}{r['service_id']:<22}{RESET} {r['total']:>8}  "
              f"{ecol}{errs:>8}{RESET}  {wcol}{warns:>9}{RESET}  {DIM}{last}{RESET}")
    print()


def cmd_start(_args):
    """pso logs-agg start — background collection daemon"""
    print(f"Log aggregator started — collecting every {COLLECT_INTERVAL}s")
    print("Press Ctrl+C to stop.")
    store     = LogStore()
    collector = LogCollector()
    try:
        while True:
            try:
                collector.collect_all()
                store.prune()
            except Exception as e:
                print(f"[log-aggregator] error: {e}", file=sys.stderr)
            time.sleep(COLLECT_INTERVAL)
    except KeyboardInterrupt:
        print("\nLog aggregator stopped.")


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "show"
    rest = args[1:]
    dispatch = {
        "show":    cmd_show,
        "search":  cmd_search,
        "tail":    cmd_tail,
        "collect": cmd_collect,
        "stats":   cmd_stats,
        "start":   cmd_start,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown: {cmd}")
        print(f"  Use: show | search | tail | collect | stats | start\n")


if __name__ == "__main__":
    main()