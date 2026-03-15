#!/usr/bin/env python3
"""
PSO Service Update Manager

Manages Docker image updates for services with automatic backup and rollback.
"""

import os
import sys
import json
import subprocess
from datetime import datetime
from typing import Dict, List, Optional

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.database import Database
from core.service_manager import ServiceManager
from core.backup_manager import BackupManager
from core.manifest import ManifestLoader


class UpdateError(Exception):
    """Base exception for update errors"""
    pass


class ServiceUpdateManager:
    """
    Manages service updates with safety features.
    
    Features:
    - Check for Docker image updates
    - Automatic backup before update
    - One-click updates
    - Rollback on failure
    - Update history tracking
    """
    
    def __init__(self):
        self.db = Database()
        self.service_mgr = ServiceManager()
        self.backup_mgr = BackupManager()
        self.loader = ManifestLoader()
        
        # Ensure update history table exists
        self._init_update_history()
    
    def _init_update_history(self):
        """Create update history table if not exists"""
        with self.db._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS update_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    old_digest TEXT,
                    new_digest TEXT,
                    updated_at TEXT NOT NULL,
                    backup_id TEXT,
                    status TEXT NOT NULL,
                    error_message TEXT,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            """)
            conn.commit()
    
    def check_updates(self, service_id: Optional[str] = None) -> List[Dict]:
        """
        Check for available updates.
        
        Args:
            service_id: Check specific service, or all if None
            
        Returns:
            List of services with available updates
        """
        updates_available = []
        
        # Get services to check
        if service_id:
            service = self.db.get_service(service_id)
            if not service:
                raise UpdateError(f"Service not found: {service_id}")
            services = [service]
        else:
            services = self.db.list_services()
        
        print(f"Checking {len(services)} service(s) for updates...")
        
        for service in services:
            sid = service['service_id']
            
            try:
                # Get manifest
                manifest = self.loader.load(sid)
                
                # Skip non-Docker services
                if manifest.data.get('installation', {}).get('method') != 'docker':
                    continue
                
                image = manifest.data['installation']['image']
                
                # Get current and latest digests
                current_digest = self._get_current_digest(sid)
                latest_digest = self._get_latest_digest(image)
                
                if current_digest and latest_digest:
                    if current_digest != latest_digest:
                        updates_available.append({
                            'service_id': sid,
                            'service_name': service['service_name'],
                            'image': image,
                            'current_digest': current_digest[:12],
                            'latest_digest': latest_digest[:12],
                            'update_available': True
                        })
                        print(f"  ✓ {sid}: Update available")
                    else:
                        print(f"  - {sid}: Up to date")
                
            except Exception as e:
                print(f"  ✗ {sid}: Error - {e}")
        
        return updates_available
    
    def update_service(self, service_id: str, backup: bool = True, 
                      dry_run: bool = False) -> bool:
        """
        Update a service to the latest version.
        
        Args:
            service_id: Service to update
            backup: Create backup before update
            dry_run: Test update without applying
            
        Returns:
            True if successful
        """
        # Verify service exists
        service = self.db.get_service(service_id)
        if not service:
            raise UpdateError(f"Service not found: {service_id}")
        
        # Get manifest
        manifest = self.loader.load(service_id)
        
        if manifest.data.get('installation', {}).get('method') != 'docker':
            raise UpdateError(f"Service {service_id} is not a Docker service")
        
        image = manifest.data['installation']['image']
        
        print(f"Updating {service_id}...")
        print(f"Image: {image}")
        print("=" * 70)
        
        # Get current digest
        current_digest = self._get_current_digest(service_id)
        print(f"Current: {current_digest[:12] if current_digest else 'unknown'}")
        
        if dry_run:
            print("\nDRY RUN MODE - No changes will be made\n")
        
        backup_id = None
        
        try:
            # Step 1: Create backup
            if backup and not dry_run:
                print("\nStep 1: Creating backup...")
                backup_id = self.backup_mgr.create_backup(
                    service_id,
                    note=f"Pre-update backup"
                )
                print(f"Backup created: {backup_id}")
            else:
                print("\nStep 1: Skipping backup")
            
            # Step 2: Pull latest image
            print("\nStep 2: Pulling latest image...")
            if not dry_run:
                self._pull_image(image)
            else:
                print(f"Would pull: {image}")
            
            # Get new digest
            new_digest = self._get_latest_digest(image)
            print(f"Latest: {new_digest[:12] if new_digest else 'unknown'}")
            
            # Check if update needed
            if current_digest == new_digest and not dry_run:
                print("\nAlready up to date!")
                return True
            
            # Step 3: Stop service
            print("\nStep 3: Stopping service...")
            if not dry_run:
                self.service_mgr.stop(service_id)
            else:
                print(f"Would stop: {service_id}")
            
            # Step 4: Remove old container
            print("\nStep 4: Removing old container...")
            if not dry_run:
                self._remove_container(service_id)
            else:
                print(f"Would remove container: pso-{service_id}")
            
            # Step 5: Start service (will use new image)
            print("\nStep 5: Starting service with new image...")
            if not dry_run:
                self.service_mgr.start(service_id)
                
                # Wait and verify
                import time
                time.sleep(5)
                
                status = self.service_mgr.get_status(service_id)
                if status.get('status') != 'running':
                    raise UpdateError("Service failed to start after update")
                
                print("Service started successfully")
            else:
                print(f"Would start: {service_id}")
            
            # Step 6: Record update
            if not dry_run:
                self._record_update(
                    service_id=service_id,
                    old_digest=current_digest,
                    new_digest=new_digest,
                    backup_id=backup_id,
                    status='success'
                )
            
            print("\n" + "=" * 70)
            print("✓ Update completed successfully")
            if backup_id:
                print(f"Backup available: {backup_id}")
            
            return True
            
        except Exception as e:
            print("\n" + "=" * 70)
            print(f"✗ Update failed: {e}")
            
            # Record failed update
            if not dry_run:
                self._record_update(
                    service_id=service_id,
                    old_digest=current_digest,
                    new_digest=new_digest,
                    backup_id=backup_id,
                    status='failed',
                    error_message=str(e)
                )
            
            # Attempt rollback
            if backup_id and not dry_run:
                print("\nAttempting rollback...")
                try:
                    self.backup_mgr.restore_backup(service_id, backup_id)
                    print("✓ Rollback successful")
                except Exception as rollback_error:
                    print(f"✗ Rollback failed: {rollback_error}")
                    print(f"Manual restore: ./pso backup restore {service_id} {backup_id}")
            
            raise UpdateError(f"Update failed: {e}")
    
    def update_all(self, backup: bool = True, dry_run: bool = False) -> Dict:
        """
        Update all services with available updates.
        
        Args:
            backup: Create backups before updates
            dry_run: Test updates without applying
            
        Returns:
            Dict with update results
        """
        updates = self.check_updates()
        
        if not updates:
            print("All services are up to date")
            return {'updated': 0, 'failed': 0}
        
        print(f"\nFound {len(updates)} service(s) with updates available\n")
        
        results = {
            'updated': 0,
            'failed': 0,
            'details': []
        }
        
        for update_info in updates:
            service_id = update_info['service_id']
            
            print(f"\n{'='*70}")
            print(f"Updating {service_id}...")
            
            try:
                self.update_service(service_id, backup=backup, dry_run=dry_run)
                results['updated'] += 1
                results['details'].append({
                    'service_id': service_id,
                    'status': 'success'
                })
            except Exception as e:
                results['failed'] += 1
                results['details'].append({
                    'service_id': service_id,
                    'status': 'failed',
                    'error': str(e)
                })
        
        print(f"\n{'='*70}")
        print(f"Update Summary:")
        print(f"  Updated: {results['updated']}")
        print(f"  Failed: {results['failed']}")
        
        return results
    
    def get_update_history(self, service_id: Optional[str] = None, 
                          limit: int = 10) -> List[Dict]:
        """
        Get update history.
        
        Args:
            service_id: Filter by service (all if None)
            limit: Maximum number of records
            
        Returns:
            List of update records
        """
        with self.db._get_connection() as conn:
            if service_id:
                rows = conn.execute("""
                    SELECT * FROM update_history 
                    WHERE service_id = ?
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (service_id, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT * FROM update_history 
                    ORDER BY updated_at DESC
                    LIMIT ?
                """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def _get_current_digest(self, service_id: str) -> Optional[str]:
        """Get digest of currently running image"""
        try:
            result = subprocess.run(
                ['docker', 'inspect', '--format={{.Image}}', f'pso-{service_id}'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    
    def _get_latest_digest(self, image: str) -> Optional[str]:
        """Get digest of latest image from registry"""
        try:
            # Pull to get latest
            subprocess.run(
                ['docker', 'pull', image],
                capture_output=True,
                text=True,
                check=True
            )
            
            # Get digest
            result = subprocess.run(
                ['docker', 'inspect', '--format={{.Id}}', image],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except subprocess.CalledProcessError:
            return None
    
    def _pull_image(self, image: str):
        """Pull Docker image"""
        subprocess.run(['docker', 'pull', image], check=True)
    
    def _remove_container(self, service_id: str):
        """Remove Docker container"""
        try:
            subprocess.run(
                ['docker', 'rm', '-f', f'pso-{service_id}'],
                capture_output=True,
                check=True
            )
        except subprocess.CalledProcessError:
            pass
    
    def _record_update(self, service_id: str, old_digest: Optional[str], 
                      new_digest: Optional[str], backup_id: Optional[str], 
                      status: str, error_message: Optional[str] = None):
        """Record update in history"""
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT INTO update_history (
                    service_id, old_digest, new_digest, 
                    updated_at, backup_id, status, error_message
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                service_id, old_digest, new_digest,
                datetime.now().isoformat(),
                backup_id, status, error_message
            ))
            conn.commit()


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI for update management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PSO Service Update Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Check for updates
    check_parser = subparsers.add_parser('check', help='Check for available updates')
    check_parser.add_argument('service_id', nargs='?', help='Check specific service')
    
    # Update service
    update_parser = subparsers.add_parser('update', help='Update a service')
    update_parser.add_argument('service_id', help='Service to update')
    update_parser.add_argument('--no-backup', action='store_true', help='Skip backup')
    update_parser.add_argument('--dry-run', action='store_true', help='Test without applying')
    
    # Update all
    update_all_parser = subparsers.add_parser('update-all', help='Update all services')
    update_all_parser.add_argument('--no-backup', action='store_true', help='Skip backups')
    update_all_parser.add_argument('--dry-run', action='store_true', help='Test without applying')
    
    # History
    history_parser = subparsers.add_parser('history', help='Show update history')
    history_parser.add_argument('service_id', nargs='?', help='Filter by service')
    history_parser.add_argument('--limit', type=int, default=10, help='Number of records')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    manager = ServiceUpdateManager()
    
    try:
        if args.command == 'check':
            updates = manager.check_updates(args.service_id)
            
            if not updates:
                print("\nAll services are up to date")
            else:
                print(f"\nUpdates Available ({len(updates)}):")
                print("=" * 80)
                for update in updates:
                    print(f"\n{update['service_name']}")
                    print(f"  Current: {update['current_digest']}")
                    print(f"  Latest:  {update['latest_digest']}")
        
        elif args.command == 'update':
            manager.update_service(
                args.service_id,
                backup=not args.no_backup,
                dry_run=args.dry_run
            )
        
        elif args.command == 'update-all':
            manager.update_all(
                backup=not args.no_backup,
                dry_run=args.dry_run
            )
        
        elif args.command == 'history':
            history = manager.get_update_history(args.service_id, args.limit)
            
            if not history:
                print("No update history")
            else:
                print(f"Update History:")
                print("=" * 80)
                for record in history:
                    print(f"\n{record['service_id']} - {record['updated_at']}")
                    print(f"  Status: {record['status']}")
                    if record['old_digest']:
                        print(f"  Old: {record['old_digest'][:12]}")
                    if record['new_digest']:
                        print(f"  New: {record['new_digest'][:12]}")
                    if record['backup_id']:
                        print(f"  Backup: {record['backup_id']}")
                    if record['error_message']:
                        print(f"  Error: {record['error_message']}")
    
    except UpdateError as e:
        print(f"Error: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()