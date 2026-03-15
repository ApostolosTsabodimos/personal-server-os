#!/usr/bin/env python3
"""
Test uninstall cleanup to verify all resources are freed.
"""
import sqlite3
from pathlib import Path
from core import _bootstrap
from core.database import Database

def test_uninstall_cleanup():
    """Verify that uninstall properly cleans up all resources."""

    # Use test database
    test_db = Path("/tmp/test_pso_uninstall.db")
    if test_db.exists():
        test_db.unlink()

    db = Database(db_path=test_db)

    # Simulate installing a service
    print("1. Adding test service...")
    service_data = {
        'service_id': 'test-nginx',
        'service_name': 'Test Nginx',
        'version': '1.0.0',
        'category': 'web',
        'status': 'stopped',
        'installation_method': 'docker',
        'ports': {'http': 8080, 'https': 8443},
        'volumes': [{'host': '/data', 'container': '/var/www', 'readonly': False}],
        'dependencies': ['test-redis']
    }
    db.add_service(service_data)

    # Verify service was added
    conn = sqlite3.connect(test_db)

    services = conn.execute("SELECT * FROM installed_services WHERE service_id='test-nginx'").fetchall()
    ports = conn.execute("SELECT * FROM service_ports WHERE service_id='test-nginx'").fetchall()
    volumes = conn.execute("SELECT * FROM service_volumes WHERE service_id='test-nginx'").fetchall()
    deps = conn.execute("SELECT * FROM service_dependencies WHERE service_id='test-nginx'").fetchall()

    print(f"   ✓ Services: {len(services)}")
    print(f"   ✓ Ports: {len(ports)}")
    print(f"   ✓ Volumes: {len(volumes)}")
    print(f"   ✓ Dependencies: {len(deps)}")

    # Now uninstall
    print("\n2. Uninstalling test service...")
    db.remove_service('test-nginx')

    # Verify everything was cleaned up
    services_after = conn.execute("SELECT * FROM installed_services WHERE service_id='test-nginx'").fetchall()
    ports_after = conn.execute("SELECT * FROM service_ports WHERE service_id='test-nginx'").fetchall()
    volumes_after = conn.execute("SELECT * FROM service_volumes WHERE service_id='test-nginx'").fetchall()
    deps_after = conn.execute("SELECT * FROM service_dependencies WHERE service_id='test-nginx'").fetchall()

    conn.close()

    print(f"\n3. Verifying cleanup:")
    print(f"   Services remaining: {len(services_after)} (should be 0)")
    print(f"   Ports remaining: {len(ports_after)} (should be 0)")
    print(f"   Volumes remaining: {len(volumes_after)} (should be 0)")
    print(f"   Dependencies remaining: {len(deps_after)} (should be 0)")

    if len(services_after) == 0 and len(ports_after) == 0 and len(volumes_after) == 0 and len(deps_after) == 0:
        print("\n✅ SUCCESS: All database records properly cleaned up!")
        return True
    else:
        print("\n❌ FAILURE: Some records were not cleaned up!")
        return False

if __name__ == '__main__':
    success = test_uninstall_cleanup()
    exit(0 if success else 1)
