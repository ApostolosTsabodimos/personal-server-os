#!/usr/bin/env python3
"""
PSO Manifest Validator
Loads, validates, and manages service manifest files
"""

import json
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import jsonschema
from jsonschema import validate, ValidationError, Draft7Validator


class ManifestError(Exception):
    """Base exception for manifest-related errors"""
    pass


class ManifestValidationError(ManifestError):
    """Raised when manifest validation fails"""
    pass


class ManifestNotFoundError(ManifestError):
    """Raised when manifest file is not found"""
    pass


class Manifest:
    """
    Represents a service manifest with validation and helper methods
    """
    
    def __init__(self, data: Dict, source_path: Optional[Path] = None):
        """
        Initialize manifest from dictionary
        
        Args:
            data: Manifest data dictionary
            source_path: Optional path to the manifest file
        """
        self.data = data
        self.source_path = source_path
        self._validate()
    
    def _validate(self):
        """Validate manifest against schema"""
        schema_path = Path(__file__).parent / 'schemas' / 'manifest_v1.schema.json'
        
        if not schema_path.exists():
            raise ManifestError(f"Schema file not found: {schema_path}")
        
        with open(schema_path) as f:
            schema = json.load(f)
        
        try:
            validate(instance=self.data, schema=schema)
        except ValidationError as e:
            # Create a more helpful error message
            error_path = ' -> '.join(str(p) for p in e.path) if e.path else 'root'
            raise ManifestValidationError(
                f"Validation failed at '{error_path}': {e.message}"
            )
    
    @property
    def id(self) -> str:
        """Get service ID"""
        return self.data['id']
    
    @property
    def name(self) -> str:
        """Get service name"""
        return self.data['name']
    
    @property
    def version(self) -> str:
        """Get service version"""
        return self.data['version']
    
    @property
    def category(self) -> str:
        """Get service category"""
        return self.data['category']
    
    @property
    def description(self) -> str:
        """Get service description"""
        return self.data['description']
    
    @property
    def installation_method(self) -> str:
        """Get installation method"""
        return self.data['installation']['method']
    
    @property
    def dependencies(self) -> Dict[str, List[str]]:
        """Get dependencies"""
        return self.data.get('dependencies', {
            'services': [],
            'system': [],
            'conflicts': []
        })
    
    @property
    def ports(self) -> Dict[str, int]:
        """Get port mappings (name -> host port)"""
        return self.data.get('ports', {})

    @property
    def container_port(self) -> Optional[int]:
        """
        Get the container-side port the service listens on.
        When set, the installer maps host_port -> container_port.
        When absent, host_port is used for both sides.
        """
        return self.data.get('container_port')
    
    @property
    def volumes(self) -> List[Dict]:
        """Get volume mappings"""
        return self.data.get('volumes', [])
    
    @property
    def environment(self) -> Dict[str, str]:
        """Get environment variables"""
        return self.data.get('environment', {})
    
    @property
    def health_check(self) -> Optional[Dict]:
        """Get health check configuration"""
        return self.data.get('health_check')
    
    @property
    def hooks(self) -> Dict[str, Optional[str]]:
        """Get lifecycle hooks"""
        return self.data.get('hooks', {})
    
    @property
    def reverse_proxy(self) -> Optional[Dict]:
        """Get reverse proxy configuration"""
        return self.data.get('reverse_proxy')
    
    def has_dependency(self, service_id: str) -> bool:
        """Check if this manifest depends on another service"""
        return service_id in self.dependencies.get('services', [])
    
    def conflicts_with(self, service_id: str) -> bool:
        """Check if this manifest conflicts with another service"""
        return service_id in self.dependencies.get('conflicts', [])
    
    def requires_reverse_proxy(self) -> bool:
        """Check if service requires reverse proxy configuration"""
        rp = self.reverse_proxy
        return rp is not None and rp.get('enabled', False)
    
    def get_user_inputs(self) -> List[Dict]:
        """Get user input configuration for installation"""
        config = self.data.get('configuration', {})
        return config.get('user_inputs', [])
    
    def get_hook(self, hook_name: str) -> Optional[str]:
        """Get a specific lifecycle hook"""
        hooks = self.hooks
        return hooks.get(hook_name)
    
    def to_dict(self) -> Dict:
        """Export manifest as dictionary"""
        return self.data.copy()
    
    def __repr__(self) -> str:
        return f"<Manifest id={self.id} name={self.name} version={self.version}>"


class ManifestLoader:
    """
    Loads and manages service manifests
    """
    
    def __init__(self, services_dir: Optional[Path] = None):
        """
        Initialize manifest loader
        
        Args:
            services_dir: Directory containing service manifests
        """
        if services_dir is None:
            # Default to services/ directory relative to project root
            self.services_dir = Path(__file__).parent.parent / 'services'
        else:
            self.services_dir = Path(services_dir)
    
    def load(self, service_id: str) -> Manifest:
        """
        Load a manifest by service ID
        
        Args:
            service_id: Service identifier
            
        Returns:
            Manifest object
            
        Raises:
            ManifestNotFoundError: If manifest file doesn't exist
            ManifestValidationError: If manifest is invalid
        """
        manifest_path = self.services_dir / service_id / 'manifest.json'
        
        if not manifest_path.exists():
            raise ManifestNotFoundError(
                f"Manifest not found: {manifest_path}\n"
                f"Expected location: services/{service_id}/manifest.json"
            )
        
        try:
            with open(manifest_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestError(f"Invalid JSON in {manifest_path}: {e}")
        
        return Manifest(data, source_path=manifest_path)
    
    def load_from_file(self, file_path: Path) -> Manifest:
        """
        Load a manifest from a specific file path
        
        Args:
            file_path: Path to manifest file
            
        Returns:
            Manifest object
        """
        file_path = Path(file_path)
        
        if not file_path.exists():
            raise ManifestNotFoundError(f"File not found: {file_path}")
        
        try:
            with open(file_path) as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ManifestError(f"Invalid JSON in {file_path}: {e}")
        
        return Manifest(data, source_path=file_path)
    
    def list_available(self) -> List[str]:
        """
        List all available service IDs with manifests
        
        Returns:
            List of service IDs
        """
        if not self.services_dir.exists():
            return []
        
        available = []
        for service_dir in self.services_dir.iterdir():
            if service_dir.is_dir():
                manifest_path = service_dir / 'manifest.json'
                if manifest_path.exists():
                    available.append(service_dir.name)
        
        return sorted(available)
    
    def validate_all(self) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Validate all manifests in the services directory
        
        Returns:
            Tuple of (valid_services, invalid_services_with_errors)
        """
        valid = []
        invalid = []
        
        for service_id in self.list_available():
            try:
                self.load(service_id)
                valid.append(service_id)
            except ManifestError as e:
                invalid.append((service_id, str(e)))
        
        return valid, invalid
    
    def get_by_category(self, category: str) -> List[Manifest]:
        """
        Get all manifests in a specific category
        
        Args:
            category: Category name
            
        Returns:
            List of Manifest objects
        """
        manifests = []
        for service_id in self.list_available():
            try:
                manifest = self.load(service_id)
                if manifest.category == category:
                    manifests.append(manifest)
            except ManifestError:
                # Skip invalid manifests
                continue
        
        return manifests
    
    def search(self, query: str) -> List[Manifest]:
        """
        Search manifests by name, description, or tags
        
        Args:
            query: Search query (case-insensitive)
            
        Returns:
            List of matching Manifest objects
        """
        query = query.lower()
        results = []
        
        for service_id in self.list_available():
            try:
                manifest = self.load(service_id)
                
                # Search in name, description, ID
                searchable = [
                    manifest.id.lower(),
                    manifest.name.lower(),
                    manifest.description.lower()
                ]
                
                # Add tags if they exist
                metadata = manifest.data.get('metadata', {})
                if 'tags' in metadata:
                    searchable.extend([tag.lower() for tag in metadata['tags']])
                
                if any(query in text for text in searchable):
                    results.append(manifest)
                    
            except ManifestError:
                continue
        
        return results


def validate_manifest_file(file_path: Path) -> Tuple[bool, Optional[str]]:
    """
    Quick validation helper function
    
    Args:
        file_path: Path to manifest file
        
    Returns:
        Tuple of (is_valid, error_message)
    """
    try:
        loader = ManifestLoader()
        loader.load_from_file(file_path)
        return True, None
    except ManifestError as e:
        return False, str(e)