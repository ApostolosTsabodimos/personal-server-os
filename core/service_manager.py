#!/usr/bin/env python3
"""
PSO Service Manager
Manages the lifecycle of installed services (start, stop, restart, status, logs)
"""

import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import docker
from docker.errors import DockerException, APIError, NotFound

from core.database import Database, DatabaseError


class ServiceManagerError(Exception):
    """Base exception for service manager errors"""
    pass


class ServiceNotFoundError(ServiceManagerError):
    """Raised when service is not found"""
    pass


class ServiceNotRunningError(ServiceManagerError):
    """Raised when trying to operate on a stopped service"""
    pass


class ServiceManager:
    """
    Manages installed services
    
    Handles:
    - Starting/stopping/restarting services
    - Checking service status
    - Viewing service logs
    - Listing installed services
    """
    
    def __init__(self, db: Optional[Database] = None):
        """
        Initialize service manager
        
        Args:
            db: Database instance (creates one if not provided)
        """
        self.db = db or Database()
        
        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            raise ServiceManagerError(f"Docker is not available: {e}")
    
    def _get_container_name(self, service_id: str) -> str:
        """Get Docker container name for a service"""
        return f"pso-{service_id}"
    
    def _get_container(self, service_id: str):
        """Get Docker container for a service"""
        container_name = self._get_container_name(service_id)
        try:
            return self.docker_client.containers.get(container_name)
        except NotFound:
            return None
        except APIError as e:
            raise ServiceManagerError(f"Error accessing container: {e}")

    def _normalize_status(self, raw: str) -> str:
        """
        Map Docker container statuses to PSO canonical statuses.
        PSO only uses: running | stopped | error | orphaned
        """
        return {
            'running':   'running',
            'exited':    'stopped',
            'created':   'stopped',
            'paused':    'stopped',
            'restarting':'running',
            'removing':  'stopped',
            'dead':      'error',
            'not_found': 'orphaned',  # in DB but container deleted outside PSO
        }.get(raw, 'stopped')

    def _sync_status(self, service_id: str, status: str):
        """Write normalized status back to the database. Never raises."""
        try:
            self.db.update_service_status(service_id, status)
        except Exception:
            pass  # Best-effort — never crash a status read due to a DB write

    def start(self, service_id: str) -> bool:
        """
        Start a service

        Args:
            service_id: Service identifier

        Returns:
            True if started successfully

        Raises:
            ServiceNotFoundError: If service not installed
            ServiceManagerError: If start fails
        """
        # Check if service is installed
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")
        
        # Get service info
        service = self.db.get_service(service_id)
        
        # Get container
        container = self._get_container(service_id)
        if not container:
            raise ServiceManagerError(
                f"Container not found for {service_id}. "
                f"Service may need to be reinstalled."
            )
        
        # Check if already running
        if container.status == 'running':
            print(f"Service {service_id} is already running")
            return True
        
        # Start the container
        try:
            container.start()
            
            # Update status in database
            self.db.update_service_status(service_id, 'running')
            self.db.log_action(service_id, 'start', 'success', 
                             f'Service started')
            
            print(f"✓ Started {service['service_name']}")
            return True
            
        except APIError as e:
            self.db.log_action(service_id, 'start', 'failed', 
                             error_message=str(e))
            raise ServiceManagerError(f"Failed to start service: {e}")
    
    def stop(self, service_id: str, timeout: int = 10) -> bool:
        """
        Stop a service
        
        Args:
            service_id: Service identifier
            timeout: Seconds to wait before force-stopping
            
        Returns:
            True if stopped successfully
            
        Raises:
            ServiceNotFoundError: If service not installed
            ServiceManagerError: If stop fails
        """
        # Check if service is installed
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")
        
        service = self.db.get_service(service_id)
        
        # Get container
        container = self._get_container(service_id)
        if not container:
            raise ServiceManagerError(
                f"Container not found for {service_id}"
            )
        
        # Check if already stopped
        if container.status != 'running':
            print(f"Service {service_id} is already stopped")
            return True
        
        # Stop the container
        try:
            container.stop(timeout=timeout)
            
            # Update status in database
            self.db.update_service_status(service_id, 'stopped')
            self.db.log_action(service_id, 'stop', 'success', 
                             f'Service stopped')
            
            print(f"✓ Stopped {service['service_name']}")
            return True
            
        except APIError as e:
            self.db.log_action(service_id, 'stop', 'failed', 
                             error_message=str(e))
            raise ServiceManagerError(f"Failed to stop service: {e}")
    
    def restart(self, service_id: str, timeout: int = 10) -> bool:
        """
        Restart a service
        
        Args:
            service_id: Service identifier
            timeout: Seconds to wait before force-stopping
            
        Returns:
            True if restarted successfully
            
        Raises:
            ServiceNotFoundError: If service not installed
            ServiceManagerError: If restart fails
        """
        # Check if service is installed
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")
        
        service = self.db.get_service(service_id)
        
        # Get container
        container = self._get_container(service_id)
        if not container:
            raise ServiceManagerError(
                f"Container not found for {service_id}"
            )
        
        # Restart the container
        try:
            container.restart(timeout=timeout)
            
            # Update status in database
            self.db.update_service_status(service_id, 'running')
            self.db.log_action(service_id, 'restart', 'success', 
                             f'Service restarted')
            
            print(f"✓ Restarted {service['service_name']}")
            return True
            
        except APIError as e:
            self.db.log_action(service_id, 'restart', 'failed', 
                             error_message=str(e))
            raise ServiceManagerError(f"Failed to restart service: {e}")
    
    def get_status(self, service_id: str) -> Dict[str, any]:
        """
        Get service status.
        Always reads live from Docker, normalizes, and syncs to DB.
        Returns 'orphaned' when service is in DB but container no longer exists.
        """
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")

        service = self.db.get_service(service_id)
        container = self._get_container(service_id)

        if not container:
            # Container is gone but DB still has the service — it's an orphan.
            self._sync_status(service_id, 'orphaned')
            return {
                'service_id':      service_id,
                'service_name':    service['service_name'],
                'status':          'orphaned',
                'container_exists': False,
                'installed':       True,
            }

        container.reload()
        raw    = container.attrs['State']['Status']
        status = self._normalize_status(raw)
        self._sync_status(service_id, status)

        return {
            'service_id':       service_id,
            'service_name':     service['service_name'],
            'version':          service.get('version'),
            'status':           status,
            'container_status': raw,
            'running':          status == 'running',
            'ports':            service.get('ports', {}),
            'installed':        True,
            'container_exists': True,
            'container_id':     container.id[:12],
        }


    def get_logs(self, service_id: str, lines: int = 100, 
                 follow: bool = False) -> str:
        """
        Get service logs
        
        Args:
            service_id: Service identifier
            lines: Number of lines to retrieve
            follow: If True, stream logs (blocking)
            
        Returns:
            Log output as string
            
        Raises:
            ServiceNotFoundError: If service not installed
            ServiceManagerError: If logs cannot be retrieved
        """
        # Check if service is installed
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")
        
        # Get container
        container = self._get_container(service_id)
        if not container:
            raise ServiceManagerError(
                f"Container not found for {service_id}"
            )
        
        try:
            if follow:
                # Stream logs (blocking)
                for line in container.logs(stream=True, follow=True, tail=lines):
                    print(line.decode('utf-8'), end='')
            else:
                # Get logs as string
                logs = container.logs(tail=lines).decode('utf-8')
                return logs
                
        except APIError as e:
            raise ServiceManagerError(f"Failed to get logs: {e}")
    
    def list_services(self, status_filter: Optional[str] = None) -> List[Dict]:
        """
        List installed services with their live status.
        Normalizes all Docker statuses. Marks orphans where container is gone.
        """
        services = self.db.list_services()
        result   = []

        for service in services:
            service_id = service['service_id']
            container  = self._get_container(service_id)

            if container:
                container.reload()
                raw    = container.attrs['State']['Status']
                status = self._normalize_status(raw)
            else:
                raw    = 'not_found'
                status = 'orphaned'

            self._sync_status(service_id, status)

            full = self.db.get_service(service_id) or {}
            service_info = {
                'service_id':   service_id,
                'service_name': service['service_name'],
                'version':      service.get('version'),
                'category':     service.get('category'),
                'status':       status,
                'running':      status == 'running',
                'orphaned':     status == 'orphaned',
                'ports':        full.get('ports', {}),
                'installed_at': service.get('installed_at'),
            }

            if status_filter is None or status == status_filter:
                result.append(service_info)

        return result


    def remove(self, service_id: str, remove_volumes: bool = False) -> bool:
        """
        Remove a service (uninstall)
        
        Args:
            service_id: Service identifier
            remove_volumes: If True, also remove volumes
            
        Returns:
            True if removed successfully
            
        Raises:
            ServiceNotFoundError: If service not installed
            ServiceManagerError: If removal fails
        """
        # Check if service is installed
        if not self.db.is_installed(service_id):
            raise ServiceNotFoundError(f"Service not installed: {service_id}")
        
        service = self.db.get_service(service_id)
        
        # Get container
        container = self._get_container(service_id)
        
        try:
            if container:
                # Stop if running
                if container.status == 'running':
                    print(f"Stopping {service['service_name']}...")
                    container.stop(timeout=10)
                
                # Remove container
                print(f"Removing container...")
                container.remove(v=remove_volumes)

            # Remove from database
            self.db.remove_service(service_id)

            # Clean up service secrets
            try:
                from core.secrets_manager import SecretsManager
                secrets_mgr = SecretsManager()
                deleted = secrets_mgr.delete_service_secrets(service_id)
                if deleted > 0:
                    print(f"✓ Deleted {deleted} secret(s)")
            except Exception:
                pass  # Non-critical

            # Clean up Docker networks
            try:
                network_name = f"pso-{service_id}-net"
                network = self.docker_client.networks.get(network_name)
                network.remove()
                print(f"✓ Removed network {network_name}")
            except Exception:
                pass  # Network may not exist

            print(f"✓ Removed {service['service_name']}")
            return True
            
        except APIError as e:
            self.db.log_action(service_id, 'uninstall', 'failed', 
                             error_message=str(e))
            raise ServiceManagerError(f"Failed to remove service: {e}")


# Convenience functions
def start_service(service_id: str) -> bool:
    """Start a service"""
    manager = ServiceManager()
    return manager.start(service_id)


def stop_service(service_id: str) -> bool:
    """Stop a service"""
    manager = ServiceManager()
    return manager.stop(service_id)


def restart_service(service_id: str) -> bool:
    """Restart a service"""
    manager = ServiceManager()
    return manager.restart(service_id)


def get_service_status(service_id: str) -> Dict:
    """Get service status"""
    manager = ServiceManager()
    return manager.get_status(service_id)


def list_services() -> List[Dict]:
    """List all services"""
    manager = ServiceManager()
    return manager.list_services()


if __name__ == '__main__':
    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python -m core.service_manager <command> [service-id]")
        print("\nCommands:")
        print("  list                    - List all services")
        print("  start <service-id>      - Start a service")
        print("  stop <service-id>       - Stop a service")
        print("  restart <service-id>    - Restart a service")
        print("  status <service-id>     - Show service status")
        print("  logs <service-id>       - Show service logs")
        sys.exit(1)
    
    command = sys.argv[1]
    manager = ServiceManager()
    
    try:
        if command == 'list':
            services = manager.list_services()
            if not services:
                print("No services installed")
            else:
                print(f"\n{'Service':<20} {'Status':<15} {'Version':<10} {'Ports'}")
                print("─" * 70)
                for s in services:
                    status = '🟢 running' if s['running'] else '🔴 stopped'
                    ports_str = ', '.join(f"{k}:{v}" for k, v in s['ports'].items())
                    print(f"{s['service_name']:<20} {status:<15} {s['version']:<10} {ports_str}")
        
        elif command in ['start', 'stop', 'restart', 'status', 'logs']:
            if len(sys.argv) < 3:
                print(f"Error: {command} requires a service-id")
                sys.exit(1)
            
            service_id = sys.argv[2]
            
            if command == 'start':
                manager.start(service_id)
            elif command == 'stop':
                manager.stop(service_id)
            elif command == 'restart':
                manager.restart(service_id)
            elif command == 'status':
                status = manager.get_status(service_id)
                print(f"\n{status['service_name']} (v{status['version']})")
                print("─" * 50)
                print(f"Status: {status['status']}")
                print(f"Running: {'Yes' if status['running'] else 'No'}")
                if status['container_exists']:
                    print(f"Container ID: {status['container_id']}")
                print(f"Ports: {status['ports']}")
            elif command == 'logs':
                print(f"\n=== Logs for {service_id} ===\n")
                logs = manager.get_logs(service_id, lines=50)
                print(logs)
        
        else:
            print(f"Unknown command: {command}")
            sys.exit(1)
            
    except ServiceManagerError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)