# PSO Service Recommendations
# This file marks which services are essential/recommended

# Format:
# service_id: priority_level, category, tags

ESSENTIAL = []

RECOMMENDED = [
    "vaultwarden",      # Password manager - store credentials securely
    "nginx",            # Reverse proxy - for SSL/TLS termination
]

CATEGORIES = {
    # Security & Infrastructure
    "vaultwarden": {
        "category": "security",
        "tags": ["recommended", "passwords", "security", "essential-for-production"],
        "priority": 1,
        "why_recommended": "Securely store all service passwords, API keys, and credentials",
        "tier_recommendation": 2,  # VPN access
        "setup_difficulty": "easy"
    },
    "nginx": {
        "category": "infrastructure",
        "tags": ["recommended", "reverse-proxy", "ssl"],
        "priority": 2,
        "why_recommended": "Required for SSL/TLS and subdomain routing (Tier 1+)",
        "tier_recommendation": 1,
        "setup_difficulty": "medium"
    },
    
    # Media Services
    "jellyfin": {
        "category": "media",
        "tags": ["media", "streaming", "popular"],
        "priority": 5,
        "why_recommended": "Best open-source media server",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    "plex": {
        "category": "media",
        "tags": ["media", "streaming", "alternative"],
        "priority": 6,
        "why_recommended": "Alternative to Jellyfin with more polish",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    "navidrome": {
        "category": "media",
        "tags": ["media", "music"],
        "priority": 7,
        "why_recommended": "Music streaming server",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    
    # Productivity
    "nextcloud": {
        "category": "productivity",
        "tags": ["productivity", "files", "collaboration"],
        "priority": 4,
        "why_recommended": "Self-hosted alternative to Google Drive/Dropbox",
        "tier_recommendation": 2,
        "setup_difficulty": "medium"
    },
    "paperless-ngx": {
        "category": "productivity",
        "tags": ["productivity", "documents"],
        "priority": 8,
        "why_recommended": "Document management and OCR",
        "tier_recommendation": 1,
        "setup_difficulty": "medium"
    },
    "bookstack": {
        "category": "productivity",
        "tags": ["productivity", "wiki", "documentation"],
        "priority": 9,
        "why_recommended": "Wiki and documentation platform",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    
    # Development
    "gitea": {
        "category": "development",
        "tags": ["development", "git", "popular"],
        "priority": 5,
        "why_recommended": "Lightweight self-hosted Git service",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    "gitlab": {
        "category": "development",
        "tags": ["development", "git", "ci-cd"],
        "priority": 10,
        "why_recommended": "Full-featured Git platform with CI/CD",
        "tier_recommendation": 1,
        "setup_difficulty": "hard"
    },
    "code-server": {
        "category": "development",
        "tags": ["development", "ide"],
        "priority": 8,
        "why_recommended": "VS Code in your browser",
        "tier_recommendation": 2,
        "setup_difficulty": "easy"
    },
    
    # Monitoring
    "uptime-kuma": {
        "category": "monitoring",
        "tags": ["monitoring", "uptime", "recommended"],
        "priority": 3,
        "why_recommended": "Beautiful uptime monitoring dashboard",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    "grafana": {
        "category": "monitoring",
        "tags": ["monitoring", "metrics", "visualization"],
        "priority": 6,
        "why_recommended": "Metrics visualization and dashboards",
        "tier_recommendation": 1,
        "setup_difficulty": "medium"
    },
    "prometheus": {
        "category": "monitoring",
        "tags": ["monitoring", "metrics"],
        "priority": 7,
        "why_recommended": "Metrics collection and storage",
        "tier_recommendation": 0,
        "setup_difficulty": "medium"
    },
    
    # Infrastructure
    "portainer": {
        "category": "infrastructure",
        "tags": ["infrastructure", "docker", "management"],
        "priority": 6,
        "why_recommended": "Web UI for Docker container management",
        "tier_recommendation": 1,
        "setup_difficulty": "easy"
    },
    "traefik": {
        "category": "infrastructure",
        "tags": ["infrastructure", "reverse-proxy", "alternative"],
        "priority": 8,
        "why_recommended": "Alternative reverse proxy with auto-SSL",
        "tier_recommendation": 1,
        "setup_difficulty": "hard"
    },
    "wireguard": {
        "category": "infrastructure",
        "tags": ["infrastructure", "vpn", "security", "recommended"],
        "priority": 3,
        "why_recommended": "VPN server for secure remote access (Tier 2)",
        "tier_recommendation": 3,
        "setup_difficulty": "medium"
    },
    
    # Home Automation
    "home-assistant": {
        "category": "home-automation",
        "tags": ["home-automation", "iot"],
        "priority": 7,
        "why_recommended": "Complete smart home platform",
        "tier_recommendation": 1,
        "setup_difficulty": "medium"
    },
    "node-red": {
        "category": "home-automation",
        "tags": ["home-automation", "automation", "workflows"],
        "priority": 9,
        "why_recommended": "Visual automation and workflow builder",
        "tier_recommendation": 1,
        "setup_difficulty": "medium"
    },
    
    # Downloaders (Media Stack)
    "sonarr": {
        "category": "media",
        "tags": ["media", "automation", "tv"],
        "priority": 10,
        "why_recommended": "TV show automation (works with Jellyfin)",
        "tier_recommendation": 0,
        "setup_difficulty": "medium"
    },
    "radarr": {
        "category": "media",
        "tags": ["media", "automation", "movies"],
        "priority": 10,
        "why_recommended": "Movie automation (works with Jellyfin)",
        "tier_recommendation": 0,
        "setup_difficulty": "medium"
    },
    "prowlarr": {
        "category": "media",
        "tags": ["media", "automation", "indexer"],
        "priority": 10,
        "why_recommended": "Indexer manager (works with Sonarr/Radarr)",
        "tier_recommendation": 0,
        "setup_difficulty": "medium"
    }
}

# Starter Packs
STARTER_PACKS = {
    "minimal": {
        "name": "Minimal Setup",
        "description": "Just PSO core - no external services",
        "services": []
    },
    "recommended": {
        "name": "Recommended Setup",
        "description": "Essential services for production use",
        "services": ["vaultwarden", "nginx", "uptime-kuma"]
    },
    "media": {
        "name": "Media Server",
        "description": "Complete media streaming setup",
        "services": ["vaultwarden", "nginx", "jellyfin", "sonarr", "radarr", "prowlarr"]
    },
    "productivity": {
        "name": "Productivity Suite",
        "description": "File sync, documents, and collaboration",
        "services": ["vaultwarden", "nextcloud", "paperless-ngx", "bookstack"]
    },
    "development": {
        "name": "Developer Tools",
        "description": "Git hosting and code editor",
        "services": ["vaultwarden", "gitea", "code-server", "portainer"]
    },
    "complete": {
        "name": "Home Server Complete",
        "description": "Full-featured home server setup",
        "services": [
            "vaultwarden", "nginx", "wireguard", "uptime-kuma",
            "jellyfin", "nextcloud", "gitea", "home-assistant"
        ]
    }
}

def get_recommended_services():
    """Get list of recommended services"""
    return RECOMMENDED

def get_service_info(service_id):
    """Get category and tags for a service"""
    return CATEGORIES.get(service_id, {
        "category": "other",
        "tags": [],
        "priority": 99,
        "setup_difficulty": "unknown"
    })

def get_services_by_category(category):
    """Get all services in a category"""
    return [
        service_id for service_id, info in CATEGORIES.items()
        if info.get("category") == category
    ]

def get_starter_pack(pack_name):
    """Get services in a starter pack"""
    return STARTER_PACKS.get(pack_name, {}).get("services", [])