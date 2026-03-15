#!/usr/bin/env python3
"""
Tests for web/api.py Flask routes.

Run with: python -m pytest tests/test_api.py -v

Import strategy:
- web/ has no __init__.py so 'from web.api import app' does NOT work.
- We add web/ to sys.path and import 'api' directly.
- All constructors (Database, HealthMonitor, etc.) are patched BEFORE the
  import so module-level instantiation gets mocks, not real objects.
- MetricsCollector is imported at line 922 in api.py (mid-file), so it is
  patched at 'api.MetricsCollector' after import as a belt-and-braces cover.
"""

import pytest
import json
import sys
import importlib
from pathlib import Path
from unittest.mock import MagicMock, patch

# ── path setup ────────────────────────────────────────────────────────────────
_ROOT = Path(__file__).parent.parent
_WEB  = _ROOT / 'web'
sys.path.insert(0, str(_ROOT))
sys.path.insert(0, str(_WEB))


# ── shared mock instances ─────────────────────────────────────────────────────
_mock_db          = MagicMock()
_mock_loader      = MagicMock()
_mock_service_mgr = MagicMock()
_mock_backup_mgr  = MagicMock()
_mock_resolver    = MagicMock()
_mock_port_mgr    = MagicMock()
_mock_health_mon  = MagicMock()
_mock_auth        = MagicMock()
_mock_firewall    = MagicMock()
_mock_metrics     = MagicMock()

for _m in (_mock_health_mon, _mock_metrics):
    _m.start        = MagicMock()
    _m.start_daemon = MagicMock()
_mock_metrics.docker_client = MagicMock()
_mock_metrics.docker_client.containers.list.return_value = []


# ── pre-import patches ────────────────────────────────────────────────────────
# Patch constructors in their source modules so api.py's module-level
# `db = Database()`, `health_monitor = HealthMonitor(db, svc_mgr)`, etc.
# all receive our mock instances rather than trying to connect to Docker/DB.
_patches = [
    patch('core.database.Database',
          return_value=_mock_db),
    patch('core.manifest.ManifestLoader',
          return_value=_mock_loader),
    patch('core.service_manager.ServiceManager',
          return_value=_mock_service_mgr),
    patch('core.backup_manager.BackupManager',
          return_value=_mock_backup_mgr),
    patch('core.dependency_resolver.DependencyResolver',
          return_value=_mock_resolver),
    patch('core.port_manager.PortManager',
          return_value=_mock_port_mgr),
    patch('core.health_monitor.HealthMonitor',
          return_value=_mock_health_mon),
    patch('core.auth.Auth',
          return_value=_mock_auth),
    patch('core.firewall_manager.FirewallManager',
          return_value=_mock_firewall),
    # MetricsCollector is imported mid-file (line ~922) — patch it in both
    # its source module and the 'core.metrics' namespace
    patch('core.metrics.MetricsCollector',
          return_value=_mock_metrics),
]

for _p in _patches:
    _p.start()

# Now safe to import api
import api as _api_module          # noqa: E402
_flask_app = _api_module.app
_flask_app.config['TESTING'] = True

for _p in _patches:
    _p.stop()


# ── fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture(scope='session')
def app():
    return _flask_app


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture(autouse=True)
def reset_mocks():
    """Reset every mock before each test so state doesn't bleed.

    reset_mock() alone does NOT clear side_effect or return_value by default —
    pass those flags explicitly so a side_effect set in one test can't leak
    into the next.
    Also clear api.installation_status so install-status/cancel tests start
    with a clean slate regardless of test order.
    """
    for m in (_mock_db, _mock_loader, _mock_service_mgr, _mock_backup_mgr,
              _mock_resolver, _mock_port_mgr, _mock_health_mon, _mock_auth,
              _mock_firewall, _mock_metrics):
        m.reset_mock(return_value=True, side_effect=True)
    _mock_metrics.docker_client = MagicMock()
    _mock_metrics.docker_client.containers.list.return_value = []
    # Explicitly clear child mocks that tests set side_effect on directly —
    # reset_mock() does not cascade side_effect/return_value to child attributes
    _mock_loader.load.side_effect = None
    _mock_loader.load.return_value = MagicMock()
    _mock_service_mgr.start.side_effect = None
    _mock_service_mgr.stop.side_effect = None
    _mock_service_mgr.restart.side_effect = None
    _mock_db.list_services.side_effect = None
    # These return values must be JSON-serializable — MagicMock (the default
    # after reset) cannot be serialized by Flask's jsonify and causes routes
    # to fall into their except handler, returning unexpected 404/500 responses
    _mock_resolver.get_dependencies.return_value = []
    _mock_resolver.get_optional_dependencies.return_value = []
    _mock_port_mgr.get_all_ports.return_value = []
    _mock_backup_mgr.list_backups.return_value = []
    _mock_db.is_installed.return_value = False
    # Clear module-level installation tracking dict in api.py
    _api_module.installation_status.clear()


# ── helpers ───────────────────────────────────────────────────────────────────

VALID_TOKEN = 'valid-token-abc'
ADMIN_TOKEN = 'admin-token-xyz'
VALID_USER  = {'username': 'testuser', 'is_admin': False, 'id': 1}
ADMIN_USER  = {'username': 'admin',    'is_admin': True,  'id': 2}


def auth_header(token=VALID_TOKEN):
    return {'Authorization': f'Bearer {token}'}


def setup_auth(token=VALID_TOKEN, user=None):
    _mock_auth.validate_token.side_effect = (
        lambda t: (user or VALID_USER) if t == token else None
    )


def setup_admin_auth():
    def _v(t):
        if t == ADMIN_TOKEN:
            return ADMIN_USER
        if t == VALID_TOKEN:
            return VALID_USER
        return None
    _mock_auth.validate_token.side_effect = _v


def jpost(client, url, data=None, token=VALID_TOKEN):
    return client.post(
        url,
        data=json.dumps(data or {}),
        content_type='application/json',
        headers=auth_header(token),
    )


def jget(client, url, token=VALID_TOKEN):
    return client.get(url, headers=auth_header(token))


def _fake_manifest(sid):
    m = MagicMock()
    m.name        = sid.title()
    m.version     = '1.0.0'
    m.category    = 'infrastructure'
    m.description = f'{sid} description'
    m.ports       = {'http': 80}
    m.volumes     = []
    m.dependencies = {'services': []}
    m.data        = {'metadata': {}}
    return m


# ── tests: auth ───────────────────────────────────────────────────────────────

class TestAuth:

    def test_login_success(self, client):
        _mock_auth.login.return_value = {'token': VALID_TOKEN, 'username': 'testuser'}
        r = client.post('/api/auth/login',
                        data=json.dumps({'username': 'testuser', 'password': 'secret'}),
                        content_type='application/json')
        assert r.status_code == 200
        assert r.get_json()['token'] == VALID_TOKEN

    def test_login_missing_credentials(self, client):
        r = client.post('/api/auth/login',
                        data=json.dumps({'username': 'testuser'}),
                        content_type='application/json')
        assert r.status_code == 400

    def test_login_wrong_password(self, client):
        from core.auth import AuthError
        _mock_auth.login.side_effect = AuthError('Invalid credentials')
        r = client.post('/api/auth/login',
                        data=json.dumps({'username': 'u', 'password': 'bad'}),
                        content_type='application/json')
        assert r.status_code == 401

    def test_logout_success(self, client):
        setup_auth()
        r = client.post('/api/auth/logout', headers=auth_header())
        assert r.status_code == 200
        _mock_auth.logout.assert_called_once_with(VALID_TOKEN)

    def test_logout_no_token(self, client):
        assert client.post('/api/auth/logout').status_code == 401

    def test_validate_valid_token(self, client):
        setup_auth()
        r = client.get('/api/auth/validate', headers=auth_header())
        assert r.status_code == 200
        assert r.get_json()['user']['username'] == 'testuser'

    def test_validate_invalid_token(self, client):
        _mock_auth.validate_token.return_value = None
        assert client.get('/api/auth/validate',
                          headers=auth_header('bad')).status_code == 401

    def test_validate_no_token(self, client):
        assert client.get('/api/auth/validate').status_code == 401

    def test_register_non_admin_rejected(self, client):
        setup_admin_auth()
        r = jpost(client, '/api/auth/register',
                  {'username': 'new', 'password': 'pass'}, token=VALID_TOKEN)
        assert r.status_code == 403

    def test_register_as_admin(self, client):
        setup_admin_auth()
        _mock_auth.register_user.return_value = {'username': 'new'}
        r = jpost(client, '/api/auth/register',
                  {'username': 'new', 'password': 'pass'}, token=ADMIN_TOKEN)
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_register_missing_password(self, client):
        setup_admin_auth()
        r = jpost(client, '/api/auth/register',
                  {'username': 'new'}, token=ADMIN_TOKEN)
        assert r.status_code == 400


# ── tests: auth guards ────────────────────────────────────────────────────────

class TestAuthGuards:

    def test_no_token_returns_401(self, client):
        r = client.get('/api/services')
        assert r.status_code == 401
        assert 'error' in r.get_json()

    def test_invalid_token_returns_401(self, client):
        _mock_auth.validate_token.return_value = None
        assert client.get('/api/services',
                          headers=auth_header('garbage')).status_code == 401

    def test_health_requires_auth(self, client):
        assert client.get('/api/health').status_code == 401

    def test_ports_requires_auth(self, client):
        assert client.get('/api/ports').status_code == 401


# ── tests: services ───────────────────────────────────────────────────────────

class TestServices:

    def test_list_services(self, client):
        setup_auth()
        _mock_db.list_services.return_value = []
        _mock_loader.list_available.return_value = ['nginx', 'pihole']
        _mock_loader.load.side_effect = _fake_manifest
        _mock_firewall.get_service_tier.return_value = 0
        r = jget(client, '/api/services')
        assert r.status_code == 200
        assert len(r.get_json()['services']) == 2

    def test_get_service_found(self, client):
        setup_auth()
        _mock_loader.load.return_value = _fake_manifest('nginx')
        _mock_db.is_installed.return_value = True
        _mock_resolver.get_dependencies.return_value = []
        _mock_resolver.get_optional_dependencies.return_value = []
        _mock_health_mon._get_last_result.return_value = None
        r = jget(client, '/api/services/nginx')
        assert r.status_code == 200
        assert r.get_json()['id'] == 'nginx'
        assert r.get_json()['installed'] is True

    def test_get_service_not_found(self, client):
        setup_auth()
        _mock_loader.load.side_effect = Exception('Service not found: nonexistent')
        assert jget(client, '/api/services/nonexistent').status_code == 404

    def test_install_returns_202(self, client):
        setup_auth()
        _mock_loader.load.return_value = _fake_manifest('nginx')
        r = jpost(client, '/api/services/nginx/install')
        assert r.status_code == 202
        assert r.get_json()['success'] is True

    def test_uninstall_service(self, client):
        setup_auth()
        r = jpost(client, '/api/services/nginx/uninstall')
        assert r.status_code == 200
        # Uninstall uses Docker directly, not service_mgr
        _mock_db.remove_service.assert_called_once_with('nginx')

    def test_start_service(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/start').status_code == 200
        _mock_service_mgr.start.assert_called_once_with('nginx')

    def test_stop_service(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/stop').status_code == 200
        _mock_service_mgr.stop.assert_called_once_with('nginx')

    def test_restart_service(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/restart').status_code == 200
        _mock_service_mgr.restart.assert_called_once_with('nginx')

    def test_start_error_returns_500(self, client):
        setup_auth()
        _mock_service_mgr.start.side_effect = Exception('Container not found')
        r = jpost(client, '/api/services/nginx/start')
        assert r.status_code == 500
        assert 'error' in r.get_json()

    def test_get_logs(self, client):
        setup_auth()
        _mock_service_mgr.get_logs.return_value = ['line 1', 'line 2']
        r = jget(client, '/api/services/nginx/logs')
        assert r.status_code == 200
        assert len(r.get_json()['logs']) == 2

    def test_install_status_not_started(self, client):
        setup_auth()
        r = jget(client, '/api/services/nginx/install-status')
        assert r.status_code == 200
        assert r.get_json()['status'] == 'not_started'

    def test_cancel_install_not_running(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/install-cancel').status_code == 404


# ── tests: health ─────────────────────────────────────────────────────────────

class TestHealth:

    def test_get_all_health(self, client):
        setup_auth()
        _mock_health_mon.get_status.return_value = {
            'nginx': {'status': 'healthy'}
        }
        r = jget(client, '/api/health')
        assert r.status_code == 200
        assert 'nginx' in r.get_json()['health']

    def test_get_service_health(self, client):
        setup_auth()
        _mock_health_mon._get_last_result.return_value = {'current_status': 'healthy'}
        r = jget(client, '/api/health/nginx')
        assert r.status_code == 200
        assert r.get_json()['health']['current_status'] == 'healthy'

    def test_get_service_health_not_found(self, client):
        setup_auth()
        _mock_health_mon._get_last_result.return_value = None
        assert jget(client, '/api/health/unknown').status_code == 404

    def test_get_health_history(self, client):
        setup_auth()
        _mock_health_mon.get_history.return_value = [
            {'status': 'healthy', 'checked_at': '2026-03-05T10:00:00'}
        ]
        r = jget(client, '/api/health/nginx/history')
        assert r.status_code == 200
        assert len(r.get_json()['history']) == 1


# ── tests: system ─────────────────────────────────────────────────────────────

class TestSystem:

    def test_system_stats(self, client):
        setup_auth()
        _mock_db.list_services.return_value = [{'service_id': 'nginx'}]
        _mock_loader.list_available.return_value = ['nginx', 'pihole', 'jellyfin']
        r = jget(client, '/api/system/stats')
        assert r.status_code == 200
        assert r.get_json()['services']['installed'] == 1
        assert r.get_json()['services']['available'] == 3

    def test_get_ports(self, client):
        setup_auth()
        _mock_port_mgr.get_all_ports.return_value = [{'port': 80}]
        r = jget(client, '/api/ports')
        assert r.status_code == 200
        assert 'ports' in r.get_json()

    def test_get_backups(self, client):
        setup_auth()
        _mock_backup_mgr.list_backups.return_value = [{'backup_id': 'bk-001'}]
        r = jget(client, '/api/backups/nginx')
        assert r.status_code == 200
        assert len(r.get_json()['backups']) == 1

    def test_create_backup(self, client):
        setup_auth()
        _mock_backup_mgr.create_backup.return_value = '/path/to/bk'
        r = jpost(client, '/api/backups/nginx/create', {'note': 'pre-update'})
        assert r.status_code == 200
        assert r.get_json()['success'] is True


# ── tests: tiers ──────────────────────────────────────────────────────────────

class TestTiers:

    def test_get_all_tiers(self, client):
        setup_auth()
        _mock_firewall.get_all_tiers.return_value = {0: {'name': 'Internal'}}
        r = jget(client, '/api/tiers')
        assert r.status_code == 200
        assert 'tiers' in r.get_json()

    def test_get_service_tier(self, client):
        setup_auth()
        _mock_firewall.get_service_tier.return_value = 0
        _mock_firewall.get_tier_info.return_value = {'name': 'Internal Only'}
        r = jget(client, '/api/services/nginx/tier')
        assert r.status_code == 200
        assert r.get_json()['current_tier'] == 0

    def test_set_service_tier(self, client):
        setup_auth()
        _mock_firewall.get_tier_info.return_value = {'name': 'LAN'}
        r = jpost(client, '/api/services/nginx/tier', {'tier': 1})
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_set_tier_missing_field(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/tier',
                     {'reason': 'oops'}).status_code == 400

    def test_tier_3_requires_confirmation(self, client):
        setup_auth()
        r = jpost(client, '/api/services/nginx/tier', {'tier': 3})
        assert r.status_code == 400
        assert r.get_json().get('requires_confirmation') is True

    def test_tier_3_with_confirmation(self, client):
        setup_auth()
        _mock_firewall.get_tier_info.return_value = {'name': 'Public'}
        r = jpost(client, '/api/services/nginx/tier',
                  {'tier': 3, 'confirmation': True})
        assert r.status_code == 200

    def test_reset_all_non_admin_forbidden(self, client):
        setup_admin_auth()
        r = jpost(client, '/api/tiers/reset-all',
                  {'confirmation': True}, token=VALID_TOKEN)
        assert r.status_code == 403

    def test_reset_all_requires_confirmation(self, client):
        setup_admin_auth()
        r = jpost(client, '/api/tiers/reset-all',
                  {'confirmation': False}, token=ADMIN_TOKEN)
        assert r.status_code == 400

    def test_reset_all_success(self, client):
        setup_admin_auth()
        _mock_firewall.reset_all_to_tier_0.return_value = 5
        r = jpost(client, '/api/tiers/reset-all',
                  {'confirmation': True}, token=ADMIN_TOKEN)
        assert r.status_code == 200
        assert r.get_json()['count'] == 5


# ── tests: metrics ────────────────────────────────────────────────────────────

class TestMetrics:

    def test_system_metrics_latest(self, client):
        setup_auth()
        # Mock the store.latest method
        mock_store = MagicMock()
        mock_store.latest.return_value = {'value': 12.5}
        _mock_metrics.store = mock_store
        r = jget(client, '/api/metrics/system/latest')
        assert r.status_code == 200
        assert 'metrics' in r.get_json()

    def test_prometheus_no_auth_required(self, client):
        _mock_metrics.export_prometheus.return_value = '# metrics\n'
        r = client.get('/api/metrics/prometheus')
        assert r.status_code == 200
        assert 'text/plain' in r.content_type

    def test_metrics_collect_non_admin_forbidden(self, client):
        setup_admin_auth()
        assert jpost(client, '/api/metrics/collect',
                     token=VALID_TOKEN).status_code == 403

    def test_metrics_collect_as_admin(self, client):
        setup_admin_auth()
        _mock_metrics.collect_once.return_value = 5
        r = jpost(client, '/api/metrics/collect', token=ADMIN_TOKEN)
        assert r.status_code == 200
        assert r.get_json()['success'] is True


# ── tests: service-level backups ──────────────────────────────────────────────

class TestServiceBackups:

    def test_get_service_backups(self, client):
        setup_auth()
        _mock_backup_mgr.list_backups.return_value = [{'backup_id': 'bk-001'}]
        r = jget(client, '/api/services/nginx/backups')
        assert r.status_code == 200
        assert r.get_json()['count'] == 1

    def test_create_service_backup(self, client):
        setup_auth()
        _mock_backup_mgr.create_backup.return_value = 'bk-003'
        r = jpost(client, '/api/services/nginx/backup', {'note': 'pre-upgrade'})
        assert r.status_code == 200
        assert r.get_json()['backup_id'] == 'bk-003'

    def test_restore_service_backup(self, client):
        setup_auth()
        _mock_backup_mgr.restore_backup.return_value = True
        r = jpost(client, '/api/services/nginx/restore', {'backup_id': 'bk-001'})
        assert r.status_code == 200
        assert r.get_json()['success'] is True

    def test_restore_missing_backup_id(self, client):
        setup_auth()
        assert jpost(client, '/api/services/nginx/restore', {}).status_code == 400


# ── tests: error response shape ───────────────────────────────────────────────

class TestErrorResponses:

    def test_401_is_json(self, client):
        r = client.get('/api/services')
        assert r.content_type == 'application/json'
        assert 'error' in r.get_json()

    def test_403_is_json(self, client):
        setup_admin_auth()
        r = jpost(client, '/api/tiers/reset-all',
                  {'confirmation': True}, token=VALID_TOKEN)
        assert r.content_type == 'application/json'
        assert 'error' in r.get_json()

    def test_500_is_json(self, client):
        setup_auth()
        _mock_db.list_services.side_effect = Exception('DB exploded')
        r = jget(client, '/api/system/stats')
        assert r.status_code == 500
        assert r.content_type == 'application/json'
        assert 'error' in r.get_json()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])