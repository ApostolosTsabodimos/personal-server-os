#!/usr/bin/env python3
"""
Unit tests for installer module
Run with: python -m pytest tests/test_installer.py -v
"""

import pytest
import tempfile
from pathlib import Path
import sys
import docker
from unittest.mock import patch

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.installer import ServiceInstaller, InstallationError, PrerequisiteError, InstallerError
from core.manifest import ManifestLoader
from core.database import Database


@pytest.fixture
def temp_environment():
    """Create temporary environment for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        data_dir = Path(tmpdir) / 'pso_test'
        db_path = data_dir / 'test.db'
        data_dir.mkdir(parents=True)
        
        # Create database
        db = Database(db_path)
        
        yield {
            'data_dir': data_dir,
            'db': db,
            'db_path': db_path
        }


@pytest.fixture
def nginx_manifest():
    """Load nginx manifest for testing"""
    loader = ManifestLoader()
    return loader.load('nginx')


@pytest.fixture
def safe_manifest():
    """A manifest using a high port guaranteed not to be in use by the system."""
    from core.manifest import Manifest
    return Manifest({
        'id': 'pso-test-svc',
        'name': 'PSO Test Service',
        'version': '1.0.0',
        'category': 'other',
        'description': 'Ephemeral test service for pso-check',
        'installation': {'method': 'docker', 'image': 'nginx:alpine'},
        'ports': {'http': 59980},
        'volumes': [],
        'dependencies': {},
        'health_check': {'type': 'none'},
        'environment': {},
        'reverse_proxy': {},
    })


@pytest.fixture
def mock_resolver():
    """Patch DependencyResolver so synthetic test manifests don't need a catalog entry."""
    with patch('core.installer.DependencyResolver') as MockDR:
        instance = MockDR.return_value
        instance.get_installation_plan.return_value = (['pso-test-svc'], [])
        instance.check_conflicts.return_value = []
        yield instance


class TestInstallerInitialization:
    """Test installer initialization"""
    
    def test_installer_creation(self, nginx_manifest, temp_environment):
        """Test creating an installer instance"""
        installer = ServiceInstaller(
            nginx_manifest,
            data_dir=temp_environment['data_dir'],
            db=temp_environment['db']
        )
        
        assert installer.manifest.id == 'nginx'
        assert installer.db is not None
        assert installer.docker_client is not None


class TestPrerequisiteValidation:
    """Test prerequisite checking"""
    
    def test_docker_availability(self, nginx_manifest, temp_environment):
        """Test that Docker is available"""
        installer = ServiceInstaller(
            nginx_manifest,
            data_dir=temp_environment['data_dir'],
            db=temp_environment['db']
        )
        
        # Should not raise exception if Docker is available
        installer._validate_prerequisites()
    
    def test_duplicate_installation_prevention(self, nginx_manifest, temp_environment):
        """Test that duplicate installation is prevented"""
        db = temp_environment['db']
        
        # Add nginx to database
        db.add_service({
            'service_id': 'nginx',
            'service_name': 'Nginx',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        installer = ServiceInstaller(
            nginx_manifest,
            data_dir=temp_environment['data_dir'],
            db=db
        )
        
        # Should raise error about duplicate
        with pytest.raises(InstallationError, match="already installed"):
            installer.install()


class TestPortConflictDetection:
    """Test port conflict detection"""
    
    def test_port_conflict_from_database(self, safe_manifest, temp_environment, mock_resolver):
        """Test detection of port conflicts from database"""
        db = temp_environment['db']

        # Register a service already using port 59980 (same as safe_manifest)
        db.add_service({
            'service_id': 'other-service',
            'service_name': 'Other Service',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker',
            'ports': {'http': 59980}
        })

        installer = ServiceInstaller(
            safe_manifest,
            data_dir=temp_environment['data_dir'],
            db=db
        )

        # Should raise error about port conflict detected in DB
        with pytest.raises(InstallationError, match="Port conflicts detected"):
            installer.install()


class TestDryRun:
    """Test dry-run functionality"""
    
    def test_dry_run_no_changes(self, safe_manifest, temp_environment, mock_resolver):
        """Test that dry-run doesn't make changes"""
        db = temp_environment['db']
        data_dir = temp_environment['data_dir']

        installer = ServiceInstaller(
            safe_manifest,
            data_dir=data_dir,
            db=db
        )

        # Run dry-run — should succeed without touching system port
        result = installer.install(dry_run=True)

        assert result == True

        # Verify no service was added to database
        assert not db.is_installed('pso-test-svc')

        # Verify no directories were created
        service_dir = data_dir / 'pso-test-svc'
        assert not service_dir.exists()
    
    def test_dry_run_validates_prerequisites(self, safe_manifest, temp_environment, mock_resolver):
        """Test that dry-run still validates prerequisites via DB port conflict"""
        db = temp_environment['db']

        # Register a service already using port 59980 (same as safe_manifest)
        db.add_service({
            'service_id': 'conflict',
            'service_name': 'Conflict',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker',
            'ports': {'http': 59980}
        })

        installer = ServiceInstaller(
            safe_manifest,
            data_dir=temp_environment['data_dir'],
            db=db
        )

        # Dry-run should still fail on DB port conflict
        with pytest.raises(InstallationError):
            installer.install(dry_run=True)


class TestDirectoryCreation:
    """Test directory creation"""
    
    def test_creates_service_directory(self, nginx_manifest, temp_environment):
        """Test that service directory is created"""
        data_dir = temp_environment['data_dir']
        
        installer = ServiceInstaller(
            nginx_manifest,
            data_dir=data_dir,
            db=temp_environment['db']
        )
        
        installer._create_directories()
        
        service_dir = data_dir / 'nginx'
        assert service_dir.exists()
        assert service_dir.is_dir()


class TestDatabaseIntegration:
    """Test database integration"""
    
    def test_records_installation(self, temp_environment):
        """Test that successful installation is recorded"""
        # This would require a full installation which might be slow
        # For now, test the recording method directly
        
        from core.manifest import Manifest
        
        manifest_data = {
            'id': 'test-service',
            'name': 'Test Service',
            'version': '1.0.0',
            'category': 'other',
            'description': 'Test service',
            'installation': {
                'method': 'docker',
                'image': 'nginx:alpine'
            },
            'ports': {'http': 9999},
            'volumes': []
        }
        
        manifest = Manifest(manifest_data)
        installer = ServiceInstaller(
            manifest,
            data_dir=temp_environment['data_dir'],
            db=temp_environment['db']
        )
        
        # Simulate successful installation by calling record method
        installer._record_installation()
        
        # Verify it's in database
        assert temp_environment['db'].is_installed('test-service')
        
        service = temp_environment['db'].get_service('test-service')
        assert service['service_name'] == 'Test Service'
        assert service['version'] == '1.0.0'
        assert service['ports'] == {'http': 9999}


class TestRollback:
    """Test rollback functionality"""
    
    def test_rollback_removes_from_database(self, temp_environment):
        """Test that rollback removes service from database"""
        from core.manifest import Manifest
        
        manifest_data = {
            'id': 'rollback-test',
            'name': 'Rollback Test',
            'version': '1.0.0',
            'category': 'other',
            'description': 'Test rollback',
            'installation': {
                'method': 'docker',
                'image': 'nginx:alpine'
            }
        }
        
        manifest = Manifest(manifest_data)
        db = temp_environment['db']
        
        # Add to database
        db.add_service({
            'service_id': 'rollback-test',
            'service_name': 'Rollback Test',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        assert db.is_installed('rollback-test')
        
        # Create installer and rollback
        installer = ServiceInstaller(
            manifest,
            data_dir=temp_environment['data_dir'],
            db=db
        )
        installer.rollback()
        
        # Should be removed from database
        assert not db.is_installed('rollback-test')


if __name__ == '__main__':
    pytest.main([__file__, '-v'])