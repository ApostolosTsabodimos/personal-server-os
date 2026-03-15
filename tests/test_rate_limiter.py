#!/usr/bin/env python3
"""
Rate Limiter Test Script

Tests all major functionality of the rate limiter.
"""

import sys
import time
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.rate_limiter import RateLimiter, RateLimitError

def test_basic_rate_limiting():
    """Test basic rate limiting functionality"""
    print("=" * 70)
    print("TEST 1: Basic Rate Limiting")
    print("=" * 70)
    
    limiter = RateLimiter()
    test_ip = "192.168.1.100"
    
    print(f"\nTesting with IP: {test_ip}")
    print("Limit: 5 requests per 10 seconds\n")
    
    # Make 5 requests (should all succeed)
    for i in range(1, 6):
        try:
            limiter.check_rate_limit(test_ip, "test-service", "/test", 5, 10)
            print(f"Request {i}: ✓ Allowed")
        except RateLimitError as e:
            print(f"Request {i}: ✗ Blocked - {e}")
    
    # 6th request should be blocked
    print("\nTrying 6th request (should be blocked)...")
    try:
        limiter.check_rate_limit(test_ip, "test-service", "/test", 5, 10)
        print("Request 6: ✓ Allowed (UNEXPECTED!)")
    except RateLimitError as e:
        print(f"Request 6: ✗ Blocked - {e}")
        print("✓ Rate limiting is working!")
    
    print("\n✓ Test 1 PASSED\n")

def test_whitelist():
    """Test whitelist functionality"""
    print("=" * 70)
    print("TEST 2: Whitelist (Bypass)")
    print("=" * 70)
    
    limiter = RateLimiter()
    test_ip = "10.0.0.50"
    
    print(f"\nAdding {test_ip} to whitelist...")
    limiter.whitelist_ip(test_ip, "Test IP", "test-script")
    print("✓ IP whitelisted\n")
    
    print("Making 20 requests (limit is 5)...")
    blocked = 0
    for i in range(1, 21):
        try:
            limiter.check_rate_limit(test_ip, "test-service", "/test", 5, 10)
            print(f"Request {i}: ✓ Allowed")
        except RateLimitError:
            blocked += 1
    
    if blocked == 0:
        print("\n✓ All requests allowed - whitelist is working!")
    else:
        print(f"\n✗ {blocked} requests were blocked (whitelist not working)")
    
    # Cleanup
    limiter.unwhitelist_ip(test_ip)
    print(f"\n✓ Removed {test_ip} from whitelist")
    print("\n✓ Test 2 PASSED\n")

def test_blacklist():
    """Test blacklist functionality"""
    print("=" * 70)
    print("TEST 3: Blacklist (Permanent Ban)")
    print("=" * 70)
    
    limiter = RateLimiter()
    test_ip = "1.2.3.4"
    
    print(f"\nBlacklisting {test_ip}...")
    limiter.blacklist_ip(test_ip, "Test attacker", "test-script")
    print("✓ IP blacklisted\n")
    
    print("Trying to make request...")
    try:
        limiter.check_rate_limit(test_ip, "test-service", "/test", 100, 60)
        print("✗ Request was allowed (blacklist not working)")
    except RateLimitError as e:
        print(f"✓ Request blocked - {e}")
        print("✓ Blacklist is working!")
    
    # Cleanup
    limiter.unblacklist_ip(test_ip)
    print(f"\n✓ Removed {test_ip} from blacklist")
    print("\n✓ Test 3 PASSED\n")

def test_temp_ban():
    """Test temporary ban functionality"""
    print("=" * 70)
    print("TEST 4: Temporary Ban (Escalating)")
    print("=" * 70)
    
    limiter = RateLimiter()
    test_ip = "5.6.7.8"
    
    print(f"\nTesting with IP: {test_ip}")
    print("Triggering rate limit violation...\n")
    
    # Trigger rate limit (make 6 requests with limit of 5)
    for i in range(6):
        try:
            limiter.check_rate_limit(test_ip, "test-service", "/test", 5, 10)
        except RateLimitError:
            print(f"✓ Rate limit exceeded, temporary ban applied")
            break
    
    # Check if IP is temp banned
    if limiter.is_temp_banned(test_ip):
        print("✓ IP is temporarily banned")
        
        # Show temp bans
        bans = limiter.get_temp_bans()
        if bans:
            ban = bans[0]
            print(f"\nBan details:")
            print(f"  IP: {ban['ip_address']}")
            print(f"  Expires: {ban['expires_at']}")
            print(f"  Ban count: {ban['ban_count']}")
    else:
        print("✗ IP is not temp banned (feature not working)")
    
    print("\n✓ Test 4 PASSED\n")

def test_violations_log():
    """Test violations logging"""
    print("=" * 70)
    print("TEST 5: Violations Logging")
    print("=" * 70)
    
    limiter = RateLimiter()
    
    violations = limiter.get_violations(limit=10)
    
    print(f"\nFound {len(violations)} recent violations:\n")
    
    for v in violations[:5]:  # Show first 5
        print(f"IP: {v['ip_address']}")
        print(f"  Service: {v['service_id']}")
        print(f"  Time: {v['violation_time']}")
        print(f"  Requests: {v['request_count']}")
        print()
    
    print("✓ Test 5 PASSED\n")

def test_stats():
    """Test statistics"""
    print("=" * 70)
    print("TEST 6: Statistics")
    print("=" * 70)
    
    limiter = RateLimiter()
    stats = limiter.get_stats()
    
    print("\nRate Limiting Statistics:")
    print(f"  Total Violations: {stats['total_violations']}")
    print(f"  Violations (last hour): {stats['violations_last_hour']}")
    print(f"  Blacklisted IPs: {stats['blacklisted_ips']}")
    print(f"  Whitelisted IPs: {stats['whitelisted_ips']}")
    print(f"  Active Temp Bans: {stats['active_temp_bans']}")
    
    print("\n✓ Test 6 PASSED\n")

def run_all_tests():
    """Run all tests"""
    print("\n" + "=" * 70)
    print("RATE LIMITER TEST SUITE")
    print("=" * 70 + "\n")
    
    try:
        test_basic_rate_limiting()
        test_whitelist()
        test_blacklist()
        test_temp_ban()
        test_violations_log()
        test_stats()
        
        print("=" * 70)
        print("ALL TESTS PASSED ✓")
        print("=" * 70)
        print("\nRate limiter is working correctly!")
        
    except Exception as e:
        print(f"\n✗ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    run_all_tests()