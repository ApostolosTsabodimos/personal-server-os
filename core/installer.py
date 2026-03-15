#!/usr/bin/env python3
"""
PSO Service Installer
Installs services based on manifest definitions
"""

import os
import sys
import time
import socket
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import docker
from docker.errors import DockerException, APIError, ImageNotFound
import requests

from core.manifest import Manifest, ManifestLoader
from core.database import Database, DatabaseError
from core.config_manager import ConfigManager
from core.dependency_resolver import DependencyResolver, DependencyError


class InstallerError(Exception):
    """Base exception for installer errors"""
    pass


class PrerequisiteError(InstallerError):
    """Raised when prerequisites are not met"""
    pass


class InstallationError(InstallerError):
    """Raised when installation fails"""
    pass


class ServiceInstaller:
    """
    Installs services based on manifest definitions
    
    Current support:
    - Docker containers (method: "docker")
    
    Future support:
    - Docker Compose (method: "docker-compose")
    - Systemd services (method: "systemd")
    - Binary installation (method: "binary")
    """
    
    def __init__(self, manifest: Manifest, data_dir: Optional[Path] = None, 
             db: Optional[Database] = None, user_config: Optional[Dict] = None):
        """
        Initialize installer
        
        Args:
            manifest: Service manifest to install
            data_dir: Base directory for service data (default: /var/pso)
            db: Database instance (creates one if not provided)
        """
        self.manifest = manifest
        self.data_dir = data_dir or Path.home() / '.pso_dev' / 'services'
        self.service_dir = self.data_dir / manifest.id
        
        # Database connection
        self.db = db or Database()
        
        # Configuration manager
        self.config_manager = ConfigManager()
        
        # Dependency resolver
        self.resolver = DependencyResolver()
        self.user_config = user_config or {}  # Pre-provided configuration
        self.progress_callback = None  # set by api.py before calling install()
        
        # Track what we've created for rollback
        self.created_dirs = []
        self.created_container = None
        
        try:
            self.docker_client = docker.from_env()
        except DockerException as e:
            raise PrerequisiteError(f"Docker is not available: {e}")
    
    def install(self, dry_run: bool = False) -> bool:
        """
        Install the service
        
        Args:
            dry_run: If True, only validate without making changes
            
        Returns:
            True if installation successful
            
        Raises:
            InstallerError: If installation fails
        """
        print(f"\n{'[DRY RUN] ' if dry_run else ''}Installing {self.manifest.name}...")
        print("─" * 60)
        
        try:
            # Step 0: Check if already installed
            if self.db.is_installed(self.manifest.id):
                raise InstallationError(
                    f"{self.manifest.name} is already installed. "
                    f"Uninstall it first or use update command."
                )
            
            # Step 0.5: Resolve dependencies
            print("\n🔍 Checking dependencies...")
            try:
                to_install, already_installed = self.resolver.get_installation_plan(self.manifest.id)
                
                # Check for conflicts
                conflicts = self.resolver.check_conflicts(self.manifest.id)
                if conflicts:
                    raise InstallationError(
                        f"Conflicts detected: {', '.join(conflicts)} must be uninstalled first"
                    )
                
                # Show what will be installed
                if len(to_install) > 1:
                    print(f"  ✓ Found {len(to_install)} services to install (including dependencies)")
                    for i, svc in enumerate(to_install[:-1], 1):  # Exclude the main service
                        print(f"    {i}. {svc} (dependency)")
                    print(f"    {len(to_install)}. {self.manifest.id} (requested)")
                else:
                    print(f"  ✓ No dependencies required")
                
                if already_installed:
                    print(f"  ✓ {len(already_installed)} dependencies already installed")
                
            except DependencyError as e:
                raise InstallationError(f"Dependency resolution failed: {e}")
            
            # Step 1: Validate prerequisites
            self._validate_prerequisites()
            print("✓ Prerequisites validated")
            if self.progress_callback: self.progress_callback(10, "Prerequisites validated")
            
            # Step 2: Check port availability (including database conflicts)
            self._check_ports()
            print("✓ Ports available")
            if self.progress_callback: self.progress_callback(15, "Ports available")
            
            if dry_run:
                print("\n[DRY RUN] Would perform:")
                print(f"  - Create directories under {self.service_dir}")
                print(f"  - Pull image: {self.manifest.data['installation'].get('image')}")
                print(f"  - Start container with ports: {self.manifest.ports}")
                print(f"  - Run health check on: {self.manifest.health_check}")
                print(f"  - Record installation in database")
                
                # Note if config would be collected
                if self.manifest.get_user_inputs():
                    print(f"  - Collect user configuration (interactive)")
                
                return True
            
            # Step 3: Collect user inputs if needed (only for actual installation)
            user_inputs = {}
            if self.manifest.get_user_inputs():
                # Use pre-provided config if available, otherwise collect interactively
                if self.user_config:
                    print("\n📝 Using provided configuration")
                    user_inputs = self.user_config
                    print("✓ Configuration loaded")
                else:
                    print("\n📝 Configuration required for this service")
                    try:
                        user_inputs = self.config_manager.collect_user_inputs(
                            self.manifest.get_user_inputs(),
                            interactive=True
                        )
                        print("✓ Configuration collected")
                    except Exception as e:
                        raise InstallationError(f"Configuration collection failed: {e}") 
            
            # Log installation attempt
            self.db.log_action(
                self.manifest.id,
                'install',
                'in_progress',
                f'Starting installation of {self.manifest.name}'
            )
            
            # Step 4: Create directory structure
            self._create_directories()
            print(f"✓ Created directories in {self.service_dir}")
            if self.progress_callback: self.progress_callback(18, "Directories created")
            
            # Step 5: Install based on method
            method = self.manifest.installation_method
            if method == 'docker':
                self._install_docker()
            elif method == 'docker-compose':
                self._install_docker_compose()
            elif method == 'systemd':
                raise InstallerError("Systemd support not yet implemented")
            elif method == 'binary':
                raise InstallerError("Binary installation not yet implemented")
            else:
                raise InstallerError(f"Unknown installation method: {method}")
            
            print("✓ Service started")
            
            # Step 6: Wait for startup
            if self.manifest.health_check:
                start_period = self.manifest.health_check.get('start_period', 10)
                print(f"  Waiting {start_period}s for service to start...")
                for i in range(start_period):
                    time.sleep(1)
                    if self.progress_callback:
                        pct = 75 + int((i / max(start_period, 1)) * 15)
                        self.progress_callback(pct, f"Waiting for service to start... ({i+1}/{start_period}s)")
            
            # Step 7: Verify health
            self._verify_health()
            print("✓ Health check passed")
            if self.progress_callback: self.progress_callback(92, "Health check passed")
            
            # Step 8: Record in database
            self._record_installation()
            print("✓ Installation recorded in database")
            if self.progress_callback: self.progress_callback(98, "Recording installation")
            
            print("\n" + "─" * 60)
            print(f"✓ {self.manifest.name} installed successfully!")
            self._print_access_info()
            
            return True
            
        except Exception as e:
            print(f"\n✗ Installation failed: {e}")
            
            # Log failure
            try:
                self.db.log_action(
                    self.manifest.id,
                    'install',
                    'failed',
                    error_message=str(e)
                )
            except:
                pass  # Don't fail on logging failure
            
            print("\nRolling back changes...")
            self.rollback()
            raise InstallationError(f"Installation failed: {e}")
    
    def install_with_dependencies(self, dry_run: bool = False, 
                                   skip_dependencies: bool = False) -> bool:
        """
        Install service along with all dependencies
        
        Args:
            dry_run: If True, only show what would be done
            skip_dependencies: If True, skip dependency installation (not recommended)
        
        Returns:
            True if successful
        """
        # If skipping dependencies, just install this service
        if skip_dependencies:
            print(f"\n⚠️  WARNING: Installing without dependencies (--skip-dependencies)")
            print(f"   This service may not work correctly without its dependencies!")
            return self.install(dry_run=dry_run)
        
        # Get installation plan
        try:
            to_install, already_installed = self.resolver.get_installation_plan(self.manifest.id)
        except DependencyError as e:
            raise InstallationError(f"Dependency resolution failed: {e}")
        
        # Show plan
        dependencies_count = len(to_install) - 1  # Exclude the main service
        
        if not dry_run and dependencies_count > 0:
            print(f"\n{'=' * 70}")
            print(f"INSTALLATION PLAN")
            print('=' * 70)
            print(f"\nWill install {len(to_install)} services:")
            for i, service_id in enumerate(to_install, 1):
                loader = ManifestLoader()
                manifest = loader.load(service_id)
                is_main = (service_id == self.manifest.id)
                marker = "→" if is_main else " "
                dep_type = "(main service)" if is_main else "(required dependency)"
                print(f"  {marker} {i}. {manifest.name} {dep_type}")
            
            if already_installed:
                print(f"\nAlready installed (will skip): {', '.join(already_installed)}")
            
            # Show optional dependencies
            optional_deps = self.resolver.get_optional_dependencies(self.manifest.id)
            if optional_deps:
                print(f"\n💡 Optional (recommended but not required):")
                for opt in optional_deps:
                    try:
                        opt_manifest = loader.load(opt)
                        installed = "✓ installed" if self.resolver.is_installed(opt) else "not installed"
                        print(f"  • {opt_manifest.name} ({installed})")
                    except:
                        print(f"  • {opt}")
            
            print('=' * 70)
            
            # Ask for confirmation with options
            print("\nOptions:")
            print("  1. Install all (recommended)")
            print(f"  2. Install only {self.manifest.name} (skip dependencies - may not work correctly)")
            print("  3. Cancel")
            
            # When called non-interactively (e.g. from API), install all without prompting
            if self.progress_callback:
                pass  # non-interactive: install all
            else:
                while True:
                    response = input("\nYour choice [1/2/3]: ").strip()
                    if response == '1':
                        break  # Install all
                    elif response == '2':
                        print(f"\n⚠️  WARNING: Installing without dependencies")
                        print(f"   {self.manifest.name} may not work correctly without its dependencies!")
                        return self.install(dry_run=dry_run)
                    elif response == '3':
                        print("Installation cancelled.")
                        return False
                    else:
                        print("Invalid choice. Please enter 1, 2, or 3.")
        
        # Install each service in order
        loader = ManifestLoader()
        for service_id in to_install:
            manifest = loader.load(service_id)
            installer = ServiceInstaller(manifest, self.data_dir, self.db)
            
            print(f"\n{'=' * 70}")
            if not installer.install(dry_run=dry_run):
                raise InstallationError(f"Failed to install dependency: {service_id}")
        
        return True
    
    def _validate_prerequisites(self):
        """Validate system prerequisites"""
        # Check Docker is running
        try:
            self.docker_client.ping()
        except Exception as e:
            raise PrerequisiteError(f"Docker daemon is not running: {e}")
        
        # Check Docker Compose is available when needed
        if self.manifest.installation_method == 'docker-compose':
            self._get_compose_cmd()  # raises PrerequisiteError if not found
        
        # Check for system dependencies
        system_deps = self.manifest.dependencies.get('system', [])
        for dep in system_deps:
            if dep == 'docker':
                continue  # Already checked
            # Could add checks for other system dependencies
        
        # Check for conflicting services (would need database to track installed)
        # TODO: Implement when database is ready
        conflicts = self.manifest.dependencies.get('conflicts', [])
        if conflicts:
            print(f"  Note: This service conflicts with: {', '.join(conflicts)}")
    
    def _check_ports(self):
        """Check if required ports are available"""
        # First check if ports are available on the system
        for port_name, port_num in self.manifest.ports.items():
            if not self._is_port_available(port_num):
                raise PrerequisiteError(
                    f"Port {port_num} ({port_name}) is already in use"
                )
        
        # Then check database for conflicts with other installed services
        conflicts = self.db.get_port_conflicts(self.manifest.ports)
        if conflicts:
            conflict_msgs = [
                f"Port {port_num} ({port_name}) is used by {service_id}"
                for port_name, port_num, service_id in conflicts
            ]
            raise PrerequisiteError(
                f"Port conflicts detected:\n  " + "\n  ".join(conflict_msgs)
            )
    
    def _is_port_available(self, port: int) -> bool:
        """Check if a port is available"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', port))
            sock.close()
            return True
        except OSError:
            return False
    
    def _create_directories(self):
        """Create required directory structure"""
        # Create main service directory
        self.service_dir.mkdir(parents=True, exist_ok=True)
        self.created_dirs.append(self.service_dir)
        
        # Create volume directories
        for volume in self.manifest.volumes:
            host_path = Path(os.path.expanduser(volume['host']))  # Expand ~ to home directory

            # Only create if it's under our data_dir
            if str(host_path).startswith(str(self.data_dir)):
                host_path.mkdir(parents=True, exist_ok=True)
                self.created_dirs.append(host_path)
    
    def _install_docker(self):
        """Install as Docker container"""
        installation = self.manifest.data['installation']
        image = installation.get('image')
        
        if not image:
            raise InstallationError("No Docker image specified in manifest")
        
        # Pull image with streaming progress
        print(f"  Pulling image: {image}")
        try:
            layers_total = {}
            layers_done = {}
            for event in self.docker_client.api.pull(image, stream=True, decode=True):
                status = event.get('status', '')
                layer_id = event.get('id', '')
                progress_detail = event.get('progressDetail', {})

                if layer_id and status in ('Downloading', 'Pull complete', 'Already exists'):
                    if status == 'Downloading' and progress_detail.get('total'):
                        layers_total[layer_id] = progress_detail['total']
                        layers_done[layer_id] = progress_detail.get('current', 0)
                    elif status in ('Pull complete', 'Already exists'):
                        if layer_id in layers_total:
                            layers_done[layer_id] = layers_total[layer_id]
                        else:
                            layers_total[layer_id] = 1
                            layers_done[layer_id] = 1

                    if self.progress_callback and layers_total:
                        total = sum(layers_total.values())
                        done = sum(layers_done.get(k, 0) for k in layers_total)
                        pct = int((done / total) * 50) if total > 0 else 0
                        n_done = sum(1 for k in layers_total if layers_done.get(k) == layers_total.get(k))
                        self.progress_callback(20 + pct, f"Pulling image: {n_done}/{len(layers_total)} layers")

        except ImageNotFound:
            raise InstallationError(f"Image not found: {image}")
        except APIError as e:
            raise InstallationError(f"Failed to pull image: {e}")
        
        # Prepare container configuration
        container_name = f"pso-{self.manifest.id}"
        
        # Port mappings: Docker expects {container_port/tcp: host_port}
        #
        # Resolution order per named port:
        #  1. installation.port_mappings[port_name] — explicit per-port override
        #  2. manifest.container_port               — single container port for all
        #  3. host_port                             — assume same on both sides
        ports = {}
        installation_data  = self.manifest.data.get('installation', {})
        port_mappings      = installation_data.get('port_mappings', {})
        single_cport       = self.manifest.container_port

        for port_name, host_port in self.manifest.ports.items():
            if port_name in port_mappings:
                container_port = port_mappings[port_name]
            elif single_cport is not None:
                container_port = single_cport
            else:
                container_port = host_port
            ports[f"{container_port}/tcp"] = host_port
        
        # Volume mappings
        volumes = {}
        for volume in self.manifest.volumes:
            host_path = os.path.expanduser(volume['host'])  # Expand ~ to home directory
            container_path = volume['container']
            mode = 'ro' if volume.get('readonly', False) else 'rw'
            volumes[host_path] = {'bind': container_path, 'mode': mode}
        
        # Environment variables
        environment = self.manifest.environment
        
        # Start container
        print(f"  Starting container: {container_name}")
        try:
            container = self.docker_client.containers.run(
                image=image,
                name=container_name,
                ports=ports,
                volumes=volumes,
                environment=environment,
                detach=True,
                restart_policy={"Name": "unless-stopped"}
            )
            self.created_container = container
            if self.progress_callback: self.progress_callback(72, "Container started")
        except APIError as e:
            raise InstallationError(f"Failed to start container: {e}")
    
    def _verify_health(self):
        """Verify service health after install"""
        health_check = self.manifest.health_check

        if not health_check:
            print("  No health check defined, skipping verification")
            return

        check_type = health_check.get('type')
        retries    = health_check.get('retries', 5)
        timeout    = health_check.get('timeout', 10)
        start_period = health_check.get('start_period', 15)

        # Wait for start_period first — many services need time to initialize
        if start_period > 0:
            print(f"  Waiting {start_period}s for service to initialize...")
            time.sleep(start_period)

        for attempt in range(retries):
            try:
                # Before running the health check, ensure the container is
                # in a stable running state. If it's restarting, wait it out.
                if self.created_container:
                    for _ in range(10):
                        self.created_container.reload()
                        state = self.created_container.attrs['State']['Status']
                        if state == 'running':
                            break
                        if state in ('exited', 'dead'):
                            logs = self.created_container.logs(tail=20).decode('utf-8', errors='replace')
                            raise InstallationError(
                                f"Container stopped unexpectedly (status: {state}).\n"
                                f"Last logs:\n{logs}"
                            )
                        # restarting or created — wait
                        time.sleep(3)
                    else:
                        raise InstallationError(
                            f"Container did not reach running state after 30s "
                            f"(current: {state})"
                        )

                if check_type == 'http':
                    self._health_check_http(health_check, timeout)
                    return
                elif check_type == 'tcp':
                    self._health_check_tcp(health_check, timeout)
                    return
                elif check_type == 'command':
                    self._health_check_command(health_check, timeout)
                    return
                elif check_type == 'none':
                    return
                else:
                    print(f"  Unknown health check type '{check_type}', skipping")
                    return

            except InstallationError:
                raise  # container exited — no point retrying
            except Exception as e:
                if attempt < retries - 1:
                    wait = min(5 * (attempt + 1), 30)  # back-off: 5s, 10s, 15s…
                    print(f"  Health check {attempt + 1}/{retries} failed ({e}), retrying in {wait}s...")
                    time.sleep(wait)
                else:
                    raise InstallationError(
                        f"Health check failed after {retries} attempts: {e}"
                    )
    
    def _health_check_http(self, health_check: Dict, timeout: int):
        """Perform HTTP health check"""
        endpoint = health_check.get('endpoint')
        if not endpoint:
            raise InstallationError("HTTP health check requires 'endpoint'")
        
        response = requests.get(endpoint, timeout=timeout)
        if response.status_code >= 400:
            raise InstallationError(f"HTTP health check failed: {response.status_code}")
    
    def _health_check_tcp(self, health_check: Dict, timeout: int):
        """Perform TCP health check"""
        endpoint = health_check.get('endpoint', 'localhost')
        # Parse endpoint (format: host:port)
        if ':' in endpoint:
            host, port = endpoint.rsplit(':', 1)
            port = int(port)
        else:
            raise InstallationError("TCP health check requires 'host:port' format")
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
            sock.close()
        except Exception as e:
            raise InstallationError(f"TCP connection failed: {e}")
    
    def _health_check_command(self, health_check: Dict, timeout: int):
        """Perform command-based health check"""
        command = health_check.get('command')
        if not command:
            raise InstallationError("Command health check requires 'command'")
        
        if not self.created_container:
            raise InstallationError("No container available for command execution")
        
        # Run via shell so operators like ||, &&, ; work correctly.
        # Passing a plain string to exec_run splits on spaces — shell syntax breaks.
        result = self.created_container.exec_run(
            ['/bin/sh', '-c', command], demux=True
        )
        if result.exit_code != 0:
            raise InstallationError(f"Health check command failed: {result.output}")
    
    def _record_installation(self):
        """Record the installation in the database"""
        service_data = {
            'service_id': self.manifest.id,
            'service_name': self.manifest.name,
            'version': self.manifest.version,
            'category': self.manifest.category,
            'status': 'running',
            'installation_method': self.manifest.installation_method,
            'config': self.manifest.data.get('configuration', {}),
            'ports': self.manifest.ports,
            'volumes': self.manifest.volumes,
            'dependencies': self.manifest.dependencies.get('services', [])
        }
        
        try:
            self.db.add_service(service_data)
        except DatabaseError as e:
            raise InstallationError(f"Failed to record installation in database: {e}")
    
    def _print_access_info(self):
        """Print information about how to access the service"""
        print("\nAccess Information:")
        
        # Ports
        if self.manifest.ports:
            print("  Ports:")
            for port_name, port_num in self.manifest.ports.items():
                print(f"    {port_name}: http://localhost:{port_num}")
        
        # Data directory
        print(f"  Data directory: {self.service_dir}")
        
        # Reverse proxy info
        if self.manifest.reverse_proxy and self.manifest.reverse_proxy.get('enabled'):
            subdomain = self.manifest.reverse_proxy.get('subdomain')
            print(f"  Reverse proxy: {subdomain}.yourdomain.com (not yet configured)")
    
    def _get_compose_cmd(self) -> list:
        """
        Return the docker compose command as a list.
        Tries Docker Compose v2 plugin first (docker compose),
        then falls back to standalone v1 (docker-compose).
        Raises PrerequisiteError if neither is available.
        """
        # Try v2 plugin: docker compose version
        result = subprocess.run(
            ['docker', 'compose', 'version'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return ['docker', 'compose']

        # Try v1 standalone: docker-compose --version
        result = subprocess.run(
            ['docker-compose', '--version'],
            capture_output=True, text=True
        )
        if result.returncode == 0:
            return ['docker-compose']

        raise PrerequisiteError(
            "Docker Compose is not available. "
            "Install it with: sudo apt install docker-compose-plugin  "
            "(or: pip install docker-compose)"
        )

    def _install_docker_compose(self):
        """
        Install a service as a Docker Compose stack.

        The compose file must exist at:
            services/<service-id>/<compose_file>
        where <compose_file> is specified in the manifest under
        installation.compose_file (defaults to 'docker-compose.yml').

        The file is copied to self.service_dir so runtime state
        (volumes, overrides) stays separate from the manifest source.
        Environment variables defined in manifest.environment are
        injected into the process environment before running compose,
        so ${VARIABLE} references in the compose file are expanded.
        """
        import shutil

        installation = self.manifest.data.get('installation', {})
        compose_filename = installation.get('compose_file', 'docker-compose.yml')

        # Locate the source compose file next to the manifest
        services_dir = Path(__file__).parent.parent / 'services' / self.manifest.id
        src_compose = services_dir / compose_filename
        if not src_compose.exists():
            raise InstallationError(
                f"Compose file not found: {src_compose}\n"
                f"Expected at services/{self.manifest.id}/{compose_filename}"
            )

        # Copy compose file into the runtime service directory
        dest_compose = self.service_dir / 'docker-compose.yml'
        shutil.copy(src_compose, dest_compose)
        self._compose_path = dest_compose

        compose_cmd = self._get_compose_cmd()

        # Build environment: system env + manifest environment overrides
        compose_env = {**os.environ, **{k: str(v) for k, v in self.manifest.environment.items()}}

        # Pull all images defined in the compose file
        print(f"  Pulling images (this may take a while)...")
        if self.progress_callback:
            self.progress_callback(25, "Pulling compose images")

        pull_result = subprocess.run(
            compose_cmd + ['-f', str(dest_compose), 'pull'],
            capture_output=True, text=True,
            cwd=str(self.service_dir), env=compose_env
        )
        if pull_result.returncode != 0:
            raise InstallationError(
                f"Failed to pull images:\n{pull_result.stderr or pull_result.stdout}"
            )
        if self.progress_callback:
            self.progress_callback(60, "Images pulled")

        # Start the stack
        print(f"  Starting compose stack...")
        up_result = subprocess.run(
            compose_cmd + ['-f', str(dest_compose), 'up', '-d', '--remove-orphans'],
            capture_output=True, text=True,
            cwd=str(self.service_dir), env=compose_env
        )
        if up_result.returncode != 0:
            raise InstallationError(
                f"Failed to start compose stack:\n{up_result.stderr or up_result.stdout}"
            )

        self._compose_started = True
        if self.progress_callback:
            self.progress_callback(72, "Compose stack started")

        # Report which containers are now running
        ps_result = subprocess.run(
            compose_cmd + ['-f', str(dest_compose), 'ps', '--format', 'json'],
            capture_output=True, text=True,
            cwd=str(self.service_dir), env=compose_env
        )
        if ps_result.returncode == 0 and ps_result.stdout.strip():
            try:
                import json as _json
                containers = _json.loads(ps_result.stdout)
                if isinstance(containers, list):
                    for c in containers:
                        name = c.get('Name') or c.get('Service', '')
                        state = c.get('State') or c.get('Status', '')
                        print(f"    ✓ {name}: {state}")
            except Exception:
                pass  # ps output format varies between compose versions

    def rollback(self):
        """Rollback installation on failure"""
        try:
            # Stop and remove Docker Compose stack
            if getattr(self, '_compose_started', False) and getattr(self, '_compose_path', None):
                print(f"  Stopping compose stack...")
                try:
                    compose_cmd = self._get_compose_cmd()
                    subprocess.run(
                        compose_cmd + ['-f', str(self._compose_path), 'down', '--volumes', '--remove-orphans'],
                        capture_output=True, text=True, cwd=str(self.service_dir)
                    )
                except Exception as e:
                    print(f"  Warning: Failed to stop compose stack: {e}")

            # Stop and remove single Docker container
            if self.created_container:
                print(f"  Stopping container...")
                try:
                    self.created_container.stop(timeout=10)
                    self.created_container.remove()
                except Exception as e:
                    print(f"  Warning: Failed to remove container: {e}")
            
            # Remove created directories (in reverse order)
            for directory in reversed(self.created_dirs):
                try:
                    if directory.exists() and not any(directory.iterdir()):
                        directory.rmdir()
                        print(f"  Removed directory: {directory}")
                except Exception as e:
                    print(f"  Warning: Could not remove {directory}: {e}")
            
            # Remove from database if it was added
            try:
                if self.db.is_installed(self.manifest.id):
                    self.db.remove_service(self.manifest.id)
                    print(f"  Removed from database")
            except Exception as e:
                print(f"  Warning: Could not remove from database: {e}")
            
            print("✓ Rollback complete")
            
        except Exception as e:
            print(f"✗ Rollback failed: {e}")


def install_service(service_id: str, dry_run: bool = False, 
                   skip_dependencies: bool = False) -> bool:
    """
    Convenience function to install a service by ID
    
    Args:
        service_id: Service identifier from catalog
        dry_run: If True, only validate without installing
        skip_dependencies: If True, skip dependency installation
        
    Returns:
        True if installation successful
    """
    loader = ManifestLoader()
    manifest = loader.load(service_id)
    
    installer = ServiceInstaller(manifest)
    return installer.install_with_dependencies(dry_run=dry_run, 
                                              skip_dependencies=skip_dependencies)


if __name__ == '__main__':
    # Simple CLI for testing
    if len(sys.argv) < 2:
        print("Usage: python -m core.installer <service-id> [--dry-run] [--skip-dependencies]")
        sys.exit(1)
    
    service_id = sys.argv[1]
    dry_run = '--dry-run' in sys.argv
    skip_dependencies = '--skip-dependencies' in sys.argv
    
    try:
        install_service(service_id, dry_run=dry_run, skip_dependencies=skip_dependencies)
    except InstallerError as e:
        print(f"\n✗ Error: {e}")
        sys.exit(1)