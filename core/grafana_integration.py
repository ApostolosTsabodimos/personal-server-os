#!/usr/bin/env python3
"""
PSO Metrics Collection - Component #18

Collects system + per-service CPU/memory/disk/network metrics.
Stores as time-series in SQLite. Exports in Prometheus text format.

Usage:
    python3 -m core.metrics collect
    python3 -m core.metrics query cpu_percent nginx
    python3 -m core.metrics export
    python3 -m core.metrics start          # background collector daemon
"""

import json
import subprocess
import sys
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

COLLECT_INTERVAL = 30       # seconds between collections
RETENTION_DAYS   = 7        # keep 7 days of metric history


# ─────────────────────────────────────────────────────────────────────────────
# Schema
# ─────────────────────────────────────────────────────────────────────────────

SCHEMA = """
CREATE TABLE IF NOT EXISTS metrics (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    service_id  TEXT,               -- NULL = system-level metric
    metric      TEXT    NOT NULL,   -- e.g. cpu_percent, memory_mb, disk_mb
    value       REAL    NOT NULL,
    labels      TEXT,               -- JSON dict of extra labels
    collected_at TEXT   NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_metrics_lookup
    ON metrics(metric, service_id, collected_at DESC);
"""


def _ensure_schema(conn):
    conn.executescript(SCHEMA)
    conn.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Collectors
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: List[str]) -> str:
    try:
        return subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL).strip()
    except Exception:
        return ""


class SystemCollector:
    """Collects host-level metrics (CPU, RAM, disk)."""

    def collect(self) -> List[Dict]:
        now = datetime.now().isoformat()
        samples = []

        # CPU
        try:
            import psutil
            samples.append({"metric": "host_cpu_percent",   "value": psutil.cpu_percent(interval=0.5), "collected_at": now})
            vm = psutil.virtual_memory()
            samples.append({"metric": "host_memory_used_mb","value": vm.used / 1024**2,                "collected_at": now})
            samples.append({"metric": "host_memory_pct",    "value": vm.percent,                       "collected_at": now})
            du = psutil.disk_usage("/")
            samples.append({"metric": "host_disk_used_gb",  "value": du.used / 1024**3,                "collected_at": now})
            samples.append({"metric": "host_disk_pct",      "value": du.percent,                       "collected_at": now})
        except ImportError:
            # psutil not available — use /proc on Linux
            samples += self._proc_fallback(now)

        return samples

    def _proc_fallback(self, now: str) -> List[Dict]:
        """Read /proc/meminfo when psutil is unavailable."""
        samples = []
        try:
            meminfo = {}
            with open("/proc/meminfo") as f:
                for line in f:
                    k, v = line.split(":", 1)
                    meminfo[k.strip()] = int(v.split()[0])
            total = meminfo.get("MemTotal", 0)
            avail = meminfo.get("MemAvailable", 0)
            used  = total - avail
            pct   = round(used / total * 100, 1) if total else 0
            samples.append({"metric": "host_memory_used_mb", "value": used / 1024,     "collected_at": now})
            samples.append({"metric": "host_memory_pct",     "value": pct,             "collected_at": now})
        except Exception:
            pass
        try:
            out = _run(["df", "-BG", "--output=used,pcent", "/"])
            lines = [l for l in out.splitlines() if l.strip() and not l.startswith("Use")]
            if lines:
                parts = lines[0].split()
                used_gb = float(parts[0].rstrip("G"))
                pct     = float(parts[1].rstrip("%"))
                samples.append({"metric": "host_disk_used_gb", "value": used_gb, "collected_at": now})
                samples.append({"metric": "host_disk_pct",     "value": pct,     "collected_at": now})
        except Exception:
            pass
        return samples


class ContainerCollector:
    """Collects per-container metrics via docker stats."""

    def collect_service(self, service_id: str) -> List[Dict]:
        """Collect metrics for one pso-{service_id} container."""
        now  = datetime.now().isoformat()
        name = f"pso-{service_id}"
        out  = _run(["docker", "stats", "--no-stream", "--format",
                     "{{.CPUPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}", name])
        if not out:
            return []

        parts = out.split("|")
        if len(parts) < 4:
            return []

        samples = []
        try:
            cpu = float(parts[0].strip().rstrip("%"))
            samples.append({"service_id": service_id, "metric": "service_cpu_percent",
                             "value": cpu, "collected_at": now})
        except Exception:
            pass

        try:
            mem_part = parts[1].split("/")[0].strip()
            mem_mb = self._parse_size_mb(mem_part)
            if mem_mb is not None:
                samples.append({"service_id": service_id, "metric": "service_memory_mb",
                                 "value": mem_mb, "collected_at": now})
        except Exception:
            pass

        return samples

    def collect_all(self, service_ids: List[str]) -> List[Dict]:
        all_samples = []
        for svc in service_ids:
            all_samples += self.collect_service(svc)
        return all_samples

    def _parse_size_mb(self, s: str) -> Optional[float]:
        """Parse '128MiB', '1.5GiB', '512kB' → MB float."""
        s = s.strip()
        for suffix, mult in [("GiB", 1024), ("MiB", 1), ("kB", 1/1024),
                              ("GB", 1000), ("MB", 1), ("KB", 1/1024)]:
            if s.endswith(suffix):
                return float(s[:-len(suffix)]) * mult
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Metrics store
# ─────────────────────────────────────────────────────────────────────────────

class MetricsStore:
    """Write/read metrics to/from PSO's SQLite database."""

    def __init__(self, db=None):
        from core.database import Database
        self.db = db or Database()
        with self.db._get_connection() as conn:
            _ensure_schema(conn)

    def write(self, samples: List[Dict]):
        """Bulk-insert a list of metric samples."""
        if not samples:
            return
        with self.db._get_connection() as conn:
            conn.executemany("""
                INSERT INTO metrics (service_id, metric, value, labels, collected_at)
                VALUES (:service_id, :metric, :value, :labels, :collected_at)
            """, [
                {
                    "service_id":   s.get("service_id"),
                    "metric":       s["metric"],
                    "value":        s["value"],
                    "labels":       json.dumps(s.get("labels", {})) if s.get("labels") else None,
                    "collected_at": s["collected_at"],
                }
                for s in samples
            ])
            conn.commit()

    def query(self, metric: str, service_id: Optional[str] = None,
              since_hours: int = 24, limit: int = 100) -> List[Dict]:
        """Query metric history."""
        since = (datetime.now() - timedelta(hours=since_hours)).isoformat()
        with self.db._get_connection() as conn:
            if service_id:
                rows = conn.execute("""
                    SELECT service_id, metric, value, collected_at
                    FROM metrics
                    WHERE metric = ? AND service_id = ? AND collected_at > ?
                    ORDER BY collected_at DESC LIMIT ?
                """, (metric, service_id, since, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT service_id, metric, value, collected_at
                    FROM metrics
                    WHERE metric = ? AND collected_at > ?
                    ORDER BY collected_at DESC LIMIT ?
                """, (metric, since, limit)).fetchall()
        return [dict(r) for r in rows]

    def latest(self, metric: str, service_id: Optional[str] = None) -> Optional[Dict]:
        """Get the most recent value for a metric."""
        results = self.query(metric, service_id, since_hours=1, limit=1)
        return results[0] if results else None

    def prune(self):
        """Delete records older than RETENTION_DAYS."""
        cutoff = (datetime.now() - timedelta(days=RETENTION_DAYS)).isoformat()
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM metrics WHERE collected_at < ?", (cutoff,))
            conn.commit()

    def prometheus_export(self, service_id: Optional[str] = None) -> str:
        """
        Return metrics in Prometheus text exposition format.
        Only exports the latest value of each metric.
        """
        since = (datetime.now() - timedelta(minutes=5)).isoformat()
        with self.db._get_connection() as conn:
            if service_id:
                rows = conn.execute("""
                    SELECT metric, service_id, value, MAX(collected_at) as ts
                    FROM metrics
                    WHERE collected_at > ? AND (service_id = ? OR service_id IS NULL)
                    GROUP BY metric, service_id
                    ORDER BY metric
                """, (since, service_id)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT metric, service_id, value, MAX(collected_at) as ts
                    FROM metrics
                    WHERE collected_at > ?
                    GROUP BY metric, service_id
                    ORDER BY metric
                """, (since,)).fetchall()

        lines = ["# PSO metrics — Prometheus text format", f"# Generated: {datetime.now().isoformat()}", ""]
        for r in rows:
            metric = r["metric"]
            val    = r["value"]
            svc    = r["service_id"]
            labels = f'{{service="{svc}"}}' if svc else ""
            lines.append(f"pso_{metric}{labels} {val}")
        return "\n".join(lines)


# ─────────────────────────────────────────────────────────────────────────────
# Collector orchestrator
# ─────────────────────────────────────────────────────────────────────────────

class MetricsCollector:
    """Runs all collectors and writes results to MetricsStore."""

    def __init__(self):
        from core.database import Database
        self.store  = MetricsStore()
        self.db     = self.store.db
        self.sys_c  = SystemCollector()
        self.cont_c = ContainerCollector()

    def collect_once(self) -> int:
        """Run one collection cycle. Returns number of samples written."""
        samples = self.sys_c.collect()
        services = self.db.list_services()
        service_ids = [s["service_id"] for s in services]
        samples += self.cont_c.collect_all(service_ids)
        self.store.write(samples)
        return len(samples)

    def start_daemon(self):
        """Block and collect forever."""
        print(f"Metrics collector started — sampling every {COLLECT_INTERVAL}s")
        while True:
            try:
                n = self.collect_once()
                self.store.prune()
            except Exception as e:
                print(f"[metrics] error: {e}", file=sys.stderr)
            time.sleep(COLLECT_INTERVAL)


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
GREEN = "\033[0;32m"
CYAN  = "\033[1;36m"
DIM   = "\033[2m"
RESET = "\033[0m"


def cmd_collect(_args):
    """pso metrics collect — run one collection pass"""
    c = MetricsCollector()
    print("\n  Collecting metrics...")
    n = c.collect_once()
    print(f"  {GREEN}✓{RESET} {n} samples written\n")


def cmd_query(args):
    """pso metrics query <metric> [service]"""
    if not args:
        print("\n  Usage: pso metrics query <metric> [service]")
        print("  Common metrics: host_cpu_percent, host_memory_pct,")
        print("                  service_cpu_percent, service_memory_mb\n")
        return
    metric     = args[0]
    service_id = args[1] if len(args) > 1 else None
    store      = MetricsStore()
    rows       = store.query(metric, service_id, since_hours=24, limit=20)
    if not rows:
        print(f"\n  No data for '{metric}'" + (f" / {service_id}" if service_id else "") + "\n")
        print("  Run 'pso metrics collect' first.\n")
        return
    label = f"{metric}" + (f"  [{service_id}]" if service_id else "")
    print(f"\n  {BOLD}{label}{RESET}  (last {len(rows)} points)")
    print("  " + "─" * 50)
    for r in rows:
        ts  = r["collected_at"][:19].replace("T", " ")
        val = f"{r['value']:.2f}"
        print(f"  {DIM}{ts}{RESET}   {val}")
    print()


def cmd_export(args):
    """pso metrics export [service]"""
    svc   = args[0] if args else None
    store = MetricsStore()
    print(store.prometheus_export(svc))


def cmd_start(_args):
    """pso metrics start — run background daemon"""
    MetricsCollector().start_daemon()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "collect"
    rest = args[1:]
    dispatch = {
        "collect": cmd_collect,
        "query":   cmd_query,
        "export":  cmd_export,
        "start":   cmd_start,
    }
    fn = dispatch.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown command: {cmd}")
        print(f"  Use: collect | query <metric> [svc] | export [svc] | start\n")


if __name__ == "__main__":
    main()