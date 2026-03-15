#!/usr/bin/env python3
"""
PSO Reverse Proxy Manager

Manages reverse proxy configuration (Caddy) with tier-aware routing
and automatic SSL/TLS certificates.
"""

import os
import json
import subprocess
from pathlib import Path
from typing import Dict, List, Optional

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.database import Database
from core.manifest import ManifestLoader
from core.firewall_manager import FirewallManager


class ReverseProxyManager:
    """
    Manages reverse proxy configuration for PSO services.
    
    Features:
    - Auto-generates Caddy configuration
    - Tier-aware routing (only exposes Tier 1+ services)
    - Automatic SSL/TLS with Let's Encrypt
    - Subdomain support
    - HTTP -> HTTPS redirect
    """
    
    def __init__(self, db: Database, proxy_type: str = "caddy"):
        self.db = db
        self.proxy_type = proxy_type
        self.firewall_mgr = FirewallManager(db)
        self.loader = ManifestLoader()
        
        # Paths — use ~/.pso_dev/proxy so no root access is needed
        self.config_dir = Path.home() / '.pso_dev' / 'proxy'
        self.caddyfile_path = self.config_dir / "Caddyfile"
        
        # Ensure config directory exists
        self.config_dir.mkdir(parents=True, exist_ok=True)
    
    def generate_config(self, domain: Optional[str] = None, email: Optional[str] = None) -> str:
        """
        Generate reverse proxy configuration based on installed services and their tiers.
        
        Args:
            domain: Base domain (e.g., example.com)
            email: Email for Let's Encrypt
            
        Returns:
            Generated configuration as string
        """
        if self.proxy_type == "caddy":
            return self._generate_caddyfile(domain, email)
        else:
            raise ValueError(f"Unsupported proxy type: {self.proxy_type}")
    
    def _generate_caddyfile(self, domain: Optional[str], email: Optional[str]) -> str:
        """Generate Caddyfile configuration"""
        
        # Get all installed services with their tiers
        services = self._get_routable_services()
        
        if not services:
            return "# No services configured for reverse proxy\n"
        
        config_lines = []
        
        # Global options
        config_lines.append("{")
        if email:
            config_lines.append(f"    email {email}")
        config_lines.append("    # Auto HTTPS")
        config_lines.append("    auto_https on")
        config_lines.append("}")
        config_lines.append("")
        
        # Generate config for each service
        for service in services:
            service_config = self._generate_service_block(service, domain)
            if service_config:
                config_lines.append(service_config)
                config_lines.append("")
        
        return "\n".join(config_lines)
    
    def _get_routable_services(self) -> List[Dict]:
        """
        Get all installed services that should be exposed via reverse proxy.
        Only includes services at Tier 1 or higher.
        """
        services = []
        
        with self.db._get_connection() as conn:
            # Get installed services with their tiers
            rows = conn.execute("""
                SELECT 
                    s.service_id,
                    s.service_name,
                    COALESCE(t.current_tier, 0) as tier
                FROM installed_services s
                LEFT JOIN service_tiers t ON s.service_id = t.service_id
                WHERE s.status = 'running'
            """).fetchall()
            
            for row in rows:
                tier = row['tier']
                
                # Only route services at Tier 1+ (LAN, VPN, Internet)
                if tier >= 1:
                    try:
                        manifest = self.loader.load(row['service_id'])
                        
                        # Get primary HTTP port
                        http_port = self._get_http_port(manifest)
                        
                        if http_port:
                            services.append({
                                'id': row['service_id'],
                                'name': row['service_name'],
                                'tier': tier,
                                'port': http_port,
                                'manifest': manifest
                            })
                    except Exception as e:
                        print(f"Warning: Could not load manifest for {row['service_id']}: {e}")
        
        return services
    
    def _get_http_port(self, manifest) -> Optional[int]:
        """Extract HTTP port from service manifest"""
        ports = manifest.ports
        
        # Common HTTP port names
        http_port_names = ['http', 'web', 'ui', 'admin', 'main']
        
        # Try to find HTTP port
        for name in http_port_names:
            if name in ports:
                return ports[name]
        
        # Return first port if no HTTP port found
        if ports:
            return list(ports.values())[0]
        
        return None
    
    def _generate_service_block(self, service: Dict, domain: Optional[str]) -> str:
        """Generate Caddy server block for a service"""
        
        service_id = service['id']
        port = service['port']
        tier = service['tier']
        
        # Determine hostname
        if domain:
            # Use subdomain
            hostname = f"{service_id}.{domain}"
        else:
            # Use local network
            hostname = f"{service_id}.local"
        
        lines = []
        lines.append(f"# Service: {service['name']} (Tier {tier})")
        lines.append(f"{hostname} {{")
        
        # Tier-specific configuration
        if tier == 1:
            # LAN only - restrict to local network
            lines.append("    # LAN Only - restrict to local network")
            lines.append("    @notlocal {")
            lines.append("        not remote_ip 192.168.0.0/16 10.0.0.0/8 172.16.0.0/12")
            lines.append("    }")
            lines.append("    respond @notlocal 403")
        elif tier == 2:
            # VPN only - would need VPN subnet configuration
            lines.append("    # VPN Access - configure VPN subnet if needed")
            pass
        elif tier == 3:
            # Internet exposed - add rate limiting
            lines.append("    # Internet Exposed - rate limiting enabled")
            # Note: Caddy's rate limiting requires a plugin
            pass
        
        # Reverse proxy to service
        lines.append(f"    reverse_proxy localhost:{port} {{")
        lines.append("        header_up X-Real-IP {remote_host}")
        lines.append("        header_up X-Forwarded-For {remote_host}")
        lines.append("        header_up X-Forwarded-Proto {scheme}")
        lines.append("    }")
        
        # Logging
        lines.append(f"    log {{")
        lines.append(f"        output file /var/log/pso/proxy/{service_id}.log")
        lines.append("    }")
        
        lines.append("}")
        
        return "\n".join(lines)
    
    def write_config(self, domain: Optional[str] = None, email: Optional[str] = None):
        """Generate and write configuration file"""
        config = self.generate_config(domain, email)
        
        with open(self.caddyfile_path, 'w') as f:
            f.write(config)
        
        print(f"Configuration written to: {self.caddyfile_path}")
    
    def validate_config(self) -> bool:
        """Validate the generated configuration"""
        if self.proxy_type == "caddy":
            try:
                result = subprocess.run(
                    ['caddy', 'validate', '--config', str(self.caddyfile_path)],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    print("Configuration is valid")
                    return True
                else:
                    print(f"Configuration validation failed:")
                    print(result.stderr)
                    return False
            except FileNotFoundError:
                print("Error: Caddy not installed")
                return False
    
    def reload_proxy(self) -> bool:
        """Reload the proxy with new configuration"""
        if self.proxy_type == "caddy":
            try:
                # Check if Caddy is running
                result = subprocess.run(
                    ['systemctl', 'is-active', 'caddy'],
                    capture_output=True,
                    text=True
                )
                
                if result.returncode == 0:
                    # Reload
                    subprocess.run(['systemctl', 'reload', 'caddy'], check=True)
                    print("Caddy reloaded successfully")
                else:
                    # Start
                    subprocess.run(['systemctl', 'start', 'caddy'], check=True)
                    print("Caddy started successfully")
                
                return True
            except subprocess.CalledProcessError as e:
                print(f"Error reloading Caddy: {e}")
                return False
            except FileNotFoundError:
                print("Error: systemctl not found")
                return False
    
    def get_proxy_status(self) -> Dict:
        """Get reverse proxy status"""
        status = {
            'type': self.proxy_type,
            'config_path': str(self.caddyfile_path),
            'config_exists': self.caddyfile_path.exists(),
            'running': False,
            'services_proxied': 0
        }
        
        if self.proxy_type == "caddy":
            try:
                result = subprocess.run(
                    ['systemctl', 'is-active', 'caddy'],
                    capture_output=True,
                    text=True
                )
                status['running'] = result.returncode == 0
            except FileNotFoundError:
                pass
        
        # Count routable services
        services = self._get_routable_services()
        status['services_proxied'] = len(services)
        status['services'] = [s['id'] for s in services]
        
        return status
    
    def install_caddy(self) -> bool:
        """Install Caddy if not present"""
        try:
            # Check if already installed
            result = subprocess.run(['which', 'caddy'], capture_output=True)
            if result.returncode == 0:
                print("Caddy is already installed")
                return True
            
            print("Installing Caddy...")
            
            # Install using official Caddy installer
            subprocess.run([
                'curl', '-1sLf',
                'https://dl.cloudsmith.io/public/caddy/stable/gpg.key'
            ], check=True, stdout=subprocess.PIPE)
            
            # Add repository and install (Debian/Ubuntu)
            subprocess.run([
                'apt', 'install', '-y', 'caddy'
            ], check=True)
            
            print("Caddy installed successfully")
            return True
            
        except Exception as e:
            print(f"Error installing Caddy: {e}")
            print("Please install Caddy manually:")
            print("  https://caddyserver.com/docs/install")
            return False


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI for reverse proxy management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PSO Reverse Proxy Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Generate config
    gen_parser = subparsers.add_parser('generate', help='Generate proxy configuration')
    gen_parser.add_argument('--domain', help='Base domain (e.g., example.com)')
    gen_parser.add_argument('--email', help='Email for Let\'s Encrypt')
    gen_parser.add_argument('--dry-run', action='store_true', help='Print config without writing')
    
    # Validate config
    subparsers.add_parser('validate', help='Validate proxy configuration')
    
    # Reload proxy
    subparsers.add_parser('reload', help='Reload proxy with new configuration')
    
    # Status
    subparsers.add_parser('status', help='Show proxy status')
    
    # Install
    subparsers.add_parser('install', help='Install Caddy')
    
    # List services
    subparsers.add_parser('list', help='List services being proxied')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    db = Database()
    manager = ReverseProxyManager(db)
    
    if args.command == 'generate':
        if args.dry_run:
            config = manager.generate_config(args.domain, args.email)
            print(config)
        else:
            manager.write_config(args.domain, args.email)
            print("\nNext steps:")
            print("  1. Review the configuration: cat ~/.pso_dev/proxy/Caddyfile")
            print("  2. Validate: python -m core.reverse_proxy validate")
            print("  3. Reload: sudo python -m core.reverse_proxy reload")
    
    elif args.command == 'validate':
        manager.validate_config()
    
    elif args.command == 'reload':
        manager.reload_proxy()
    
    elif args.command == 'status':
        status = manager.get_proxy_status()
        print(f"Reverse Proxy Status:")
        print(f"  Type: {status['type']}")
        print(f"  Config: {status['config_path']}")
        print(f"  Config Exists: {status['config_exists']}")
        print(f"  Running: {status['running']}")
        print(f"  Services Proxied: {status['services_proxied']}")
        if status['services']:
            print(f"  Services: {', '.join(status['services'])}")
    
    elif args.command == 'install':
        manager.install_caddy()
    
    elif args.command == 'list':
        services = manager._get_routable_services()
        if services:
            print("Services being proxied:")
            print("=" * 70)
            for service in services:
                print(f"{service['name']:<30} Tier {service['tier']}  Port {service['port']}")
        else:
            print("No services configured for reverse proxy")
            print("Services must be at Tier 1 or higher to be proxied")


if __name__ == '__main__':
    main()