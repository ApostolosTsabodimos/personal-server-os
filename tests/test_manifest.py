#!/usr/bin/env python3
"""
Unit tests for manifest validation system
Run with: python -m pytest tests/test_manifest.py -v
"""

import json
import pytest
from pathlib import Path
import sys

# Add parent directory to path to import core module
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.manifest import (
    Manifest, 
    ManifestLoader, 
    ManifestError, 
    ManifestValidationError,
    ManifestNotFoundError,
    validate_manifest_file
)


class TestManifestValidation:
    """Test manifest validation against schema"""
    
    def test_valid_minimal_manifest(self):
        """Test a minimal valid manifest"""
        data = {
            "id": "test-service",
            "name": "Test Service",
            "version": "1.0.0",
            "category": "other",
            "description": "A test service for validation",
            "installation": {
                "method": "docker",
                "image": "nginx:latest"
            }
        }
        manifest = Manifest(data)
        assert manifest.id == "test-service"
        assert manifest.name == "Test Service"
        assert manifest.version == "1.0.0"
    
    def test_invalid_id_format(self):
        """Test that invalid ID format is rejected"""
        data = {
            "id": "Invalid_Service",  # Uppercase and underscore not allowed
            "name": "Test Service",
            "version": "1.0.0",
            "category": "other",
            "description": "A test service",
            "installation": {"method": "docker", "image": "nginx:latest"}
        }
        with pytest.raises(ManifestValidationError):
            Manifest(data)
    
    def test_invalid_version_format(self):
        """Test that invalid version format is rejected"""
        data = {
            "id": "test-service",
            "name": "Test Service",
            "version": "1.0",  # Should be semantic version x.y.z
            "category": "other",
            "description": "A test service",
            "installation": {"method": "docker", "image": "nginx:latest"}
        }
        with pytest.raises(ManifestValidationError):
            Manifest(data)
    
    def test_invalid_category(self):
        """Test that invalid category is rejected"""
        data = {
            "id": "test-service",
            "name": "Test Service",
            "version": "1.0.0",
            "category": "invalid-category",
            "description": "A test service",
            "installation": {"method": "docker", "image": "nginx:latest"}
        }
        with pytest.raises(ManifestValidationError):
            Manifest(data)
    
    def test_missing_required_field(self):
        """Test that missing required fields are caught"""
        data = {
            "id": "test-service",
            "name": "Test Service",
            # Missing version
            "category": "other",
            "description": "A test service",
            "installation": {"method": "docker", "image": "nginx:latest"}
        }
        with pytest.raises(ManifestValidationError):
            Manifest(data)
    
    def test_docker_method_requires_image(self):
        """Test that docker installation method requires image"""
        data = {
            "id": "test-service",
            "name": "Test Service",
            "version": "1.0.0",
            "category": "other",
            "description": "A test service",
            "installation": {
                "method": "docker"
                # Missing image
            }
        }
        with pytest.raises(ManifestValidationError):
            Manifest(data)
    
    def test_valid_full_manifest(self):
        """Test a fully populated valid manifest"""
        data = {
            "id": "full-service",
            "name": "Full Service",
            "version": "2.1.0",
            "category": "productivity",
            "description": "A fully featured test service with all options",
            "author": "Test Author",
            "homepage": "https://example.com",
            "documentation": "https://docs.example.com",
            "installation": {
                "method": "docker",
                "image": "example/service:latest"
            },
            "dependencies": {
                "services": ["nginx"],
                "system": ["docker", "python3"],
                "conflicts": ["other-service"]
            },
            "ports": {
                "http": 8080,
                "admin": 9090
            },
            "volumes": [
                {
                    "host": "/data",
                    "container": "/app/data",
                    "type": "bind",
                    "readonly": False
                }
            ],
            "environment": {
                "APP_ENV": "production",
                "LOG_LEVEL": "info"
            },
            "health_check": {
                "type": "http",
                "endpoint": "http://localhost:8080/health",
                "interval": 30,
                "timeout": 5,
                "retries": 3
            },
            "reverse_proxy": {
                "enabled": True,
                "subdomain": "app",
                "port": 8080,
                "ssl": True
            }
        }
        manifest = Manifest(data)
        assert manifest.id == "full-service"
        assert len(manifest.ports) == 2
        assert manifest.requires_reverse_proxy() == True


class TestManifestProperties:
    """Test manifest property accessors"""
    
    @pytest.fixture
    def sample_manifest(self):
        """Create a sample manifest for testing"""
        data = {
            "id": "sample",
            "name": "Sample Service",
            "version": "1.0.0",
            "category": "productivity",
            "description": "Sample service for testing",
            "installation": {
                "method": "docker",
                "image": "sample:latest"
            },
            "dependencies": {
                "services": ["nginx", "postgres"],
                "system": ["docker"],
                "conflicts": ["old-sample"]
            },
            "health_check": {
                "type": "http",
                "endpoint": "http://localhost:8080"
            },
            "hooks": {
                "post_install": "setup.sh",
                "pre_uninstall": "cleanup.sh"
            }
        }
        return Manifest(data)
    
    def test_basic_properties(self, sample_manifest):
        """Test basic property accessors"""
        assert sample_manifest.id == "sample"
        assert sample_manifest.name == "Sample Service"
        assert sample_manifest.version == "1.0.0"
        assert sample_manifest.category == "productivity"
        assert sample_manifest.installation_method == "docker"
    
    def test_dependencies(self, sample_manifest):
        """Test dependency checking"""
        assert sample_manifest.has_dependency("nginx") == True
        assert sample_manifest.has_dependency("postgres") == True
        assert sample_manifest.has_dependency("redis") == False
        assert sample_manifest.conflicts_with("old-sample") == True
    
    def test_hooks(self, sample_manifest):
        """Test hook accessors"""
        assert sample_manifest.get_hook("post_install") == "setup.sh"
        assert sample_manifest.get_hook("pre_uninstall") == "cleanup.sh"
        assert sample_manifest.get_hook("pre_install") is None


class TestManifestLoader:
    """Test manifest loading functionality"""
    
    def test_load_nginx_manifest(self):
        """Test loading the nginx manifest"""
        loader = ManifestLoader()
        manifest = loader.load("nginx")
        assert manifest.id == "nginx"
        assert manifest.name == "Nginx Web Server"
        assert manifest.installation_method == "docker"
    
    def test_load_portainer_manifest(self):
        """Test loading the portainer manifest"""
        loader = ManifestLoader()
        manifest = loader.load("portainer")
        assert manifest.id == "portainer"
        assert manifest.requires_reverse_proxy() == True
    
    def test_load_nonexistent_manifest(self):
        """Test that loading non-existent manifest raises error"""
        loader = ManifestLoader()
        with pytest.raises(ManifestNotFoundError):
            loader.load("nonexistent-service")
    
    def test_list_available(self):
        """Test listing available manifests"""
        loader = ManifestLoader()
        available = loader.list_available()
        assert "nginx" in available
        assert "portainer" in available
    
    def test_get_by_category(self):
        """Test filtering by category"""
        loader = ManifestLoader()
        infrastructure = loader.get_by_category("infrastructure")
        ids = [m.id for m in infrastructure]
        assert "nginx" in ids
        assert "portainer" in ids
    
    def test_search_functionality(self):
        """Test search functionality"""
        loader = ManifestLoader()
        
        # Search by name
        results = loader.search("nginx")
        assert len(results) > 0
        assert results[0].id == "nginx"
        
        # Search by description keyword
        results = loader.search("container")
        portainer_found = any(m.id == "portainer" for m in results)
        assert portainer_found == True


class TestManifestValidationHelper:
    """Test validation helper functions"""
    
    def test_validate_valid_file(self):
        """Test validating a valid manifest file"""
        nginx_path = Path("services/nginx/manifest.json")
        is_valid, error = validate_manifest_file(nginx_path)
        assert is_valid == True
        assert error is None
    
    def test_validate_invalid_file(self, tmp_path):
        """Test validating an invalid manifest file"""
        # Create a temporary invalid manifest
        invalid_manifest = tmp_path / "invalid.json"
        invalid_manifest.write_text(json.dumps({
            "id": "test",
            "name": "Test"
            # Missing required fields
        }))
        
        is_valid, error = validate_manifest_file(invalid_manifest)
        assert is_valid == False
        assert error is not None


if __name__ == "__main__":
    # Allow running tests directly
    pytest.main([__file__, "-v"])