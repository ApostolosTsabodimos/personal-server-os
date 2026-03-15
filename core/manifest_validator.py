#!/usr/bin/env python3
"""
Manifest Validator for PSO

Validates service manifests and provides helpful error messages.
"""

import sys
from typing import List, Tuple

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.manifest import ManifestLoader, ManifestError


class ManifestValidator:
    """Validates service manifests"""
    
    def __init__(self):
        self.loader = ManifestLoader()
    
    def validate_one(self, service_id: str) -> Tuple[bool, str]:
        """
        Validate a single service manifest
        
        Returns:
            (is_valid, message)
        """
        try:
            manifest = self.loader.load(service_id)
            
            # Additional checks beyond schema validation
            warnings = []
            
            # Check port consistency
            if manifest.ports:
                for port_name, port_num in manifest.ports.items():
                    # Check health check uses correct port
                    if manifest.health_check:
                        hc_endpoint = manifest.health_check.get('endpoint', '')
                        if 'localhost:' in hc_endpoint:
                            hc_port = hc_endpoint.split(':')[-1].split('/')[0]
                            if hc_port and hc_port != str(port_num):
                                warnings.append(
                                    f"Health check port ({hc_port}) doesn't match "
                                    f"service port {port_name} ({port_num})"
                                )
                    
                    # Check reverse proxy uses correct port
                    if manifest.reverse_proxy and manifest.reverse_proxy.get('enabled'):
                        rp_port = manifest.reverse_proxy.get('port')
                        if rp_port and rp_port not in manifest.ports.values():
                            warnings.append(
                                f"Reverse proxy port ({rp_port}) not in service ports"
                            )
            
            if warnings:
                return True, f"Valid with warnings:\n  " + "\n  ".join(warnings)
            else:
                return True, "Valid ✓"
                
        except ManifestError as e:
            return False, f"Invalid: {e}"
        except Exception as e:
            return False, f"Error: {e}"
    
    def validate_all(self) -> Tuple[List[str], List[Tuple[str, str]]]:
        """
        Validate all manifests
        
        Returns:
            (valid_services, invalid_services_with_errors)
        """
        valid = []
        invalid = []
        
        for service_id in self.loader.list_available():
            is_valid, message = self.validate_one(service_id)
            if is_valid:
                valid.append(service_id)
            else:
                invalid.append((service_id, message))
        
        return valid, invalid
    
    def display_validation_results(self, service_id: str = None):
        """Display validation results in a nice format"""
        if service_id:
            # Validate single service
            is_valid, message = self.validate_one(service_id)
            
            print(f"\nValidating: {service_id}")
            print("─" * 70)
            
            if is_valid:
                print(f"✓ {message}")
            else:
                print(f"✗ {message}")
        else:
            # Validate all services
            valid, invalid = self.validate_all()
            
            print("\n" + "=" * 70)
            print("MANIFEST VALIDATION RESULTS")
            print("=" * 70)
            
            if valid:
                print(f"\n✓ Valid manifests ({len(valid)}):")
                for service_id in sorted(valid):
                    try:
                        manifest = self.loader.load(service_id)
                        print(f"  • {service_id:<20} {manifest.name} v{manifest.version}")
                    except:
                        print(f"  • {service_id}")
            
            if invalid:
                print(f"\n✗ Invalid manifests ({len(invalid)}):")
                for service_id, error in invalid:
                    print(f"\n  • {service_id}:")
                    # Indent error message
                    for line in error.split('\n'):
                        print(f"    {line}")
            
            print("\n" + "=" * 70)
            print(f"Summary: {len(valid)} valid, {len(invalid)} invalid")
            print("=" * 70)
            
            if invalid:
                return 1
            return 0


if __name__ == '__main__':
    validator = ManifestValidator()
    
    if len(sys.argv) > 1:
        service_id = sys.argv[1]
        validator.display_validation_results(service_id)
    else:
        exit_code = validator.display_validation_results()
        sys.exit(exit_code)