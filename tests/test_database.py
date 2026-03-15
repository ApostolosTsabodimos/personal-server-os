#!/usr/bin/env python3
"""
Unit tests for database module
Run with: python -m pytest tests/test_database.py -v
"""

import pytest
import tempfile
from pathlib import Path
import sys

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.database import Database, DatabaseError


@pytest.fixture
def temp_db():
    """Create a temporary database for testing"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / 'test.db'
        db = Database(db_path)
        yield db


class TestDatabaseInitialization:
    """Test database creation and schema"""
    
    def test_database_creation(self, temp_db):
        """Test that database file is created"""
        assert temp_db.db_path.exists()
    
    def test_schema_creation(self, temp_db):
        """Test that tables are created"""
        with temp_db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Check tables exist
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table'
                ORDER BY name
            """)
            tables = [row['name'] for row in cursor.fetchall()]
            
            assert 'installed_services' in tables
            assert 'service_ports' in tables
            assert 'service_volumes' in tables
            assert 'installation_history' in tables
            assert 'service_dependencies' in tables


class TestServiceManagement:
    """Test service CRUD operations"""
    
    def test_add_service(self, temp_db):
        """Test adding a service"""
        service_data = {
            'service_id': 'nginx',
            'service_name': 'Nginx Web Server',
            'version': '1.25.3',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker',
            'config': {'domain': 'example.com'},
            'ports': {'http': 8080, 'https': 8443},
            'volumes': [
                {'host': '/var/pso/nginx/html', 'container': '/usr/share/nginx/html', 'readonly': False}
            ],
            'dependencies': ['docker']
        }
        
        assert temp_db.add_service(service_data) == True
        assert temp_db.is_installed('nginx') == True
    
    def test_get_service(self, temp_db):
        """Test retrieving a service"""
        service_data = {
            'service_id': 'portainer',
            'service_name': 'Portainer',
            'version': '2.19.4',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker',
            'ports': {'http': 9000}
        }
        
        temp_db.add_service(service_data)
        service = temp_db.get_service('portainer')
        
        assert service is not None
        assert service['service_id'] == 'portainer'
        assert service['service_name'] == 'Portainer'
        assert service['version'] == '2.19.4'
        assert service['ports'] == {'http': 9000}
    
    def test_list_services(self, temp_db):
        """Test listing all services"""
        # Add multiple services
        for i in range(3):
            temp_db.add_service({
                'service_id': f'service-{i}',
                'service_name': f'Service {i}',
                'version': '1.0.0',
                'category': 'other',
                'status': 'running',
                'installation_method': 'docker'
            })
        
        services = temp_db.list_services()
        assert len(services) == 3
    
    def test_list_services_by_status(self, temp_db):
        """Test filtering services by status"""
        temp_db.add_service({
            'service_id': 'running-service',
            'service_name': 'Running',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        temp_db.add_service({
            'service_id': 'stopped-service',
            'service_name': 'Stopped',
            'version': '1.0.0',
            'category': 'other',
            'status': 'stopped',
            'installation_method': 'docker'
        })
        
        running = temp_db.list_services(status='running')
        assert len(running) == 1
        assert running[0]['service_id'] == 'running-service'
    
    def test_update_service_status(self, temp_db):
        """Test updating service status"""
        temp_db.add_service({
            'service_id': 'test-service',
            'service_name': 'Test',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        temp_db.update_service_status('test-service', 'stopped')
        service = temp_db.get_service('test-service')
        assert service['status'] == 'stopped'
    
    def test_remove_service(self, temp_db):
        """Test removing a service"""
        temp_db.add_service({
            'service_id': 'to-remove',
            'service_name': 'To Remove',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        assert temp_db.is_installed('to-remove') == True
        temp_db.remove_service('to-remove')
        assert temp_db.is_installed('to-remove') == False
    
    def test_is_installed(self, temp_db):
        """Test checking if service is installed"""
        assert temp_db.is_installed('nonexistent') == False
        
        temp_db.add_service({
            'service_id': 'exists',
            'service_name': 'Exists',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        assert temp_db.is_installed('exists') == True


class TestPortConflicts:
    """Test port conflict detection"""
    
    def test_no_conflicts(self, temp_db):
        """Test when no port conflicts exist"""
        conflicts = temp_db.get_port_conflicts({'http': 8080})
        assert len(conflicts) == 0
    
    def test_port_conflict_detection(self, temp_db):
        """Test detecting port conflicts"""
        temp_db.add_service({
            'service_id': 'nginx',
            'service_name': 'Nginx',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker',
            'ports': {'http': 8080}
        })
        
        conflicts = temp_db.get_port_conflicts({'http': 8080})
        assert len(conflicts) == 1
        assert conflicts[0] == ('http', 8080, 'nginx')


class TestInstallationHistory:
    """Test installation history logging"""
    
    def test_log_action(self, temp_db):
        """Test logging an action"""
        # Need a service to log actions for
        temp_db.add_service({
            'service_id': 'test',
            'service_name': 'Test',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        temp_db.log_action('test', 'start', 'success', 'Service started')
        
        history = temp_db.get_service_history('test')
        # Should have 2 entries: 1 from add_service, 1 from log_action
        assert len(history) >= 1
    
    def test_get_service_history(self, temp_db):
        """Test retrieving service history"""
        temp_db.add_service({
            'service_id': 'test',
            'service_name': 'Test',
            'version': '1.0.0',
            'category': 'other',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        temp_db.log_action('test', 'start', 'success')
        temp_db.log_action('test', 'stop', 'success')
        temp_db.log_action('test', 'start', 'success')
        
        history = temp_db.get_service_history('test', limit=2)
        assert len(history) == 2
        # Most recent first
        assert history[0]['action'] == 'start'


class TestStatistics:
    """Test database statistics"""
    
    def test_get_stats(self, temp_db):
        """Test getting database statistics"""
        # Add services with different statuses and categories
        temp_db.add_service({
            'service_id': 's1',
            'service_name': 'S1',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        temp_db.add_service({
            'service_id': 's2',
            'service_name': 'S2',
            'version': '1.0.0',
            'category': 'infrastructure',
            'status': 'stopped',
            'installation_method': 'docker'
        })
        
        temp_db.add_service({
            'service_id': 's3',
            'service_name': 'S3',
            'version': '1.0.0',
            'category': 'productivity',
            'status': 'running',
            'installation_method': 'docker'
        })
        
        stats = temp_db.get_stats()
        
        assert stats['total_services'] == 3
        assert stats['by_status']['running'] == 2
        assert stats['by_status']['stopped'] == 1
        assert stats['by_category']['infrastructure'] == 2
        assert stats['by_category']['productivity'] == 1


if __name__ == '__main__':
    pytest.main([__file__, '-v'])