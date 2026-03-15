#!/usr/bin/env python3
"""
PSO Backup Manager - Complete Edition

Manages service backups with restore, verification, and pruning capabilities.
"""

import os
import sys
import json
import shutil
import sqlite3
import tarfile
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.database import Database

DB_PATH = Path(os.environ.get("PSO_DB_PATH", Path.home() / ".pso_dev" / "pso.db"))


class BackupError(Exception):
    """Base exception for backup errors"""
    pass


class BackupManager:
    """
    Manages backups for PSO services.
    
    Features:
    - Create compressed backups of service data
    - Restore from backup
    - Verify backup integrity
    - Prune old backups
    - Scheduled backups
    - Metadata tracking
    """
    
    def __init__(self, backup_dir: Optional[Path] = None):
        """
        Initialize backup manager.

        Args:
            backup_dir: Directory for storing backups (default: /var/pso/backups)
        """
        self.db = Database()
        self._ensure_schema()

        if backup_dir is None:
            backup_dir = Path.home() / '.pso_dev' / 'backups' 

        self.backup_dir = Path(backup_dir)
        self.backup_dir.mkdir(parents=True, exist_ok=True)

    def _ensure_schema(self):
        """Create the backups table if it doesn't exist, migrate missing columns."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS backups (
                    id          INTEGER PRIMARY KEY AUTOINCREMENT,
                    backup_id   TEXT NOT NULL UNIQUE,
                    service_id  TEXT NOT NULL,
                    backup_path TEXT NOT NULL DEFAULT '',
                    created_at  TEXT NOT NULL,
                    size_bytes  INTEGER DEFAULT 0,
                    checksum    TEXT,
                    note        TEXT
                )
            """)
            for col, typedef in [
                ("backup_path", "TEXT NOT NULL DEFAULT ''"),
                ("size_bytes",  "INTEGER DEFAULT 0"),
                ("checksum",    "TEXT"),
                ("note",        "TEXT"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE backups ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_backups_service ON backups(service_id)"
            )
            conn.commit()
        finally:
            conn.close()

    def _db_conn(self):
        """Return a configured sqlite3 connection pointing at DB_PATH."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def create_backup(self, service_id: str, note: Optional[str] = None) -> str:
        """
        Create a backup of a service.
        
        Args:
            service_id: Service to backup
            note: Optional note about this backup
            
        Returns:
            Backup ID
        """
        # Verify service exists
        service = self.db.get_service(service_id)
        if not service:
            raise BackupError(f"Service not found: {service_id}")
        
        # Get service data directory
        data_dir = Path.home() / '.pso_dev' / 'services' / service_id
        if not data_dir.exists():
            raise BackupError(f"Service data directory not found: {data_dir}")
        
        # Generate backup ID
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_id = f"{service_id}_{timestamp}"
        
        # Create backup archive
        backup_file = self.backup_dir / f"{backup_id}.tar.gz"
        
        print(f"Creating backup: {backup_id}")
        print(f"Source: {data_dir}")
        print(f"Destination: {backup_file}")
        
        try:
            # Create tar.gz archive
            with tarfile.open(backup_file, "w:gz") as tar:
                tar.add(data_dir, arcname=service_id)
            
            # Calculate checksum
            checksum = self._calculate_checksum(backup_file)
            
            # Get backup size
            size_bytes = backup_file.stat().st_size
            
            # Create metadata
            metadata = {
                'backup_id': backup_id,
                'service_id': service_id,
                'timestamp': datetime.now().isoformat(),
                'note': note,
                'size_bytes': size_bytes,
                'checksum': checksum,
                'backup_path': str(backup_file)
            }
            
            # Save metadata to database
            with self._db_conn() as conn:
                conn.execute("""
                    INSERT INTO backups (
                        backup_id, service_id, backup_path, 
                        created_at, size_bytes, checksum, note
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    backup_id,
                    service_id,
                    str(backup_file),
                    datetime.now().isoformat(),
                    size_bytes,
                    checksum,
                    note
                ))
                conn.commit()
            
            # Save metadata JSON alongside backup
            metadata_file = self.backup_dir / f"{backup_id}.json"
            with open(metadata_file, 'w') as f:
                json.dump(metadata, f, indent=2)
            
            print(f"Backup created successfully: {backup_id}")
            print(f"Size: {self._format_size(size_bytes)}")
            print(f"Checksum: {checksum[:16]}...")
            
            return backup_id
            
        except Exception as e:
            # Cleanup on failure
            if backup_file.exists():
                backup_file.unlink()
            raise BackupError(f"Backup creation failed: {e}")
    
    def restore_backup(self, service_id: str, backup_id: str, 
                      stop_service: bool = True) -> bool:
        """
        Restore a service from backup.
        
        Args:
            service_id: Service to restore
            backup_id: Backup to restore from
            stop_service: Whether to stop the service first
            
        Returns:
            True if successful
        """
        # Verify backup exists
        backup_info = self._get_backup_info(backup_id)
        if not backup_info:
            raise BackupError(f"Backup not found: {backup_id}")
        
        if backup_info['service_id'] != service_id:
            raise BackupError(
                f"Backup is for {backup_info['service_id']}, not {service_id}"
            )
        
        backup_file = Path(backup_info['backup_path'])
        if not backup_file.exists():
            raise BackupError(f"Backup file not found: {backup_file}")
        
        # Verify backup integrity
        print("Verifying backup integrity...")
        if not self.verify_backup(backup_id):
            raise BackupError("Backup integrity check failed")
        
        print(f"Restoring {service_id} from backup {backup_id}")
        
        # Stop service if requested
        if stop_service:
            print(f"Stopping service {service_id}...")
            try:
                from core.service_manager import ServiceManager
                mgr = ServiceManager()
                mgr.stop(service_id)
            except Exception as e:
                print(f"Warning: Could not stop service: {e}")
        
        # Backup current data (safety backup)
        data_dir = Path.home() / '.pso_dev' / 'services' / service_id
        if data_dir.exists():
            safety_backup = data_dir.parent / f"{service_id}_pre_restore_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            print(f"Creating safety backup: {safety_backup.name}")
            shutil.move(str(data_dir), str(safety_backup))
        
        try:
            # Extract backup
            print(f"Extracting backup...")
            data_dir.parent.mkdir(parents=True, exist_ok=True)
            
            with tarfile.open(backup_file, "r:gz") as tar:
                tar.extractall(path=data_dir.parent)
            
            print(f"Restore completed successfully")
            
            # Restart service if it was stopped
            if stop_service:
                print(f"Starting service {service_id}...")
                try:
                    from core.service_manager import ServiceManager
                    mgr = ServiceManager()
                    mgr.start(service_id)
                except Exception as e:
                    print(f"Warning: Could not start service: {e}")
                    print("Please start manually: ./pso start {service_id}")
            
            return True
            
        except Exception as e:
            # Restore safety backup on failure
            print(f"Restore failed: {e}")
            if safety_backup.exists():
                print("Restoring previous state...")
                if data_dir.exists():
                    shutil.rmtree(data_dir)
                shutil.move(str(safety_backup), str(data_dir))
            raise BackupError(f"Restore failed: {e}")
    
    def verify_backup(self, backup_id: str) -> bool:
        """
        Verify backup integrity using checksum.
        
        Args:
            backup_id: Backup to verify
            
        Returns:
            True if backup is valid
        """
        backup_info = self._get_backup_info(backup_id)
        if not backup_info:
            raise BackupError(f"Backup not found: {backup_id}")
        
        backup_file = Path(backup_info['backup_path'])
        if not backup_file.exists():
            print(f"Backup file missing: {backup_file}")
            return False
        
        # Check if it's a valid tar.gz
        try:
            with tarfile.open(backup_file, "r:gz") as tar:
                # Try to list contents
                members = tar.getmembers()
                if not members:
                    print("Backup archive is empty")
                    return False
        except Exception as e:
            print(f"Backup archive is corrupted: {e}")
            return False
        
        # Verify checksum if available
        if backup_info.get('checksum'):
            print("Verifying checksum...")
            current_checksum = self._calculate_checksum(backup_file)
            stored_checksum = backup_info['checksum']
            
            if current_checksum != stored_checksum:
                print(f"Checksum mismatch!")
                print(f"Expected: {stored_checksum}")
                print(f"Got:      {current_checksum}")
                return False
        
        print(f"Backup {backup_id} is valid")
        return True
    
    def prune_backups(self, service_id: str, keep: int = 5) -> int:
        """
        Remove old backups, keeping only the most recent ones.
        
        Args:
            service_id: Service whose backups to prune
            keep: Number of backups to keep
            
        Returns:
            Number of backups deleted
        """
        backups = self.list_backups(service_id)
        
        if len(backups) <= keep:
            print(f"Only {len(backups)} backups exist, nothing to prune")
            return 0
        
        # Sort by created_at (newest first)
        backups.sort(key=lambda b: b['created_at'], reverse=True)
        
        # Keep the newest, delete the rest
        to_delete = backups[keep:]
        deleted = 0
        
        print(f"Pruning {len(to_delete)} old backups for {service_id}")
        
        for backup in to_delete:
            try:
                backup_id = backup['backup_id']
                backup_file = Path(backup['backup_path'])
                
                # Delete backup file
                if backup_file.exists():
                    backup_file.unlink()
                
                # Delete metadata file
                metadata_file = backup_file.with_suffix('.json')
                if metadata_file.exists():
                    metadata_file.unlink()
                
                # Remove from database
                with self._db_conn() as conn:
                    conn.execute(
                        "DELETE FROM backups WHERE backup_id = ?",
                        (backup_id,)
                    )
                    conn.commit()
                
                print(f"Deleted: {backup_id}")
                deleted += 1
                
            except Exception as e:
                print(f"Warning: Could not delete {backup_id}: {e}")
        
        print(f"Pruned {deleted} backups, kept {keep} most recent")
        return deleted
    
    def list_backups(self, service_id: Optional[str] = None) -> List[Dict]:
        """
        List all backups, optionally filtered by service.
        
        Args:
            service_id: Optional service filter
            
        Returns:
            List of backup information dicts
        """
        with self._db_conn() as conn:
            if service_id:
                rows = conn.execute("""
                    SELECT * FROM backups 
                    WHERE service_id = ?
                    ORDER BY created_at DESC
                """, (service_id,)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM backups 
                    ORDER BY created_at DESC
                """).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_backup_info(self, backup_id: str) -> Optional[Dict]:
        """Get detailed information about a backup"""
        return self._get_backup_info(backup_id)
    
    def schedule_backup(self, service_id: str, frequency: str = "daily") -> bool:
        """
        Schedule automatic backups using cron.
        
        Args:
            service_id: Service to backup
            frequency: daily, weekly, or monthly
            
        Returns:
            True if scheduled successfully
        """
        # Determine cron schedule
        schedules = {
            'daily': '0 2 * * *',      # 2 AM daily
            'weekly': '0 2 * * 0',     # 2 AM Sunday
            'monthly': '0 2 1 * *'     # 2 AM 1st of month
        }
        
        if frequency not in schedules:
            raise ValueError(f"Invalid frequency: {frequency}")
        
        cron_schedule = schedules[frequency]
        
        # Create cron job command
        pso_path = Path(__file__).parent.parent
        command = f"{cron_schedule} cd {pso_path} && python -m core.backup_manager create {service_id}"
        
        print(f"Scheduled {frequency} backup for {service_id}")
        print(f"Cron: {command}")
        print("\nTo add to crontab manually:")
        print(f"  crontab -e")
        print(f"  {command}")
        
        return True
    
    def _get_backup_info(self, backup_id: str) -> Optional[Dict]:
        """Internal method to get backup info"""
        with self._db_conn() as conn:
            row = conn.execute(
                "SELECT * FROM backups WHERE backup_id = ?",
                (backup_id,)
            ).fetchone()
            
            if row:
                return dict(row)
            return None
    
    def _calculate_checksum(self, file_path: Path) -> str:
        """Calculate SHA256 checksum of a file"""
        sha256 = hashlib.sha256()
        
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                sha256.update(chunk)
        
        return sha256.hexdigest()
    
    def _format_size(self, size_bytes: int) -> str:
        """Format byte size to human readable"""
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if size_bytes < 1024.0:
                return f"{size_bytes:.2f} {unit}"
            size_bytes /= 1024.0
        return f"{size_bytes:.2f} PB"


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI for backup management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PSO Backup Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Create backup
    create_parser = subparsers.add_parser('create', help='Create a backup')
    create_parser.add_argument('service_id', help='Service to backup')
    create_parser.add_argument('--note', help='Note about this backup')
    
    # Restore backup
    restore_parser = subparsers.add_parser('restore', help='Restore from backup')
    restore_parser.add_argument('service_id', help='Service to restore')
    restore_parser.add_argument('backup_id', help='Backup to restore from')
    restore_parser.add_argument('--no-stop', action='store_true', 
                               help='Do not stop service before restore')
    
    # Verify backup
    verify_parser = subparsers.add_parser('verify', help='Verify backup integrity')
    verify_parser.add_argument('backup_id', help='Backup to verify')
    
    # List backups
    list_parser = subparsers.add_parser('list', help='List backups')
    list_parser.add_argument('service_id', nargs='?', help='Filter by service')
    
    # Prune backups
    prune_parser = subparsers.add_parser('prune', help='Delete old backups')
    prune_parser.add_argument('service_id', help='Service whose backups to prune')
    prune_parser.add_argument('--keep', type=int, default=5, 
                             help='Number of backups to keep (default: 5)')
    
    # Schedule backup
    schedule_parser = subparsers.add_parser('schedule', help='Schedule automatic backups')
    schedule_parser.add_argument('service_id', help='Service to backup')
    schedule_parser.add_argument('--frequency', choices=['daily', 'weekly', 'monthly'],
                                default='daily', help='Backup frequency')
    
    # Info
    info_parser = subparsers.add_parser('info', help='Show backup details')
    info_parser.add_argument('backup_id', help='Backup ID')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = BackupManager()
    
    try:
        if args.command == 'create':
            backup_id = manager.create_backup(args.service_id, args.note)
            print(f"\nBackup ID: {backup_id}")
            print("\nTo restore:")
            print(f"  python -m core.backup_manager restore {args.service_id} {backup_id}")
        
        elif args.command == 'restore':
            manager.restore_backup(
                args.service_id, 
                args.backup_id,
                stop_service=not args.no_stop
            )
        
        elif args.command == 'verify':
            if manager.verify_backup(args.backup_id):
                print("Backup is valid")
            else:
                print("Backup verification failed")
                sys.exit(1)
        
        elif args.command == 'list':
            backups = manager.list_backups(args.service_id)
            
            if not backups:
                print("No backups found")
            else:
                print(f"Backups ({len(backups)}):")
                print("=" * 80)
                for backup in backups:
                    size = manager._format_size(backup['size_bytes'])
                    print(f"\nID: {backup['backup_id']}")
                    print(f"  Service: {backup['service_id']}")
                    print(f"  Created: {backup['created_at']}")
                    print(f"  Size: {size}")
                    if backup.get('note'):
                        print(f"  Note: {backup['note']}")
        
        elif args.command == 'prune':
            deleted = manager.prune_backups(args.service_id, args.keep)
            print(f"\nDeleted {deleted} old backups")
        
        elif args.command == 'schedule':
            manager.schedule_backup(args.service_id, args.frequency)
        
        elif args.command == 'info':
            info = manager.get_backup_info(args.backup_id)
            if info:
                print(f"Backup Information:")
                print("=" * 80)
                for key, value in info.items():
                    if key == 'size_bytes':
                        value = f"{value} ({manager._format_size(value)})"
                    print(f"{key}: {value}")
            else:
                print(f"Backup not found: {args.backup_id}")
    
    except BackupError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()