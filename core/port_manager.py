#!/usr/bin/env python3
"""
Port Management for PSO

Automatically tracks port allocations across all services.
"""

import socket
import sys
from typing import Dict, List, Set, Tuple
from collections import defaultdict

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.manifest import ManifestLoader
from core.database import Database


class PortManager:
    """Manages port allocations and detects conflicts"""
    
    # Port range definitions
    PORT_RANGES = {
        'infrastructure': (80, 8099),
        'productivity': (8100, 8199),
        'media': (8200, 8299),
        'monitoring': (8300, 8399),
        'networking': (8400, 8499),
        'automation': (8500, 8599),
        'database': (9000, 9999),
        'high': (11000, 65535)
    }
    
    def __init__(self):
        self.loader = ManifestLoader()
        self.db = Database()
    
    def scan_all_ports(self) -> Dict[str, Dict[int, str]]:
        """
        Scan all manifests and return port allocations
        
        Returns:
            Dict mapping service_id to {port: purpose}
        """
        allocations = {}
        
        for service_id in self.loader.list_available():
            try:
                manifest = self.loader.load(service_id)
                if manifest.ports:
                    allocations[service_id] = manifest.ports
            except Exception:
                continue
        
        return allocations
    
    def get_all_used_ports(self) -> Set[int]:
        """Get set of all ports used by any service"""
        used = set()
        allocations = self.scan_all_ports()
        
        for service_ports in allocations.values():
            used.update(service_ports.values())
        
        return used
    
    def is_port_available(self, port: int) -> Tuple[bool, str]:
        """
        Check if a port is available
        
        Returns:
            (is_available, reason)
        """
        # Check if port is in use by the system
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('0.0.0.0', port))
            sock.close()
            system_available = True
        except OSError:
            system_available = False
        
        # Check if port is allocated in manifests
        allocations = self.scan_all_ports()
        for service_id, ports in allocations.items():
            if port in ports.values():
                return False, f"Allocated to {service_id}"
        
        # Check if port is used by installed service
        try:
            conflicts = self.db.get_port_conflicts({port: port})
            if conflicts:
                service_id = conflicts[0][2]
                return False, f"Used by installed service: {service_id}"
        except Exception:
            pass  # socket already closed or not bound
        
        if not system_available:
            return False, "In use by system"
        
        return True, "Available"
    
    def get_available_in_range(self, range_name: str) -> List[int]:
        """Get available ports in a specific range"""
        if range_name not in self.PORT_RANGES:
            return []
        
        start, end = self.PORT_RANGES[range_name]
        used = self.get_all_used_ports()
        
        available = []
        for port in range(start, min(end + 1, start + 100)):  # Limit to 100 ports
            if port not in used:
                available.append(port)
        
        return available
    
    def display_allocations(self):
        """Display all port allocations in a nice format"""
        allocations = self.scan_all_ports()
        
        if not allocations:
            print("No services with port allocations found")
            return
        
        # Group by port range
        by_range = defaultdict(list)
        for service_id, ports in allocations.items():
            try:
                manifest = self.loader.load(service_id)
                for port_name, port_num in ports.items():
                    # Determine which range this port belongs to
                    range_name = self._get_range_for_port(port_num)
                    by_range[range_name].append((service_id, manifest.name, port_num, port_name))
            except:
                continue
        
        print("\n" + "=" * 80)
        print("PORT ALLOCATIONS")
        print("=" * 80)
        
        for range_name in ['infrastructure', 'productivity', 'media', 'monitoring', 
                          'networking', 'automation', 'database', 'high']:
            if range_name not in by_range:
                continue
            
            start, end = self.PORT_RANGES[range_name]
            print(f"\n{range_name.upper()} ({start}-{end}):")
            print("-" * 80)
            
            # Sort by port number
            for service_id, service_name, port, purpose in sorted(by_range[range_name], key=lambda x: x[2]):
                print(f"  {port:<6} {service_name:<25} ({purpose})")
        
        print("\n" + "=" * 80)
        total_ports = sum(len(ports) for ports in allocations.values())
        print(f"Total ports allocated: {total_ports}")
        print("=" * 80)
    
    def display_available(self):
        """Display available ports by range"""
        print("\n" + "=" * 80)
        print("AVAILABLE PORTS BY RANGE")
        print("=" * 80)
        
        for range_name, (start, end) in self.PORT_RANGES.items():
            available = self.get_available_in_range(range_name)
            
            print(f"\n{range_name.upper()} ({start}-{end}):")
            if available[:10]:  # Show first 10
                ports_str = ', '.join(str(p) for p in available[:10])
                print(f"  {ports_str}")
                if len(available) > 10:
                    print(f"  ... and {len(available) - 10} more")
            else:
                print("  (All allocated)")
        
        print("\n" + "=" * 80)
    
    def check_port(self, port: int):
        """Display status of a specific port"""
        available, reason = self.is_port_available(port)
        
        print(f"\nPort {port}:")
        print("-" * 40)
        
        if available:
            print(f"✓ Available")
            range_name = self._get_range_for_port(port)
            if range_name:
                print(f"  Range: {range_name}")
        else:
            print(f"✗ Not available")
            print(f"  Reason: {reason}")
    
    def _get_range_for_port(self, port: int) -> str:
        """Determine which range a port belongs to"""
        for range_name, (start, end) in self.PORT_RANGES.items():
            if start <= port <= end:
                return range_name
        return 'other'


if __name__ == '__main__':
    import sys
    
    pm = PortManager()
    
    if len(sys.argv) < 2:
        pm.display_allocations()
    elif sys.argv[1] == 'available':
        pm.display_available()
    elif sys.argv[1] == 'check':
        if len(sys.argv) < 3:
            print("Usage: python port_manager.py check <port>")
            sys.exit(1)
        try:
            port = int(sys.argv[2])
            pm.check_port(port)
        except ValueError:
            print("Error: Port must be a number")
            sys.exit(1)
    else:
        print("Usage: python port_manager.py [available|check <port>]")
        sys.exit(1)