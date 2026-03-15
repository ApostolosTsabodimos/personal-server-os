#!/usr/bin/env python3
"""
PSO Notification Service - Component #19

Sends alerts when health checks fail, services go down, or updates are available.
Supports email (SMTP), webhook (Slack/Discord/generic), and local desktop notify.

Notifications are triggered by other PSO components — they call:
    from core.notifications import notify
    notify("service_down", service_id="nginx", detail="Port 80 unreachable")

Configuration stored in PSO's database under the 'notifications_config' key.

Usage:
    python3 -m core.notifications status
    python3 -m core.notifications test email
    python3 -m core.notifications test webhook
    python3 -m core.notifications config set --email you@example.com
    python3 -m core.notifications history
"""

import json
import smtplib
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, List, Optional, Any


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS notifications_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    event       TEXT NOT NULL,
    service_id  TEXT,
    channel     TEXT NOT NULL,   -- email / webhook / desktop / log
    sent_at     TEXT NOT NULL,
    success     INTEGER NOT NULL,
    detail      TEXT
);

CREATE TABLE IF NOT EXISTS notifications_config (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

def _ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Event definitions (what triggers alerts)
# ─────────────────────────────────────────────────────────────────────────────

EVENTS = {
    "service_down":     "Service went down",
    "service_up":       "Service recovered",
    "service_unhealthy":"Service health check failed",
    "update_available": "Update available",
    "update_applied":   "Update applied",
    "backup_failed":    "Backup failed",
    "backup_complete":  "Backup completed",
    "tier_changed":     "Security tier changed",
    "login_failed":     "Failed login attempt",
    "disk_warning":     "Disk usage high",
    "memory_warning":   "Memory usage high",
    "cpu_warning":      "CPU usage high",
}

# Default: only these events send notifications
DEFAULT_ENABLED_EVENTS = {
    "service_down", "service_up", "backup_failed", "tier_changed",
    "cpu_warning", "memory_warning", "disk_warning",
}


# ─────────────────────────────────────────────────────────────────────────────
# Config manager
# ─────────────────────────────────────────────────────────────────────────────

class NotificationConfig:
    """Reads/writes notification settings from PSO database."""

    def __init__(self, db=None):
        from core.database import Database
        self.db = db or Database()
        with self.db._get_connection() as conn:
            _ensure_schema(conn)

    def get(self, key: str, default=None):
        with self.db._get_connection() as conn:
            row = conn.execute(
                "SELECT value FROM notifications_config WHERE key = ?", (key,)
            ).fetchone()
        if row:
            try:
                return json.loads(row["value"])
            except Exception:
                return row["value"]
        return default

    def set(self, key: str, value):
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications_config (key, value)
                VALUES (?, ?)
                ON CONFLICT(key) DO UPDATE SET value = excluded.value
            """, (key, json.dumps(value)))
            conn.commit()

    def all(self) -> Dict:
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT key, value FROM notifications_config").fetchall()
        out = {}
        for r in rows:
            try:
                out[r["key"]] = json.loads(r["value"])
            except Exception:
                out[r["key"]] = r["value"]
        return out


# ─────────────────────────────────────────────────────────────────────────────
# Channels
# ─────────────────────────────────────────────────────────────────────────────

class EmailChannel:
    """Send alerts via SMTP."""

    def send(self, cfg: Dict, subject: str, body: str) -> tuple:
        """
        Returns (success, error_str).
        cfg keys: smtp_host, smtp_port, smtp_user, smtp_pass, to_email
        """
        required = ["smtp_host", "smtp_port", "smtp_user", "smtp_pass", "to_email"]
        missing  = [k for k in required if not cfg.get(k)]
        if missing:
            return False, f"Missing config: {', '.join(missing)}"

        try:
            msg = MIMEMultipart("alternative")
            msg["Subject"] = f"[PSO] {subject}"
            msg["From"]    = cfg["smtp_user"]
            msg["To"]      = cfg["to_email"]
            msg.attach(MIMEText(body, "plain"))

            with smtplib.SMTP(cfg["smtp_host"], int(cfg["smtp_port"]), timeout=10) as s:
                s.starttls()
                s.login(cfg["smtp_user"], cfg["smtp_pass"])
                s.sendmail(cfg["smtp_user"], cfg["to_email"], msg.as_string())
            return True, None
        except Exception as e:
            return False, str(e)


class WebhookChannel:
    """Send alerts to Slack/Discord/generic JSON webhook."""

    def send(self, url: str, subject: str, body: str, flavor: str = "generic") -> tuple:
        """Returns (success, error_str). flavor: slack / discord / generic"""
        if not url:
            return False, "No webhook URL configured"

        if flavor == "slack":
            payload = {"text": f"*{subject}*\n{body}"}
        elif flavor == "discord":
            payload = {"content": f"**{subject}**\n{body}"}
        else:
            payload = {"subject": subject, "body": body, "source": "PSO"}

        data = json.dumps(payload).encode()
        req  = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        try:
            with urllib.request.urlopen(req, timeout=10):
                return True, None
        except urllib.error.HTTPError as e:
            return False, f"HTTP {e.code}: {e.reason}"
        except Exception as e:
            return False, str(e)


class DesktopChannel:
    """Send a system notification via notify-send (Linux) or osascript (macOS)."""

    def send(self, subject: str, body: str) -> tuple:
        import subprocess, platform
        try:
            if platform.system() == "Darwin":
                subprocess.run(
                    ["osascript", "-e",
                     f'display notification "{body}" with title "{subject}"'],
                    timeout=5
                )
            else:
                subprocess.run(
                    ["notify-send", f"[PSO] {subject}", body],
                    timeout=5
                )
            return True, None
        except Exception as e:
            return False, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Notification dispatcher
# ─────────────────────────────────────────────────────────────────────────────

class NotificationService:
    """
    Central dispatcher. PSO components call notify() on this.
    Routes each event to configured channels and logs the result.
    """

    def __init__(self, db=None):
        from core.database import Database
        self.db     = db or Database()
        self.config = NotificationConfig(self.db)
        self.email  = EmailChannel()
        self.webhook = WebhookChannel()
        self.desktop = DesktopChannel()

    def notify(
        self,
        event: str,
        service_id: Optional[str] = None,
        detail: str = "",
        force: bool = False,
    ) -> List[Dict]:
        """
        Send a notification for an event.

        Args:
            event:      One of the EVENTS keys
            service_id: Which service this is about (optional)
            detail:     Extra context
            force:      Send even if event type is disabled

        Returns:
            List of send results per channel
        """
        # Check if this event type is enabled
        enabled = set(self.config.get("enabled_events", list(DEFAULT_ENABLED_EVENTS)))
        if event not in enabled and not force:
            return []

        subject = EVENTS.get(event, event)
        if service_id:
            subject = f"{subject}: {service_id}"
        body = f"Event: {event}\n"
        if service_id:
            body += f"Service: {service_id}\n"
        if detail:
            body += f"Detail: {detail}\n"
        body += f"Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        body += f"\nManage at: http://localhost:5000"

        results = []
        # Email
        email_cfg = self.config.get("email", {})
        if email_cfg.get("enabled"):
            ok, err = self.email.send(email_cfg, subject, body)
            self._log(event, service_id, "email", ok, err)
            results.append({"channel": "email", "ok": ok, "error": err})

        # Webhook
        wh_cfg = self.config.get("webhook", {})
        if wh_cfg.get("url"):
            ok, err = self.webhook.send(
                wh_cfg["url"], subject, body,
                flavor=wh_cfg.get("flavor", "generic")
            )
            self._log(event, service_id, "webhook", ok, err)
            results.append({"channel": "webhook", "ok": ok, "error": err})

        # Desktop
        if self.config.get("desktop_enabled"):
            ok, err = self.desktop.send(subject, body)
            self._log(event, service_id, "desktop", ok, err)
            results.append({"channel": "desktop", "ok": ok, "error": err})

        # Always log to DB even if no channels configured
        if not results:
            self._log(event, service_id, "log", True, None)
            results.append({"channel": "log", "ok": True})

        return results

    def get_history(self, limit: int = 50) -> List[Dict]:
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT event, service_id, channel, sent_at, success, detail
                FROM notifications_log
                ORDER BY sent_at DESC LIMIT ?
            """, (limit,)).fetchall()
        return [dict(r) for r in rows]

    def _log(self, event, service_id, channel, success, detail):
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT INTO notifications_log (event, service_id, channel, sent_at, success, detail)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (event, service_id, channel, datetime.now().isoformat(),
                  1 if success else 0, detail))
            conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Module-level convenience function (used by other PSO components)
# ─────────────────────────────────────────────────────────────────────────────

_service: Optional[NotificationService] = None

def notify(event: str, service_id: Optional[str] = None, detail: str = "", force: bool = False):
    """
    One-line notification from anywhere in PSO.

    Usage:
        from core.notifications import notify
        notify("service_down", service_id="nginx", detail="Port 80 unreachable")
    """
    global _service
    if _service is None:
        _service = NotificationService()
    return _service.notify(event, service_id=service_id, detail=detail, force=force)


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


def cmd_status(_args):
    """pso notifications status"""
    svc = NotificationService()
    cfg = svc.config.all()

    email_cfg = cfg.get("email", {})
    wh_cfg    = cfg.get("webhook", {})
    desktop   = cfg.get("desktop_enabled", False)
    events    = set(cfg.get("enabled_events", list(DEFAULT_ENABLED_EVENTS)))

    print(f"\n  {BOLD}Notification Channels{RESET}")
    print("  " + "─" * 50)

    if email_cfg.get("enabled") and email_cfg.get("smtp_host"):
        print(f"  {GREEN}✓{RESET} Email    → {email_cfg.get('to_email','?')}")
    else:
        print(f"  {DIM}○ Email      not configured{RESET}")
        print(f"    {DIM}pso notifications config set --email you@example.com{RESET}")

    if wh_cfg.get("url"):
        flavor = wh_cfg.get("flavor","generic")
        print(f"  {GREEN}✓{RESET} Webhook  → {flavor}  {wh_cfg['url'][:40]}...")
    else:
        print(f"  {DIM}○ Webhook    not configured{RESET}")
        print(f"    {DIM}pso notifications config set --webhook-url https://hooks.slack.com/...{RESET}")

    print(f"  {'✓' if desktop else '○'} Desktop  {'enabled' if desktop else 'disabled (notify-send)'}")

    print(f"\n  {BOLD}Enabled events{RESET}")
    for ev, desc in EVENTS.items():
        mark = f"{GREEN}✓{RESET}" if ev in events else f"{DIM}○{RESET}"
        print(f"  {mark} {ev:<22} {DIM}{desc}{RESET}")

    # Recent history summary
    history = svc.get_history(limit=5)
    if history:
        print(f"\n  {BOLD}Last 5 notifications{RESET}")
        print("  " + "─" * 50)
        for h in history:
            ok  = f"{GREEN}✓{RESET}" if h["success"] else f"{RED}✗{RESET}"
            ts  = h["sent_at"][:16].replace("T"," ")
            svc_label = f" [{h['service_id']}]" if h.get("service_id") else ""
            print(f"  {ok} {DIM}{ts}{RESET}  {h['event']}{svc_label}  via {h['channel']}")
    print()


def cmd_test(args):
    """pso notifications test email|webhook|desktop"""
    channel = args[0] if args else None
    if not channel:
        print("\n  Usage: pso notifications test email|webhook|desktop\n")
        return
    svc = NotificationService()
    results = svc.notify("service_down", service_id="test", detail="This is a test notification", force=True)
    for r in results:
        if r["channel"] == channel:
            if r["ok"]:
                print(f"\n  {GREEN}✓{RESET} Test sent via {channel}\n")
            else:
                print(f"\n  {RED}✗{RESET} {channel} failed: {r.get('error','?')}\n")
            return
    print(f"\n  {channel} channel is not configured. Check 'pso notifications status'.\n")


def cmd_config(args):
    """pso notifications config set [--email X] [--webhook-url X] [--webhook-flavor slack]"""
    if not args or args[0] != "set":
        print("\n  Usage: pso notifications config set [options]")
        print("  Options:")
        print("    --email <addr>          Destination email address")
        print("    --smtp-host <host>      SMTP server hostname")
        print("    --smtp-port <port>      SMTP port (default 587)")
        print("    --smtp-user <user>      SMTP username")
        print("    --smtp-pass <pass>      SMTP password")
        print("    --webhook-url <url>     Webhook URL")
        print("    --webhook-flavor <f>    slack | discord | generic")
        print("    --desktop               Enable desktop notifications\n")
        return

    cfg_obj = NotificationConfig()
    email_cfg = cfg_obj.get("email", {})
    wh_cfg    = cfg_obj.get("webhook", {})
    changed   = False

    i = 1
    while i < len(args):
        flag = args[i]
        val  = args[i+1] if i+1 < len(args) else None
        if flag == "--email" and val:
            email_cfg["to_email"] = val
            email_cfg["enabled"]  = True
            changed = True; i += 2
        elif flag == "--smtp-host" and val:
            email_cfg["smtp_host"] = val; changed = True; i += 2
        elif flag == "--smtp-port" and val:
            email_cfg["smtp_port"] = int(val); changed = True; i += 2
        elif flag == "--smtp-user" and val:
            email_cfg["smtp_user"] = val; changed = True; i += 2
        elif flag == "--smtp-pass" and val:
            email_cfg["smtp_pass"] = val; changed = True; i += 2
        elif flag == "--webhook-url" and val:
            wh_cfg["url"] = val; changed = True; i += 2
        elif flag == "--webhook-flavor" and val:
            wh_cfg["flavor"] = val; changed = True; i += 2
        elif flag == "--desktop":
            cfg_obj.set("desktop_enabled", True); changed = True; i += 1
        else:
            i += 1

    if changed:
        cfg_obj.set("email", email_cfg)
        cfg_obj.set("webhook", wh_cfg)
        print(f"\n  {GREEN}✓{RESET} Notification config saved.")
        print(f"  Run 'pso notifications test email' or 'pso notifications test webhook' to verify.\n")
    else:
        print(f"\n  No changes. Run 'pso notifications config set --help' for options.\n")


def cmd_history(_args):
    """pso notifications history"""
    svc  = NotificationService()
    rows = svc.get_history(limit=20)
    if not rows:
        print("\n  No notification history.\n")
        return
    print(f"\n  {BOLD}Notification History{RESET}  (last {len(rows)})")
    print("  " + "─" * 60)
    for h in rows:
        ok  = f"{GREEN}✓{RESET}" if h["success"] else f"{RED}✗{RESET}"
        ts  = h["sent_at"][:16].replace("T", " ")
        svc_label = f" [{h['service_id']}]" if h.get("service_id") else ""
        err = f"  {RED}{h['detail']}{RESET}" if not h["success"] and h.get("detail") else ""
        print(f"  {ok} {DIM}{ts}{RESET}  {h['event']}{svc_label}  via {h['channel']}{err}")
    print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"
    rest = args[1:]
    dispatch = {
        "status":  cmd_status,
        "test":    cmd_test,
        "config":  cmd_config,
        "history": cmd_history,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown: {cmd}  —  use: status | test | config | history\n")


if __name__ == "__main__":
    main()