#!/usr/bin/env python3
"""
Dependency Resolver for PSO

Resolves service dependencies and determines installation order.
"""

import sys
from typing import List, Set, Dict, Tuple

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.manifest import ManifestLoader, ManifestError
from core.database import Database


class DependencyError(Exception):
    """Raised when dependency resolution fails"""
    pass


class DependencyResolver:
    """Resolves service dependencies and installation order"""
    
    def __init__(self):
        self.loader = ManifestLoader()
        self.db = Database()
    
    def get_dependencies(self, service_id: str) -> List[str]:
        """
        Get direct dependencies for a service
        
        Returns:
            List of service IDs that this service depends on
        """
        try:
            manifest = self.loader.load(service_id)
            return manifest.dependencies.get('services', [])
        except Exception:
            return []
    
    def get_optional_dependencies(self, service_id: str) -> List[str]:
        """
        Get optional dependencies for a service
        
        Returns:
            List of service IDs that are optional
        """
        try:
            manifest = self.loader.load(service_id)
            return manifest.dependencies.get('optional', [])
        except Exception:
            return []
    
    def get_conflicts(self, service_id: str) -> List[str]:
        """
        Get services that conflict with this one
        
        Returns:
            List of service IDs that conflict
        """
        try:
            manifest = self.loader.load(service_id)
            return manifest.dependencies.get('conflicts', [])
        except Exception:
            return []
    
    def is_installed(self, service_id: str) -> bool:
        """Check if a service is already installed"""
        try:
            installed = self.db.get_installed_services()
            return service_id in [s[0] for s in installed]
        except Exception:
            return False
    
    def check_conflicts(self, service_id: str) -> List[str]:
        """
        Check if installing this service would conflict with installed services
        
        Returns:
            List of installed services that conflict
        """
        conflicts = self.get_conflicts(service_id)
        installed_conflicts = []
        
        for conflict in conflicts:
            if self.is_installed(conflict):
                installed_conflicts.append(conflict)
        
        return installed_conflicts
    
    def resolve_order(self, service_id: str, visited: Set[str] = None, 
                      path: List[str] = None) -> List[str]:
        """
        Resolve installation order using topological sort (DFS)
        
        Returns:
            List of service IDs in installation order (dependencies first)
        
        Raises:
            DependencyError: If circular dependency or missing dependency
        """
        if visited is None:
            visited = set()
        if path is None:
            path = []
        
        # Check for circular dependency
        if service_id in path:
            cycle = ' -> '.join(path + [service_id])
            raise DependencyError(f"Circular dependency detected: {cycle}")
        
        # Already processed
        if service_id in visited:
            return []
        
        # Check if service exists and get dependencies in one load
        try:
            manifest = self.loader.load(service_id)
        except ManifestError:
            raise DependencyError(f"Service not found: {service_id}")
        
        # Read dependencies directly from the already-loaded manifest
        dependencies = manifest.dependencies.get('services', [])
        
        # Process dependencies first
        order = []
        for dep in dependencies:
            dep_order = self.resolve_order(dep, visited, path + [service_id])
            order.extend(dep_order)
        
        # Add this service
        visited.add(service_id)
        order.append(service_id)
        
        return order
    
    def get_installation_plan(self, service_id: str) -> Tuple[List[str], List[str]]:
        """
        Get complete installation plan
        
        Returns:
            (to_install, already_installed)
            - to_install: Services that need to be installed (in order)
            - already_installed: Services already installed (skipped)
        """
        # Resolve full dependency tree
        full_order = self.resolve_order(service_id)
        
        # Separate into to-install and already-installed
        to_install = []
        already_installed = []
        
        for service in full_order:
            if self.is_installed(service):
                already_installed.append(service)
            else:
                to_install.append(service)
        
        return to_install, already_installed
    
    def display_plan(self, service_id: str):
        """Display installation plan in human-readable format"""
        print(f"\n{'=' * 70}")
        print(f"INSTALLATION PLAN: {service_id}")
        print('=' * 70)
        
        # Check conflicts
        conflicts = self.check_conflicts(service_id)
        if conflicts:
            print(f"\n⚠️  CONFLICTS DETECTED:")
            for conflict in conflicts:
                print(f"  • {conflict} is already installed and conflicts with {service_id}")
            print(f"\n  You must uninstall conflicting services first:")
            for conflict in conflicts:
                print(f"    ./pso uninstall {conflict}")
            print()
            return False
        
        # Get installation plan
        try:
            to_install, already_installed = self.get_installation_plan(service_id)
        except DependencyError as e:
            print(f"\n✗ Error: {e}\n")
            return False
        
        # Display plan
        if already_installed:
            print(f"\n✓ Already Installed (will skip):")
            for service in already_installed:
                try:
                    manifest = self.loader.load(service)
                    print(f"  • {manifest.name}")
                except:
                    print(f"  • {service}")
        
        if to_install:
            print(f"\n→ Will Install ({len(to_install)} services):")
            for i, service in enumerate(to_install, 1):
                try:
                    manifest = self.loader.load(service)
                    deps = self.get_dependencies(service)
                    if deps:
                        print(f"  {i}. {manifest.name} (requires: {', '.join(deps)})")
                    else:
                        print(f"  {i}. {manifest.name}")
                except:
                    print(f"  {i}. {service}")
        else:
            print(f"\n✓ No installation needed - service and all dependencies already installed")
        
        # Show optional dependencies
        optional = self.get_optional_dependencies(service_id)
        if optional:
            print(f"\n💡 Optional (recommended but not required):")
            for opt in optional:
                try:
                    manifest = self.loader.load(opt)
                    installed = "✓ installed" if self.is_installed(opt) else "not installed"
                    print(f"  • {manifest.name} ({installed})")
                except:
                    print(f"  • {opt}")
        
        print(f"\n{'=' * 70}\n")
        return True


if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: python dependency_resolver.py <service-id>")
        sys.exit(1)
    
    resolver = DependencyResolver()
    service_id = sys.argv[1]
    
    success = resolver.display_plan(service_id)
    sys.exit(0 if success else 1)