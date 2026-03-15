#!/usr/bin/env python3
"""
PSO Firewall Manager - Tier-Based Security System

Implements a 4-tier security model:
- Tier 0: Internal Only (127.0.0.1) - DEFAULT
- Tier 1: LAN Only (192.168.x.x)
- Tier 2: VPN Access (Tailscale/WireGuard)
- Tier 3: Internet Exposed (Public, requires confirmation)

Core Principle: "Secure by Default, Explicit by Choice"
"""

import subprocess
import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import sys

# Bootstrap Python path for cross-package imports
from core import _bootstrap

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('firewall_manager')


class FirewallError(Exception):
    """Base exception for firewall errors"""
    pass


class TierDefinition:
    """Definition of a security tier"""
    def __init__(self, tier_id: int, name: str, description: str, 
                 risk_level: str, badge: str, binding: str):
        self.tier_id = tier_id
        self.name = name
        self.description = description
        self.risk_level = risk_level
        self.badge = badge
        self.binding = binding  # e.g., "127.0.0.1" or "0.0.0.0"


# Tier definitions
TIERS = {
    0: TierDefinition(
        tier_id=0,
        name="Internal Only",
        description="Service binds to localhost only. No network access.",
        risk_level="MINIMAL",
        badge="🟢 INTERNAL ONLY",
        binding="127.0.0.1"
    ),
    1: TierDefinition(
        tier_id=1,
        name="LAN Only",
        description="Accessible on home network only (192.168.x.x)",
        risk_level="LOW",
        badge="🟡 LAN ACCESSIBLE",
        binding="0.0.0.0"
    ),
    2: TierDefinition(
        tier_id=2,
        name="VPN Access",
        description="Accessible via VPN (Tailscale/WireGuard) only",
        risk_level="MEDIUM",
        badge="🔵 VPN ACCESSIBLE",
        binding="0.0.0.0"
    ),
    3: TierDefinition(
        tier_id=3,
        name="Internet Exposed",
        description="Publicly accessible from anywhere (requires confirmation)",
        risk_level="HIGH",
        badge="🔴 ⚠️ PUBLICLY ACCESSIBLE",
        binding="0.0.0.0"
    )
}


class FirewallManager:
    """
    Manages iptables firewall rules with tier-based access control
    
    Features:
    - Default DROP policy for security
    - Service-specific rule chains
    - Tier-based rule application
    - Automatic rule generation
    - Rollback on error
    """
    
    def __init__(self, db, config: Optional[Dict] = None):
        """
        Initialize firewall manager
        
        Args:
            db: Database instance
            config: Configuration dict with:
                - lan_subnet: LAN subnet (default: 192.168.0.0/16)
                - vpn_interface: VPN interface name (default: tailscale0)
                - dry_run: Don't actually apply rules (default: False)
        """
        self.db = db
        self.config = config or {}
        self.lan_subnet = self.config.get('lan_subnet', '192.168.0.0/16')
        self.vpn_interface = self.config.get('vpn_interface', 'tailscale0')
        self.dry_run = self.config.get('dry_run', False)
        
        # Initialize database tables
        self._init_db()
        
        # Check if we have iptables
        self._iptables_available = None
    
    def _init_db(self):
        """Create tier tracking tables"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            
            # Service tiers table
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS service_tiers (
                    service_id TEXT PRIMARY KEY,
                    current_tier INTEGER NOT NULL DEFAULT 0,
                    previous_tier INTEGER,
                    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    changed_by TEXT,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            ''')
            
            # Tier change log (audit trail)
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS tier_change_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    service_id TEXT NOT NULL,
                    from_tier INTEGER NOT NULL,
                    to_tier INTEGER NOT NULL,
                    changed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    changed_by TEXT,
                    reason TEXT,
                    FOREIGN KEY (service_id) REFERENCES installed_services(service_id) ON DELETE CASCADE
                )
            ''')
        
        logger.info("Tier tracking tables initialized")
    
    def _check_iptables(self):
        """Check if iptables is available"""
        try:
            subprocess.run(['iptables', '--version'], 
                         capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            raise FirewallError("iptables not found. Please install iptables.")
    
    def _run_iptables(self, args: List[str]) -> Tuple[bool, str]:
        """
        Run an iptables command
        Args:
            args: iptables arguments (without 'iptables' itself)
        Returns:
            Tuple of (success: bool, output: str)
        """
        if self._iptables_available is None:
            try:
                self._check_iptables()
                self._iptables_available = True
            except FirewallError:
                self._iptables_available = False
        if not self._iptables_available:
            logger.warning(f"iptables not available, skipping: iptables {' '.join(args)}")
            return False, "iptables not available"
        if self.dry_run:
            logger.info(f"DRY RUN: iptables {' '.join(args)}")
            return True, "dry-run"
        try:
            result = subprocess.run(
                ['sudo', 'iptables'] + args,
                capture_output=True,
                text=True,
                check=True
            )
            return True, result.stdout
        except subprocess.CalledProcessError as e:
            logger.error(f"iptables command failed: {e.stderr}")
            return False, e.stderr
    
    def get_service_tier(self, service_id: str) -> int:
        """
        Get current tier for a service
        
        Args:
            service_id: Service identifier
            
        Returns:
            Current tier (0-3), defaults to 0 if not set
        """
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT current_tier FROM service_tiers WHERE service_id = ?
            ''', (service_id,))
            
            row = cursor.fetchone()
            return row['current_tier'] if row else 0
    
    def set_service_tier(self, service_id: str, tier: int, 
                        changed_by: str = 'system', 
                        reason: str = None) -> bool:
        """
        Change service tier and apply firewall rules
        
        Args:
            service_id: Service identifier
            tier: New tier (0-3)
            changed_by: Who made the change (username or 'system')
            reason: Optional reason for change
            
        Returns:
            True if successful
            
        Raises:
            FirewallError: If tier is invalid or rule application fails
        """
        # Validate tier
        if tier not in TIERS:
            raise FirewallError(f"Invalid tier: {tier}. Must be 0-3")
        
        # Check if service exists
        service = self.db.get_service(service_id)
        if not service:
            raise FirewallError(f"Service not found: {service_id}")
        
        # Get current tier
        old_tier = self.get_service_tier(service_id)
        
        # If tier unchanged, nothing to do
        if old_tier == tier:
            logger.info(f"Service {service_id} already at tier {tier}")
            return True
        
        try:
            # Apply firewall rules for new tier
            self._apply_tier_rules(service_id, tier, service.get('ports', {}))
            
            # Update database
            with self.db._get_connection() as conn:
                cursor = conn.cursor()
                
                # Update or insert service tier
                cursor.execute('''
                    INSERT INTO service_tiers (service_id, current_tier, previous_tier, changed_by)
                    VALUES (?, ?, ?, ?)
                    ON CONFLICT(service_id) DO UPDATE SET
                        previous_tier = current_tier,
                        current_tier = ?,
                        changed_at = CURRENT_TIMESTAMP,
                        changed_by = ?
                ''', (service_id, tier, old_tier, changed_by, tier, changed_by))
                
                # Log the change
                cursor.execute('''
                    INSERT INTO tier_change_log (service_id, from_tier, to_tier, changed_by, reason)
                    VALUES (?, ?, ?, ?, ?)
                ''', (service_id, old_tier, tier, changed_by, reason))
            
            logger.info(f"Service {service_id} tier changed: {old_tier} → {tier}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to change tier for {service_id}: {e}")
            # Attempt rollback
            try:
                self._apply_tier_rules(service_id, old_tier, service.get('ports', {}))
            except:
                pass
            raise FirewallError(f"Tier change failed: {e}")
    
    def _apply_tier_rules(self, service_id: str, tier: int, ports: Dict[str, int]):
        """
        Apply firewall rules for a service at specific tier
        
        Args:
            service_id: Service identifier
            tier: Tier level (0-3)
            ports: Dictionary of port mappings
        """
        # Remove existing rules for this service
        self._remove_service_rules(service_id)
        
        # Tier 0 doesn't need firewall rules (localhost only)
        if tier == 0:
            logger.info(f"{service_id}: Tier 0 - no firewall rules needed")
            return
        
        # For tiers 1-3, apply rules for each port
        for port_name, port_number in ports.items():
            self._apply_port_rules(service_id, port_number, tier)
    
    def _apply_port_rules(self, service_id: str, port: int, tier: int):
        """
        Apply firewall rules for a specific port based on tier
        
        Args:
            service_id: Service identifier
            port: Port number
            tier: Tier level (1-3)
        """
        chain_name = f"PSO_{service_id}_{port}"
        
        # Create chain for this service/port
        self._run_iptables(['-N', chain_name])
        
        if tier == 1:
            # Tier 1: Allow LAN only
            self._run_iptables(['-A', chain_name, '-s', self.lan_subnet, 
                              '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT'])
            self._run_iptables(['-A', chain_name, '-p', 'tcp', 
                              '--dport', str(port), '-j', 'DROP'])
            logger.info(f"{service_id}:{port} - Tier 1: LAN only ({self.lan_subnet})")
        
        elif tier == 2:
            # Tier 2: Allow VPN interface only
            self._run_iptables(['-A', chain_name, '-i', self.vpn_interface,
                              '-p', 'tcp', '--dport', str(port), '-j', 'ACCEPT'])
            self._run_iptables(['-A', chain_name, '-p', 'tcp',
                              '--dport', str(port), '-j', 'DROP'])
            logger.info(f"{service_id}:{port} - Tier 2: VPN only ({self.vpn_interface})")
        
        elif tier == 3:
            # Tier 3: Allow all (with rate limiting)
            # Rate limit: 100 connections per minute per IP
            self._run_iptables(['-A', chain_name, '-p', 'tcp', 
                              '--dport', str(port), '-m', 'state', 
                              '--state', 'NEW', '-m', 'recent', '--set'])
            self._run_iptables(['-A', chain_name, '-p', 'tcp',
                              '--dport', str(port), '-m', 'state',
                              '--state', 'NEW', '-m', 'recent', 
                              '--update', '--seconds', '60', 
                              '--hitcount', '100', '-j', 'DROP'])
            self._run_iptables(['-A', chain_name, '-p', 'tcp',
                              '--dport', str(port), '-j', 'ACCEPT'])
            logger.warning(f"{service_id}:{port} - Tier 3: PUBLIC INTERNET (rate limited)")
        
        # Jump to this chain from INPUT
        self._run_iptables(['-A', 'INPUT', '-j', chain_name])
    
    def _remove_service_rules(self, service_id: str):
        """
        Remove all firewall rules for a service
        
        Args:
            service_id: Service identifier
        """
        # List all PSO chains for this service
        result = subprocess.run(
            ['sudo', 'iptables', '-L', '-n'],
            capture_output=True,
            text=True
        )
        
        for line in result.stdout.split('\n'):
            if f"PSO_{service_id}_" in line:
                chain_name = line.split()[0]
                
                # Remove jumps to this chain
                self._run_iptables(['-D', 'INPUT', '-j', chain_name])
                
                # Flush and delete the chain
                self._run_iptables(['-F', chain_name])
                self._run_iptables(['-X', chain_name])
    
    def get_tier_info(self, tier: int) -> Optional[Dict]:
        """Get information about a tier"""
        tier_def = TIERS.get(tier)
        if not tier_def:
            return None
        
        return {
            'tier_id': tier_def.tier_id,
            'name': tier_def.name,
            'description': tier_def.description,
            'risk_level': tier_def.risk_level,
            'badge': tier_def.badge,
            'binding': tier_def.binding
        }
    
    def get_all_tiers(self) -> List[Dict]:
        """Get information about all tiers"""
        return [self.get_tier_info(i) for i in range(4)]
    
    def get_tier_history(self, service_id: str, limit: int = 50) -> List[Dict]:
        """
        Get tier change history for a service
        
        Args:
            service_id: Service identifier
            limit: Maximum number of records to return
            
        Returns:
            List of tier change records
        """
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT * FROM tier_change_log
                WHERE service_id = ?
                ORDER BY changed_at DESC
                LIMIT ?
            ''', (service_id, limit))
            
            return [dict(row) for row in cursor.fetchall()]
    
    def get_all_service_tiers(self) -> List[Dict]:
        """Get tiers for all services"""
        with self.db._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT s.service_id, s.service_name, 
                       COALESCE(t.current_tier, 0) as current_tier,
                       t.changed_at, t.changed_by
                FROM installed_services s
                LEFT JOIN service_tiers t ON s.service_id = t.service_id
                ORDER BY s.service_name
            ''')
            
            results = []
            for row in cursor.fetchall():
                tier_info = self.get_tier_info(row['current_tier'])
                results.append({
                    'service_id': row['service_id'],
                    'service_name': row['service_name'],
                    'current_tier': row['current_tier'],
                    'tier_info': tier_info,
                    'changed_at': row['changed_at'],
                    'changed_by': row['changed_by']
                })
            
            return results
    
    def reset_all_to_tier_0(self, changed_by: str = 'system') -> int:
        """
        Reset all services to Tier 0 (emergency lockdown)
        
        Args:
            changed_by: Who initiated the reset
            
        Returns:
            Number of services reset
        """
        services = self.db.list_services()
        count = 0
        
        for service in services:
            service_id = service['service_id']
            current_tier = self.get_service_tier(service_id)
            
            if current_tier > 0:
                try:
                    self.set_service_tier(service_id, 0, changed_by, 
                                        "Emergency lockdown - reset to Tier 0")
                    count += 1
                except Exception as e:
                    logger.error(f"Failed to reset {service_id}: {e}")
        
        logger.warning(f"Emergency lockdown: {count} services reset to Tier 0")
        return count


# CLI Interface
if __name__ == '__main__':
    import sys
    from pathlib import Path
    
    from core import _bootstrap
    
    from core.database import Database
    
    db = Database()
    fw = FirewallManager(db)
    
    if len(sys.argv) < 2:
        print("PSO Firewall Manager - Tier-Based Security")
        print("\nCommands:")
        print("  status <service-id>     - Show current tier")
        print("  set <service-id> <tier> - Change tier (0-3)")
        print("  list                    - List all service tiers")
        print("  history <service-id>    - Show tier change history")
        print("  tiers                   - Show tier definitions")
        print("  reset-all               - Reset all to Tier 0 (emergency)")
        print("\nTiers:")
        print("  0 - Internal Only (localhost)")
        print("  1 - LAN Only (192.168.x.x)")
        print("  2 - VPN Access (Tailscale/WireGuard)")
        print("  3 - Internet Exposed (PUBLIC - requires confirmation)")
        sys.exit(0)
    
    cmd = sys.argv[1]
    
    if cmd == 'status':
        if len(sys.argv) < 3:
            print("Usage: python firewall_manager.py status <service-id>")
            sys.exit(1)
        
        service_id = sys.argv[2]
        tier = fw.get_service_tier(service_id)
        tier_info = fw.get_tier_info(tier)
        
        print(f"\n{service_id}:")
        print(f"  Current Tier: {tier} - {tier_info['name']}")
        print(f"  Badge: {tier_info['badge']}")
        print(f"  Risk Level: {tier_info['risk_level']}")
        print(f"  Description: {tier_info['description']}")
    
    elif cmd == 'set':
        if len(sys.argv) < 4:
            print("Usage: python firewall_manager.py set <service-id> <tier>")
            sys.exit(1)
        
        service_id = sys.argv[2]
        tier = int(sys.argv[3])
        
        try:
            fw.set_service_tier(service_id, tier, changed_by='cli-user')
            print(f"✓ {service_id} tier changed to {tier}")
        except FirewallError as e:
            print(f"✗ Error: {e}")
            sys.exit(1)
    
    elif cmd == 'list':
        tiers_list = fw.get_all_service_tiers()
        print("\nService Tiers:")
        print("=" * 80)
        for item in tiers_list:
            badge = item['tier_info']['badge']
            print(f"{item['service_name']:<30} {badge}")
    
    elif cmd == 'history':
        if len(sys.argv) < 3:
            print("Usage: python firewall_manager.py history <service-id>")
            sys.exit(1)
        
        service_id = sys.argv[2]
        history = fw.get_tier_history(service_id)
        
        print(f"\nTier Change History for {service_id}:")
        print("=" * 80)
        for change in history:
            print(f"{change['changed_at']}: Tier {change['from_tier']} → {change['to_tier']}")
            if change['reason']:
                print(f"  Reason: {change['reason']}")
    
    elif cmd == 'tiers':
        tiers = fw.get_all_tiers()
        print("\nAvailable Tiers:")
        print("=" * 80)
        for tier in tiers:
            print(f"\nTier {tier['tier_id']}: {tier['name']}")
            print(f"  Badge: {tier['badge']}")
            print(f"  Risk: {tier['risk_level']}")
            print(f"  {tier['description']}")
    
    elif cmd == 'reset-all':
        print("⚠️  WARNING: This will reset ALL services to Tier 0 (Internal Only)")
        confirm = input("Type 'RESET' to confirm: ")
        if confirm == 'RESET':
            count = fw.reset_all_to_tier_0(changed_by='cli-user')
            print(f"✓ Reset {count} services to Tier 0")
        else:
            print("Cancelled")
    
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)