#!/usr/bin/env python3
"""
Resource Manager - Set and enforce resource limits on services

Manages CPU, memory, and disk quotas with predefined profiles and custom limits.
Integrates with Docker to enforce limits on running containers.
"""

import docker
import json
import os
import sqlite3
from pathlib import Path
from typing import Dict, Optional, List, Tuple
from dataclasses import dataclass, asdict


@dataclass
class ResourceProfile:
    """Resource allocation profile"""
    name: str
    cpu_cores: float  # CPU cores (0.5, 1, 2, etc)
    memory_mb: int    # Memory in MB
    disk_mb: int      # Disk quota in MB
    description: str


DB_PATH = Path(os.environ.get("PSO_DB_PATH", Path.home() / ".pso_dev" / "pso.db"))


class ResourceManager:
    """Manage resource limits for services"""
    
    # Predefined resource profiles
    PROFILES = {
        'tiny': ResourceProfile(
            name='tiny',
            cpu_cores=0.5,
            memory_mb=256,
            disk_mb=1024,  # 1GB
            description='Minimal resources - lightweight services (dashboards, utilities)'
        ),
        'small': ResourceProfile(
            name='small',
            cpu_cores=1.0,
            memory_mb=512,
            disk_mb=5120,  # 5GB
            description='Small services - web apps, APIs, basic databases'
        ),
        'medium': ResourceProfile(
            name='medium',
            cpu_cores=2.0,
            memory_mb=2048,
            disk_mb=20480,  # 20GB
            description='Medium services - media servers, heavier databases'
        ),
        'large': ResourceProfile(
            name='large',
            cpu_cores=4.0,
            memory_mb=4096,
            disk_mb=102400,  # 100GB
            description='Large services - video processing, ML workloads'
        ),
        'unlimited': ResourceProfile(
            name='unlimited',
            cpu_cores=0,  # 0 means no limit
            memory_mb=0,
            disk_mb=0,
            description='No resource limits (use with caution)'
        )
    }
    
    # Docker restart policies
    RESTART_POLICIES = {
        'no': {'Name': 'no'},
        'on-failure': {'Name': 'on-failure', 'MaximumRetryCount': 3},
        'always': {'Name': 'always'},
        'unless-stopped': {'Name': 'unless-stopped'}
    }
    
    def __init__(self, db=None):
        """Initialize Resource Manager. db parameter kept for backward compatibility."""
        self.docker_client = docker.from_env()
        self._ensure_schema()

    def _ensure_schema(self):
        """Create resource tables if they don't exist, migrate missing columns."""
        conn = sqlite3.connect(DB_PATH)
        try:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS resource_limits (
                    service_id TEXT PRIMARY KEY,
                    profile TEXT DEFAULT 'small',
                    cpu_cores REAL DEFAULT 1.0,
                    memory_mb INTEGER DEFAULT 512,
                    disk_mb INTEGER DEFAULT 5120,
                    restart_policy TEXT DEFAULT 'unless-stopped',
                    custom BOOLEAN DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS resource_usage (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT,
                    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    cpu_percent REAL,
                    memory_mb INTEGER,
                    disk_mb INTEGER
                )
            ''')
            for col, typedef in [
                ("custom",   "BOOLEAN DEFAULT 0"),
                ("updated_at","TIMESTAMP DEFAULT CURRENT_TIMESTAMP"),
            ]:
                try:
                    conn.execute(f"ALTER TABLE resource_limits ADD COLUMN {col} {typedef}")
                except sqlite3.OperationalError:
                    pass
            conn.commit()
        finally:
            conn.close()

    def _conn(self):
        """Return a configured sqlite3 connection."""
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        return conn
    
    def get_profile(self, profile_name: str) -> Optional[ResourceProfile]:
        """Get a resource profile by name"""
        return self.PROFILES.get(profile_name)
    
    def list_profiles(self) -> Dict[str, Dict]:
        """List all available profiles"""
        return {
            name: asdict(profile) 
            for name, profile in self.PROFILES.items()
        }
    
    def get_service_limits(self, service_id: str) -> Dict:
        """
        Get current resource limits for a service
        
        Returns:
            Dict with cpu_cores, memory_mb, disk_mb, restart_policy, profile
        """
        with self._conn() as conn:
            row = conn.execute(
                'SELECT * FROM resource_limits WHERE service_id = ?',
                (service_id,)
            ).fetchone()
        
        if row:
            return {
                'service_id': row[0],
                'profile': row[1],
                'cpu_cores': row[2],
                'memory_mb': row[3],
                'disk_mb': row[4],
                'restart_policy': row[5],
                'custom': bool(row[6])
            }
        else:
            # Return default (small profile)
            return self._get_default_limits()
    
    def _get_default_limits(self) -> Dict:
        """Get default resource limits"""
        profile = self.PROFILES['small']
        return {
            'profile': 'small',
            'cpu_cores': profile.cpu_cores,
            'memory_mb': profile.memory_mb,
            'disk_mb': profile.disk_mb,
            'restart_policy': 'unless-stopped',
            'custom': False
        }
    
    def set_service_limits(
        self, 
        service_id: str,
        profile: Optional[str] = None,
        cpu_cores: Optional[float] = None,
        memory_mb: Optional[int] = None,
        disk_mb: Optional[int] = None,
        restart_policy: Optional[str] = None
    ) -> bool:
        """
        Set resource limits for a service
        
        Args:
            service_id: Service identifier
            profile: Profile name (tiny/small/medium/large/unlimited)
            cpu_cores: Custom CPU cores (overrides profile)
            memory_mb: Custom memory in MB (overrides profile)
            disk_mb: Custom disk quota in MB (overrides profile)
            restart_policy: Docker restart policy
            
        Returns:
            True if successful
        """
        # If profile specified, use its values as base
        if profile and profile in self.PROFILES:
            prof = self.PROFILES[profile]
            final_cpu = cpu_cores if cpu_cores is not None else prof.cpu_cores
            final_mem = memory_mb if memory_mb is not None else prof.memory_mb
            final_disk = disk_mb if disk_mb is not None else prof.disk_mb
            is_custom = (cpu_cores is not None or 
                        memory_mb is not None or 
                        disk_mb is not None)
        else:
            # Custom limits only
            if cpu_cores is None or memory_mb is None:
                raise ValueError("Must specify profile or custom cpu_cores and memory_mb")
            final_cpu = cpu_cores
            final_mem = memory_mb
            final_disk = disk_mb or 5120
            profile = 'custom'
            is_custom = True
        
        final_restart = restart_policy or 'unless-stopped'
        
        # Validate restart policy
        if final_restart not in self.RESTART_POLICIES:
            raise ValueError(f"Invalid restart policy: {final_restart}")
        
        # Save to database
        with self._conn() as conn:
            conn.execute('''
                INSERT OR REPLACE INTO resource_limits
                (service_id, profile, cpu_cores, memory_mb, disk_mb, restart_policy, custom, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ''', (service_id, profile, final_cpu, final_mem, final_disk, final_restart, is_custom))
            conn.commit()
        
        return True
    
    def apply_limits_to_container(self, service_id: str, container_name: str) -> bool:
        """
        Apply resource limits to a running container
        
        Args:
            service_id: Service identifier
            container_name: Docker container name
            
        Returns:
            True if successful
        """
        limits = self.get_service_limits(service_id)
        
        try:
            container = self.docker_client.containers.get(container_name)
            
            # Build update configuration
            update_config = {}
            
            # CPU limits (nano_cpus = cores * 1e9)
            if limits['cpu_cores'] > 0:
                update_config['nano_cpus'] = int(limits['cpu_cores'] * 1e9)
            
            # Memory limits (convert MB to bytes)
            if limits['memory_mb'] > 0:
                update_config['mem_limit'] = limits['memory_mb'] * 1024 * 1024
                # Also set memory reservation (soft limit) to 80% of hard limit
                update_config['mem_reservation'] = int(update_config['mem_limit'] * 0.8)
            
            # Restart policy
            restart_policy = self.RESTART_POLICIES.get(limits['restart_policy'])
            if restart_policy:
                update_config['restart_policy'] = restart_policy
            
            # Apply updates
            container.update(**update_config)
            
            return True
            
        except docker.errors.NotFound:
            raise RuntimeError(f"Container not found: {container_name}")
        except docker.errors.APIError as e:
            raise RuntimeError(f"Docker API error: {e}")
    
    def get_container_stats(self, container_name: str) -> Dict:
        """
        Get current resource usage for a container
        
        Returns:
            Dict with cpu_percent, memory_mb, disk_mb
        """
        try:
            container = self.docker_client.containers.get(container_name)
            stats = container.stats(stream=False)
            
            # Calculate CPU percentage
            cpu_delta = stats['cpu_stats']['cpu_usage']['total_usage'] - \
                       stats['precpu_stats']['cpu_usage']['total_usage']
            system_delta = stats['cpu_stats']['system_cpu_usage'] - \
                          stats['precpu_stats']['system_cpu_usage']
            cpu_percent = 0.0
            if system_delta > 0:
                cpu_percent = (cpu_delta / system_delta) * 100.0
            
            # Memory usage in MB
            memory_mb = stats['memory_stats']['usage'] / (1024 * 1024)
            
            # Disk usage (approximate from filesystem stats)
            disk_mb = 0
            if 'storage_stats' in stats:
                disk_mb = stats['storage_stats'].get('used_bytes', 0) / (1024 * 1024)
            
            return {
                'cpu_percent': round(cpu_percent, 2),
                'memory_mb': round(memory_mb, 2),
                'disk_mb': round(disk_mb, 2)
            }
            
        except docker.errors.NotFound:
            return {
                'cpu_percent': 0,
                'memory_mb': 0,
                'disk_mb': 0
            }
        except Exception as e:
            print(f"Error getting stats: {e}")
            return {
                'cpu_percent': 0,
                'memory_mb': 0,
                'disk_mb': 0
            }
    
    def record_usage(self, service_id: str, container_name: str, notifier=None):
        """Record current resource usage in database.
        
        Args:
            service_id:     Service identifier
            container_name: Docker container name
            notifier:       Optional NotificationService instance. If provided,
                            resource alerts are fired when thresholds are exceeded.
        """
        stats = self.get_container_stats(container_name)
        
        with self._conn() as conn:
            conn.execute('''
                INSERT INTO resource_usage (service_id, cpu_percent, memory_mb, disk_mb)
                VALUES (?, ?, ?, ?)
            ''', (service_id, stats['cpu_percent'], stats['memory_mb'], stats['disk_mb']))
            conn.commit()
        
        if notifier is not None:
            self.check_resource_alerts(service_id, container_name, notifier, stats=stats)
    

    def check_resource_alerts(
        self,
        service_id: str,
        container_name: str,
        notifier,
        stats: Dict = None,
        cpu_threshold: float = 85.0,
        memory_threshold: float = 90.0,
    ) -> List[str]:
        """
        Check resource usage against thresholds and fire notifications if exceeded.

        Called automatically by record_usage() when a notifier is provided.
        Can also be called directly for on-demand checks.

        Thresholds:
          - CPU:    fires 'cpu_warning'    if cpu_percent   > cpu_threshold (default 85%)
          - Memory: fires 'memory_warning' if memory usage  > memory_threshold % of limit
                    (if no limit is set, fires if memory_mb > 1024 MB as a safe default)
          - Disk:   fires 'disk_warning'   if disk usage exceeds the configured quota

        Args:
            service_id:       Service identifier
            container_name:   Docker container name (used to fetch stats if not provided)
            notifier:         NotificationService instance
            stats:            Pre-fetched stats dict (saves a Docker API call if already known)
            cpu_threshold:    CPU percent above which to alert (default 85.0)
            memory_threshold: Memory percent-of-limit above which to alert (default 90.0)

        Returns:
            List of event names that were fired (empty if nothing triggered)
        """
        if stats is None:
            stats = self.get_container_stats(container_name)

        limits  = self.get_service_limits(service_id)
        fired   = []

        # ── CPU alert ────────────────────────────────────────────────────────
        cpu_pct = stats.get('cpu_percent', 0)
        if cpu_pct > cpu_threshold:
            detail = (
                f"CPU at {cpu_pct:.1f}% "
                f"(threshold: {cpu_threshold:.0f}%)"
            )
            notifier.notify('cpu_warning', service_id=service_id, detail=detail)
            fired.append('cpu_warning')

        # ── Memory alert ─────────────────────────────────────────────────────
        memory_mb    = stats.get('memory_mb', 0)
        memory_limit = limits.get('memory_mb', 0)  # 0 means no limit configured

        if memory_limit > 0:
            memory_pct = (memory_mb / memory_limit) * 100
            if memory_pct > memory_threshold:
                detail = (
                    f"Memory at {memory_mb:.0f} MB "
                    f"({memory_pct:.1f}% of {memory_limit:.0f} MB limit)"
                )
                notifier.notify('memory_warning', service_id=service_id, detail=detail)
                fired.append('memory_warning')
        else:
            # No configured limit — alert if usage exceeds a safe absolute default
            ABSOLUTE_MEMORY_WARNING_MB = 1024
            if memory_mb > ABSOLUTE_MEMORY_WARNING_MB:
                detail = (
                    f"Memory at {memory_mb:.0f} MB "
                    f"(no limit set; default warning at {ABSOLUTE_MEMORY_WARNING_MB} MB)"
                )
                notifier.notify('memory_warning', service_id=service_id, detail=detail)
                fired.append('memory_warning')

        # ── Disk alert ───────────────────────────────────────────────────────
        disk_quota = limits.get('disk_mb', 0)
        if disk_quota > 0:
            disk_mb = stats.get('disk_mb', 0)
            if disk_mb > disk_quota:
                detail = (
                    f"Disk at {disk_mb:.0f} MB "
                    f"(quota: {disk_quota:.0f} MB)"
                )
                notifier.notify('disk_warning', service_id=service_id, detail=detail)
                fired.append('disk_warning')

        return fired

    def get_usage_history(
        self, 
        service_id: str, 
        limit: int = 100
    ) -> List[Dict]:
        """
        Get historical resource usage for a service
        
        Args:
            service_id: Service identifier
            limit: Number of records to return
            
        Returns:
            List of usage records
        """
        with self._conn() as conn:
            rows = conn.execute('''
                SELECT timestamp, cpu_percent, memory_mb, disk_mb
                FROM resource_usage
                WHERE service_id = ?
                ORDER BY timestamp DESC
                LIMIT ?
            ''', (service_id, limit)).fetchall()

        return [
            {
                'timestamp': row[0],
                'cpu_percent': row[1],
                'memory_mb': row[2],
                'disk_mb': row[3]
            }
            for row in rows
        ]
    
    def check_disk_quota(self, service_id: str, service_dir: Path) -> Tuple[int, int, bool]:
        """
        Check if service is within disk quota
        
        Args:
            service_id: Service identifier
            service_dir: Path to service data directory
            
        Returns:
            Tuple of (used_mb, quota_mb, within_quota)
        """
        limits = self.get_service_limits(service_id)
        quota_mb = limits['disk_mb']
        
        # Calculate directory size
        total_size = 0
        if service_dir.exists():
            for path in service_dir.rglob('*'):
                if path.is_file():
                    total_size += path.stat().st_size
        
        used_mb = total_size / (1024 * 1024)
        within_quota = quota_mb == 0 or used_mb <= quota_mb
        
        return (round(used_mb, 2), quota_mb, within_quota)
    
    def get_recommended_profile(self, service_category: str) -> str:
        """
        Get recommended profile based on service category
        
        Args:
            service_category: Service category (media, database, web, etc)
            
        Returns:
            Profile name
        """
        recommendations = {
            'infrastructure': 'tiny',
            'web': 'small',
            'productivity': 'small',
            'automation': 'small',
            'monitoring': 'small',
            'networking': 'small',
            'media': 'medium',
            'database': 'medium',
            'development': 'medium',
            'ai': 'large',
            'video': 'large'
        }
        
        return recommendations.get(service_category.lower(), 'small')


# CLI interface
if __name__ == '__main__':
    import sys
    import argparse
    
    parser = argparse.ArgumentParser(description='PSO Resource Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # List profiles
    subparsers.add_parser('profiles', help='List available resource profiles')
    
    # Get service limits
    get_parser = subparsers.add_parser('get', help='Get service resource limits')
    get_parser.add_argument('service_id', help='Service ID')
    
    # Set service limits
    set_parser = subparsers.add_parser('set', help='Set service resource limits')
    set_parser.add_argument('service_id', help='Service ID')
    set_parser.add_argument('--profile', choices=['tiny', 'small', 'medium', 'large', 'unlimited'])
    set_parser.add_argument('--cpu', type=float, help='CPU cores')
    set_parser.add_argument('--memory', type=int, help='Memory in MB')
    set_parser.add_argument('--disk', type=int, help='Disk quota in MB')
    set_parser.add_argument('--restart', choices=['no', 'on-failure', 'always', 'unless-stopped'])
    
    # Apply limits
    apply_parser = subparsers.add_parser('apply', help='Apply limits to running container')
    apply_parser.add_argument('service_id', help='Service ID')
    apply_parser.add_argument('container', help='Container name')
    
    # Get stats
    stats_parser = subparsers.add_parser('stats', help='Get container resource usage')
    stats_parser.add_argument('container', help='Container name')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    rm = ResourceManager()
    
    if args.command == 'profiles':
        profiles = rm.list_profiles()
        print("\nAvailable Resource Profiles:")
        print("=" * 80)
        for name, prof in profiles.items():
            print(f"\n{name.upper()}")
            print(f"  CPU:    {prof['cpu_cores']} cores")
            print(f"  Memory: {prof['memory_mb']} MB")
            print(f"  Disk:   {prof['disk_mb']} MB")
            print(f"  Info:   {prof['description']}")
    
    elif args.command == 'get':
        limits = rm.get_service_limits(args.service_id)
        print(f"\nResource Limits for {args.service_id}:")
        print("=" * 60)
        print(f"Profile:        {limits['profile']}")
        print(f"CPU Cores:      {limits['cpu_cores']}")
        print(f"Memory:         {limits['memory_mb']} MB")
        print(f"Disk Quota:     {limits['disk_mb']} MB")
        print(f"Restart Policy: {limits['restart_policy']}")
        print(f"Custom:         {'Yes' if limits['custom'] else 'No'}")
    
    elif args.command == 'set':
        rm.set_service_limits(
            args.service_id,
            profile=args.profile,
            cpu_cores=args.cpu,
            memory_mb=args.memory,
            disk_mb=args.disk,
            restart_policy=args.restart
        )
        print(f"✓ Updated resource limits for {args.service_id}")
    
    elif args.command == 'apply':
        rm.apply_limits_to_container(args.service_id, args.container)
        print(f"✓ Applied resource limits to {args.container}")
    
    elif args.command == 'stats':
        stats = rm.get_container_stats(args.container)
        print(f"\nResource Usage for {args.container}:")
        print("=" * 60)
        print(f"CPU:    {stats['cpu_percent']}%")
        print(f"Memory: {stats['memory_mb']} MB")
        print(f"Disk:   {stats['disk_mb']} MB")