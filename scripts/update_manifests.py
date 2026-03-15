#!/usr/bin/env python3
"""
Update all service manifests with GitHub repository URLs and official websites
"""

import json
from pathlib import Path

# Complete service metadata mapping
SERVICE_METADATA = {
    'nginx': {
        'github_repo': 'https://github.com/nginx/nginx',
        'website': 'https://nginx.org'
    },
    'portainer': {
        'github_repo': 'https://github.com/portainer/portainer',
        'website': 'https://www.portainer.io'
    },
    'homer': {
        'github_repo': 'https://github.com/bastienwirtz/homer'
    },
    'firefly-iii': {
        'github_repo': 'https://github.com/firefly-iii/firefly-iii',
        'website': 'https://www.firefly-iii.org'
    },
    'homeassistant': {
        'github_repo': 'https://github.com/home-assistant/core',
        'website': 'https://www.home-assistant.io'
    },
    'airvpn': {
        'github_repo': 'https://github.com/dperson/openvpn-client'
    },
    'nextcloud-aio': {
        'github_repo': 'https://github.com/nextcloud/all-in-one',
        'website': 'https://nextcloud.com'
    },
    'docmost': {
        'github_repo': 'https://github.com/docmost/docmost'
    },
    'filebrowser': {
        'github_repo': 'https://github.com/filebrowser/filebrowser'
    },
    'trilium': {
        'github_repo': 'https://github.com/zadam/trilium'
    },
    'vaultwarden': {
        'github_repo': 'https://github.com/dani-garcia/vaultwarden'
    },
    'jellyfin': {
        'github_repo': 'https://github.com/jellyfin/jellyfin',
        'website': 'https://jellyfin.org'
    },
    'immich': {
        'github_repo': 'https://github.com/immich-app/immich'
    },
    'prowlarr': {
        'github_repo': 'https://github.com/Prowlarr/Prowlarr'
    },
    'tautulli': {
        'github_repo': 'https://github.com/Tautulli/Tautulli'
    },
    'grafana': {
        'github_repo': 'https://github.com/grafana/grafana',
        'website': 'https://grafana.com'
    },
    'uptime-kuma': {
        'github_repo': 'https://github.com/louislam/uptime-kuma'
    },
    'influxdb': {
        'github_repo': 'https://github.com/influxdata/influxdb',
        'website': 'https://www.influxdata.com'
    },
    'pihole': {
        'github_repo': 'https://github.com/pi-hole/pi-hole',
        'website': 'https://pi-hole.net'
    },
    'zigbee2mqtt': {
        'github_repo': 'https://github.com/Koenkk/zigbee2mqtt'
    },
    'mosquitto': {
        'github_repo': 'https://github.com/eclipse/mosquitto'
    },
}

def update_manifest(service_id, metadata):
    """Update a single manifest with GitHub repo and website"""
    manifest_path = Path('services') / service_id / 'manifest.json'
    
    if not manifest_path.exists():
        print(f"⚠️  Manifest not found: {manifest_path}")
        return False
    
    try:
        with open(manifest_path, 'r') as f:
            manifest = json.load(f)
        
        # Ensure metadata section exists
        if 'metadata' not in manifest:
            manifest['metadata'] = {}
        
        # Add GitHub repo
        if 'github_repo' in metadata:
            manifest['metadata']['github_repo'] = metadata['github_repo']
        
        # Add website if it exists
        if 'website' in metadata:
            manifest['metadata']['website'] = metadata['website']
        
        # Write back with nice formatting
        with open(manifest_path, 'w') as f:
            json.dump(manifest, f, indent=2)
        
        links = []
        if 'github_repo' in metadata:
            links.append('GitHub')
        if 'website' in metadata:
            links.append('Website')
        
        print(f"✓ Updated {service_id:20s} [{', '.join(links)}]")
        return True
        
    except Exception as e:
        print(f"✗ Error updating {service_id}: {e}")
        return False

def main():
    print("=" * 70)
    print("Updating Service Manifests with GitHub Repos and Websites")
    print("=" * 70)
    print()
    
    updated = 0
    failed = 0
    
    for service_id, metadata in SERVICE_METADATA.items():
        if update_manifest(service_id, metadata):
            updated += 1
        else:
            failed += 1
    
    print()
    print("=" * 70)
    print(f"✓ Updated: {updated}")
    print(f"✗ Failed: {failed}")
    print("=" * 70)
    print()
    print("Summary:")
    print(f"  - Services with both Website + GitHub: 9")
    print(f"  - Services with GitHub only: 12")
    print()
    print("Next steps:")
    print("  1. Replace web/api.py and web/static/app.js")
    print("  2. Restart the API: python web/api.py")
    print("  3. Refresh browser - links will appear on service cards!")

if __name__ == '__main__':
    main()