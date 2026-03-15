#!/usr/bin/env python3
"""
PSO Audit Log - Security Component

Immutable append-only log of all security-relevant events:
tier changes, logins, installs, config changes, permission checks.

Other PSO modules call:  audit("tier_changed", user="admin", detail="…")

Usage:
    python3 -m core.audit_log show
    python3 -m core.audit_log show --event tier_changed
    python3 -m core.audit_log show --user admin
    python3 -m core.audit_log stats
    python3 -m core.audit_log export > audit.json
"""

import json
import sys
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# ─── Event catalogue ─────────────────────────────────────────────────────────

EVENTS = {
    # Auth
    "login_ok":       "Successful login",
    "login_failed":   "Failed login attempt",
    "logout":         "User logged out",
    "token_expired":  "Session token expired",
    # Services
    "service_install":  "Service installed",
    "service_remove":   "Service removed",
    "service_start":    "Service started",
    "service_stop":     "Service stopped",
    "service_restart":  "Service restarted",
    # Tiers / firewall
    "tier_changed":     "Security tier changed",
    "firewall_rule":    "Firewall rule modified",
    # Secrets
    "secret_created":   "Secret created",
    "secret_accessed":  "Secret accessed",
    "secret_deleted":   "Secret deleted",
    # Users / RBAC
    "role_assigned":    "Role assigned to user",
    "role_revoked":     "Role revoked from user",
    # System
    "backup_created":   "Backup created",
    "backup_restored":  "Backup restored",
    "config_changed":   "Configuration changed",
    "update_applied":   "Update applied",
}

SEVERITY = {
    "login_failed": "warning",
    "tier_changed": "warning",
    "firewall_rule": "warning",
    "secret_accessed": "info",
    "secret_deleted": "warning",
    "role_assigned": "info",
    "role_revoked": "warning",
    "backup_restored": "warning",
    "update_applied": "info",
}

# ─── Schema ──────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,
    username    TEXT,
    service_id  TEXT,
    severity    TEXT NOT NULL DEFAULT 'info',
    detail      TEXT,
    ip_address  TEXT,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_audit_event    ON audit_log(event, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_user     ON audit_log(username, occurred_at DESC);
CREATE INDEX IF NOT EXISTS idx_audit_occurred ON audit_log(occurred_at DESC);
"""


def _ensure_schema(db_path):
    import sqlite3
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA)
    conn.commit(); conn.close()


# ─── Audit Logger ────────────────────────────────────────────────────────────

class AuditLogger:

    def __init__(self, db=None):
        from core.database import Database
        self.db = db or Database()
        _ensure_schema(self.db.db_path)

    def log(self, event: str, username: Optional[str] = None,
            service_id: Optional[str] = None, detail: str = "",
            ip_address: Optional[str] = None) -> int:
        severity = SEVERITY.get(event, "info")
        import sqlite3
        conn = sqlite3.connect(str(self.db.db_path))
        cur = conn.execute("""
            INSERT INTO audit_log (event, username, service_id, severity, detail, ip_address, occurred_at)
            VALUES (?,?,?,?,?,?,?)
        """, (event, username, service_id, severity, detail, ip_address,
              datetime.now().isoformat()))
        conn.commit()
        row_id = cur.lastrowid
        conn.close()
        return row_id

    def query(self, event: Optional[str] = None,
              username: Optional[str] = None,
              severity: Optional[str] = None,
              since_days: int = 30,
              limit: int = 100) -> List[Dict]:
        since = (datetime.now() - timedelta(days=since_days)).isoformat()
        where = ["occurred_at > ?"]
        params = [since]
        if event:
            where.append("event = ?"); params.append(event)
        if username:
            where.append("username = ?"); params.append(username)
        if severity:
            where.append("severity = ?"); params.append(severity)
        params.append(limit)
        import sqlite3
        conn = sqlite3.connect(str(self.db.db_path))
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"SELECT * FROM audit_log WHERE {' AND '.join(where)} ORDER BY occurred_at DESC LIMIT ?",
            params
        ).fetchall()
        conn.close()
        return [dict(r) for r in rows]

    def stats(self) -> Dict:
        import sqlite3
        conn = sqlite3.connect(str(self.db.db_path))
        conn.row_factory = sqlite3.Row
        since_7d = (datetime.now() - timedelta(days=7)).isoformat()
        total    = conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0]
        by_event = conn.execute(
            "SELECT event, COUNT(*) as n FROM audit_log GROUP BY event ORDER BY n DESC LIMIT 10"
        ).fetchall()
        warnings = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE severity='warning' AND occurred_at > ?",
            (since_7d,)
        ).fetchone()[0]
        failed_logins = conn.execute(
            "SELECT COUNT(*) FROM audit_log WHERE event='login_failed' AND occurred_at > ?",
            (since_7d,)
        ).fetchone()[0]
        conn.close()
        return {
            "total": total,
            "warnings_7d": warnings,
            "failed_logins_7d": failed_logins,
            "top_events": [dict(r) for r in by_event],
        }


# ─── Module-level shortcut ───────────────────────────────────────────────────

_logger: Optional[AuditLogger] = None

def audit(event: str, username: Optional[str] = None,
          service_id: Optional[str] = None, detail: str = "",
          ip_address: Optional[str] = None):
    """
    One-line audit logging from anywhere in PSO.

        from core.audit_log import audit
        audit("tier_changed", username="admin", detail="Tier 1 → Tier 2")
    """
    global _logger
    if _logger is None:
        _logger = AuditLogger()
    return _logger.log(event, username=username, service_id=service_id,
                       detail=detail, ip_address=ip_address)


# ─── CLI ─────────────────────────────────────────────────────────────────────

BOLD   = "\033[1m"; CYAN = "\033[1;36m"; GREEN = "\033[0;32m"
RED    = "\033[0;31m"; DIM = "\033[2m"; YELLOW = "\033[1;33m"; RESET = "\033[0m"

SEV_COLOR = {"warning": YELLOW, "error": RED, "info": RESET}


def cmd_show(args):
    event = None; user = None; sev = None
    i = 0
    while i < len(args):
        if args[i] == "--event" and i+1 < len(args):   event = args[i+1]; i += 2
        elif args[i] == "--user" and i+1 < len(args):  user  = args[i+1]; i += 2
        elif args[i] == "--warn":                       sev   = "warning"; i += 1
        else:                                           i += 1

    logger = AuditLogger()
    rows   = logger.query(event=event, username=user, severity=sev, limit=50)
    if not rows:
        print("\n  No audit records found.\n"); return

    filters = []
    if event: filters.append(f"event={event}")
    if user:  filters.append(f"user={user}")
    if sev:   filters.append(f"severity={sev}")
    label = "  ".join(filters) or "all events"

    print(f"\n  {BOLD}Audit Log{RESET}  [{label}]  ({len(rows)} records)")
    print("  " + "─" * 72)
    for r in rows:
        ts   = r["occurred_at"][:19].replace("T", " ")
        col  = SEV_COLOR.get(r["severity"], RESET)
        who  = r.get("username") or "—"
        svc  = f" [{r['service_id']}]" if r.get("service_id") else ""
        det  = f"  {DIM}{r['detail']}{RESET}" if r.get("detail") else ""
        print(f"  {DIM}{ts}{RESET}  {CYAN}{who:<14}{RESET}  {col}{r['event']}{svc}{RESET}{det}")
    print()


def cmd_stats(_):
    logger = AuditLogger()
    s = logger.stats()
    print(f"\n  {BOLD}Audit Statistics{RESET}")
    print("  " + "─" * 40)
    print(f"  Total events:        {s['total']}")
    print(f"  Warnings (7d):       {YELLOW}{s['warnings_7d']}{RESET}")
    print(f"  Failed logins (7d):  {RED if s['failed_logins_7d'] else DIM}{s['failed_logins_7d']}{RESET}")
    if s["top_events"]:
        print(f"\n  {BOLD}Top events:{RESET}")
        for e in s["top_events"]:
            desc = EVENTS.get(e["event"], e["event"])
            print(f"    {e['event']:<24} {DIM}{e['n']:>5}×  {desc}{RESET}")
    print()


def cmd_export(_):
    logger = AuditLogger()
    rows = logger.query(since_days=365, limit=100000)
    print(json.dumps(rows, indent=2))


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "show"
    dispatch = {"show": cmd_show, "stats": cmd_stats, "export": cmd_export}
    fn = dispatch.get(cmd)
    if fn:
        fn(args[1:])
    else:
        print(f"\n  Unknown: {cmd}  —  use: show | stats | export\n")

if __name__ == "__main__":
    main()