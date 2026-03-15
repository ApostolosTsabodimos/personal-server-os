#!/usr/bin/env python3
"""
PSO Service Recommendations CLI

Show recommended services and starter packs.
"""

import sys
from pathlib import Path

# Add parent directory
sys.path.insert(0, str(Path(__file__).parent))

from service_recommendations import (
    get_recommended_services,
    get_service_info,
    get_services_by_category,
    get_starter_pack,
    STARTER_PACKS,
    CATEGORIES
)

def show_recommended():
    """Show recommended services"""
    print("\n" + "="*70)
    print("PSO RECOMMENDED SERVICES")
    print("="*70)
    
    print("\n🔴 ESSENTIAL FOR PRODUCTION:\n")
    
    # Get top priority services
    essential = [
        (sid, info) for sid, info in CATEGORIES.items()
        if info.get('priority', 99) <= 3
    ]
    essential.sort(key=lambda x: x[1]['priority'])
    
    for service_id, info in essential:
        print(f"  🔐 {service_id}")
        print(f"     {info['why_recommended']}")
        print(f"     Tier: {info['tier_recommendation']} | Difficulty: {info['setup_difficulty']}")
        print()
    
    print("\n" + "="*70)

def show_categories():
    """Show services by category"""
    print("\n" + "="*70)
    print("SERVICES BY CATEGORY")
    print("="*70)
    
    categories = {}
    for service_id, info in CATEGORIES.items():
        cat = info['category']
        if cat not in categories:
            categories[cat] = []
        categories[cat].append((service_id, info))
    
    for category in ['security', 'infrastructure', 'monitoring', 'productivity', 'media', 'development', 'home-automation']:
        if category not in categories:
            continue
        
        print(f"\n📁 {category.upper().replace('-', ' ')}")
        print("-" * 70)
        
        services = categories[category]
        services.sort(key=lambda x: x[1]['priority'])
        
        for service_id, info in services:
            tags_str = ", ".join(info['tags'][:3])
            print(f"  • {service_id:<20} {info['why_recommended']}")
            print(f"    Tags: {tags_str}")
        
        print()

def show_starter_packs():
    """Show starter pack options"""
    print("\n" + "="*70)
    print("STARTER PACKS - Quick Setup Options")
    print("="*70)
    
    for pack_id, pack_info in STARTER_PACKS.items():
        print(f"\n📦 {pack_info['name']}")
        print(f"   {pack_info['description']}")
        print(f"   Services: {', '.join(pack_info['services']) if pack_info['services'] else 'None'}")
        print(f"   Install: ./pso install-pack {pack_id}")

def main():
    if len(sys.argv) < 2:
        print("PSO Service Recommendations")
        print("\nCommands:")
        print("  recommended - Show recommended services")
        print("  categories  - Show services by category")
        print("  packs       - Show starter packs")
        print("  info <service> - Show service details")
        return
    
    command = sys.argv[1]
    
    if command == "recommended":
        show_recommended()
    elif command == "categories":
        show_categories()
    elif command == "packs":
        show_starter_packs()
    elif command == "info" and len(sys.argv) > 2:
        service_id = sys.argv[2]
        info = get_service_info(service_id)
        
        if info.get('priority') == 99:
            print(f"No recommendation info for: {service_id}")
        else:
            print(f"\n{service_id.upper()}")
            print("="*70)
            print(f"Category: {info['category']}")
            print(f"Priority: {info['priority']}")
            print(f"Why: {info['why_recommended']}")
            print(f"Recommended Tier: {info['tier_recommendation']}")
            print(f"Difficulty: {info['setup_difficulty']}")
            print(f"Tags: {', '.join(info['tags'])}")
    else:
        print(f"Unknown command: {command}")

if __name__ == '__main__':
    main()