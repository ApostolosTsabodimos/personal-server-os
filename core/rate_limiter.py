#!/usr/bin/env python3
"""
PSO Rate Limiter & DDoS Protection

Protects services (especially Tier 3) from abuse with rate limiting,
automatic IP banning, and fail2ban integration.
"""

import os
import time
import subprocess
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from collections import defaultdict

# Bootstrap Python path for cross-package imports
from core import _bootstrap

from core.database import Database


class RateLimitError(Exception):
    """Exception raised when rate limit is exceeded"""
    pass


class RateLimiter:
    """
    Rate limiting and DDoS protection for PSO services.
    
    Features:
    - Per-IP rate limiting
    - Automatic temporary bans
    - Permanent IP blacklist
    - IP whitelist (bypass rate limits)
    - fail2ban integration
    - Request tracking and analytics
    """
    
    def __init__(self):
        self.db = Database()
        
        # In-memory rate limit tracking
        self.request_counts = defaultdict(lambda: defaultdict(list))
        
        # Initialize database tables
        self._init_tables()
    
    def _init_tables(self):
        """Create rate limiting tables"""
        with self.db._get_connection() as conn:
            # IP blacklist (permanent bans)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ip_blacklist (
                    ip_address TEXT PRIMARY KEY,
                    reason TEXT,
                    banned_at TEXT NOT NULL,
                    banned_by TEXT DEFAULT 'system'
                )
            """)
            
            # IP whitelist (bypass rate limits)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS ip_whitelist (
                    ip_address TEXT PRIMARY KEY,
                    reason TEXT,
                    added_at TEXT NOT NULL,
                    added_by TEXT DEFAULT 'system'
                )
            """)
            
            # Temporary bans (auto-expire)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS temp_bans (
                    ip_address TEXT PRIMARY KEY,
                    service_id TEXT,
                    reason TEXT,
                    banned_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    ban_count INTEGER DEFAULT 1
                )
            """)
            
            # Rate limit violations log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS rate_limit_violations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    ip_address TEXT NOT NULL,
                    service_id TEXT,
                    endpoint TEXT,
                    violation_time TEXT NOT NULL,
                    request_count INTEGER,
                    action_taken TEXT
                )
            """)
            
            conn.commit()
    
    def check_rate_limit(self, ip_address: str, service_id: str, 
                         endpoint: str = "/", 
                         max_requests: int = 100,
                         window_seconds: int = 60) -> bool:
        """
        Check if IP is within rate limits.
        
        Args:
            ip_address: Client IP
            service_id: Service being accessed
            endpoint: Specific endpoint (optional)
            max_requests: Max requests allowed in window
            window_seconds: Time window in seconds
            
        Returns:
            True if within limits, raises RateLimitError if exceeded
        """
        # Check if IP is whitelisted
        if self.is_whitelisted(ip_address):
            return True
        
        # Check if IP is blacklisted
        if self.is_blacklisted(ip_address):
            raise RateLimitError(f"IP {ip_address} is blacklisted")
        
        # Check if IP has temporary ban
        if self.is_temp_banned(ip_address):
            raise RateLimitError(f"IP {ip_address} is temporarily banned")
        
        # Track this request
        current_time = time.time()
        key = f"{service_id}:{endpoint}"
        
        # Add current request
        self.request_counts[ip_address][key].append(current_time)
        
        # Remove old requests outside window
        cutoff_time = current_time - window_seconds
        self.request_counts[ip_address][key] = [
            t for t in self.request_counts[ip_address][key] 
            if t > cutoff_time
        ]
        
        # Count requests in window
        request_count = len(self.request_counts[ip_address][key])
        
        # Check if limit exceeded
        if request_count > max_requests:
            # Log violation
            self._log_violation(ip_address, service_id, endpoint, request_count)
            
            # Apply temporary ban
            self._apply_temp_ban(ip_address, service_id, request_count)
            
            raise RateLimitError(
                f"Rate limit exceeded: {request_count}/{max_requests} requests in {window_seconds}s"
            )
        
        return True
    
    def is_blacklisted(self, ip_address: str) -> bool:
        """Check if IP is permanently blacklisted"""
        with self.db._get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM ip_blacklist WHERE ip_address = ?",
                (ip_address,)
            ).fetchone()
            return result is not None
    
    def is_whitelisted(self, ip_address: str) -> bool:
        """Check if IP is whitelisted"""
        with self.db._get_connection() as conn:
            result = conn.execute(
                "SELECT 1 FROM ip_whitelist WHERE ip_address = ?",
                (ip_address,)
            ).fetchone()
            return result is not None
    
    def is_temp_banned(self, ip_address: str) -> bool:
        """Check if IP has active temporary ban"""
        with self.db._get_connection() as conn:
            result = conn.execute("""
                SELECT expires_at FROM temp_bans 
                WHERE ip_address = ?
            """, (ip_address,)).fetchone()
            
            if result:
                expires_at = datetime.fromisoformat(result['expires_at'])
                if datetime.now() < expires_at:
                    return True
                else:
                    # Ban expired, remove it
                    conn.execute(
                        "DELETE FROM temp_bans WHERE ip_address = ?",
                        (ip_address,)
                    )
                    conn.commit()
            
            return False
    
    def blacklist_ip(self, ip_address: str, reason: str, banned_by: str = "admin"):
        """Add IP to permanent blacklist"""
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ip_blacklist (ip_address, reason, banned_at, banned_by)
                VALUES (?, ?, ?, ?)
            """, (ip_address, reason, datetime.now().isoformat(), banned_by))
            conn.commit()
        
        # Also add to iptables if available
        self._add_iptables_block(ip_address)
    
    def whitelist_ip(self, ip_address: str, reason: str, added_by: str = "admin"):
        """Add IP to whitelist (bypass rate limits)"""
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO ip_whitelist (ip_address, reason, added_at, added_by)
                VALUES (?, ?, ?, ?)
            """, (ip_address, reason, datetime.now().isoformat(), added_by))
            conn.commit()
    
    def unblacklist_ip(self, ip_address: str):
        """Remove IP from blacklist"""
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM ip_blacklist WHERE ip_address = ?", (ip_address,))
            conn.commit()
        
        # Remove from iptables
        self._remove_iptables_block(ip_address)
    
    def unwhitelist_ip(self, ip_address: str):
        """Remove IP from whitelist"""
        with self.db._get_connection() as conn:
            conn.execute("DELETE FROM ip_whitelist WHERE ip_address = ?", (ip_address,))
            conn.commit()
    
    def _apply_temp_ban(self, ip_address: str, service_id: str, request_count: int):
        """Apply temporary ban to IP"""
        # Ban duration increases with repeated violations
        base_duration = 300  # 5 minutes
        
        with self.db._get_connection() as conn:
            # Check if IP has existing bans
            result = conn.execute(
                "SELECT ban_count FROM temp_bans WHERE ip_address = ?",
                (ip_address,)
            ).fetchone()
            
            if result:
                ban_count = result['ban_count'] + 1
            else:
                ban_count = 1
            
            # Calculate ban duration (doubles each time, max 24 hours)
            duration_seconds = min(base_duration * (2 ** (ban_count - 1)), 86400)
            expires_at = datetime.now() + timedelta(seconds=duration_seconds)
            
            conn.execute("""
                INSERT OR REPLACE INTO temp_bans 
                (ip_address, service_id, reason, banned_at, expires_at, ban_count)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                ip_address,
                service_id,
                f"Rate limit exceeded ({request_count} requests)",
                datetime.now().isoformat(),
                expires_at.isoformat(),
                ban_count
            ))
            conn.commit()
        
        print(f"Temporarily banned {ip_address} for {duration_seconds}s (ban #{ban_count})")
    
    def _log_violation(self, ip_address: str, service_id: str, 
                      endpoint: str, request_count: int):
        """Log rate limit violation"""
        with self.db._get_connection() as conn:
            conn.execute("""
                INSERT INTO rate_limit_violations 
                (ip_address, service_id, endpoint, violation_time, request_count, action_taken)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (
                ip_address,
                service_id,
                endpoint,
                datetime.now().isoformat(),
                request_count,
                "temp_ban"
            ))
            conn.commit()
    
    def get_violations(self, limit: int = 100) -> List[Dict]:
        """Get recent rate limit violations"""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM rate_limit_violations
                ORDER BY violation_time DESC
                LIMIT ?
            """, (limit,)).fetchall()
            
            return [dict(row) for row in rows]
    
    def get_blacklist(self) -> List[Dict]:
        """Get all blacklisted IPs"""
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT * FROM ip_blacklist ORDER BY banned_at DESC").fetchall()
            return [dict(row) for row in rows]
    
    def get_whitelist(self) -> List[Dict]:
        """Get all whitelisted IPs"""
        with self.db._get_connection() as conn:
            rows = conn.execute("SELECT * FROM ip_whitelist ORDER BY added_at DESC").fetchall()
            return [dict(row) for row in rows]
    
    def get_temp_bans(self) -> List[Dict]:
        """Get active temporary bans"""
        with self.db._get_connection() as conn:
            rows = conn.execute("""
                SELECT * FROM temp_bans 
                WHERE expires_at > ?
                ORDER BY banned_at DESC
            """, (datetime.now().isoformat(),)).fetchall()
            
            return [dict(row) for row in rows]
    
    def _add_iptables_block(self, ip_address: str):
        """Add IP to iptables DROP rule"""
        try:
            subprocess.run([
                'iptables', '-I', 'INPUT', '-s', ip_address, '-j', 'DROP'
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass  # iptables may not be available
        except FileNotFoundError:
            pass  # iptables not installed
    
    def _remove_iptables_block(self, ip_address: str):
        """Remove IP from iptables DROP rule"""
        try:
            subprocess.run([
                'iptables', '-D', 'INPUT', '-s', ip_address, '-j', 'DROP'
            ], check=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass
        except FileNotFoundError:
            pass
    
    def cleanup_expired_bans(self):
        """Remove expired temporary bans"""
        with self.db._get_connection() as conn:
            conn.execute("""
                DELETE FROM temp_bans 
                WHERE expires_at < ?
            """, (datetime.now().isoformat(),))
            conn.commit()
    
    def get_stats(self) -> Dict:
        """Get rate limiting statistics"""
        with self.db._get_connection() as conn:
            stats = {
                'total_violations': conn.execute(
                    "SELECT COUNT(*) as count FROM rate_limit_violations"
                ).fetchone()['count'],
                'blacklisted_ips': conn.execute(
                    "SELECT COUNT(*) as count FROM ip_blacklist"
                ).fetchone()['count'],
                'whitelisted_ips': conn.execute(
                    "SELECT COUNT(*) as count FROM ip_whitelist"
                ).fetchone()['count'],
                'active_temp_bans': conn.execute("""
                    SELECT COUNT(*) as count FROM temp_bans 
                    WHERE expires_at > ?
                """, (datetime.now().isoformat(),)).fetchone()['count'],
                'violations_last_hour': conn.execute("""
                    SELECT COUNT(*) as count FROM rate_limit_violations
                    WHERE violation_time > ?
                """, ((datetime.now() - timedelta(hours=1)).isoformat(),)).fetchone()['count']
            }
            
            return stats


# ============================================================================
# CLI Interface
# ============================================================================

def main():
    """CLI for rate limiting management"""
    import argparse
    
    parser = argparse.ArgumentParser(description='PSO Rate Limiter & DDoS Protection')
    subparsers = parser.add_subparsers(dest='command', help='Commands')
    
    # Blacklist IP
    blacklist_parser = subparsers.add_parser('blacklist', help='Add IP to blacklist')
    blacklist_parser.add_argument('ip', help='IP address to blacklist')
    blacklist_parser.add_argument('--reason', required=True, help='Reason for blacklisting')
    
    # Unblacklist IP
    unblacklist_parser = subparsers.add_parser('unblacklist', help='Remove IP from blacklist')
    unblacklist_parser.add_argument('ip', help='IP address to unblacklist')
    
    # Whitelist IP
    whitelist_parser = subparsers.add_parser('whitelist', help='Add IP to whitelist')
    whitelist_parser.add_argument('ip', help='IP address to whitelist')
    whitelist_parser.add_argument('--reason', required=True, help='Reason for whitelisting')
    
    # Unwhitelist IP
    unwhitelist_parser = subparsers.add_parser('unwhitelist', help='Remove IP from whitelist')
    unwhitelist_parser.add_argument('ip', help='IP address to unwhitelist')
    
    # List blacklist
    subparsers.add_parser('list-blacklist', help='Show blacklisted IPs')
    
    # List whitelist
    subparsers.add_parser('list-whitelist', help='Show whitelisted IPs')
    
    # List temp bans
    subparsers.add_parser('list-bans', help='Show temporary bans')
    
    # List violations
    violations_parser = subparsers.add_parser('violations', help='Show rate limit violations')
    violations_parser.add_argument('--limit', type=int, default=50, help='Number of violations to show')
    
    # Stats
    subparsers.add_parser('stats', help='Show rate limiting statistics')
    
    # Cleanup
    subparsers.add_parser('cleanup', help='Remove expired bans')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    limiter = RateLimiter()
    
    if args.command == 'blacklist':
        limiter.blacklist_ip(args.ip, args.reason)
        print(f"✓ Blacklisted {args.ip}")
        print(f"Reason: {args.reason}")
    
    elif args.command == 'unblacklist':
        limiter.unblacklist_ip(args.ip)
        print(f"✓ Removed {args.ip} from blacklist")
    
    elif args.command == 'whitelist':
        limiter.whitelist_ip(args.ip, args.reason)
        print(f"✓ Whitelisted {args.ip}")
        print(f"Reason: {args.reason}")
    
    elif args.command == 'unwhitelist':
        limiter.unwhitelist_ip(args.ip)
        print(f"✓ Removed {args.ip} from whitelist")
    
    elif args.command == 'list-blacklist':
        blacklist = limiter.get_blacklist()
        if not blacklist:
            print("No blacklisted IPs")
        else:
            print(f"Blacklisted IPs ({len(blacklist)}):")
            print("=" * 80)
            for entry in blacklist:
                print(f"\n{entry['ip_address']}")
                print(f"  Reason: {entry['reason']}")
                print(f"  Banned: {entry['banned_at']}")
                print(f"  By: {entry['banned_by']}")
    
    elif args.command == 'list-whitelist':
        whitelist = limiter.get_whitelist()
        if not whitelist:
            print("No whitelisted IPs")
        else:
            print(f"Whitelisted IPs ({len(whitelist)}):")
            print("=" * 80)
            for entry in whitelist:
                print(f"\n{entry['ip_address']}")
                print(f"  Reason: {entry['reason']}")
                print(f"  Added: {entry['added_at']}")
                print(f"  By: {entry['added_by']}")
    
    elif args.command == 'list-bans':
        bans = limiter.get_temp_bans()
        if not bans:
            print("No active temporary bans")
        else:
            print(f"Active Temporary Bans ({len(bans)}):")
            print("=" * 80)
            for ban in bans:
                print(f"\n{ban['ip_address']}")
                print(f"  Service: {ban['service_id']}")
                print(f"  Reason: {ban['reason']}")
                print(f"  Banned: {ban['banned_at']}")
                print(f"  Expires: {ban['expires_at']}")
                print(f"  Ban Count: {ban['ban_count']}")
    
    elif args.command == 'violations':
        violations = limiter.get_violations(args.limit)
        if not violations:
            print("No violations logged")
        else:
            print(f"Rate Limit Violations (last {len(violations)}):")
            print("=" * 80)
            for v in violations:
                print(f"\n{v['violation_time']}")
                print(f"  IP: {v['ip_address']}")
                print(f"  Service: {v['service_id']}")
                print(f"  Endpoint: {v['endpoint']}")
                print(f"  Requests: {v['request_count']}")
                print(f"  Action: {v['action_taken']}")
    
    elif args.command == 'stats':
        stats = limiter.get_stats()
        print("Rate Limiting Statistics:")
        print("=" * 80)
        print(f"Total Violations: {stats['total_violations']}")
        print(f"Violations (last hour): {stats['violations_last_hour']}")
        print(f"Blacklisted IPs: {stats['blacklisted_ips']}")
        print(f"Whitelisted IPs: {stats['whitelisted_ips']}")
        print(f"Active Temp Bans: {stats['active_temp_bans']}")
    
    elif args.command == 'cleanup':
        limiter.cleanup_expired_bans()
        print("✓ Cleaned up expired bans")


if __name__ == '__main__':
    main()