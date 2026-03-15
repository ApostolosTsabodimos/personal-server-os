#!/usr/bin/env python3
"""
PSO Migration & Import Tools - Component #12

Lets you bring existing Docker infrastructure under PSO management without
reinstalling anything. Three import paths:

  1. docker-compose.yml  — scan a compose file, import each service into PSO
  2. Running containers  — detect containers already on the host, adopt them
  3. PSO export/import   — move a PSO setup between machines (backup + restore)

Nothing is stopped or recreated during import unless you explicitly ask.
PSO just starts tracking the container and adds it to the database.
"""

import json
import subprocess
import sys
import re
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, List, Any, Tuple


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _run(cmd: List[str], capture: bool = True) -> Tuple[int, str, str]:
    """Run a shell command, return (returncode, stdout, stderr)."""
    try:
        r = subprocess.run(cmd, capture_output=capture, text=True)
        return r.returncode, r.stdout.strip(), r.stderr.strip()
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def _docker_available() -> bool:
    code, _, _ = _run(["docker", "info"])
    return code == 0


def _slugify(name: str) -> str:
    """Turn any string into a safe service_id."""
    return re.sub(r"[^a-z0-9-]", "-", name.lower()).strip("-")


CATEGORY_GUESSES = {
    "jellyfin": "media",   "plex": "media",    "navidrome": "media",
    "sonarr":   "media",   "radarr": "media",  "prowlarr": "media",
    "nextcloud": "productivity", "bookstack": "productivity",
    "paperless": "productivity",
    "gitea": "development", "gitlab": "development", "code-server": "development",
    "grafana": "monitoring", "prometheus": "monitoring", "uptime": "monitoring",
    "nginx": "infrastructure", "traefik": "infrastructure", "caddy": "infrastructure",
    "wireguard": "infrastructure", "portainer": "infrastructure",
    "vaultwarden": "security", "authelia": "security",
    "home-assistant": "home-automation", "node-red": "home-automation",
}

def _guess_category(name: str) -> str:
    name_lower = name.lower()
    for keyword, cat in CATEGORY_GUESSES.items():
        if keyword in name_lower:
            return cat
    return "other"


# ─────────────────────────────────────────────────────────────────────────────
# 1. Docker Compose importer
# ─────────────────────────────────────────────────────────────────────────────

class ComposeImporter:
    """
    Parse a docker-compose.yml and register each service into PSO.

    Usage:
        importer = ComposeImporter()
        preview = importer.preview("/path/to/docker-compose.yml")
        results = importer.import_file("/path/to/docker-compose.yml")
    """

    def preview(self, compose_path: str) -> List[Dict[str, Any]]:
        """Return what would be imported without writing anything."""
        services = self._parse(compose_path)
        return services

    def import_file(
        self,
        compose_path: str,
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """
        Import all services from a docker-compose.yml into PSO.

        Args:
            compose_path: Path to docker-compose.yml
            dry_run:      If True, show what would happen without writing
            overwrite:    If True, update existing PSO services

        Returns:
            Dict with keys: imported, skipped, errors, services
        """
        services = self._parse(compose_path)
        results = {"imported": [], "skipped": [], "errors": [], "services": services}

        if dry_run:
            results["note"] = "Dry run — nothing was written"
            return results

        try:
            from core.database import Database
            db = Database()
        except Exception as e:
            results["errors"].append(f"Could not connect to PSO database: {e}")
            return results

        for svc in services:
            svc_id = svc["service_id"]
            try:
                existing = db.get_service(svc_id)
                if existing and not overwrite:
                    results["skipped"].append(f"{svc_id} (already in PSO, use --overwrite)")
                    continue

                db.add_service({
                    "service_id":           svc_id,
                    "service_name":         svc["name"],
                    "version":              svc.get("version", "imported"),
                    "category":             svc["category"],
                    "status":               "imported",
                    "installation_method":  "compose-import",
                    "config": {
                        "compose_source": str(compose_path),
                        "image":          svc.get("image", ""),
                        "ports":          svc.get("ports", {}),
                        "volumes":        svc.get("volumes", []),
                        "environment":    svc.get("environment", {}),
                    },
                    "ports": svc.get("ports", {}),
                })
                results["imported"].append(svc_id)
            except Exception as e:
                results["errors"].append(f"{svc_id}: {e}")

        return results

    def _parse(self, compose_path: str) -> List[Dict[str, Any]]:
        """Parse docker-compose.yml into a list of service dicts."""
        path = Path(compose_path)
        if not path.exists():
            raise FileNotFoundError(f"File not found: {compose_path}")

        # Try PyYAML first, fall back to basic parser
        try:
            import yaml
            with open(path) as f:
                data = yaml.safe_load(f)
        except ImportError:
            data = self._basic_yaml_parse(path)

        if not data or "services" not in data:
            raise ValueError("No 'services' key found in compose file")

        results = []
        for name, cfg in (data.get("services") or {}).items():
            if not cfg:
                cfg = {}

            # Parse ports: ["8096:8096", "8097:8097/udp"] → {"web": 8096}
            ports = {}
            for i, p in enumerate(cfg.get("ports", [])):
                p_str = str(p).split("/")[0]  # strip /udp etc
                parts = p_str.split(":")
                host_port = int(parts[-2]) if len(parts) >= 2 else int(parts[0])
                port_name = "web" if i == 0 else f"port{i}"
                ports[port_name] = host_port

            # Parse environment
            env = cfg.get("environment", {})
            if isinstance(env, list):
                env = dict(e.split("=", 1) if "=" in e else (e, "") for e in env)

            results.append({
                "service_id": _slugify(name),
                "name":       name,
                "image":      cfg.get("image", ""),
                "category":   _guess_category(name),
                "version":    self._version_from_image(cfg.get("image", "")),
                "ports":      ports,
                "volumes":    cfg.get("volumes", []),
                "environment": env,
                "restart":    cfg.get("restart", ""),
            })

        return results

    def _version_from_image(self, image: str) -> str:
        """Extract version tag from image name, e.g. nginx:1.25 → 1.25."""
        if ":" in image:
            tag = image.split(":")[-1]
            return tag if tag != "latest" else "latest"
        return "unknown"

    def _basic_yaml_parse(self, path: Path) -> Dict:
        """
        Minimal YAML parser for simple compose files when PyYAML is unavailable.
        Handles indented key:value structure only — not anchors, sequences, etc.
        """
        # Fall back to running 'docker compose config' if available
        code, out, _ = _run(["docker", "compose", "-f", str(path), "config"])
        if code == 0 and out:
            try:
                import yaml
                return yaml.safe_load(out)
            except Exception:
                pass
        raise ImportError(
            "PyYAML not installed and docker compose config failed.\n"
            "Install with: pip install pyyaml --break-system-packages"
        )


# ─────────────────────────────────────────────────────────────────────────────
# 2. Running container adopter
# ─────────────────────────────────────────────────────────────────────────────

class ContainerAdopter:
    """
    Detect Docker containers already running on the host and register them
    with PSO so they appear in 'pso list', 'pso discover', etc.

    The containers are NOT restarted or modified — PSO just starts tracking them.
    """

    # Container name prefixes PSO itself creates — skip these
    PSO_PREFIX = "pso-"

    def scan(self, include_stopped: bool = False) -> List[Dict[str, Any]]:
        """
        List containers on the host that are not already managed by PSO.
        Returns a list of container info dicts.
        """
        if not _docker_available():
            raise RuntimeError("Docker is not running or not installed")

        fmt = "{{.ID}}|{{.Names}}|{{.Image}}|{{.Status}}|{{.Ports}}"
        flags = ["docker", "ps", "--format", fmt]
        if include_stopped:
            flags.append("-a")

        code, out, err = _run(flags)
        if code != 0:
            raise RuntimeError(f"docker ps failed: {err}")

        containers = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split("|")
            if len(parts) < 4:
                continue

            cid, names, image, status, ports_raw = (parts + [""])[:5]
            name = names.lstrip("/").split(",")[0]

            # Skip PSO-managed containers
            if name.startswith(self.PSO_PREFIX):
                continue

            ports = self._parse_ports_str(ports_raw)
            containers.append({
                "container_id": cid[:12],
                "service_id":   _slugify(name),
                "name":         name,
                "image":        image,
                "status":       "running" if "Up" in status else "stopped",
                "category":     _guess_category(name),
                "version":      self._version_from_image(image),
                "ports":        ports,
            })

        return containers

    def adopt(
        self,
        container_names: Optional[List[str]] = None,
        dry_run: bool = False,
    ) -> Dict[str, Any]:
        """
        Register unmanaged containers into PSO.

        Args:
            container_names: List of names to adopt. None = adopt all detected.
            dry_run:         Preview only, no writes.
        """
        containers = self.scan(include_stopped=True)

        if container_names:
            containers = [c for c in containers if c["name"] in container_names
                          or c["service_id"] in container_names]

        results = {"adopted": [], "skipped": [], "errors": [], "containers": containers}

        if dry_run:
            results["note"] = "Dry run — nothing was written"
            return results

        if not containers:
            results["note"] = "No unmanaged containers found"
            return results

        try:
            from core.database import Database
            db = Database()
        except Exception as e:
            results["errors"].append(f"Could not connect to PSO database: {e}")
            return results

        for c in containers:
            svc_id = c["service_id"]
            try:
                existing = db.get_service(svc_id)
                if existing:
                    results["skipped"].append(f"{svc_id} (already in PSO)")
                    continue

                db.add_service({
                    "service_id":          svc_id,
                    "service_name":        c["name"],
                    "version":             c["version"],
                    "category":            c["category"],
                    "status":              c["status"],
                    "installation_method": "container-adopt",
                    "config": {
                        "container_id": c["container_id"],
                        "image":        c["image"],
                        "ports":        c["ports"],
                        "adopted_at":   datetime.now().isoformat(),
                    },
                    "ports": c["ports"],
                })
                results["adopted"].append(svc_id)
            except Exception as e:
                results["errors"].append(f"{svc_id}: {e}")

        return results

    def _parse_ports_str(self, ports_raw: str) -> Dict[str, int]:
        """Parse docker ps port string like '0.0.0.0:8096->8096/tcp' → {'web': 8096}."""
        ports = {}
        i = 0
        for match in re.finditer(r":(\d+)->\d+", ports_raw):
            port_num = int(match.group(1))
            key = "web" if i == 0 else f"port{i}"
            ports[key] = port_num
            i += 1
        return ports

    def _version_from_image(self, image: str) -> str:
        if ":" in image:
            tag = image.split(":")[-1]
            return tag if tag != "latest" else "latest"
        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# 3. PSO export / import (move between machines)
# ─────────────────────────────────────────────────────────────────────────────

class PSOExporter:
    """
    Export PSO service registry to a JSON file so it can be imported
    on another machine or used as a migration snapshot.
    """

    def export(self, output_path: str) -> Dict[str, Any]:
        """Export all PSO-managed services to a JSON file."""
        try:
            from core.database import Database
            db = Database()
            services = db.list_services()
        except Exception as e:
            return {"error": str(e)}

        export_data = {
            "pso_export_version": "1.0",
            "exported_at": datetime.now().isoformat(),
            "service_count": len(services),
            "services": services,
        }

        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(export_data, f, indent=2, default=str)

        return {
            "success": True,
            "path": str(path),
            "services": len(services),
        }

    def import_export(
        self,
        import_path: str,
        dry_run: bool = False,
        overwrite: bool = False,
    ) -> Dict[str, Any]:
        """Import services from a PSO export JSON file."""
        path = Path(import_path)
        if not path.exists():
            return {"error": f"File not found: {import_path}"}

        with open(path) as f:
            data = json.load(f)

        if "services" not in data:
            return {"error": "Invalid export file — missing 'services' key"}

        services = data["services"]
        results = {
            "imported": [], "skipped": [], "errors": [],
            "source_date": data.get("exported_at", "unknown"),
            "total": len(services),
        }

        if dry_run:
            results["note"] = "Dry run — nothing was written"
            results["would_import"] = [s.get("service_id") for s in services]
            return results

        try:
            from core.database import Database
            db = Database()
        except Exception as e:
            results["errors"].append(f"Could not connect to PSO database: {e}")
            return results

        for svc in services:
            svc_id = svc.get("service_id")
            if not svc_id:
                continue
            try:
                existing = db.get_service(svc_id)
                if existing and not overwrite:
                    results["skipped"].append(f"{svc_id} (exists, use --overwrite)")
                    continue
                svc["installation_method"] = svc.get("installation_method", "pso-import")
                db.add_service(svc)
                results["imported"].append(svc_id)
            except Exception as e:
                results["errors"].append(f"{svc_id}: {e}")

        return results


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

BOLD  = "\033[1m"
CYAN  = "\033[1;36m"
GREEN = "\033[0;32m"
RED   = "\033[0;31m"
DIM   = "\033[2m"
RESET = "\033[0m"


def _print_results(results: Dict[str, Any], action: str = "imported"):
    imported = results.get("imported") or results.get("adopted", [])
    skipped  = results.get("skipped", [])
    errors   = results.get("errors", [])

    if results.get("note"):
        print(f"\n  {DIM}{results['note']}{RESET}")

    if imported:
        print(f"\n  {GREEN}✓{RESET} {action.title()}: {len(imported)}")
        for s in imported:
            print(f"      {s}")
    if skipped:
        print(f"\n  — Skipped: {len(skipped)}")
        for s in skipped:
            print(f"      {DIM}{s}{RESET}")
    if errors:
        print(f"\n  {RED}✗{RESET} Errors: {len(errors)}")
        for e in errors:
            print(f"      {e}")
    print()


def cmd_compose(args):
    """pso migrate compose <file> [--dry-run] [--overwrite]"""
    if not args:
        print("\n  Usage: pso migrate compose <docker-compose.yml> [--dry-run] [--overwrite]\n")
        return

    path = args[0]
    dry_run   = "--dry-run"   in args
    overwrite = "--overwrite" in args

    importer = ComposeImporter()

    try:
        services = importer.preview(path)
    except Exception as e:
        print(f"\n  {RED}✗{RESET} Could not read compose file: {e}\n")
        return

    W = 68
    print()
    print(f"{BOLD}  Compose Import Preview: {Path(path).name}{RESET}")
    print("  " + "─" * W)
    print(f"  {'Service':<24} {'Category':<16} {'Image':<26}")
    print("  " + "─" * W)
    for s in services:
        image_short = s['image'].split("/")[-1][:25] if s['image'] else "(none)"
        ports_str = ", ".join(str(v) for v in s['ports'].values()) if s['ports'] else "—"
        print(f"  {BOLD}{s['service_id']:<24}{RESET} {s['category']:<16} {image_short:<26}  :{ports_str}")
    print()

    if dry_run:
        print(f"  {DIM}Dry run — run without --dry-run to import{RESET}\n")
        return

    confirm = input(f"  Import {len(services)} service(s) into PSO? (yes/no): ").strip()
    if confirm != "yes":
        print("  Cancelled\n")
        return

    results = importer.import_file(path, dry_run=False, overwrite=overwrite)
    _print_results(results, "imported")

    if results["imported"]:
        print(f"  Run {BOLD}pso discover sync{RESET} to update the service directory.")
        print()


def cmd_adopt(args):
    """pso migrate adopt [<name> ...] [--dry-run] [--all]"""
    dry_run = "--dry-run" in args
    adopt_all = "--all" in args
    names = [a for a in args if not a.startswith("--")]

    adopter = ContainerAdopter()

    try:
        containers = adopter.scan(include_stopped=True)
    except RuntimeError as e:
        print(f"\n  {RED}✗{RESET} {e}\n")
        return

    if not containers:
        print("\n  No unmanaged containers found on this host.\n")
        print(f"  {DIM}(PSO-managed containers with 'pso-' prefix are excluded){RESET}\n")
        return

    W = 68
    print()
    print(f"{BOLD}  Unmanaged Containers Detected{RESET}")
    print("  " + "─" * W)
    print(f"  {'Name':<24} {'Status':<10} {'Category':<16} {'Port(s)'}")
    print("  " + "─" * W)
    for c in containers:
        ports_str = ", ".join(f":{v}" for v in c['ports'].values()) if c['ports'] else "—"
        color = GREEN if c['status'] == 'running' else DIM
        print(f"  {BOLD}{c['name']:<24}{RESET} {color}{c['status']:<10}{RESET} {c['category']:<16} {ports_str}")
    print()

    if dry_run:
        print(f"  {DIM}Dry run — run without --dry-run to adopt{RESET}\n")
        return

    if not adopt_all and not names:
        print("  Options:")
        print(f"    pso migrate adopt --all              Adopt all {len(containers)} containers")
        print(f"    pso migrate adopt <name> [<name>]    Adopt specific containers")
        print(f"    pso migrate adopt --dry-run          Preview only")
        print()
        return

    target_names = None if adopt_all else names
    results = adopter.adopt(container_names=target_names, dry_run=False)
    _print_results(results, "adopted")

    if results.get("adopted"):
        print(f"  Run {BOLD}pso discover sync{RESET} to update the service directory.")
        print()


def cmd_export(args):
    """pso migrate export [output_path]"""
    out = args[0] if args else f"pso-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
    exporter = PSOExporter()
    result = exporter.export(out)
    if result.get("error"):
        print(f"\n  {RED}✗{RESET} Export failed: {result['error']}\n")
    else:
        print(f"\n  {GREEN}✓{RESET} Exported {result['services']} service(s) to: {result['path']}\n")


def cmd_import(args):
    """pso migrate import <file> [--dry-run] [--overwrite]"""
    if not args:
        print("\n  Usage: pso migrate import <pso-export.json> [--dry-run] [--overwrite]\n")
        return
    path      = args[0]
    dry_run   = "--dry-run"   in args
    overwrite = "--overwrite" in args
    exporter  = PSOExporter()
    results   = exporter.import_export(path, dry_run=dry_run, overwrite=overwrite)
    if results.get("error"):
        print(f"\n  {RED}✗{RESET} {results['error']}\n")
    else:
        print(f"\n  Source export: {DIM}{results.get('source_date','?')}{RESET}")
        _print_results(results, "imported")


def cmd_status(args):
    """pso migrate status — show what's in PSO vs what's running in Docker"""
    if not _docker_available():
        print("\n  Docker is not running.\n")
        return

    try:
        from core.database import Database
        db = Database()
        pso_services = {s['service_id'] for s in db.list_services()}
    except Exception as e:
        print(f"\n  Could not read PSO database: {e}\n")
        return

    adopter = ContainerAdopter()
    try:
        unmanaged = adopter.scan()
    except Exception:
        unmanaged = []

    unmanaged_ids = {c['service_id'] for c in unmanaged}

    print()
    print(f"{BOLD}  PSO Migration Status{RESET}")
    print("  " + "─" * 50)
    print(f"  PSO-managed services:    {len(pso_services)}")
    print(f"  Unmanaged containers:    {len(unmanaged_ids)}")
    if unmanaged:
        print(f"\n  {CYAN}Unmanaged (not in PSO):{RESET}")
        for c in unmanaged:
            print(f"    {c['name']:<26} {DIM}{c['image']}{RESET}")
        print(f"\n  Run {BOLD}pso migrate adopt --all{RESET} to bring them under PSO management.")
    else:
        print(f"\n  {GREEN}✓{RESET} All running containers are managed by PSO.")
    print()


def main():
    args = sys.argv[1:]
    cmd  = args[0] if args else "status"
    rest = args[1:]

    commands = {
        "compose": cmd_compose,
        "adopt":   cmd_adopt,
        "export":  cmd_export,
        "import":  cmd_import,
        "status":  cmd_status,
    }

    fn = commands.get(cmd)
    if fn:
        fn(rest)
    else:
        print(f"\n  Unknown command: {cmd}")
        print(f"  Available: {', '.join(commands)}\n")


if __name__ == "__main__":
    main()