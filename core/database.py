#!/usr/bin/env python3
"""
PSO Database Layer
SQLite database for tracking installed services, configurations, and history
"""

import sqlite3
import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime
from contextlib import contextmanager


class DatabaseError(Exception):
    """Base exception for database errors"""
    pass


class Database:
    """
    SQLite database manager for PSO
    
    Stores:
    - Installed services (id, version, status, config)
    - Installation history and logs
    - Service configurations
    """
    
    def __init__(self, db_path: Optional[Path] = None):
        """
        Initialize database connection
        
        Args:
            db_path: Path to SQLite database file (default: /var/pso/pso.db)
        """
        if db_path is None:
            # Use home directory for development
            db_path = Path.home() / '.pso_dev' / 'pso.db'
        
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Initialize database schema
        self._init_schema()
    
    @contextmanager
    def _get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path, timeout=10.0)
        conn.row_factory = sqlite3.Row  # Return rows as dictionaries
        conn.execute("PRAGMA journal_mode=WAL")   # Better concurrency
        try:
            yield conn
            conn.commit()
        except Exception as e:
            conn.rollback()
            raise DatabaseError(f"Database error: {e}")
        finally:
            conn.close()
    
    def _init_schema(self):
        """Initialize database schema"""
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Table: installed_services
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS installed_services (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT UNIQUE NOT NULL,
                    service_name TEXT NOT NULL,
                    version TEXT NOT NULL,
                    category TEXT NOT NULL,
                    status TEXT NOT NULL,
                    installation_method TEXT NOT NULL,
                    installed_at TIMESTAMP NOT NULL,
                    updated_at TIMESTAMP NOT NULL,
                    config JSON,
                    UNIQUE(service_id)
                )
            """)
            
            # Table: service_ports
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_ports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    port_name TEXT NOT NULL,
                    port_number INTEGER NOT NULL,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE,
                    UNIQUE(service_id, port_name)
                )
            """)
            
            # Table: service_volumes
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_volumes (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    host_path TEXT NOT NULL,
                    container_path TEXT NOT NULL,
                    readonly BOOLEAN NOT NULL DEFAULT 0,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            """)
            
            # Table: installation_history
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS installation_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    status TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    details TEXT,
                    error_message TEXT,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            """)
            
            # Table: service_dependencies
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS service_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    depends_on TEXT NOT NULL,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            """)
            
            # Create indexes for performance
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_service_status 
                ON installed_services(status)
            """)
            
            cursor.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_service 
                ON installation_history(service_id, timestamp)
            """)
    
    # ========== Service Management ==========
    
    def _purge_service_records(self, service_id: str):
        """
        Delete ALL database records for a service_id with FK enforcement OFF.
        Safe to call whether or not the service exists — used to guarantee a
        clean slate before install and during uninstall.
        """
        raw = sqlite3.connect(self.db_path, timeout=10.0)
        try:
            raw.execute("PRAGMA foreign_keys = OFF")
            for table in ('service_ports', 'service_volumes',
                          'service_dependencies', 'installed_services'):
                raw.execute(f"DELETE FROM {table} WHERE service_id = ?", (service_id,))
            raw.commit()
        finally:
            raw.close()

    def add_service(self, service_data: Dict[str, Any]) -> bool:
        """
        Add a newly installed service to the database.
        Idempotent: purges orphaned records first via a raw FK-off connection,
        then inserts cleanly. Reinstalling after any kind of failed uninstall
        will always work.
        """
        service_id = service_data['service_id']

        # Purge orphaned records in a separate connection with FK OFF.
        # PRAGMA foreign_keys cannot be toggled inside an active transaction,
        # so this MUST be a separate connection before _get_connection opens.
        self._purge_service_records(service_id)

        with self._get_connection() as conn:
            cursor = conn.cursor()
            now = datetime.now().isoformat()

            # Insert main service record
            cursor.execute("""
                INSERT INTO installed_services
                (service_id, service_name, version, category, status,
                 installation_method, installed_at, updated_at, config)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                service_id,
                service_data['service_name'],
                service_data['version'],
                service_data['category'],
                service_data['status'],
                service_data['installation_method'],
                now, now,
                json.dumps(service_data.get('config', {}))
            ))

            # Insert ports
            for port_name, port_number in service_data.get('ports', {}).items():
                cursor.execute("""
                    INSERT INTO service_ports (service_id, port_name, port_number)
                    VALUES (?, ?, ?)
                """, (service_id, port_name, port_number))

            # Insert volumes
            for volume in service_data.get('volumes', []):
                cursor.execute("""
                    INSERT INTO service_volumes
                    (service_id, host_path, container_path, readonly)
                    VALUES (?, ?, ?, ?)
                """, (
                    service_id,
                    os.path.expanduser(volume['host']),  # Expand ~ to home directory
                    volume['container'],
                    volume.get('readonly', False)
                ))

            # Insert dependencies
            for dep in service_data.get('dependencies', []):
                cursor.execute("""
                    INSERT INTO service_dependencies (service_id, depends_on)
                    VALUES (?, ?)
                """, (service_id, dep))

            # Log the installation
            cursor.execute("""
                INSERT INTO installation_history
                (service_id, action, status, timestamp, details, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (service_id, 'install', 'success', now,
                  'Service installed successfully', None))

            return True
    
    def remove_service(self, service_id: str) -> bool:
        """
        Remove a service from the database
        
        Args:
            service_id: Service identifier
            
        Returns:
            True if successful
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check if service exists
            if not self.is_installed(service_id):
                raise DatabaseError(f"Service not found: {service_id}")
            
            pass  # existence already checked above

        # Purge all records (FK OFF) then log the uninstall (FK OFF so no
        # parent constraint required for installation_history).
        self._purge_service_records(service_id)

        try:
            raw = sqlite3.connect(self.db_path, timeout=10.0)
            raw.execute("PRAGMA foreign_keys = OFF")
            raw.execute("""
                INSERT INTO installation_history
                (service_id, action, status, timestamp, details, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (service_id, 'uninstall', 'success',
                  datetime.now().isoformat(), 'Service uninstalled', None))
            raw.commit()
            raw.close()
        except Exception:
            pass  # History logging is best-effort

        return True
    
    def update_service_status(self, service_id: str, status: str) -> bool:
        """
        Update service status.
        Returns True if updated, False if service not found (never raises).
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE installed_services
                SET status = ?, updated_at = ?
                WHERE service_id = ?
            """, (status, datetime.now().isoformat(), service_id))
            return cursor.rowcount > 0
    
    def get_service(self, service_id: str) -> Optional[Dict[str, Any]]:
        """
        Get service information
        
        Args:
            service_id: Service identifier
            
        Returns:
            Service data dictionary or None if not found
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM installed_services WHERE service_id = ?
            """, (service_id,))
            
            row = cursor.fetchone()
            if not row:
                return None
            
            service = dict(row)
            service['config'] = json.loads(service['config']) if service['config'] else {}
            
            # Get ports
            cursor.execute("""
                SELECT port_name, port_number FROM service_ports 
                WHERE service_id = ?
            """, (service_id,))
            service['ports'] = {row['port_name']: row['port_number'] 
                              for row in cursor.fetchall()}
            
            # Get volumes
            cursor.execute("""
                SELECT host_path, container_path, readonly FROM service_volumes 
                WHERE service_id = ?
            """, (service_id,))
            service['volumes'] = [dict(row) for row in cursor.fetchall()]
            
            # Get dependencies
            cursor.execute("""
                SELECT depends_on FROM service_dependencies 
                WHERE service_id = ?
            """, (service_id,))
            service['dependencies'] = [row['depends_on'] for row in cursor.fetchall()]
            
            return service
    
    def list_services(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        List all installed services
        
        Args:
            status: Filter by status (optional)
            
        Returns:
            List of service dictionaries
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            if status:
                cursor.execute("""
                    SELECT * FROM installed_services WHERE status = ?
                    ORDER BY service_name
                """, (status,))
            else:
                cursor.execute("""
                    SELECT * FROM installed_services ORDER BY service_name
                """)
            
            services = []
            for row in cursor.fetchall():
                service = dict(row)
                service['config'] = json.loads(service['config']) if service['config'] else {}
                services.append(service)
            
            return services
    
    def is_installed(self, service_id: str) -> bool:
        """
        Check if a service is installed
        
        Args:
            service_id: Service identifier
            
        Returns:
            True if installed
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT COUNT(*) as count FROM installed_services 
                WHERE service_id = ?
            """, (service_id,))
            return cursor.fetchone()['count'] > 0
    
    def get_port_conflicts(self, ports: Dict[str, int]) -> List[Tuple[str, int, str]]:
        """
        Check if any ports are already in use by installed services
        
        Args:
            ports: Dictionary of port_name: port_number
            
        Returns:
            List of (port_name, port_number, conflicting_service_id)
        """
        conflicts = []
        
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            for port_name, port_number in ports.items():
                cursor.execute("""
                    SELECT service_id FROM service_ports 
                    WHERE port_number = ?
                """, (port_number,))
                
                row = cursor.fetchone()
                if row:
                    conflicts.append((port_name, port_number, row['service_id']))
        
        return conflicts
    
    # ========== Installation History ==========
    
    def log_action(self, service_id: str, action: str, status: str, 
                   details: Optional[str] = None, 
                   error_message: Optional[str] = None):
        """
        Log a service action to history
        
        Args:
            service_id: Service identifier
            action: Action type (install, uninstall, start, stop, update, etc.)
            status: Action status (success, failed, in_progress)
            details: Additional details
            error_message: Error message if failed
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO installation_history 
                (service_id, action, status, timestamp, details, error_message)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                service_id,
                action,
                status,
                datetime.now().isoformat(),
                details,
                error_message
            ))
    
    def get_service_history(self, service_id: str, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get installation history for a service
        
        Args:
            service_id: Service identifier
            limit: Maximum number of records to return
            
        Returns:
            List of history records
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT * FROM installation_history 
                WHERE service_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (service_id, limit))
            
            return [dict(row) for row in cursor.fetchall()]
    
    # ========== Statistics ==========
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get database statistics
        
        Returns:
            Dictionary with stats
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            
            # Total services
            cursor.execute("SELECT COUNT(*) as count FROM installed_services")
            total = cursor.fetchone()['count']
            
            # By status
            cursor.execute("""
                SELECT status, COUNT(*) as count 
                FROM installed_services 
                GROUP BY status
            """)
            by_status = {row['status']: row['count'] for row in cursor.fetchall()}
            
            # By category
            cursor.execute("""
                SELECT category, COUNT(*) as count 
                FROM installed_services 
                GROUP BY category
            """)
            by_category = {row['category']: row['count'] for row in cursor.fetchall()}
            
            return {
                'total_services': total,
                'by_status': by_status,
                'by_category': by_category
            }
    
    # ========== Utility ==========
    
    def close(self):
        """Close database connection (handled by context manager)"""
        pass
    
    def reset(self):
        """
        Reset database (delete all data)
        WARNING: This will delete all installed service records!
        """
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM installed_services")
            cursor.execute("DELETE FROM installation_history")


# Convenience functions
def get_database(db_path: Optional[Path] = None) -> Database:
    """Get database instance"""
    return Database(db_path)