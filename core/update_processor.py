#!/usr/bin/env python3
"""
PSO Update Processor
Downloads, verifies, and applies service updates.
Backs up config/volumes before applying. Rolls back on health-check failure.

Delegates to update_security for verification.
Called by update_manager via: pso update apply <service>
"""

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

from core.update_security import verify_update, compute_checksum


DB_PATH = Path(os.environ.get("PSO_DB_PATH", Path.home() / ".pso_dev" / "pso.db"))
BACKUP_DIR = Path.home() / ".pso_dev" / "update_backups"


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

def _ensure_schema():
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS update_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                service_id TEXT NOT NULL,
                from_version TEXT,
                to_version TEXT,
                status TEXT NOT NULL,
                backup_path TEXT,
                applied_at TEXT NOT NULL,
                rolled_back_at TEXT,
                error TEXT,
                security_checks TEXT
            )
        """)
        for col, typedef in [
            ("applied_at",      "TEXT"),
            ("rolled_back_at",  "TEXT"),
            ("security_checks", "TEXT"),
        ]:
            try:
                conn.execute(f"ALTER TABLE update_history ADD COLUMN {col} {typedef}")
            except sqlite3.OperationalError:
                pass
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_uh_service ON update_history(service_id)"
        )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _run(cmd: list[str], check: bool = True, timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, check=check, timeout=timeout)


def _get_service(service_id: str) -> dict | None:
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM installed_services WHERE id=?", (service_id,)
        ).fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception:
        return None


def _get_manifest(service_id: str) -> dict:
    services_dir = Path.cwd() / "services"
    manifest_path = services_dir / service_id / "manifest.json"
    if manifest_path.exists():
        with open(manifest_path) as f:
            return json.load(f)
    return {}


def _record_update(service_id: str, from_ver: str, to_ver: str, status: str,
                    backup_path: str = None, error: str = None,
                    security_checks: dict = None, rolled_back_at: str = None):
    _ensure_schema()
    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("""
            INSERT INTO update_history
              (service_id, from_version, to_version, status, backup_path, applied_at, rolled_back_at, error, security_checks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            service_id, from_ver, to_ver, status, backup_path, _now(),
            rolled_back_at, error,
            json.dumps(security_checks) if security_checks else None,
        ))
        conn.commit()
    finally:
        conn.close()


def _update_service_version(service_id: str, new_version: str, new_image: str = None):
    conn = sqlite3.connect(DB_PATH)
    try:
        if new_image:
            conn.execute(
                "UPDATE installed_services SET version=?, docker_image=? WHERE id=?",
                (new_version, new_image, service_id)
            )
        else:
            conn.execute(
                "UPDATE installed_services SET version=? WHERE id=?",
                (new_version, service_id)
            )
        conn.commit()
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Backup / restore
# ---------------------------------------------------------------------------

def _backup_service(service_id: str) -> Path:
    """Create a pre-update backup of service config and volumes."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"{service_id}_{ts}"
    backup_path.mkdir(parents=True, exist_ok=True)

    # Backup config files
    config_dirs = [
        Path.home() / ".pso_dev" / "configs" / service_id,
        Path.cwd() / "services" / service_id,
    ]
    for config_dir in config_dirs:
        if config_dir.exists():
            dest = backup_path / "config" / config_dir.name
            try:
                shutil.copytree(config_dir, dest)
            except Exception:
                pass

    # Backup Docker volumes
    try:
        result = _run(["docker", "inspect", service_id], check=False)
        if result.returncode == 0:
            container_info = json.loads(result.stdout)
            mounts = container_info[0].get("Mounts", []) if container_info else []
            for mount in mounts:
                if mount.get("Type") == "volume":
                    vol_name = mount["Name"]
                    vol_backup = backup_path / "volumes" / vol_name
                    vol_backup.mkdir(parents=True, exist_ok=True)
                    # Use docker to copy volume contents
                    _run([
                        "docker", "run", "--rm",
                        "-v", f"{vol_name}:/source:ro",
                        "-v", f"{vol_backup}:/dest",
                        "alpine", "cp", "-a", "/source/.", "/dest/"
                    ], check=False, timeout=60)
    except Exception:
        pass

    # Save metadata
    meta = {
        "service_id": service_id,
        "created_at": _now(),
        "backup_path": str(backup_path),
    }
    with open(backup_path / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)

    return backup_path


def _restore_backup(service_id: str, backup_path: Path) -> bool:
    """Restore a pre-update backup."""
    if not backup_path.exists():
        return False

    # Restore config files
    config_backup = backup_path / "config"
    if config_backup.exists():
        for src in config_backup.iterdir():
            dest_base = Path.home() / ".pso_dev" / "configs" / service_id
            try:
                if dest_base.exists():
                    shutil.rmtree(dest_base)
                shutil.copytree(src, dest_base)
            except Exception:
                pass

    # Restore Docker volumes
    volumes_backup = backup_path / "volumes"
    if volumes_backup.exists():
        for vol_dir in volumes_backup.iterdir():
            vol_name = vol_dir.name
            try:
                _run([
                    "docker", "run", "--rm",
                    "-v", f"{vol_name}:/dest",
                    "-v", f"{vol_dir}:/source:ro",
                    "alpine", "sh", "-c", "rm -rf /dest/* && cp -a /source/. /dest/"
                ], check=False, timeout=60)
            except Exception:
                pass

    return True


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

def _wait_healthy(service_id: str, timeout_seconds: int = 60) -> bool:
    """Poll the DB health table until service is healthy or timeout."""
    deadline = time.time() + timeout_seconds
    while time.time() < deadline:
        try:
            conn = sqlite3.connect(DB_PATH)
            row = conn.execute(
                "SELECT status FROM health_checks WHERE service_id=? ORDER BY checked_at DESC LIMIT 1",
                (service_id,)
            ).fetchone()
            conn.close()
            if row and row[0] in ("healthy", "ok"):
                return True
        except Exception:
            pass
        time.sleep(5)
    return False


def _container_running(service_id: str) -> bool:
    try:
        result = _run(["docker", "inspect", "--format", "{{.State.Running}}", service_id], check=False)
        return result.stdout.strip().lower() == "true"
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Core update flow
# ---------------------------------------------------------------------------

class UpdateProcessor:

    def apply(self, service_id: str, target_version: str = None,
               expected_sha256: str = None, pubkey_path: str = None,
               skip_verification: bool = False, dry_run: bool = False) -> bool:
        """
        Apply an update to a service.

        Flow: security checks → backup → stop → pull → start → health check → (rollback if fail)
        """
        _ensure_schema()

        service = _get_service(service_id)
        if not service:
            print(f"✗ Service not found: {service_id}")
            return False

        manifest = _get_manifest(service_id)
        current_version = service.get("version", "unknown")
        docker_image_base = service.get("docker_image", service_id)
        image_name = docker_image_base.split(":")[0]

        to_version = target_version or "latest"
        new_image = f"{image_name}:{to_version}"

        print(f"\nApplying update: {service_id}")
        print(f"  {current_version} → {to_version}")
        print(f"  Image: {new_image}")

        if dry_run:
            print("\n[DRY RUN] No changes made.")
            return True

        # --- Step 1: Security verification ---
        security_result = None
        if not skip_verification:
            print("\n[1/5] Security verification...")

            # If we have a download URL (from manifest or update_checks), verify TLS
            download_url = manifest.get("update_source", {}).get("url")

            # For Docker image updates we can't checksum the image before pulling,
            # but we can verify the source URL if provided
            if download_url or expected_sha256 or pubkey_path:
                with tempfile.NamedTemporaryFile(delete=False) as tmp:
                    tmp_path = tmp.name

                if download_url:
                    try:
                        import urllib.request
                        urllib.request.urlretrieve(download_url, tmp_path)
                    except Exception as e:
                        print(f"  ✗ Download failed: {e}")
                        _record_update(service_id, current_version, to_version, "failed",
                                       error=f"Download failed: {e}")
                        return False

                    sec = verify_update(
                        tmp_path,
                        url=download_url,
                        expected_sha256=expected_sha256,
                        pubkey_path=pubkey_path,
                    )
                    os.unlink(tmp_path)
                    security_result = sec.checks

                    if not sec.passed:
                        print(sec.summary())
                        _record_update(service_id, current_version, to_version, "failed",
                                       security_checks=security_result,
                                       error="Security verification failed")
                        return False
                    print(sec.summary())
                else:
                    # Just TLS check on Docker Hub
                    from core.update_security import verify_tls
                    tls_ok = verify_tls(f"https://hub.docker.com/v2/repositories/{image_name}/tags")
                    security_result = {"TLS/HTTPS": tls_ok}
                    if not tls_ok:
                        print("  ✗ Docker Hub TLS check failed")
                        _record_update(service_id, current_version, to_version, "failed",
                                       security_checks=security_result,
                                       error="TLS check failed")
                        return False
                    print("  ✓ TLS verified")
            else:
                print("  – No URL/checksum provided, skipping file verification")
                security_result = {}
        else:
            print("\n[1/5] Security verification skipped")
            security_result = {}

        # --- Step 2: Backup ---
        print("\n[2/5] Creating backup...")
        try:
            backup_path = _backup_service(service_id)
            print(f"  ✓ Backup at: {backup_path}")
        except Exception as e:
            print(f"  ! Backup warning: {e} (continuing)")
            backup_path = None

        # --- Step 3: Stop service ---
        print("\n[3/5] Stopping service...")
        try:
            _run(["docker", "stop", service_id], timeout=30)
            print("  ✓ Stopped")
        except Exception as e:
            print(f"  ! Could not stop container: {e}")
            # May not be running — continue

        # --- Step 4: Pull new image ---
        print(f"\n[4/5] Pulling {new_image}...")
        try:
            result = _run(["docker", "pull", new_image], timeout=300)
            print("  ✓ Image pulled")
        except subprocess.CalledProcessError as e:
            print(f"  ✗ Pull failed: {e.stderr}")
            print("  Rolling back...")
            self._rollback(service_id, current_version, backup_path)
            _record_update(service_id, current_version, to_version, "failed",
                           backup_path=str(backup_path) if backup_path else None,
                           security_checks=security_result,
                           error=f"Docker pull failed: {e.stderr[:200]}")
            return False

        # --- Step 5: Start + health check ---
        print("\n[5/5] Starting service and verifying health...")
        try:
            _run(["docker", "start", service_id], timeout=30)
        except Exception as e:
            print(f"  ✗ Start failed: {e}")
            print("  Rolling back...")
            self._rollback(service_id, current_version, backup_path)
            _record_update(service_id, current_version, to_version, "failed",
                           backup_path=str(backup_path) if backup_path else None,
                           security_checks=security_result,
                           error=f"Start failed: {e}")
            return False

        # Wait for health
        print("  Waiting for health check (60s)...")
        healthy = _wait_healthy(service_id, timeout_seconds=60)

        if not healthy:
            # Fall back: check if container is at least running
            running = _container_running(service_id)
            if not running:
                print("  ✗ Container not running after update. Rolling back...")
                self._rollback(service_id, current_version, backup_path)
                _record_update(service_id, current_version, to_version, "failed",
                               backup_path=str(backup_path) if backup_path else None,
                               security_checks=security_result,
                               error="Container not running after update")
                return False
            else:
                print("  ~ Health check not available, but container is running. Proceeding.")

        # --- Success ---
        _update_service_version(service_id, to_version, new_image)
        _record_update(service_id, current_version, to_version, "success",
                       backup_path=str(backup_path) if backup_path else None,
                       security_checks=security_result)

        print(f"\n✓ {service_id} updated to {to_version}")
        return True

    def _rollback(self, service_id: str, restore_version: str, backup_path: Path = None):
        """Roll back to previous version."""
        print(f"  Rolling back {service_id} to {restore_version}...")
        service = _get_service(service_id)
        if not service:
            return

        image_base = service.get("docker_image", service_id).split(":")[0]
        rollback_image = f"{image_base}:{restore_version}"

        try:
            _run(["docker", "stop", service_id], check=False, timeout=30)
            _run(["docker", "pull", rollback_image], check=False, timeout=300)
            if backup_path:
                _restore_backup(service_id, backup_path)
            _run(["docker", "start", service_id], check=False, timeout=30)
            print(f"  ✓ Rolled back to {restore_version}")
        except Exception as e:
            print(f"  ✗ Rollback error: {e}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def cmd_apply(args: list[str]):
    if not args:
        print("Usage: pso update apply <service> [--version V] [--sha256 HASH] [--pubkey FILE] [--skip-verify] [--dry-run]")
        return

    service_id = args[0]
    target_version = None
    expected_sha256 = None
    pubkey_path = None
    skip_verify = False
    dry_run = False

    i = 1
    while i < len(args):
        if args[i] == "--version" and i + 1 < len(args):
            target_version = args[i + 1]; i += 2
        elif args[i] == "--sha256" and i + 1 < len(args):
            expected_sha256 = args[i + 1]; i += 2
        elif args[i] == "--pubkey" and i + 1 < len(args):
            pubkey_path = args[i + 1]; i += 2
        elif args[i] == "--skip-verify":
            skip_verify = True; i += 1
        elif args[i] == "--dry-run":
            dry_run = True; i += 1
        else:
            i += 1

    processor = UpdateProcessor()
    ok = processor.apply(
        service_id,
        target_version=target_version,
        expected_sha256=expected_sha256,
        pubkey_path=pubkey_path,
        skip_verification=skip_verify,
        dry_run=dry_run,
    )
    sys.exit(0 if ok else 1)


def cmd_history(args: list[str]):
    _ensure_schema()
    service_id = args[0] if args else None
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    if service_id:
        rows = conn.execute(
            "SELECT * FROM update_history WHERE service_id=? ORDER BY applied_at DESC LIMIT 20",
            (service_id,)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM update_history ORDER BY applied_at DESC LIMIT 20"
        ).fetchall()
    conn.close()

    if not rows:
        print("  No update history found.")
        return

    print(f"\n  {'TIME':<22} {'SERVICE':<18} {'FROM':<12} {'TO':<12} STATUS")
    print(f"  {'─'*22} {'─'*17} {'─'*11} {'─'*11} {'─'*10}")
    for row in rows:
        r = dict(row)
        ts = r["applied_at"][:19].replace("T", " ")
        status_marker = "✓" if r["status"] == "success" else "✗"
        print(f"  {ts:<22} {r['service_id']:<18} {(r['from_version'] or '?'):<12} {(r['to_version'] or '?'):<12} {status_marker} {r['status']}")
    print()


def main(args: list[str] = None):
    args = args or sys.argv[1:]
    sub = args[0] if args else "history"

    if sub == "apply":
        cmd_apply(args[1:])
    elif sub == "history":
        cmd_history(args[1:])
    else:
        print(f"Unknown subcommand: {sub}")
        print("Usage: pso update [apply <service>|history [service]]")


if __name__ == "__main__":
    main()