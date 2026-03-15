#!/usr/bin/env python3
"""
Tests for the PSO update pipeline:
  core/update_security.py   — checksum, TLS, signature, combined verify
  core/update_monitor.py    — check_service version detection logic
  core/update_processor.py  — full apply() pipeline with rollback
  core/update_manager.py    — ServiceUpdateManager orchestration

Docker, DB, and network calls are mocked throughout.
Run with: python -m pytest tests/test_update_pipeline.py -v
"""

import os
import sys
import json
import hashlib
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch, call
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
# update_security — verify_checksum
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyChecksum:

    def _write_file(self, content: bytes) -> Path:
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def _sha256(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    def test_matching_checksum_returns_true(self):
        from core.update_security import verify_checksum
        data = b"PSO test payload"
        p = self._write_file(data)
        try:
            assert verify_checksum(p, self._sha256(data)) is True
        finally:
            p.unlink()

    def test_mismatched_checksum_returns_false(self):
        from core.update_security import verify_checksum
        p = self._write_file(b"real content")
        try:
            assert verify_checksum(p, "a" * 64) is False
        finally:
            p.unlink()

    def test_sha256_prefix_is_stripped(self):
        from core.update_security import verify_checksum
        data = b"prefixed"
        p = self._write_file(data)
        try:
            assert verify_checksum(p, f"sha256:{self._sha256(data)}") is True
        finally:
            p.unlink()

    def test_missing_file_raises(self):
        from core.update_security import verify_checksum
        with pytest.raises(FileNotFoundError):
            verify_checksum("/nonexistent/file.bin", "a" * 64)

    def test_bad_digest_length_raises(self):
        from core.update_security import verify_checksum
        p = self._write_file(b"x")
        try:
            with pytest.raises(ValueError):
                verify_checksum(p, "tooshort")
        finally:
            p.unlink()

    def test_case_insensitive(self):
        from core.update_security import verify_checksum
        data = b"case test"
        p = self._write_file(data)
        digest = self._sha256(data).upper()
        try:
            assert verify_checksum(p, digest) is True
        finally:
            p.unlink()


class TestComputeChecksum:

    def test_compute_matches_verify(self):
        from core.update_security import compute_checksum, verify_checksum
        data = b"compute test"
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(data)
            p = Path(f.name)
        try:
            digest = compute_checksum(p)
            assert len(digest) == 64
            assert verify_checksum(p, digest) is True
        finally:
            p.unlink()

    def test_missing_file_raises(self):
        from core.update_security import compute_checksum
        with pytest.raises(FileNotFoundError):
            compute_checksum("/no/such/file")


# ─────────────────────────────────────────────────────────────────────────────
# update_security — verify_tls
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyTls:

    def test_http_url_rejected(self):
        from core.update_security import verify_tls
        assert verify_tls("http://example.com") is False

    def test_https_valid_returns_true(self):
        from core.update_security import verify_tls
        import urllib.request
        mock_resp = MagicMock()
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_resp.status = 200
        with patch('urllib.request.urlopen', return_value=mock_resp):
            assert verify_tls("https://example.com") is True

    def test_ssl_error_returns_false(self):
        from core.update_security import verify_tls
        import ssl
        with patch('urllib.request.urlopen', side_effect=ssl.SSLError("bad cert")):
            assert verify_tls("https://bad-cert.example.com") is False


# ─────────────────────────────────────────────────────────────────────────────
# update_security — verify_update (combined)
# ─────────────────────────────────────────────────────────────────────────────

class TestVerifyUpdate:

    def _tmp_file(self, content=b"data"):
        f = tempfile.NamedTemporaryFile(delete=False)
        f.write(content)
        f.close()
        return Path(f.name)

    def test_all_skipped_when_no_args(self):
        from core.update_security import verify_update
        p = self._tmp_file()
        try:
            result = verify_update(p)
            # No checks were executed — all None (skipped)
            assert all(v is None for v in result.checks.values())
            # No executed checks → passed is False (nothing verified)
            assert result.passed is False
        finally:
            p.unlink()

    def test_checksum_pass(self):
        from core.update_security import verify_update
        data = b"checksum test"
        digest = hashlib.sha256(data).hexdigest()
        p = self._tmp_file(data)
        try:
            result = verify_update(p, expected_sha256=digest)
            assert result.checks["SHA-256 checksum"] is True
            assert result.passed is True
        finally:
            p.unlink()

    def test_checksum_fail(self):
        from core.update_security import verify_update
        p = self._tmp_file(b"wrong content")
        try:
            result = verify_update(p, expected_sha256="a" * 64)
            assert result.checks["SHA-256 checksum"] is False
            assert result.passed is False
            assert result.errors
        finally:
            p.unlink()

    def test_tls_included_when_url_provided(self):
        from core.update_security import verify_update
        import ssl
        p = self._tmp_file()
        try:
            with patch('core.update_security.verify_tls', return_value=True):
                result = verify_update(p, url="https://example.com")
            assert "TLS/HTTPS" in result.checks
            assert result.checks["TLS/HTTPS"] is True
        finally:
            p.unlink()

    def test_tls_fail_makes_result_fail(self):
        from core.update_security import verify_update
        p = self._tmp_file()
        try:
            with patch('core.update_security.verify_tls', return_value=False):
                result = verify_update(p, url="https://bad.example.com")
            assert result.passed is False
        finally:
            p.unlink()

    def test_bool_conversion(self):
        from core.update_security import VerificationResult
        assert bool(VerificationResult(passed=True))  is True
        assert bool(VerificationResult(passed=False)) is False


# ─────────────────────────────────────────────────────────────────────────────
# update_monitor — check_service version detection
# ─────────────────────────────────────────────────────────────────────────────

class TestCheckService:

    def _service(self, service_id="nginx", version="1.25.3", docker_image="nginx:1.25.3"):
        return {"id": service_id, "version": version,
                "docker_image": docker_image, "name": service_id.title()}

    def test_update_available_when_versions_differ(self):
        from core.update_monitor import check_service
        svc = self._service(version="1.25.3")
        with patch('core.update_monitor._get_manifest_update_source', return_value=None), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value="1.26.0"):
            result = check_service(svc)
        assert result["update_available"] == 1
        assert result["latest_version"] == "1.26.0"

    def test_no_update_when_versions_same(self):
        from core.update_monitor import check_service
        svc = self._service(version="1.25.3")
        with patch('core.update_monitor._get_manifest_update_source', return_value=None), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value="1.25.3"):
            result = check_service(svc)
        assert result["update_available"] == 0

    def test_error_recorded_when_fetch_fails(self):
        from core.update_monitor import check_service
        svc = self._service()
        with patch('core.update_monitor._get_manifest_update_source', return_value=None), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value=None):
            result = check_service(svc)
        assert result["error"] is not None
        assert result["update_available"] == 0

    def test_uses_manifest_update_source_dockerhub(self):
        from core.update_monitor import check_service
        svc = self._service()
        source = {"type": "dockerhub", "image": "library/nginx"}
        with patch('core.update_monitor._get_manifest_update_source', return_value=source), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value="1.26.0") as mock_fetch:
            result = check_service(svc)
        mock_fetch.assert_called_once_with("library/nginx")
        assert result["update_available"] == 1

    def test_uses_manifest_update_source_github(self):
        from core.update_monitor import check_service
        svc = self._service()
        source = {"type": "github", "repo": "nginx/nginx"}
        with patch('core.update_monitor._get_manifest_update_source', return_value=source), \
             patch('core.update_monitor._fetch_github_latest', return_value="v1.26.0") as mock_gh:
            result = check_service(svc)
        mock_gh.assert_called_once_with("nginx/nginx")

    def test_latest_tag_not_flagged_as_update(self):
        """'latest' tag should never be flagged as an update available."""
        from core.update_monitor import check_service
        svc = self._service(version="1.25.3")
        with patch('core.update_monitor._get_manifest_update_source', return_value=None), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value="latest"):
            result = check_service(svc)
        assert result["update_available"] == 0

    def test_result_contains_required_keys(self):
        from core.update_monitor import check_service
        svc = self._service()
        with patch('core.update_monitor._get_manifest_update_source', return_value=None), \
             patch('core.update_monitor._fetch_dockerhub_latest', return_value="1.26.0"):
            result = check_service(svc)
        for key in ("service_id", "current_version", "latest_version",
                    "update_available", "checked_at", "error"):
            assert key in result


# ─────────────────────────────────────────────────────────────────────────────
# update_processor — UpdateProcessor.apply() pipeline
# ─────────────────────────────────────────────────────────────────────────────

def _make_processor():
    """Return UpdateProcessor with all heavy functions patched at module level."""
    from core.update_processor import UpdateProcessor
    return UpdateProcessor()


def _patch_processor(service=None, manifest=None):
    """Context manager stack for a standard processor test."""
    from unittest.mock import patch as _patch
    import contextlib

    default_service = service or {
        "id": "nginx", "name": "Nginx",
        "version": "1.25.3", "docker_image": "nginx:1.25.3",
        "status": "running"
    }
    default_manifest = manifest or {"update_source": {}}

    return contextlib.ExitStack()   # caller builds the patches


class TestUpdateProcessorApply:

    def _run(self, *, service=None, pull_ok=True, start_ok=True,
             healthy=True, backup_ok=True, dry_run=False,
             skip_verification=True):
        """
        Run UpdateProcessor.apply() with controlled mocks.
        Returns (success: bool, rollback_called: bool).
        """
        from core.update_processor import UpdateProcessor

        svc = service or {
            "id": "nginx", "version": "1.25.3",
            "docker_image": "nginx:1.25.3", "name": "Nginx",
        }

        proc = UpdateProcessor.__new__(UpdateProcessor)
        rollback_calls = []

        def _fake_rollback(sid, ver, bp=None):
            rollback_calls.append(sid)

        proc._rollback = _fake_rollback

        pull_result = MagicMock(returncode=0)
        import subprocess as _sp
        pull_error  = _sp.CalledProcessError(1, 'docker pull', stderr="pull failed") if not pull_ok else None
        start_error = Exception("start failed") if not start_ok else None

        with patch('core.update_processor._ensure_schema'), \
             patch('core.update_processor._get_service', return_value=svc), \
             patch('core.update_processor._get_manifest', return_value={"update_source": {}}), \
             patch('core.update_processor._backup_service',
                   return_value=Path("/tmp/fake-backup") if backup_ok else (_ for _ in ()).throw(Exception("backup failed"))), \
             patch('core.update_processor._run',
                   side_effect=[MagicMock(),          # docker stop
                                 pull_error or pull_result,   # docker pull
                                 start_error or MagicMock()]  # docker start
                   if not dry_run else None), \
             patch('core.update_processor._wait_healthy', return_value=healthy), \
             patch('core.update_processor._container_running', return_value=True), \
             patch('core.update_processor._update_service_version'), \
             patch('core.update_processor._record_update'):

            result = proc.apply(
                "nginx",
                target_version="1.26.0",
                skip_verification=skip_verification,
                dry_run=dry_run,
            )

        return result, rollback_calls

    def test_dry_run_returns_true_no_docker(self):
        success, rollback = self._run(dry_run=True)
        assert success is True
        assert rollback == []

    def test_happy_path_returns_true(self):
        success, rollback = self._run()
        assert success is True
        assert rollback == []

    def test_pull_failure_triggers_rollback(self):
        success, rollback = self._run(pull_ok=False)
        assert success is False
        assert rollback == ["nginx"]

    def test_start_failure_triggers_rollback(self):
        success, rollback = self._run(start_ok=False)
        assert success is False
        assert rollback == ["nginx"]

    def test_missing_service_returns_false(self):
        from core.update_processor import UpdateProcessor
        proc = UpdateProcessor.__new__(UpdateProcessor)
        with patch('core.update_processor._ensure_schema'), \
             patch('core.update_processor._get_service', return_value=None):
            result = proc.apply("nonexistent", skip_verification=True)
        assert result is False

    def test_health_fail_but_container_running_succeeds(self):
        """If health check times out but container IS running, proceed."""
        success, rollback = self._run(healthy=False)
        # _container_running returns True in _run helper → should succeed
        assert success is True
        assert rollback == []


# ─────────────────────────────────────────────────────────────────────────────
# update_manager — ServiceUpdateManager
# ─────────────────────────────────────────────────────────────────────────────

class TestServiceUpdateManager:
    """
    update_manager.ServiceUpdateManager has its own pipeline — it does NOT
    delegate to UpdateProcessor. It uses service_mgr, backup_mgr, loader,
    and _pull_image/_remove_container directly.
    """

    def _make_manager(self):
        from core.update_manager import ServiceUpdateManager
        mgr = ServiceUpdateManager.__new__(ServiceUpdateManager)
        mgr.db           = MagicMock()
        mgr.service_mgr  = MagicMock()
        mgr.backup_mgr   = MagicMock()
        mgr.loader       = MagicMock()
        mgr.docker_client = MagicMock()
        mgr._pull_image      = MagicMock()
        mgr._remove_container = MagicMock()
        mgr._get_current_digest = MagicMock(return_value="sha256:aaa")
        mgr._get_latest_digest  = MagicMock(return_value="sha256:bbb")
        mgr._record_update      = MagicMock()

        # Manifest stub
        manifest = MagicMock()
        manifest.data = {'installation': {'method': 'docker', 'image': 'nginx:latest'}}
        mgr.loader.load.return_value = manifest

        # Service stub
        mgr.db.get_service.return_value = {
            'service_id': 'nginx', 'version': '1.25.3'
        }
        mgr.service_mgr.get_status.return_value = {'status': 'running'}
        mgr.backup_mgr.create_backup.return_value = 'bk-001'
        return mgr

    def test_update_service_happy_path(self):
        import time as _time
        mgr = self._make_manager()
        with patch('time.sleep'):
            success = mgr.update_service("nginx", backup=False)
        assert success is True
        mgr.service_mgr.stop.assert_called_once_with("nginx")
        mgr.service_mgr.start.assert_called_once_with("nginx")

    def test_update_service_already_up_to_date(self):
        mgr = self._make_manager()
        # Same digest → no update needed
        mgr._get_current_digest.return_value = "sha256:same"
        mgr._get_latest_digest.return_value  = "sha256:same"
        with patch('time.sleep'):
            success = mgr.update_service("nginx", backup=False)
        assert success is True
        mgr.service_mgr.stop.assert_not_called()

    def test_update_service_creates_backup_when_requested(self):
        mgr = self._make_manager()
        with patch('time.sleep'):
            mgr.update_service("nginx", backup=True)
        mgr.backup_mgr.create_backup.assert_called_once()

    def test_update_service_missing_service_raises(self):
        from core.update_manager import UpdateError
        mgr = self._make_manager()
        mgr.db.get_service.return_value = None
        with pytest.raises(UpdateError, match="Service not found"):
            mgr.update_service("nonexistent")

    def test_update_service_start_failure_raises_and_records(self):
        from core.update_manager import UpdateError
        mgr = self._make_manager()
        mgr.service_mgr.start.side_effect = Exception("container crash")
        with patch('time.sleep'):
            with pytest.raises(UpdateError):
                mgr.update_service("nginx", backup=False)
        mgr._record_update.assert_called()
        # Last call should record failure
        last_call_kwargs = mgr._record_update.call_args[1]
        assert last_call_kwargs.get('status') == 'failed'


# ─────────────────────────────────────────────────────────────────────────────
# update_security — VerificationResult.summary()
# ─────────────────────────────────────────────────────────────────────────────

class TestVerificationResultSummary:

    def test_summary_contains_passed(self):
        from core.update_security import VerificationResult
        r = VerificationResult(
            passed=True,
            checks={"TLS/HTTPS": True, "SHA-256 checksum": True},
        )
        s = r.summary()
        assert "PASSED" in s
        assert "TLS/HTTPS" in s

    def test_summary_contains_failed(self):
        from core.update_security import VerificationResult
        r = VerificationResult(
            passed=False,
            checks={"SHA-256 checksum": False},
            errors=["Checksum mismatch"],
        )
        s = r.summary()
        assert "FAILED" in s
        assert "Checksum mismatch" in s

    def test_skipped_checks_shown(self):
        from core.update_security import VerificationResult
        r = VerificationResult(
            passed=False,
            checks={"TLS/HTTPS": None, "SHA-256 checksum": True},
        )
        s = r.summary()
        assert "TLS/HTTPS" in s


if __name__ == '__main__':
    pytest.main([__file__, '-v'])