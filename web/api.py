#!/usr/bin/env python3
"""
PSO Web Dashboard API - With Authentication

Flask backend providing REST endpoints for the web interface.
"""

from flask import Flask, jsonify, request, send_from_directory, Response
from flask_cors import CORS
from functools import wraps
from pathlib import Path
import sys
import subprocess
import logging
import collections
import json
import time
from datetime import datetime

# ── Structured logging ────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger('pso.api')

# In-memory ring buffer — last 500 entries, streamed to dashboard
_LOG_BUFFER: collections.deque = collections.deque(maxlen=500)

class _BufferHandler(logging.Handler):
    """Tees log records into the ring buffer for live dashboard streaming."""
    def emit(self, record):
        _LOG_BUFFER.append({
            'ts':      datetime.now().strftime('%H:%M:%S'),
            'level':   record.levelname,
            'name':    record.name,
            'message': self.format(record),
        })

_buf_handler = _BufferHandler()
_buf_handler.setFormatter(logging.Formatter('%(name)s: %(message)s'))
logging.getLogger().addHandler(_buf_handler)

# Add parent directory for imports

# Enhanced dashboard imports
try:
    from core.update_manager import ServiceUpdateManager
except ImportError:
    ServiceUpdateManager = None

try:
    from core.service_recommendations import get_recommended_services, CATEGORIES
except ImportError:
    get_recommended_services = None
    CATEGORIES = {}
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.manifest import ManifestLoader
from core.database import Database
from core.service_manager import ServiceManager
from core.backup_manager import BackupManager
from core.dependency_resolver import DependencyResolver
from core.port_manager import PortManager
from core.health_monitor import HealthMonitor
from core.auth import Auth, AuthError
from core.firewall_manager import FirewallManager, FirewallError


app = Flask(__name__, static_folder='static', static_url_path='')
_dashboard_start = __import__('time').time()
CORS(app)  # Enable CORS for development

# Initialize managers
loader = ManifestLoader()
db = Database()
service_mgr = ServiceManager()
backup_mgr = BackupManager()
resolver = DependencyResolver()
port_mgr = PortManager()
health_monitor = HealthMonitor(db, service_mgr)
auth = Auth(db)
firewall_mgr = FirewallManager(db)

# Start health monitor in background
if hasattr(health_monitor, 'start'):
    health_monitor.start()
elif hasattr(health_monitor, 'start_daemon'):
    health_monitor.start_daemon()

# Installation tracking
installation_status = {}


# ============================================================================
# AUTHENTICATION MIDDLEWARE
# ============================================================================

def require_auth(f):
    """Decorator to require authentication for routes"""
    @wraps(f)
    def decorated(*args, **kwargs):
        # Get token from Authorization header
        auth_header = request.headers.get('Authorization')
        
        if not auth_header:
            return jsonify({'error': 'No authorization token provided'}), 401
        
        try:
            # Extract token (format: "Bearer <token>")
            token = auth_header.split(' ')[1] if ' ' in auth_header else auth_header
        except IndexError:
            return jsonify({'error': 'Invalid authorization header'}), 401
        
        # Validate token
        user = auth.validate_token(token)
        
        if not user:
            return jsonify({'error': 'Invalid or expired token'}), 401
        
        # Add user to request context
        request.user = user
        
        return f(*args, **kwargs)
    
    return decorated


def require_admin(f):
    """Decorator to require admin privileges"""
    @wraps(f)
    @require_auth
    def decorated(*args, **kwargs):
        if not request.user.get('is_admin'):
            return jsonify({'error': 'Admin privileges required'}), 403
        return f(*args, **kwargs)
    
    return decorated


# ============================================================================
# AUTHENTICATION ENDPOINTS (Public)
# ============================================================================

@app.route('/api/auth/login', methods=['POST'])
def login():
    """Login endpoint"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        remember_me = data.get('remember_me', False)
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        result = auth.login(username, password, remember_me=remember_me)
        return jsonify(result)
        
    except AuthError as e:
        return jsonify({'error': str(e)}), 401
    except Exception as e:
        return jsonify({'error': 'Login failed'}), 500


@app.route('/api/auth/logout', methods=['POST'])
@require_auth
def logout():
    """Logout endpoint"""
    auth_header = request.headers.get('Authorization')
    token = auth_header.split(' ')[1] if ' ' in auth_header else auth_header
    
    auth.logout(token)
    return jsonify({'success': True, 'message': 'Logged out successfully'})


@app.route('/api/auth/validate', methods=['GET'])
@require_auth
def validate():
    """Validate token and return user info"""
    return jsonify({'user': request.user})


@app.route('/api/auth/register', methods=['POST'])
@require_admin
def register():
    """Register new user (admin only)"""
    try:
        data = request.json
        username = data.get('username')
        password = data.get('password')
        email = data.get('email')
        full_name = data.get('full_name')
        is_admin = data.get('is_admin', False)
        
        if not username or not password:
            return jsonify({'error': 'Username and password required'}), 400
        
        user = auth.register_user(username, password, email, full_name, is_admin)
        return jsonify({'success': True, 'user': user})
        
    except AuthError as e:
        return jsonify({'error': str(e)}), 400


# ============================================================================
# PUBLIC ROUTES (No auth required)
# ============================================================================

@app.route('/')
def index():
    """Serve the main dashboard (auth handled by JavaScript)"""
    return send_from_directory('static', 'index.html')


@app.route('/login')
def login_page():
    """Serve login page"""
    return send_from_directory('static', 'login.html')


# ============================================================================
# PROTECTED ROUTES (Authentication required)
# ============================================================================

@app.route('/api/services', methods=['GET'])
@require_auth
def get_services():
    """Get all services (installed and available) with health status"""
    try:
        # Get installed services
        installed = db.list_services()
        installed_ids = {s['service_id'] for s in installed}
        
        # Get all available services
        available = loader.list_available()
        
        services = []
        for service_id in available:
            try:
                manifest = loader.load(service_id)
                is_installed = service_id in installed_ids
                
                # Get status and health if installed
                status = 'stopped'
                health = None
                health_info = None
                
                if is_installed:
                    try:
                        container_status = service_mgr.get_status(service_id)
                        status = container_status.get('status', 'stopped')
                    except Exception as e:
                        logger.error(f"get_status failed for {service_id}: {e}")
                        status = 'stopped'

                    try:
                        health_info = health_monitor._get_last_result(service_id)
                        if health_info:
                            health = health_info.get('status')
                    except Exception:
                        pass                
                services.append({
                    'id': service_id,
                    'name': manifest.name,
                    'version': manifest.version,
                    'category': manifest.category,
                    'description': manifest.description,
                    'ports': manifest.ports,
                    'installed': is_installed,
                    'status': status,
                    'health': health,
                    'health_info': health_info,
                    'tier': firewall_mgr.get_service_tier(service_id) if is_installed else None,
                    'icon': manifest.data.get('metadata', {}).get('icon'),
                    'metadata': manifest.data.get('metadata', {}),
                })
            except Exception as e:
                print(f"ERROR loading service {service_id}: {e}")  # Add this line
                import traceback
                traceback.print_exc()  # Add this line
                continue
        
        return jsonify({'services': services})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>', methods=['GET'])
@require_auth
def get_service(service_id):
    """Get details for a specific service with health info"""
    try:
        manifest = loader.load(service_id)
        is_installed = db.is_installed(service_id)
        
        # Get dependencies
        deps = resolver.get_dependencies(service_id)
        optional_deps = resolver.get_optional_dependencies(service_id)
        
        # Get health info if installed
        health_info = None
        if is_installed:
            health_info = health_monitor._get_last_result(service_id)
        
        return jsonify({
            'id': service_id,
            'name': manifest.name,
            'version': manifest.version,
            'category': manifest.category,
            'description': manifest.description,
            'ports': manifest.ports,
            'volumes': manifest.volumes,
            'dependencies': {
                'required': deps,
                'optional': optional_deps
            },
            'installed': is_installed,
            'health': health_info,
            'metadata': manifest.data.get('metadata', {}),
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 404

@app.route('/api/services/<service_id>/config-schema', methods=['GET'])
@require_auth
def get_service_config_schema(service_id):
    """Get configuration schema for a service"""
    try:
        manifest = loader.load(service_id)
        user_inputs = manifest.get_user_inputs()
            
        return jsonify({
            'needs_config': len(user_inputs) > 0 if user_inputs else False,
            'inputs': user_inputs or []
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/install', methods=['POST'])
@require_auth
def install_service(service_id):
    """Install a service with optional configuration and progress tracking"""
    import threading
    
    # Get configuration from request body if provided
    data = request.get_json() or {}
    user_config = data.get('config', {})
    
    # Initialize progress tracking
    installation_status[service_id] = {
        'status': 'in_progress',
        'progress': 0,
        'step': 'Starting installation',
        'error': None,
        'cancelled': False
    }
    
    def run_installation():
        """Background installation thread"""
        try:
            from core.installer import ServiceInstaller

            logger.info(f"[{service_id}] Installation started")
            installation_status[service_id].update({
                'progress': 10,
                'step': 'Loading service manifest'
            })

            manifest = loader.load(service_id)
            logger.info(f"[{service_id}] Manifest loaded: {manifest.name}")

            def is_cancelled():
                return installation_status.get(service_id, {}).get('cancelled', False)

            if is_cancelled():
                logger.info(f"[{service_id}] Cancelled before start")
                installation_status[service_id].update({
                    'status': 'cancelled', 'progress': 0,
                    'step': 'Installation cancelled'
                })
                return

            installer = ServiceInstaller(
                manifest,
                user_config=user_config,
                db=db
            )

            def on_progress(pct, step):
                if not is_cancelled():
                    logger.info(f"[{service_id}] {pct}% — {step}")
                    installation_status[service_id].update({
                        'progress': pct,
                        'step': step
                    })

            installer.progress_callback = on_progress
            installer.cancel_check = is_cancelled

            success = installer.install(dry_run=False)

            if is_cancelled():
                logger.info(f"[{service_id}] Cancelled mid-install")
                installation_status[service_id].update({
                    'status': 'cancelled', 'progress': 0,
                    'step': 'Installation cancelled'
                })
                return

            if success:
                logger.info(f"[{service_id}] Installation complete")
                installation_status[service_id].update({
                    'status': 'complete', 'progress': 100,
                    'step': 'Installation complete'
                })
            else:
                logger.error(f"[{service_id}] Installation failed")
                installation_status[service_id].update({
                    'status': 'failed', 'progress': 0,
                    'step': 'Installation failed',
                    'error': 'Installation failed'
                })
                    
        except subprocess.TimeoutExpired:
            installation_status[service_id].update({
                'status': 'failed',
                'progress': 0,
                'step': 'Installation timeout',
                'error': 'Installation timeout (5 minutes)'
            })
        except Exception as e:
            installation_status[service_id].update({
                'status': 'failed',
                'progress': 0,
                'step': 'Installation error',
                'error': str(e)
            })
        finally:
            # Clean up status after 30 seconds
            import time
            time.sleep(30)
            if service_id in installation_status:
                del installation_status[service_id]
    
    # Start installation in background thread
    thread = threading.Thread(target=run_installation, daemon=True)
    thread.start()
    
    # Return immediately
    return jsonify({
        'success': True,
        'message': f'Installation of {service_id} started'
    }), 202
    
@app.route('/api/services/<service_id>/uninstall', methods=['POST'])
@require_auth
def uninstall_service(service_id):
    """Uninstall a service — stops container, removes it, cleans DB and data dir"""
    try:
        import docker as _docker
        import shutil

        errors = []
        data = request.get_json(silent=True) or {}
        remove_data = data.get('remove_data', False)  # optionally wipe data dir

        # 1. Stop and remove Docker container
        try:
            client = _docker.from_env()
            container_name = f"pso-{service_id}"
            try:
                container = client.containers.get(container_name)
                container.stop(timeout=10)
                container.remove()
            except _docker.errors.NotFound:
                pass  # already gone
        except Exception as e:
            errors.append(f"Container removal: {e}")

        # 2. Remove from PSO database (services + ports + volumes + dependencies)
        try:
            db.remove_service(service_id)
        except Exception:
            pass  # may already be gone

        # 3. Clean up orphaned port records
        try:
            with db._get_connection() as conn:
                conn.execute('DELETE FROM service_ports WHERE service_id = ?', (service_id,))
                conn.commit()
        except Exception as e:
            errors.append(f"Port cleanup: {e}")

        # 4. Clean up Docker volumes
        try:
            client = _docker.from_env()
            volumes = client.volumes.list(filters={'label': f'pso.service={service_id}'})
            for vol in volumes:
                try:
                    vol.remove(force=True)
                except:
                    pass
        except Exception as e:
            errors.append(f"Volume cleanup: {e}")

        # 5. Clean up Docker networks
        try:
            client = _docker.from_env()
            network_name = f"pso-{service_id}-net"
            try:
                network = client.networks.get(network_name)
                network.remove()
            except _docker.errors.NotFound:
                pass
        except Exception as e:
            errors.append(f"Network cleanup: {e}")

        # 6. Clean up service secrets
        try:
            from core.secrets_manager import SecretsManager
            secrets_mgr = SecretsManager()
            secrets_mgr.delete_service_secrets(service_id)
        except Exception as e:
            errors.append(f"Secrets cleanup: {e}")

        # 7. Optionally remove data directory
        if remove_data:
            try:
                data_dir = Path.home() / '.pso_dev' / 'services' / service_id
                if data_dir.exists():
                    shutil.rmtree(data_dir)
            except Exception as e:
                errors.append(f"Data dir removal: {e}")

        if errors:
            return jsonify({
                'success': True,
                'message': f'{service_id} uninstalled (with warnings)',
                'warnings': errors
            })

        return jsonify({'success': True, 'message': f'{service_id} uninstalled successfully'})

    except Exception as e:
        logger.error(f"Uninstall failed for {service_id}: {e}")
        return jsonify({'error': f'Uninstall failed: {str(e)}'}), 500


@app.route('/api/services/<service_id>/cleanup', methods=['POST'])
@require_auth
def cleanup_orphan(service_id):
    """
    Remove an orphaned service from the PSO database.
    Used when a container was deleted outside PSO (docker rm, etc.)
    The container is already gone — this just cleans up the DB records.
    """
    errors = []

    try:
        db.remove_service(service_id)
    except Exception as e:
        errors.append(f"DB removal: {e}")

    try:
        with db._get_connection() as conn:
            conn.execute('DELETE FROM service_ports WHERE service_id = ?', (service_id,))
            conn.commit()
    except Exception as e:
        errors.append(f"Port cleanup: {e}")

    if errors:
        return jsonify({'success': True, 'warnings': errors})
    return jsonify({'success': True, 'message': f'{service_id} cleaned up'})


@app.route('/api/services/<service_id>/start', methods=['POST'])
@require_auth
def start_service(service_id):
    """Start a service"""
    try:
        # Get live Docker status first
        current = service_mgr.get_status(service_id)
        if current.get('status') == 'running':
            return jsonify({'success': True, 'message': f'{service_id} is already running', 'already_running': True})
        service_mgr.start(service_id)
        return jsonify({'success': True, 'message': f'{service_id} started'})
    except Exception as e:
        logger.error(f"start failed for {service_id}: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/stop', methods=['POST'])
@require_auth
def stop_service(service_id):
    """Stop a service"""
    try:
        service_mgr.stop(service_id)
        return jsonify({'success': True, 'message': f'{service_id} stopped'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/bulk/stop-all', methods=['POST'])
@require_auth
def stop_all_services():
    """Stop all running services"""
    import docker as _docker
    try:
        client = _docker.from_env()
        stopped = []
        errors = []

        # Get all PSO containers
        containers = client.containers.list(filters={'label': 'pso.managed=true'})

        for container in containers:
            try:
                service_id = container.labels.get('pso.service')
                container.stop(timeout=10)
                stopped.append(service_id)
            except Exception as e:
                errors.append(f"{service_id}: {str(e)}")

        return jsonify({
            'success': True,
            'stopped': stopped,
            'count': len(stopped),
            'errors': errors
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/bulk/start-all', methods=['POST'])
@require_auth
def start_all_services():
    """Start all stopped services that are installed"""
    started = []
    errors = []

    try:
        # Get all installed services from database
        installed = db.get_all_services()

        for service_info in installed:
            service_id = service_info.get('service_id')
            try:
                # Check if already running
                status = service_mgr.get_status(service_id)
                if status.get('status') != 'running':
                    service_mgr.start(service_id)
                    started.append(service_id)
            except Exception as e:
                errors.append(f"{service_id}: {str(e)}")

        return jsonify({
            'success': True,
            'started': started,
            'count': len(started),
            'errors': errors
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/restart', methods=['POST'])
@require_auth
def restart_service(service_id):
    """Restart a service"""
    try:
        service_mgr.restart(service_id)
        return jsonify({'success': True, 'message': f'{service_id} restarted'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/logs', methods=['GET'])
@require_auth
def get_logs(service_id):
    """Get service logs"""
    try:
        lines = request.args.get('lines', 100, type=int)
        logs = service_mgr.get_logs(service_id, lines=lines)
        return jsonify({'logs': logs})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# HEALTH MONITORING ENDPOINTS
# ============================================================================

@app.route('/api/health', methods=['GET'])
@require_auth
def get_all_health():
    """Get health status for all services"""
    try:
        health_status = health_monitor.get_status()
        return jsonify({'health': health_status})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health/<service_id>', methods=['GET'])
@require_auth
def get_service_health(service_id):
    """Get health status for a specific service"""
    try:
        health = health_monitor._get_last_result(service_id)
        if not health:
            return jsonify({'error': 'Service not found or no health data'}), 404
        return jsonify({'health': health})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health/<service_id>/history', methods=['GET'])
@require_auth
def get_health_history(service_id):
    """Get health check history for a service"""
    try:
        limit = request.args.get('limit', 100, type=int)
        history = health_monitor.get_history(service_id, limit=limit)
        return jsonify({'history': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/health/<service_id>/check', methods=['POST'])
@require_auth
def trigger_health_check(service_id):
    """Manually trigger a health check for a service"""
    try:
        check = health_monitor.check_service(service_id)
        return jsonify({'check': check.to_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# OTHER PROTECTED ENDPOINTS
# ============================================================================

@app.route('/api/ports', methods=['GET'])
@require_auth
def get_ports():
    """Get port allocations"""
    try:
        allocations = port_mgr.get_all_ports()
        return jsonify({'ports': allocations})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<service_id>', methods=['GET'])
@require_auth
def get_backups(service_id):
    """List backups for a service"""
    try:
        backups = backup_mgr.list_backups(service_id)
        return jsonify({'backups': backups})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/backups/<service_id>/create', methods=['POST'])
@require_auth
def create_backup(service_id):
    """Create a backup"""
    try:
        note = request.json.get('note') if request.json else None
        backup_path = backup_mgr.create_backup(service_id, note=note)
        return jsonify({'success': True, 'path': str(backup_path)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/stats', methods=['GET'])
@require_auth
def get_system_stats():
    """Get system statistics"""
    try:
        import shutil, time, os

        # Services
        installed_services = db.list_services()
        installed = len(installed_services)
        available = len(loader.list_available())

        # Count running by asking Docker directly
        running  = 0
        healthy  = 0
        orphaned = 0
        for svc in installed_services:
            try:
                st = service_mgr.get_status(svc['service_id'])
                s  = st.get('status')
                if s == 'running':
                    running += 1
                    healthy += 1
                elif s == 'orphaned':
                    orphaned += 1
            except Exception:
                pass

        # Disk usage for /
        try:
            total, used, free = shutil.disk_usage('/')
            disk_pct = round(used / total * 100, 1)
            disk_used = f"{disk_pct}%"
        except Exception:
            disk_used = 'N/A'

        # Dashboard uptime (since this Flask process started)
        try:
            secs = int(time.time() - _dashboard_start)
            h = secs // 3600
            m = (secs % 3600) // 60
            uptime = f"{h}h {m}m"
        except Exception:
            uptime = 'N/A'

        return jsonify({
            'services_installed': installed,
            'services_running':   running,
            'services_healthy':   healthy,
            'services_orphaned':  orphaned,
            'services_available': available,
            'disk_used':  disk_used,
            'uptime':     uptime,
            'services': {
                'installed': installed,
                'running':   running,
                'available': available,
                'orphaned':  orphaned,
            },
            'system': {
                'version': '1.0.0',
                'status':  'running',
                'uptime':  uptime,
                'disk':    disk_used,
            }
        })
    except Exception as e:
        logger.error(f"system stats error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/pause', methods=['POST'])
@require_auth
def system_pause():
    """Stop all running PSO service containers"""
    try:
        import docker as docker_lib
        client = docker_lib.from_env()
        containers = client.containers.list(filters={'name': 'pso-'})
        stopped = []
        failed = []
        for c in containers:
            try:
                c.stop(timeout=10)
                stopped.append(c.name.replace('pso-', '', 1))
            except Exception as e:
                failed.append({'name': c.name, 'error': str(e)})
        return jsonify({
            'stopped': stopped,
            'failed': failed,
            'count': len(stopped)
        })
    except Exception as e:
        logger.error(f"system pause error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/system/resume', methods=['POST'])
@require_auth
def system_resume():
    """Start all stopped PSO service containers"""
    try:
        import docker as docker_lib
        client = docker_lib.from_env()
        containers = client.containers.list(
            all=True, filters={'name': 'pso-'}
        )
        started = []
        skipped = []
        failed = []
        for c in containers:
            if c.status == 'running':
                skipped.append(c.name.replace('pso-', '', 1))
            else:
                try:
                    c.start()
                    started.append(c.name.replace('pso-', '', 1))
                except Exception as e:
                    failed.append({'name': c.name, 'error': str(e)})
        return jsonify({
            'started': started,
            'skipped': skipped,
            'failed': failed,
            'count': len(started)
        })
    except Exception as e:
        logger.error(f"system resume error: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/tiers', methods=['GET'])
@require_auth
def get_tiers():
    """Get all tier definitions"""
    try:
        tiers = firewall_mgr.get_all_tiers()
        return jsonify({'tiers': tiers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/tier', methods=['GET'])
@require_auth
def get_service_tier(service_id):
    """Get current tier for a service"""
    try:
        tier = firewall_mgr.get_service_tier(service_id)
        tier_info = firewall_mgr.get_tier_info(tier)
        
        return jsonify({
            'service_id': service_id,
            'current_tier': tier,
            'tier_info': tier_info
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/tier', methods=['POST'])
@require_auth
def set_service_tier_endpoint(service_id):
    """Change service tier"""
    try:
        data = request.json
        new_tier = data.get('tier')
        confirmation = data.get('confirmation', False)
        reason = data.get('reason')
        
        if new_tier is None:
            return jsonify({'error': 'Tier is required'}), 400
        
        # Tier 3 requires explicit confirmation
        if new_tier == 3 and not confirmation:
            return jsonify({
                'error': 'Tier 3 requires explicit confirmation',
                'requires_confirmation': True
            }), 400
        
        # Get current user from token
        username = request.user.get('username', 'unknown')
        
        # Change tier
        firewall_mgr.set_service_tier(
            service_id, 
            new_tier, 
            changed_by=username,
            reason=reason
        )
        
        return jsonify({
            'success': True,
            'service_id': service_id,
            'new_tier': new_tier,
            'tier_info': firewall_mgr.get_tier_info(new_tier)
        })
        
    except FirewallError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/tier/history', methods=['GET'])
@require_auth
def get_tier_history_endpoint(service_id):
    """Get tier change history for a service"""
    try:
        limit = request.args.get('limit', 50, type=int)
        history = firewall_mgr.get_tier_history(service_id, limit=limit)
        
        return jsonify({
            'service_id': service_id,
            'history': history
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tiers/services', methods=['GET'])
@require_auth
def get_all_service_tiers():
    """Get tiers for all services"""
    try:
        service_tiers = firewall_mgr.get_all_service_tiers()
        return jsonify({'services': service_tiers})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/tiers/reset-all', methods=['POST'])
@require_admin
def reset_all_tiers():
    """Reset all services to Tier 0 (admin only, emergency)"""
    try:
        data = request.json or {}
        confirmation = data.get('confirmation', False)
        
        if not confirmation:
            return jsonify({
                'error': 'Confirmation required',
                'message': 'This will reset ALL services to Tier 0 (Internal Only)'
            }), 400
        
        username = request.user.get('username', 'unknown')
        count = firewall_mgr.reset_all_to_tier_0(changed_by=username)
        
        return jsonify({
            'success': True,
            'message': f'Reset {count} services to Tier 0',
            'count': count
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# INSTALLATION PROGRESS ENDPOINTS
# ============================================================================

@app.route('/api/services/<service_id>/install-status', methods=['GET'])
@require_auth
def get_install_status(service_id):
    """Get installation progress for a service"""
    status = installation_status.get(service_id, {
        'status': 'not_started',
        'progress': 0,
        'step': '',
        'error': None
    })
    return jsonify(status)


@app.route('/api/services/<service_id>/install-cancel', methods=['POST'])
@require_auth
def cancel_install(service_id):
    """Cancel an ongoing installation"""
    if service_id in installation_status:
        installation_status[service_id]['cancelled'] = True
        logger.info(f"[{service_id}] Cancellation requested by user")
        return jsonify({'success': True, 'message': 'Cancellation requested'})
    return jsonify({'error': 'No installation in progress'}), 404


# ============================================================================
# LIVE LOG ENDPOINTS
# ============================================================================

@app.route('/api/logs', methods=['GET'])
@require_auth
def get_logs_buffer():
    """Return recent log entries from the in-memory buffer (polling)"""
    since = request.args.get('since', 0, type=int)  # index to paginate
    entries = list(_LOG_BUFFER)
    return jsonify({
        'logs': entries[since:],
        'total': len(entries)
    })


@app.route('/api/logs/stream')
@require_auth
def stream_logs():
    """
    Server-Sent Events stream of live log entries.
    Frontend connects once and receives log lines as they arrive.
    """
    import time as _time

    def generate():
        last = len(_LOG_BUFFER)
        yield f"data: {json.dumps({'type': 'connected'})}\n\n"
        while True:
            current = list(_LOG_BUFFER)
            if len(current) > last:
                for entry in current[last:]:
                    yield f"data: {json.dumps(entry)}\n\n"
                last = len(current)
            _time.sleep(0.5)

    return Response(
        generate(),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',  # disable nginx buffering
        }
    )

# ============================================================================
# RESOURCE MANAGEMENT ENDPOINTS
# ============================================================================

@app.route('/api/resources/profiles', methods=['GET'])
@require_auth
def get_resource_profiles():
    """Get all available resource profiles"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager()
        profiles = rm.list_profiles()
        return jsonify({'profiles': profiles})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/resources', methods=['GET'])
@require_auth
def get_service_resources(service_id):
    """Get resource limits and current usage for a service"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager(db)
        
        # Get configured limits
        limits = rm.get_service_limits(service_id)
        
        # Get current usage if service is running
        container_name = f"pso-{service_id}"
        usage = rm.get_container_stats(container_name)
        
        # Get usage history
        history = rm.get_usage_history(service_id, limit=20)
        
        return jsonify({
            'limits': limits,
            'usage': usage,
            'history': history
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/resources', methods=['POST'])
@require_auth
def set_service_resources(service_id):
    """Set resource limits for a service"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager(db)
        
        data = request.json or {}
        
        # Extract parameters
        profile = data.get('profile')
        cpu_cores = data.get('cpu_cores')
        memory_mb = data.get('memory_mb')
        disk_mb = data.get('disk_mb')
        restart_policy = data.get('restart_policy')
        
        # Set limits
        rm.set_service_limits(
            service_id,
            profile=profile,
            cpu_cores=cpu_cores,
            memory_mb=memory_mb,
            disk_mb=disk_mb,
            restart_policy=restart_policy
        )
        
        return jsonify({
            'success': True,
            'message': f'Resource limits updated for {service_id}'
        })
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/resources/apply', methods=['POST'])
@require_auth
def apply_service_resources(service_id):
    """Apply resource limits to a running container"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager(db)
        
        container_name = f"pso-{service_id}"
        rm.apply_limits_to_container(service_id, container_name)
        
        return jsonify({
            'success': True,
            'message': f'Resource limits applied to {service_id}'
        })
    except RuntimeError as e:
        return jsonify({'error': str(e)}), 404
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/resources/stats', methods=['GET'])
@require_auth
def get_service_resource_stats(service_id):
    """Get current resource usage statistics"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager(db)
        
        container_name = f"pso-{service_id}"
        stats = rm.get_container_stats(container_name)
        
        return jsonify({'stats': stats})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/resources/history', methods=['GET'])
@require_auth
def get_service_resource_history(service_id):
    """Get historical resource usage"""
    try:
        from core.resource_manager import ResourceManager
        rm = ResourceManager(db)
        
        limit = request.args.get('limit', 100, type=int)
        history = rm.get_usage_history(service_id, limit=limit)
        
        return jsonify({'history': history})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# METRICS ENDPOINTS
# ============================================================================

# Initialize metrics collector.
# Delay startup by 5s so Flask finishes booting before the first
# docker stats call (which is slow and would delay the dashboard).
import threading as _threading
from core.metrics import MetricsCollector

metrics_collector = MetricsCollector()

def _start_metrics_delayed():
    time.sleep(5)
    metrics_collector.start_daemon()

_threading.Thread(target=_start_metrics_delayed, daemon=True).start()


def _latest_dict(service_id=None):
    """Return all latest metrics as a flat {metric: value} dict."""
    store = metrics_collector.store
    SYSTEM_METRICS = [
        'host_cpu_percent', 'host_memory_used_mb',
        'host_memory_pct', 'host_disk_used_gb', 'host_disk_pct',
    ]
    SERVICE_METRICS = ['service_cpu_percent', 'service_memory_mb']
    metrics = SERVICE_METRICS if service_id else SYSTEM_METRICS
    result = {}
    for m in metrics:
        row = store.latest(m, service_id=service_id)
        if row:
            result[m] = row['value']
    return result


@app.route('/api/metrics/system/latest', methods=['GET'])
@require_auth
def get_system_metrics_latest():
    """Get latest system metrics"""
    try:
        return jsonify({'metrics': _latest_dict()})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/system/<metric_name>', methods=['GET'])
@require_auth
def get_system_metric_history(metric_name):
    """Get historical data for a system metric"""
    try:
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 1000, type=int)
        data = metrics_collector.store.query(
            metric_name, since_hours=hours, limit=limit
        )
        return jsonify({'metric': metric_name, 'data': data, 'hours': hours})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/services/<service_id>/latest', methods=['GET'])
@require_auth
def get_service_metrics_latest(service_id):
    """Get latest metrics for a service"""
    try:
        return jsonify({'metrics': _latest_dict(service_id)})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/services/<service_id>/<metric_name>', methods=['GET'])
@require_auth
def get_service_metric_history(service_id, metric_name):
    """Get historical data for a service metric"""
    try:
        hours = request.args.get('hours', 24, type=int)
        limit = request.args.get('limit', 1000, type=int)
        data = metrics_collector.store.query(
            metric_name, service_id=service_id, since_hours=hours, limit=limit
        )
        return jsonify({'service': service_id, 'metric': metric_name,
                        'data': data, 'hours': hours})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/prometheus', methods=['GET'])
def get_prometheus_metrics():
    """Prometheus-compatible endpoint (no auth — for Prometheus scraping)"""
    try:
        output = metrics_collector.store.prometheus_export()
        return output, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f'# Error: {e}\n', 500, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/api/metrics/prometheus/services/<service_id>', methods=['GET'])
def get_prometheus_service_metrics(service_id):
    """Prometheus-compatible metrics for a specific service"""
    try:
        output = metrics_collector.store.prometheus_export(service_id)
        return output, 200, {'Content-Type': 'text/plain; charset=utf-8'}
    except Exception as e:
        return f'# Error: {e}\n', 500, {'Content-Type': 'text/plain; charset=utf-8'}


@app.route('/api/metrics/collect', methods=['POST'])
@require_admin
def trigger_metrics_collection():
    """Manually trigger one metrics collection cycle (admin only)"""
    try:
        n = metrics_collector.collect_once()
        return jsonify({'success': True, 'samples_written': n})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/metrics/dashboard', methods=['GET'])
@require_auth
def get_dashboard_metrics():
    """Aggregated metrics for the dashboard overview panel"""
    try:
        system = _latest_dict()
        services = {}
        for svc in db.list_services():
            sid = svc['service_id']
            m   = _latest_dict(sid)
            if m:
                services[sid] = m
        return jsonify({
            'system': {
                'cpu_percent':    system.get('host_cpu_percent', 0),
                'memory_percent': system.get('host_memory_pct', 0),
                'memory_used_mb': system.get('host_memory_used_mb', 0),
                'disk_percent':   system.get('host_disk_pct', 0),
                'disk_used_gb':   system.get('host_disk_used_gb', 0),
            },
            'services':  services,
            'timestamp': time.time()
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ============================================================================
# NOTIFICATION SETTINGS ENDPOINTS
# ============================================================================

if __name__ == '__main__':
    import os as _os

    _PSO_DIR  = _os.path.expanduser('~/.pso_dev')
    _CERT     = _os.path.join(_PSO_DIR, 'dashboard.crt')
    _KEY      = _os.path.join(_PSO_DIR, 'dashboard.key')
    _SSL      = _os.path.isfile(_CERT) and _os.path.isfile(_KEY)
    _PROTOCOL = 'https' if _SSL else 'http'

    print("🚀 Starting PSO Web Dashboard...")
    print(f"📍 {_PROTOCOL}://localhost:5000")
    if _SSL:
        print("🔐 HTTPS enabled (self-signed certificate)")
    print("💚 Health monitoring enabled (30s intervals)")
    print("🔒 Authentication enabled")
    print("🛡️  Tier system enabled (4-tier security)")
    print("")
    print("Default login:")
    print("  Username: admin")
    print("  Password: (set during 'pso init' — change with 'pso user passwd admin')")
    print("")
    print("All services start at Tier 0 (Internal Only)")
    print("")

    _ssl_ctx = (_CERT, _KEY) if _SSL else None

    try:
        app.run(host='0.0.0.0', port=5000, debug=False, ssl_context=_ssl_ctx)
    finally:
        # Stop health monitor on shutdown
        if hasattr(health_monitor, 'stop'):
            health_monitor.stop()


 # Additional API Endpoints for Enhanced Dashboard
# Add these to your web/api.py file

from core.update_manager import ServiceUpdateManager
from core.backup_manager import BackupManager
from core.service_recommendations import get_recommended_services, CATEGORIES

# ============================================================================
# LOG VIEWER ENDPOINTS
# ============================================================================

@app.route('/api/services/<service_id>/logs')
@require_auth
def get_service_logs(service_id):
    """Get service logs with optional line limit"""
    try:
        lines = int(request.args.get('lines', 100))
        
        # Get logs from Docker
        result = subprocess.run(
            ['docker', 'logs', '--tail', str(lines), f'pso-{service_id}'],
            capture_output=True,
            text=True
        )
        
        logs = result.stdout + result.stderr
        log_lines = logs.split('\n') if logs else []
        
        return jsonify({
            'logs': log_lines,
            'total_lines': len(log_lines)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


# ============================================================================
# UPDATE MANAGER ENDPOINTS
# ============================================================================

@app.route('/api/services/<service_id>/check-update')
@require_auth
def check_service_update(service_id):
    """Check if service has updates available"""
    try:
        update_mgr = ServiceUpdateManager()
        updates = update_mgr.check_updates(service_id)
        
        if updates and len(updates) > 0:
            update = updates[0]
            return jsonify({
                'update_available': True,
                'current_digest': update.get('current_digest', 'unknown'),
                'latest_digest': update.get('latest_digest', 'unknown'),
                'image': update.get('image', '')
            })
        
        return jsonify({
            'update_available': False,
            'current_digest': 'unknown',
            'latest_digest': 'unknown'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/update', methods=['POST'])
@require_auth
def update_service(service_id):
    """Update service to latest version"""
    try:
        update_mgr = ServiceUpdateManager()
        success = update_mgr.update_service(service_id, backup=True)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{service_id} updated successfully'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Update failed'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# BACKUP MANAGER ENDPOINTS
# ============================================================================

@app.route('/api/services/<service_id>/backups')
@require_auth
def get_service_backups(service_id):
    """Get list of backups for a service"""
    try:
        backup_mgr = BackupManager()
        backups = backup_mgr.list_backups(service_id)
        
        return jsonify({
            'backups': backups,
            'count': len(backups)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@app.route('/api/services/<service_id>/backup', methods=['POST'])
@require_auth
def create_service_backup(service_id):
    """Create a backup for a service"""
    try:
        data = request.json or {}
        note = data.get('note', 'Manual backup from dashboard')
        
        backup_mgr = BackupManager()
        backup_id = backup_mgr.create_backup(service_id, note=note)
        
        return jsonify({
            'success': True,
            'backup_id': backup_id,
            'message': 'Backup created successfully'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


@app.route('/api/services/<service_id>/restore', methods=['POST'])
@require_auth
def restore_service_backup(service_id):
    """Restore service from a backup"""
    try:
        data = request.json
        backup_id = data.get('backup_id')
        
        if not backup_id:
            return jsonify({'error': 'backup_id required'}), 400
        
        backup_mgr = BackupManager()
        success = backup_mgr.restore_backup(service_id, backup_id)
        
        if success:
            return jsonify({
                'success': True,
                'message': f'{service_id} restored from {backup_id}'
            })
        else:
            return jsonify({
                'success': False,
                'error': 'Restore failed'
            }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ============================================================================
# METRICS ENDPOINTS
# ============================================================================

@app.route('/api/services/<service_id>/metrics')
@require_auth
def get_service_metrics(service_id):
    """Get real-time metrics for a service"""
    try:
        # Get Docker stats
        result = subprocess.run(
            ['docker', 'stats', f'pso-{service_id}', '--no-stream', '--format', 
             '{{.CPUPerc}}|{{.MemPerc}}|{{.MemUsage}}|{{.NetIO}}|{{.BlockIO}}'],
            capture_output=True,
            text=True,
            timeout=5
        )
        
        if result.returncode != 0:
            return jsonify({
                'cpu': 0,
                'memory': 0,
                'disk': {'used': 'N/A'},
                'network': {'tx': '0', 'rx': '0'}
            })
        
        stats = result.stdout.strip().split('|')
        
        # Parse stats
        cpu = float(stats[0].replace('%', '')) if len(stats) > 0 else 0
        memory = float(stats[1].replace('%', '')) if len(stats) > 1 else 0
        mem_usage = stats[2] if len(stats) > 2 else 'N/A'
        net_io = stats[3].split('/') if len(stats) > 3 else ['0', '0']
        
        return jsonify({
            'cpu': round(cpu, 1),
            'memory': round(memory, 1),
            'disk': {'used': mem_usage},
            'network': {
                'rx': net_io[0].strip() if len(net_io) > 0 else '0',
                'tx': net_io[1].strip() if len(net_io) > 1 else '0'
            }
        })
    except Exception as e:
        return jsonify({
            'cpu': 0,
            'memory': 0,
            'disk': {'used': 'N/A'},
            'network': {'tx': '0', 'rx': '0'}
        })


# ============================================================================
# SYSTEM STATS ENDPOINTS
# ============================================================================

@app.route('/api/recommendations')
@require_auth
def get_recommendations():
    """Get recommended services to install"""
    try:
        recommended_ids = get_recommended_services()
        recommendations = []
        
        for service_id in recommended_ids:
            info = CATEGORIES.get(service_id, {})
            recommendations.append({
                'service_id': service_id,
                'name': service_id.replace('-', ' ').title(),
                'why_recommended': info.get('why_recommended', ''),
                'tags': info.get('tags', []),
                'icon': '🔐' if service_id == 'vaultwarden' else '📦',
                'category': info.get('category', 'other'),
                'priority': info.get('priority', 99)
            })
        
        # Sort by priority
        recommendations.sort(key=lambda x: x['priority'])
        
        return jsonify({
            'recommendations': recommendations[:5]  # Top 5
        })
    except Exception as e:
        return jsonify({
            'recommendations': []
        })



@app.route('/api/settings/notifications', methods=['GET', 'POST'])
@require_auth
def notification_settings():
    """Get or update notification settings"""
    settings_file = '/var/pso/settings/notifications.json'
    
    if request.method == 'POST':
        try:
            settings = request.json
            
            # Save settings
            os.makedirs('/var/pso/settings', exist_ok=True)
            with open(settings_file, 'w') as f:
                json.dump(settings, f)
            
            return jsonify({'success': True})
        except Exception as e:
            return jsonify({'error': str(e)}), 500
    else:
        # Load settings
        try:
            if os.path.exists(settings_file):
                with open(settings_file) as f:
                    settings = json.load(f)
            else:
                # Default settings
                settings = {
                    'health_failures': True,
                    'backups': True,
                    'updates': True,
                    'tier_changes': True,
                    'rate_limits': False
                }
            
            return jsonify(settings)
        except Exception as e:
            return jsonify({
                'health_failures': True,
                'backups': True,
                'updates': True,
                'tier_changes': True,
                'rate_limits': False
            })