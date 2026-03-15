#!/usr/bin/env python3
"""
Tests for resource alerting — check_resource_alerts() in ResourceManager
and the cpu_warning/memory_warning/disk_warning events in NotificationService.

All Docker and DB calls are mocked.
"""

import pytest
import sys
from pathlib import Path
from unittest.mock import MagicMock, call

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_rm(limits=None):
    """
    Return a ResourceManager with mocked DB and Docker.
    Uses __new__ to bypass __init__ entirely so no real Docker connection
    or DB schema creation happens — patches on the module namespace are
    not needed and the instance state is fully controlled.
    """
    from core.resource_manager import ResourceManager
    rm = ResourceManager.__new__(ResourceManager)
    rm.docker_client = MagicMock()
    rm.db = MagicMock()
    rm.get_service_limits = MagicMock(return_value=limits or {
        'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0
    })
    return rm


def _notifier():
    return MagicMock()


def _stats(cpu=0.0, memory_mb=0.0, disk_mb=0.0):
    return {'cpu_percent': cpu, 'memory_mb': memory_mb, 'disk_mb': disk_mb}


# ─────────────────────────────────────────────────────────────────────────────
# CPU alerts
# ─────────────────────────────────────────────────────────────────────────────

class TestCpuAlerts:

    def test_cpu_below_threshold_no_alert(self):
        rm = _make_rm()
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(cpu=50.0))
        assert 'cpu_warning' not in fired
        n.notify.assert_not_called()

    def test_cpu_at_threshold_no_alert(self):
        """Exactly at threshold should NOT fire (must be strictly above)."""
        rm = _make_rm()
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(cpu=85.0),
                                         cpu_threshold=85.0)
        assert 'cpu_warning' not in fired

    def test_cpu_above_threshold_fires(self):
        rm = _make_rm()
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(cpu=91.0))
        assert 'cpu_warning' in fired
        n.notify.assert_called_once()
        call_kwargs = n.notify.call_args
        assert call_kwargs[0][0] == 'cpu_warning'
        assert call_kwargs[1]['service_id'] == 'nginx'

    def test_cpu_detail_contains_percent(self):
        rm = _make_rm()
        n  = _notifier()
        rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                 stats=_stats(cpu=92.5))
        detail = n.notify.call_args[1]['detail']
        assert '92.5' in detail

    def test_custom_cpu_threshold(self):
        rm = _make_rm()
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(cpu=70.0),
                                         cpu_threshold=60.0)
        assert 'cpu_warning' in fired


# ─────────────────────────────────────────────────────────────────────────────
# Memory alerts — with configured limit
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryAlertsWithLimit:

    def test_memory_below_threshold_no_alert(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 0})
        n  = _notifier()
        # 800 MB / 1024 MB = 78% — below 90% default
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(memory_mb=800))
        assert 'memory_warning' not in fired

    def test_memory_above_threshold_fires(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 0})
        n  = _notifier()
        # 950 MB / 1024 MB ≈ 92.8% — above 90% default
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(memory_mb=950))
        assert 'memory_warning' in fired

    def test_memory_detail_shows_usage_and_limit(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 0})
        n  = _notifier()
        rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                 stats=_stats(memory_mb=950))
        detail = n.notify.call_args[1]['detail']
        assert '950' in detail
        assert '1024' in detail

    def test_custom_memory_threshold(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 0})
        n  = _notifier()
        # 600 MB / 1024 MB = 58.6% — above custom 50% threshold
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(memory_mb=600),
                                         memory_threshold=50.0)
        assert 'memory_warning' in fired


# ─────────────────────────────────────────────────────────────────────────────
# Memory alerts — no configured limit (absolute fallback)
# ─────────────────────────────────────────────────────────────────────────────

class TestMemoryAlertsNoLimit:

    def test_below_absolute_default_no_alert(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0})
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(memory_mb=512))
        assert 'memory_warning' not in fired

    def test_above_absolute_default_fires(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0})
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(memory_mb=1200))
        assert 'memory_warning' in fired

    def test_detail_mentions_no_limit(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0})
        n  = _notifier()
        rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                 stats=_stats(memory_mb=1200))
        detail = n.notify.call_args[1]['detail']
        assert 'no limit' in detail.lower()


# ─────────────────────────────────────────────────────────────────────────────
# Disk alerts
# ─────────────────────────────────────────────────────────────────────────────

class TestDiskAlerts:

    def test_no_disk_quota_no_alert(self):
        """disk_mb = 0 means no quota configured — never alert."""
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0})
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(disk_mb=99999))
        assert 'disk_warning' not in fired

    def test_disk_within_quota_no_alert(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 5120})
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(disk_mb=4000))
        assert 'disk_warning' not in fired

    def test_disk_over_quota_fires(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 5120})
        n  = _notifier()
        fired = rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                         stats=_stats(disk_mb=6000))
        assert 'disk_warning' in fired

    def test_disk_detail_shows_usage_and_quota(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 5120})
        n  = _notifier()
        rm.check_resource_alerts('nginx', 'pso-nginx', n,
                                 stats=_stats(disk_mb=6000))
        detail = n.notify.call_args[1]['detail']
        assert '6000' in detail
        assert '5120' in detail


# ─────────────────────────────────────────────────────────────────────────────
# Multiple alerts at once
# ─────────────────────────────────────────────────────────────────────────────

class TestMultipleAlerts:

    def test_all_three_can_fire_together(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 5120})
        n  = _notifier()
        fired = rm.check_resource_alerts(
            'nginx', 'pso-nginx', n,
            stats={'cpu_percent': 95.0, 'memory_mb': 1000, 'disk_mb': 6000},
        )
        assert 'cpu_warning'    in fired
        assert 'memory_warning' in fired
        assert 'disk_warning'   in fired
        assert n.notify.call_count == 3

    def test_returns_empty_when_all_fine(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 5120})
        n  = _notifier()
        fired = rm.check_resource_alerts(
            'nginx', 'pso-nginx', n,
            stats={'cpu_percent': 20.0, 'memory_mb': 200, 'disk_mb': 1000},
        )
        assert fired == []
        n.notify.assert_not_called()

    def test_service_id_passed_to_all_notifications(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 1024, 'disk_mb': 5120})
        n  = _notifier()
        rm.check_resource_alerts(
            'jellyfin', 'pso-jellyfin', n,
            stats={'cpu_percent': 95.0, 'memory_mb': 1000, 'disk_mb': 6000},
        )
        for c in n.notify.call_args_list:
            assert c[1]['service_id'] == 'jellyfin'


# ─────────────────────────────────────────────────────────────────────────────
# record_usage integration
# ─────────────────────────────────────────────────────────────────────────────

class TestRecordUsageIntegration:

    def test_record_usage_without_notifier_no_alerts(self):
        rm = _make_rm()
        rm.get_container_stats = MagicMock(return_value=_stats(cpu=99.0))
        rm._conn = MagicMock()
        rm._conn.return_value.__enter__ = MagicMock(return_value=MagicMock())
        rm._conn.return_value.__exit__  = MagicMock(return_value=False)
        # Should not raise and should not call any notifier
        rm.record_usage('nginx', 'pso-nginx')  # no notifier passed

    def test_record_usage_with_notifier_fires_alert(self):
        rm = _make_rm(limits={'cpu_cores': 0, 'memory_mb': 0, 'disk_mb': 0})
        rm.get_container_stats = MagicMock(return_value=_stats(cpu=92.0))
        rm.check_resource_alerts = MagicMock(return_value=['cpu_warning'])
        conn_mock = MagicMock()
        rm._conn = MagicMock()
        rm._conn.return_value.__enter__ = MagicMock(return_value=conn_mock)
        rm._conn.return_value.__exit__  = MagicMock(return_value=False)

        n = _notifier()
        rm.record_usage('nginx', 'pso-nginx', notifier=n)

        rm.check_resource_alerts.assert_called_once_with(
            'nginx', 'pso-nginx', n, stats=_stats(cpu=92.0)
        )


# ─────────────────────────────────────────────────────────────────────────────
# Notification events catalogue
# ─────────────────────────────────────────────────────────────────────────────

class TestNotificationEvents:

    def test_cpu_warning_in_events(self):
        from core.notifications import EVENTS
        assert 'cpu_warning' in EVENTS

    def test_memory_warning_in_events(self):
        from core.notifications import EVENTS
        assert 'memory_warning' in EVENTS

    def test_disk_warning_in_events(self):
        from core.notifications import EVENTS
        assert 'disk_warning' in EVENTS

    def test_all_three_in_default_enabled(self):
        from core.notifications import DEFAULT_ENABLED_EVENTS
        assert 'cpu_warning'    in DEFAULT_ENABLED_EVENTS
        assert 'memory_warning' in DEFAULT_ENABLED_EVENTS
        assert 'disk_warning'   in DEFAULT_ENABLED_EVENTS


if __name__ == '__main__':
    pytest.main([__file__, '-v'])