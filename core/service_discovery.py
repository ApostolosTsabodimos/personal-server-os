#!/usr/bin/env python3
"""
PSO Service Discovery - Component #11
Tracks all running services, their addresses, ports, and health so that:
  - Services can find each other by name (e.g. "jellyfin" → host:8096)
  - Users can see a live directory of what's running and where
  - The web dashboard and CLI always have accurate address info
  - Future: mDNS/Bonjour announcements on the local network

No external dependencies — pure Python + SQLite (same DB as rest of PSO).
"""

import json
import socket
import time
import threading
import logging
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Any

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Data model
# ─────────────────────────────────────────────────────────────────────────────

class ServiceRecord:
    """A single registered service entry."""

    def __init__(
        self,
        service_id: str,
        name: str,
        host: str,
        port: int,
        category: str = "other",
        protocol: str = "http",
        path: str = "/",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        self.service_id = service_id
        self.name = name
        self.host = host
        self.port = port
        self.category = category
        self.protocol = protocol
        self.path = path
        self.tags = tags or []
        self.metadata = metadata or {}
        self.registered_at = datetime.now().isoformat()
        self.last_seen = datetime.now().isoformat()
        self.status = "up"

    @property
    def url(self) -> str:
        """Human-readable URL for this service."""
        base = f"{self.protocol}://{self.host}:{self.port}"
        if self.path and self.path != "/":
            base += self.path
        return base

    @property
    def local_url(self) -> str:
        """URL using detected local hostname."""
        hostname = _get_local_hostname()
        base = f"{self.protocol}://{hostname}:{self.port}"
        if self.path and self.path != "/":
            base += self.path
        return base

    def to_dict(self) -> Dict[str, Any]:
        return {
            "service_id": self.service_id,
            "name": self.name,
            "host": self.host,
            "port": self.port,
            "category": self.category,
            "protocol": self.protocol,
            "path": self.path,
            "tags": self.tags,
            "metadata": self.metadata,
            "registered_at": self.registered_at,
            "last_seen": self.last_seen,
            "status": self.status,
            "url": self.url,
            "local_url": self.local_url,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceRecord":
        r = cls(
            service_id=data["service_id"],
            name=data["name"],
            host=data["host"],
            port=data["port"],
            category=data.get("category", "other"),
            protocol=data.get("protocol", "http"),
            path=data.get("path", "/"),
            tags=data.get("tags", []),
            metadata=data.get("metadata", {}),
        )
        r.registered_at = data.get("registered_at", r.registered_at)
        r.last_seen = data.get("last_seen", r.last_seen)
        r.status = data.get("status", "up")
        return r


# ─────────────────────────────────────────────────────────────────────────────
# Registry
# ─────────────────────────────────────────────────────────────────────────────

class ServiceRegistry:
    """
    In-memory + SQLite-backed registry of all PSO-managed services.

    Usage:
        registry = ServiceRegistry()
        registry.register("jellyfin", "Jellyfin", "localhost", 8096, category="media")
        rec = registry.lookup("jellyfin")
        print(rec.url)   # http://localhost:8096
    """

    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            db_path = Path.home() / ".pso_dev" / "pso.db"
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_schema()

    # ── Schema ────────────────────────────────────────────────────────────────

    def _init_schema(self):
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS service_registry (
                    service_id   TEXT PRIMARY KEY,
                    name         TEXT NOT NULL,
                    host         TEXT NOT NULL,
                    port         INTEGER NOT NULL,
                    category     TEXT NOT NULL DEFAULT 'other',
                    protocol     TEXT NOT NULL DEFAULT 'http',
                    path         TEXT NOT NULL DEFAULT '/',
                    tags         TEXT NOT NULL DEFAULT '[]',
                    metadata     TEXT NOT NULL DEFAULT '{}',
                    registered_at TEXT NOT NULL,
                    last_seen    TEXT NOT NULL,
                    status       TEXT NOT NULL DEFAULT 'up'
                )
            """)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS service_discovery_events (
                    id           INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id   TEXT NOT NULL,
                    event        TEXT NOT NULL,
                    detail       TEXT,
                    occurred_at  TEXT NOT NULL
                )
            """)
            conn.commit()

    # ── Write operations ───────────────────────────────────────────────────────

    def register(
        self,
        service_id: str,
        name: str,
        host: str,
        port: int,
        category: str = "other",
        protocol: str = "http",
        path: str = "/",
        tags: Optional[List[str]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> ServiceRecord:
        """Register or update a service in the registry."""
        import sqlite3

        record = ServiceRecord(
            service_id=service_id,
            name=name,
            host=host,
            port=port,
            category=category,
            protocol=protocol,
            path=path,
            tags=tags or [],
            metadata=metadata or {},
        )

        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                # Check if already registered (update vs insert)
                existing = conn.execute(
                    "SELECT registered_at FROM service_registry WHERE service_id = ?",
                    (service_id,)
                ).fetchone()

                if existing:
                    record.registered_at = existing[0]
                    conn.execute("""
                        UPDATE service_registry
                        SET name=?, host=?, port=?, category=?, protocol=?, path=?,
                            tags=?, metadata=?, last_seen=?, status='up'
                        WHERE service_id=?
                    """, (
                        name, host, port, category, protocol, path,
                        json.dumps(record.tags), json.dumps(record.metadata),
                        record.last_seen, service_id
                    ))
                    event = "updated"
                else:
                    conn.execute("""
                        INSERT INTO service_registry
                        (service_id, name, host, port, category, protocol, path,
                         tags, metadata, registered_at, last_seen, status)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,'up')
                    """, (
                        service_id, name, host, port, category, protocol, path,
                        json.dumps(record.tags), json.dumps(record.metadata),
                        record.registered_at, record.last_seen
                    ))
                    event = "registered"

                self._log_event(conn, service_id, event, f"port={port}")
                conn.commit()

        logger.info(f"Service {event}: {service_id} → {record.url}")
        return record

    def deregister(self, service_id: str) -> bool:
        """Remove a service from the registry."""
        import sqlite3
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "DELETE FROM service_registry WHERE service_id = ?",
                    (service_id,)
                ).rowcount
                if rows:
                    self._log_event(conn, service_id, "deregistered", None)
                conn.commit()
        return rows > 0

    def mark_down(self, service_id: str, reason: str = "") -> bool:
        """Mark a service as down without removing it."""
        import sqlite3
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "UPDATE service_registry SET status='down', last_seen=? WHERE service_id=?",
                    (datetime.now().isoformat(), service_id)
                ).rowcount
                if rows:
                    self._log_event(conn, service_id, "down", reason or None)
                conn.commit()
        return rows > 0

    def mark_up(self, service_id: str) -> bool:
        """Mark a service as back up."""
        import sqlite3
        with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                rows = conn.execute(
                    "UPDATE service_registry SET status='up', last_seen=? WHERE service_id=?",
                    (datetime.now().isoformat(), service_id)
                ).rowcount
                if rows:
                    self._log_event(conn, service_id, "up", None)
                conn.commit()
        return rows > 0

    # ── Read operations ────────────────────────────────────────────────────────

    def lookup(self, service_id: str) -> Optional[ServiceRecord]:
        """Find a service by its ID."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM service_registry WHERE service_id = ?",
                (service_id,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def lookup_by_port(self, port: int) -> Optional[ServiceRecord]:
        """Find a service by port number."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT * FROM service_registry WHERE port = ?", (port,)
            ).fetchone()
        return self._row_to_record(row) if row else None

    def list_all(self, include_down: bool = True) -> List[ServiceRecord]:
        """List all registered services."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            query = "SELECT * FROM service_registry"
            if not include_down:
                query += " WHERE status = 'up'"
            query += " ORDER BY category, name"
            rows = conn.execute(query).fetchall()
        return [self._row_to_record(r) for r in rows]

    def list_by_category(self, category: str) -> List[ServiceRecord]:
        """List all services in a category."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                "SELECT * FROM service_registry WHERE category = ? ORDER BY name",
                (category,)
            ).fetchall()
        return [self._row_to_record(r) for r in rows]

    def search(self, query: str) -> List[ServiceRecord]:
        """Search services by name, ID, category, or tags."""
        import sqlite3
        q = f"%{query.lower()}%"
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM service_registry
                WHERE lower(service_id) LIKE ?
                   OR lower(name) LIKE ?
                   OR lower(category) LIKE ?
                   OR lower(tags) LIKE ?
                ORDER BY category, name
            """, (q, q, q, q)).fetchall()
        return [self._row_to_record(r) for r in rows]

    def get_events(self, service_id: str, limit: int = 20) -> List[Dict]:
        """Get discovery event history for a service."""
        import sqlite3
        with sqlite3.connect(self.db_path) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute("""
                SELECT * FROM service_discovery_events
                WHERE service_id = ?
                ORDER BY occurred_at DESC
                LIMIT ?
            """, (service_id, limit)).fetchall()
        return [dict(r) for r in rows]

    # ── Helpers ────────────────────────────────────────────────────────────────

    def _row_to_record(self, row) -> ServiceRecord:
        d = dict(row)
        d["tags"] = json.loads(d.get("tags", "[]"))
        d["metadata"] = json.loads(d.get("metadata", "{}"))
        return ServiceRecord.from_dict(d)

    def _log_event(self, conn, service_id: str, event: str, detail: Optional[str]):
        conn.execute(
            "INSERT INTO service_discovery_events (service_id, event, detail, occurred_at) VALUES (?,?,?,?)",
            (service_id, event, detail, datetime.now().isoformat())
        )


# ─────────────────────────────────────────────────────────────────────────────
# Port prober — checks if a service port is actually open
# ─────────────────────────────────────────────────────────────────────────────

def probe_port(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if host:port is accepting connections."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except (ConnectionRefusedError, OSError, TimeoutError):
        return False


# ─────────────────────────────────────────────────────────────────────────────
# Auto-sync with installed services
# ─────────────────────────────────────────────────────────────────────────────

class DiscoverySync:
    """
    Watches PSO's installed_services table and keeps the registry in sync.
    Run once manually or start as a background thread.
    """

    # Default port map for known services (fallback when no manifest)
    DEFAULT_PORTS: Dict[str, int] = {
        "jellyfin": 8096, "plex": 32400, "navidrome": 4533,
        "nextcloud": 80,  "bookstack": 80, "paperless-ngx": 8000,
        "vaultwarden": 80, "gitea": 3000, "gitlab": 80,
        "code-server": 8080, "grafana": 3000, "prometheus": 9090,
        "uptime-kuma": 3001, "portainer": 9000, "traefik": 8080,
        "nginx": 80, "wireguard": 51820, "home-assistant": 8123,
        "node-red": 1880, "sonarr": 8989, "radarr": 7878,
        "prowlarr": 9696,
    }

    def __init__(self, registry: ServiceRegistry, db_path: Optional[Path] = None):
        self.registry = registry
        if db_path is None:
            db_path = Path.home() / ".pso_dev" / "pso.db"
        self.db_path = Path(db_path)
        self._running = False
        self._thread: Optional[threading.Thread] = None

    def sync_once(self) -> Dict[str, int]:
        """
        One-shot sync: read installed_services, register/update in registry.
        Returns counts: {"registered": N, "updated": N, "down": N}
        """
        import sqlite3
        counts = {"registered": 0, "updated": 0, "down": 0}

        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.row_factory = sqlite3.Row
                rows = conn.execute(
                    "SELECT * FROM installed_services"
                ).fetchall()
        except Exception as e:
            logger.warning(f"Could not read installed_services: {e}")
            return counts

        host = "localhost"

        for row in rows:
            svc_id = row["service_id"]
            config = json.loads(row["config"] or "{}")

            # Determine port
            port = (
                config.get("port")
                or config.get("ports", {}).get("web")
                or config.get("ports", {}).get("http")
                or self.DEFAULT_PORTS.get(svc_id)
            )

            if not port:
                logger.debug(f"No port found for {svc_id}, skipping")
                continue

            existing = self.registry.lookup(svc_id)
            self.registry.register(
                service_id=svc_id,
                name=row["service_name"],
                host=host,
                port=port,
                category=row.get("category", "other"),
                metadata={"version": row.get("version", ""), "status": row.get("status", "")},
            )

            if existing:
                counts["updated"] += 1
            else:
                counts["registered"] += 1

            # Quick port probe to mark up/down
            if row.get("status") == "running":
                if probe_port(host, port):
                    self.registry.mark_up(svc_id)
                else:
                    self.registry.mark_down(svc_id, "port not responding")
                    counts["down"] += 1

        return counts

    def start(self, interval: int = 30):
        """Start background sync thread (syncs every `interval` seconds)."""
        self._running = True
        self._thread = threading.Thread(
            target=self._loop, args=(interval,), daemon=True, name="pso-discovery-sync"
        )
        self._thread.start()
        logger.info(f"Discovery sync started (every {interval}s)")

    def stop(self):
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _loop(self, interval: int):
        while self._running:
            try:
                self.sync_once()
            except Exception as e:
                logger.error(f"Discovery sync error: {e}")
            time.sleep(interval)


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────

def _get_local_hostname() -> str:
    """Best-effort local network hostname."""
    try:
        # Connect to a remote addr (doesn't actually send data) to find our IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except Exception:
        return "localhost"


def get_server_info() -> Dict[str, str]:
    """Return network info about this PSO host."""
    local_ip = _get_local_hostname()
    return {
        "hostname": socket.gethostname(),
        "local_ip": local_ip,
        "mdns_name": f"{socket.gethostname()}.local",
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

CATEGORY_EMOJI = {
    "infrastructure": "⚙ ",
    "security":       "🔒",
    "media":          "🎬",
    "productivity":   "📁",
    "development":    "💻",
    "monitoring":     "📊",
    "home-automation":"🏠",
    "other":          "📦",
}

STATUS_COLOR = {
    "up":   "\033[0;32m",
    "down": "\033[0;31m",
}
RESET = "\033[0m"
BOLD  = "\033[1m"
CYAN  = "\033[1;36m"


def cmd_list(args):
    registry = ServiceRegistry()
    services = registry.list_all(include_down=True)

    if not services:
        print("\n  No services registered. Run: pso discover sync\n")
        return

    # Group by category
    grouped: Dict[str, List[ServiceRecord]] = {}
    for s in services:
        grouped.setdefault(s.category, []).append(s)

    server = get_server_info()
    server_line = f"{server['local_ip']}  ·  {server['hostname']}.local  ({len(services)} services)"
    W = 70
    print()
    print(f"{BOLD}╔{'═'*(W-2)}╗{RESET}")
    print(f"{BOLD}║{'  PSO SERVICE DIRECTORY'.center(W-2)}║{RESET}")
    print(f"{BOLD}║{server_line.center(W-2)}║{RESET}")
    print(f"{BOLD}╚{'═'*(W-2)}╝{RESET}")

    for cat, svcs in sorted(grouped.items()):
        emoji = CATEGORY_EMOJI.get(cat, "📦")
        print(f"\n{CYAN}  {emoji}  {cat.title()}{RESET}")
        print("  " + "─" * (W - 4))
        for s in svcs:
            sc = STATUS_COLOR.get(s.status, "")
            status_str = f"{sc}{s.status:<4}{RESET}"
            print(f"  {BOLD}{s.service_id:<22}{RESET}  {status_str}  {s.local_url}")
    print()
    print(f"  {BOLD}pso discover info <service>{RESET}   — full details and history")
    print(f"  {BOLD}pso discover sync{RESET}             — refresh from installed services")
    print()


def cmd_info(args):
    if not args:
        print("Usage: pso discover info <service-id>")
        return
    service_id = args[0]
    registry = ServiceRegistry()
    rec = registry.lookup(service_id)
    if not rec:
        print(f"\n  ✗ Service not found: {service_id}")
        print("  Run 'pso discover list' to see registered services\n")
        return

    W = 60
    sc = STATUS_COLOR.get(rec.status, "")
    print()
    print(f"{BOLD}{'─'*W}{RESET}")
    print(f"  {BOLD}{rec.name}{RESET}  [{sc}{rec.status}{RESET}]")
    print(f"{'─'*W}")
    print(f"  ID:          {rec.service_id}")
    print(f"  Category:    {rec.category}")
    print(f"  Address:     {rec.local_url}")
    print(f"  Host:        {rec.host}:{rec.port}")
    reachable = probe_port(rec.host, rec.port)
    print(f"  Reachable:   {'✓ yes' if reachable else '✗ no (port closed)'}")
    print(f"  Registered:  {rec.registered_at[:19]}")
    print(f"  Last seen:   {rec.last_seen[:19]}")
    if rec.tags:
        print(f"  Tags:        {', '.join(rec.tags)}")
    if rec.metadata:
        for k, v in rec.metadata.items():
            if v:
                print(f"  {k.title():<12} {v}")

    events = registry.get_events(service_id, limit=5)
    if events:
        print(f"\n  Recent events:")
        for e in events:
            ts = e["occurred_at"][:19]
            detail = f"  ({e['detail']})" if e.get("detail") else ""
            print(f"    {ts}  {e['event']}{detail}")
    print()


def cmd_sync(args):
    print("\n  Syncing with installed services...")
    registry = ServiceRegistry()
    sync = DiscoverySync(registry)
    counts = sync.sync_once()
    total = counts["registered"] + counts["updated"]
    print(f"  ✓ Done — {counts['registered']} new, {counts['updated']} updated, {counts['down']} down")
    if total:
        print(f"  Run 'pso discover list' to see the directory\n")
    else:
        print(f"  No installed services found. Install one first: pso install <service>\n")


def cmd_search(args):
    if not args:
        print("Usage: pso discover search <query>")
        return
    query = " ".join(args)
    registry = ServiceRegistry()
    results = registry.search(query)
    if not results:
        print(f"\n  No services matching '{query}'\n")
        return
    print(f"\n  {len(results)} result(s) for '{query}':\n")
    for s in results:
        sc = STATUS_COLOR.get(s.status, "")
        print(f"  {BOLD}{s.service_id:<22}{RESET}  {sc}{s.status:<4}{RESET}  {s.local_url}")
    print()


def cmd_server(args):
    info = get_server_info()
    print(f"\n  Hostname:   {info['hostname']}")
    print(f"  Local IP:   {info['local_ip']}")
    print(f"  mDNS name:  {info['mdns_name']}")
    print()


# ─────────────────────────────────────────────────────────────────────────────
# Entry point (python3 -m core.service_discovery <command>)
# ─────────────────────────────────────────────────────────────────────────────

def main():
    import sys
    args = sys.argv[1:]
    cmd = args[0] if args else "list"
    rest = args[1:]

    commands = {
        "list":   cmd_list,
        "info":   cmd_info,
        "sync":   cmd_sync,
        "search": cmd_search,
        "server": cmd_server,
    }

    fn = commands.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown command: {cmd}")
        print(f"  Available: {', '.join(commands)}\n")


if __name__ == "__main__":
    main()