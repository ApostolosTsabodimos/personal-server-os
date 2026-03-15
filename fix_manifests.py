#!/usr/bin/env python3
"""
Patch all service manifests with correct container_port values.
Run from ~/personal-server-os/

For single-port services: sets top-level container_port
For multi-port services: sets installation.port_mappings {port_name: container_port}
  and removes top-level container_port if it was wrong
"""
import json, sys
from pathlib import Path

# Single-port services: container_port is what the app listens on inside Docker
SINGLE_PORT = {
    'docmost':      3000,   # host 8100 -> container 3000
    'filebrowser':  80,     # host 8101 -> container 80
    'firefly-iii':  8080,   # host 8082 -> container 8080
    'grafana':      3000,   # host 8300 -> container 3000
    'homeassistant':8123,   # host 8123 -> container 8123
    'homer':        8080,   # host 8081 -> container 8080
    'immich':       2283,   # host 8202 -> container 2283
    'influxdb':     8086,   # host 8086 -> container 8086
    'prowlarr':     9696,   # host 8203 -> container 9696
    'tautulli':     8181,   # host 8301 -> container 8181
    'trilium':      8080,   # host 8102 -> container 8080
    'uptime-kuma':  3001,   # host 8302 -> container 3001
    'vaultwarden':  80,     # host 8103 -> container 80
    'zigbee2mqtt':  8080,   # host 8580 -> container 8080
}

# Multi-port services: port_name -> container_port
# host ports stay as defined in manifest.ports
MULTI_PORT = {
    'jellyfin': {
        'http':  8096,  # host 8200 -> container 8096
        'https': 8920,  # host 8201 -> container 8920
    },
    'mosquitto': {
        'mqtt':      1883,  # host 1883 -> container 1883
        'websocket': 9001,  # host 9001 -> container 9001
    },
    'nextcloud-aio': {
        'admin':  80,    # host 8090 -> container 80
        'apache': 11000, # host 11000 -> container 11000
    },
    'nginx': {
        'http':  80,   # host 80  -> container 80
        'https': 443,  # host 443 -> container 443
    },
    'pihole': {
        'web': 80,  # host 8400 -> container 80
        'dns': 53,  # host 53   -> container 53
    },
    'portainer': {
        'http': 9000,  # host 9000 -> container 9000
        'edge': 8000,  # host 8000 -> container 8000
    },
}

# Skip entirely (VPN client, no web ports to map)
SKIP = {'airvpn'}

services_dir = Path('services')
if not services_dir.exists():
    print("ERROR: run from ~/personal-server-os/")
    sys.exit(1)

fixed = 0
already_correct = 0
skipped = 0

all_services = {s.name for s in services_dir.iterdir() if (s / 'manifest.json').exists()}
handled = set(SINGLE_PORT) | set(MULTI_PORT) | SKIP
unhandled = all_services - handled
if unhandled:
    print(f"WARNING: No mapping defined for: {sorted(unhandled)}")
    print()

for service_id in sorted(all_services):
    manifest_path = services_dir / service_id / 'manifest.json'
    data = json.load(open(manifest_path))

    if service_id in SKIP:
        print(f"  SKIP: {service_id}")
        skipped += 1
        continue

    changed = False

    if service_id in SINGLE_PORT:
        cp = SINGLE_PORT[service_id]
        if data.get('container_port') != cp:
            data['container_port'] = cp
            # Remove any stale port_mappings from installation block
            data.get('installation', {}).pop('port_mappings', None)
            changed = True

    elif service_id in MULTI_PORT:
        mappings = MULTI_PORT[service_id]
        install = data.setdefault('installation', {})
        if install.get('port_mappings') != mappings:
            install['port_mappings'] = mappings
            changed = True
        # Remove top-level container_port — port_mappings takes precedence
        if 'container_port' in data:
            del data['container_port']
            changed = True

    if changed:
        with open(manifest_path, 'w') as f:
            json.dump(data, f, indent=2)
        print(f"  FIXED: {service_id}")
        fixed += 1
    else:
        already_correct += 1

print(f"\nDone: {fixed} fixed, {already_correct} already correct, {skipped} skipped")