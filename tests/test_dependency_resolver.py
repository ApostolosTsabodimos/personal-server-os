#!/usr/bin/env python3
"""
Tests for core/dependency_resolver.py

Covers: dependency ordering, circular detection, conflict checking,
        missing service handling, already-installed filtering.

All manifest loading and database calls are mocked so tests run
without a real services/ directory or database.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

def _make_manifest(service_id, deps=None, conflicts=None, optional=None):
    """Build a fake Manifest-like object."""
    m = MagicMock()
    m.id   = service_id
    m.name = service_id.title()
    m.dependencies = {
        'services':  deps     or [],
        'conflicts': conflicts or [],
        'optional':  optional or [],
    }
    return m


@pytest.fixture
def resolver():
    """
    Return a DependencyResolver with ManifestLoader and Database mocked.
    Tests configure loader.load and db behaviour per-test.
    """
    with patch('core.dependency_resolver.ManifestLoader') as MockLoader, \
         patch('core.dependency_resolver.Database')       as MockDB:

        mock_loader = MockLoader.return_value
        mock_db     = MockDB.return_value
        mock_db.get_installed_services.return_value = []

        from core.dependency_resolver import DependencyResolver
        r = DependencyResolver()
        r._mock_loader = mock_loader
        r._mock_db     = mock_db
        yield r


def _setup_catalog(resolver, catalog: dict):
    """
    Configure the mock loader to serve manifests from a dict.
    catalog = { 'nginx': ['dep1', 'dep2'], 'dep1': [] }
    """
    from core.manifest import ManifestError

    def _load(sid):
        if sid not in catalog:
            raise ManifestError(f"Service not found: {sid}")
        return _make_manifest(sid, deps=catalog[sid])

    resolver._mock_loader.load.side_effect = _load
    resolver.loader = resolver._mock_loader


def _set_installed(resolver, installed: list):
    resolver._mock_db.get_installed_services.return_value = [
        (sid,) for sid in installed
    ]


# ─────────────────────────────────────────────────────────────────────────────
# resolve_order — ordering
# ─────────────────────────────────────────────────────────────────────────────

class TestResolveOrder:

    def test_no_dependencies(self, resolver):
        _setup_catalog(resolver, {'nginx': []})
        order = resolver.resolve_order('nginx')
        assert order == ['nginx']

    def test_single_dependency_comes_first(self, resolver):
        _setup_catalog(resolver, {
            'nextcloud': ['nginx'],
            'nginx': [],
        })
        order = resolver.resolve_order('nextcloud')
        assert order.index('nginx') < order.index('nextcloud')
        assert set(order) == {'nginx', 'nextcloud'}

    def test_chain_a_requires_b_requires_c(self, resolver):
        _setup_catalog(resolver, {
            'a': ['b'],
            'b': ['c'],
            'c': [],
        })
        order = resolver.resolve_order('a')
        assert order == ['c', 'b', 'a']

    def test_diamond_dependency_no_duplicates(self, resolver):
        """A → B, A → C, both B and C → D. D must appear exactly once."""
        _setup_catalog(resolver, {
            'a': ['b', 'c'],
            'b': ['d'],
            'c': ['d'],
            'd': [],
        })
        order = resolver.resolve_order('a')
        assert order.count('d') == 1
        assert order.index('d') < order.index('b')
        assert order.index('d') < order.index('c')
        assert order[-1] == 'a'

    def test_multiple_independent_deps(self, resolver):
        _setup_catalog(resolver, {
            'app': ['redis', 'postgres'],
            'redis': [],
            'postgres': [],
        })
        order = resolver.resolve_order('app')
        assert set(order) == {'app', 'redis', 'postgres'}
        assert order[-1] == 'app'
        assert order.index('redis')    < order.index('app')
        assert order.index('postgres') < order.index('app')


# ─────────────────────────────────────────────────────────────────────────────
# resolve_order — circular detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCircularDetection:

    def test_self_dependency(self, resolver):
        _setup_catalog(resolver, {'a': ['a']})
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError, match="Circular dependency"):
            resolver.resolve_order('a')

    def test_two_node_cycle(self, resolver):
        _setup_catalog(resolver, {'a': ['b'], 'b': ['a']})
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError, match="Circular dependency"):
            resolver.resolve_order('a')

    def test_three_node_cycle(self, resolver):
        _setup_catalog(resolver, {
            'a': ['b'],
            'b': ['c'],
            'c': ['a'],
        })
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError, match="Circular dependency"):
            resolver.resolve_order('a')

    def test_error_message_shows_full_cycle(self, resolver):
        _setup_catalog(resolver, {'x': ['y'], 'y': ['x']})
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError) as exc_info:
            resolver.resolve_order('x')
        assert 'x' in str(exc_info.value)
        assert 'y' in str(exc_info.value)

    def test_valid_graph_with_shared_node_does_not_raise(self, resolver):
        """Shared dep (not a cycle) must not trigger circular detection."""
        _setup_catalog(resolver, {
            'a': ['b', 'c'],
            'b': ['d'],
            'c': ['d'],
            'd': [],
        })
        # Should not raise
        order = resolver.resolve_order('a')
        assert 'a' in order


# ─────────────────────────────────────────────────────────────────────────────
# resolve_order — missing service
# ─────────────────────────────────────────────────────────────────────────────

class TestMissingService:

    def test_missing_root_raises(self, resolver):
        _setup_catalog(resolver, {})
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError, match="Service not found"):
            resolver.resolve_order('nonexistent')

    def test_missing_dependency_raises(self, resolver):
        _setup_catalog(resolver, {'app': ['missing-dep']})
        from core.dependency_resolver import DependencyError
        with pytest.raises(DependencyError, match="Service not found"):
            resolver.resolve_order('app')


# ─────────────────────────────────────────────────────────────────────────────
# get_installation_plan — already-installed filtering
# ─────────────────────────────────────────────────────────────────────────────

class TestInstallationPlan:

    def test_nothing_installed(self, resolver):
        _setup_catalog(resolver, {
            'app': ['db'],
            'db': [],
        })
        to_install, already = resolver.get_installation_plan('app')
        assert set(to_install) == {'app', 'db'}
        assert already == []

    def test_dependency_already_installed(self, resolver):
        _setup_catalog(resolver, {
            'app': ['db'],
            'db': [],
        })
        _set_installed(resolver, ['db'])
        to_install, already = resolver.get_installation_plan('app')
        assert to_install == ['app']
        assert already == ['db']

    def test_all_already_installed(self, resolver):
        _setup_catalog(resolver, {
            'app': ['db'],
            'db': [],
        })
        _set_installed(resolver, ['app', 'db'])
        to_install, already = resolver.get_installation_plan('app')
        assert to_install == []
        assert set(already) == {'app', 'db'}

    def test_ordering_preserved_after_filtering(self, resolver):
        _setup_catalog(resolver, {
            'app': ['b', 'c'],
            'b': ['d'],
            'c': ['d'],
            'd': [],
        })
        _set_installed(resolver, ['d'])
        to_install, already = resolver.get_installation_plan('app')
        # d is already installed, b and c should still appear before app
        assert 'app' in to_install
        assert to_install.index('b') < to_install.index('app')
        assert to_install.index('c') < to_install.index('app')
        assert 'd' in already


# ─────────────────────────────────────────────────────────────────────────────
# Conflict checking
# ─────────────────────────────────────────────────────────────────────────────

class TestConflicts:

    def _setup_conflict(self, resolver, service_id, conflicts):
        from core.manifest import ManifestError

        def _load(sid):
            if sid == service_id:
                return _make_manifest(sid, conflicts=conflicts)
            raise ManifestError(f"Service not found: {sid}")

        resolver._mock_loader.load.side_effect = _load
        resolver.loader = resolver._mock_loader

    def test_no_conflicts_when_nothing_installed(self, resolver):
        self._setup_conflict(resolver, 'apache', conflicts=['nginx'])
        _set_installed(resolver, [])
        assert resolver.check_conflicts('apache') == []

    def test_conflict_detected_when_installed(self, resolver):
        self._setup_conflict(resolver, 'apache', conflicts=['nginx'])
        _set_installed(resolver, ['nginx'])
        assert resolver.check_conflicts('apache') == ['nginx']

    def test_multiple_conflicts(self, resolver):
        self._setup_conflict(resolver, 'apache', conflicts=['nginx', 'caddy'])
        _set_installed(resolver, ['nginx', 'caddy'])
        assert set(resolver.check_conflicts('apache')) == {'nginx', 'caddy'}

    def test_only_installed_conflicts_reported(self, resolver):
        self._setup_conflict(resolver, 'apache', conflicts=['nginx', 'caddy'])
        _set_installed(resolver, ['nginx'])   # caddy not installed
        assert resolver.check_conflicts('apache') == ['nginx']


# ─────────────────────────────────────────────────────────────────────────────
# get_dependencies / get_optional_dependencies helpers
# ─────────────────────────────────────────────────────────────────────────────

class TestHelpers:

    def test_get_dependencies_returns_list(self, resolver):
        from core.manifest import ManifestError

        def _load(sid):
            if sid == 'app':
                return _make_manifest('app', deps=['db', 'redis'])
            raise ManifestError()

        resolver._mock_loader.load.side_effect = _load
        resolver.loader = resolver._mock_loader
        assert resolver.get_dependencies('app') == ['db', 'redis']

    def test_get_dependencies_returns_empty_on_error(self, resolver):
        from core.manifest import ManifestError
        resolver._mock_loader.load.side_effect = ManifestError("not found")
        resolver.loader = resolver._mock_loader
        assert resolver.get_dependencies('missing') == []

    def test_get_optional_dependencies(self, resolver):
        from core.manifest import ManifestError

        def _load(sid):
            if sid == 'app':
                return _make_manifest('app', optional=['grafana'])
            raise ManifestError()

        resolver._mock_loader.load.side_effect = _load
        resolver.loader = resolver._mock_loader
        assert resolver.get_optional_dependencies('app') == ['grafana']


if __name__ == '__main__':
    pytest.main([__file__, '-v'])