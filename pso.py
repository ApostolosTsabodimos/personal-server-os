#!/usr/bin/env python3
"""
PSO - Personal Server OS Project Tracker
Automated component detection and progress tracking
"""

import json
import re
import sys
from pathlib import Path

class Colors:
    RESET = '\033[0m'
    BOLD = '\033[1m'
    GREEN = '\033[92m'
    BLUE = '\033[94m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    YELLOW = '\033[93m'
    CYAN = '\033[96m'


class PSO:
    """Project tracker with automated component detection"""
    
    # Component definitions - add new components here
    ARCHITECTURE = {
        # Core System (8 components)
        'installer': {
            'file': 'core/installer.py',
            'name': 'Installation & Bootstrap',
            'phase': 'Core System',
            'description': 'Service installation system with manifest support',
            'size_threshold': 5000
        },
        'service-manager': {
            'file': 'core/service_manager.py',
            'name': 'Service Manager',
            'phase': 'Core System',
            'description': 'Start/stop/restart services (Docker + systemd)',
            'size_threshold': 4000
        },
        'dependency-resolver': {
            'file': 'core/dependency_resolver.py',
            'name': 'Dependency Resolver',
            'phase': 'Core System',
            'description': 'Calculate install order and check conflicts',
            'size_threshold': 3000
        },
        'config-manager': {
            'file': 'core/config_manager.py',
            'name': 'Configuration Manager',
            'phase': 'Core System',
            'description': 'Template engine, env vars, validation, rollback',
            'size_threshold': 4000
        },
        'database': {
            'file': 'core/database.py',
            'name': 'Data Layer (SQLite)',
            'phase': 'Core System',
            'description': 'SQLite databases for services, health, users',
            'size_threshold': 4000
        },
        'backup': {
            'file': 'core/backup_manager.py',
            'name': 'Backup System',
            'phase': 'Core System',
            'description': 'Automated backups with retention policies',
            'size_threshold': 3000
        },
        'reverse-proxy': {
            'file': 'core/reverse_proxy.py',
            'name': 'Reverse Proxy Manager',
            'phase': 'Core System',
            'description': 'Auto-configure Caddy/Traefik with tier-aware routing, SSL/TLS',
            'size_threshold': 4000
        },
        'resource-manager': {
            'file': 'core/resource_manager.py',
            'name': 'Resource Manager',
            'phase': 'Core System',
            'description': 'CPU, memory, disk quotas with Docker enforcement',
            'size_threshold': 4000
        },
        
        # Services (4 components)
        'service-manifests': {
            'file': 'core/manifest.py',
            'name': 'Service Manifest System',
            'phase': 'Services',
            'description': 'JSON schema for service definitions',
            'size_threshold': 4000
        },
        'service-catalog': {
            'file': 'services/',
            'name': 'Services Catalog',
            'phase': 'Services',
            'description': 'Library of installable services',
            'detect': 'count_manifests'
        },
        'service-discovery': {
            'file': 'core/service_discovery.py',
            'name': 'Service Discovery',
            'phase': 'Services',
            'description': 'Internal DNS, service-to-service communication',
            'size_threshold': 4000
        },
        'migration-tools': {
            'file': 'core/migration_tools.py',
            'name': 'Migration & Import Tools',
            'phase': 'Services',
            'description': 'Import Docker Compose, migrate platforms',
            'size_threshold': 4000
        },
        
        # Interface (4 components)
        'cli-tool': {
            'file': 'pso',
            'name': 'CLI Tool',
            'phase': 'Interface',
            'description': 'Command-line interface',
            'size_threshold': 15000
        },
        'interactive-menu': {
            'file': 'pso-menu',
            'name': 'Interactive Menu',
            'phase': 'Interface',
            'description': 'Guided menu interface with tier management',
            'size_threshold': 15000
        },
        'web-ui': {
            'file': 'web/',
            'name': 'Web Dashboard',
            'phase': 'Interface',
            'description': 'Web-based control panel',
            'detect': 'check_web_dashboard'
        },
        'api': {
            'file': 'web/api.py',
            'name': 'REST API',
            'phase': 'Interface',
            'description': 'HTTP API for remote management',
            'size_threshold': 5000
        },
        
        # Monitoring (4 components)
        'health-monitor': {
            'file': 'core/health_monitor.py',
            'name': 'Health Monitor',
            'phase': 'Monitoring',
            'description': 'Continuous health checks and uptime monitoring',
            'size_threshold': 3000
        },
        'metrics': {
            'file': 'core/metrics.py',
            'name': 'Metrics Collection',
            'phase': 'Monitoring',
            'description': 'Prometheus-compatible metrics with time-series storage',
            'size_threshold': 500
        },
        'notification-service': {
            'file': 'core/notifications.py',
            'name': 'Notification Service',
            'phase': 'Monitoring',
            'description': 'Email/SMS/webhook alerts',
            'size_threshold': 2000
        },
        'dashboard-integration': {
            'file': 'core/grafana_integration.py',
            'name': 'Grafana Integration',
            'phase': 'Monitoring',
            'description': 'Metrics visualization and dashboards',
            'size_threshold': 2000
        },
        'log-aggregator': {
            'file': 'core/log_aggregator.py',
            'name': 'Log Aggregator',
            'phase': 'Monitoring',
            'description': 'Centralized log collection, search, and tailing across all services',
            'size_threshold': 3000
        },
        
        # Security (6 components)
        'auth': {
            'file': 'core/auth.py',
            'name': 'Authentication System',
            'phase': 'Security',
            'description': 'User accounts, JWT sessions, password hashing (bcrypt)',
            'size_threshold': 3000
        },
        'rbac': {
            'file': 'core/rbac.py',
            'name': 'Access Control (RBAC)',
            'phase': 'Security',
            'description': 'Role-based permissions and policies',
            'size_threshold': 2000
        },
        'firewall': {
            'file': 'core/firewall_manager.py',
            'name': 'Firewall & Tier System',
            'phase': 'Security',
            'description': '4-tier security model (Internal/LAN/VPN/Internet) with iptables',
            'size_threshold': 4000
        },
        'secrets': {
            'file': 'core/secrets_manager.py',
            'name': 'Secrets Management',
            'phase': 'Security',
            'description': 'Encrypted vault for API keys and credentials',
            'size_threshold': 2000
        },
        'audit-log': {
            'file': 'core/audit_log.py',
            'name': 'Audit Logging',
            'phase': 'Security',
            'description': 'Track tier changes, logins, and system modifications',
            'size_threshold': 2000
        },
        'rate-limiter': {
            'file': 'core/rate_limiter.py',
            'name': 'Rate Limiting & fail2ban',
            'phase': 'Security',
            'description': 'Protection against brute force and DoS attacks',
            'size_threshold': 2000
        },
        
        # Updates (4 components)
        'update-manager': {
            'file': 'core/update_manager.py',
            'name': 'Service Update Manager',
            'phase': 'Updates',
            'description': 'Check for updates, auto-update with backup and rollback',
            'size_threshold': 4000
        },
        'update-monitor': {
            'file': 'core/update_monitor.py',
            'name': 'Update Monitor Service',
            'phase': 'Updates',
            'description': 'Isolated container checking for updates',
            'size_threshold': 2000
        },
        'update-security': {
            'file': 'core/update_security.py',
            'name': 'Update Security Layer',
            'phase': 'Updates',
            'description': 'TLS, signature verification',
            'size_threshold': 2000
        },
        'update-processor': {
            'file': 'core/update_processor.py',
            'name': 'Update Processing',
            'phase': 'Updates',
            'description': 'Download, verify, apply updates',
            'size_threshold': 2000
        },
        
        # Infrastructure (3 components)
        'port-manager': {
            'file': 'core/port_manager.py',
            'name': 'Port Manager',
            'phase': 'Infrastructure',
            'description': 'Port allocation and conflict detection',
            'size_threshold': 2000
        },
        'network-manager': {
            'file': 'core/network_manager.py',
            'name': 'Network Manager',
            'phase': 'Infrastructure',
            'description': 'Internal networking and DNS',
            'size_threshold': 2000
        },
        'storage-manager': {
            'file': 'core/storage_manager.py',
            'name': 'Storage Manager',
            'phase': 'Infrastructure',
            'description': 'Volume management and quotas',
            'size_threshold': 2000
        }
    }
    
    def __init__(self):
        self.root = Path.cwd()
        self.data_file = self.root / '.pso' / 'data.json'
    
    def _get_file_size(self, path: Path) -> int:
        """Get file size, handling errors gracefully"""
        try:
            return path.stat().st_size
        except:
            return 0
    
    def _check_web_dashboard(self, base_path: Path) -> str:
        """Custom detector for web dashboard"""
        static_dir = base_path / 'static'
        if not static_dir.exists():
            return None
        
        required = ['index.html', 'app.js', 'styles.css']
        optional = ['logos']
        
        has_required = all((static_dir / f).exists() for f in required)
        has_optional = (static_dir / 'logos').exists()
        
        if has_required and has_optional:
            return 'completed'
        elif has_required or any((static_dir / f).exists() for f in required):
            return 'in-progress'
        return None
    
    def _count_manifests(self, services_dir: Path) -> str:
        """Custom detector for service catalog"""
        if not services_dir.exists():
            return None
        
        manifests = list(services_dir.glob('*/manifest.json'))
        count = len(manifests)
        
        if count >= 20:
            return 'completed'
        elif count >= 3:
            return 'in-progress'
        return None
    
    def _detect_component_status(self, comp_id: str) -> str:
        """Auto-detect component status using configurable rules"""
        comp_info = self.ARCHITECTURE.get(comp_id)
        if not comp_info or 'file' not in comp_info:
            return None
        
        file_path = comp_info['file']
        full_path = self.root / file_path
        
        if not full_path.exists():
            return None
        
        # Use custom detector if specified
        if 'detect' in comp_info:
            detector_name = comp_info['detect']
            if detector_name == 'check_web_dashboard':
                return self._check_web_dashboard(full_path)
            elif detector_name == 'count_manifests':
                return self._count_manifests(full_path)
        
        # Directory detection (aggregate size of Python files)
        if full_path.is_dir():
            py_files = list(full_path.glob('*.py'))
            if not py_files:
                return 'in-progress'
            
            total_size = sum(self._get_file_size(f) for f in py_files)
            threshold = comp_info.get('size_threshold', 3000)
            
            if total_size > threshold:
                return 'completed'
            elif total_size > 500:
                return 'in-progress'
            return None
        
        # File detection (based on size threshold)
        size = self._get_file_size(full_path)
        threshold = comp_info.get('size_threshold', 3000)
        
        if size > threshold:
            return 'completed'
        elif size > 100:
            return 'in-progress'
        return None
    
    def init(self):
        """Initialize PSO tracking system"""
        pso_dir = self.root / '.pso'
        pso_dir.mkdir(exist_ok=True)
        
        # Load existing data if available
        existing_data = {"components": {}}
        if self.data_file.exists():
            print(f"{Colors.YELLOW}Merging with existing data...{Colors.RESET}")
            with open(self.data_file) as f:
                existing_data = json.load(f)
        
        # Build new structure
        new_data = {"components": {}}
        for comp_id, comp_info in self.ARCHITECTURE.items():
            new_data["components"][comp_id] = {
                "name": comp_info['name'],
                "status": existing_data.get('components', {}).get(comp_id, {}).get('status', 'not-started'),
                "phase": comp_info['phase'],
                "description": comp_info['description']
            }
        
        # Save
        with open(self.data_file, 'w') as f:
            json.dump(new_data, f, indent=2)
        
        added = len([c for c in new_data['components'] if c not in existing_data.get('components', {})])
        if added > 0:
            print(f"{Colors.GREEN}✓ Updated structure (+{added} components){Colors.RESET}")
        else:
            print(f"{Colors.GREEN}✓ PSO initialized{Colors.RESET}")
        print(f"{Colors.GRAY}Data: {self.data_file}{Colors.RESET}")
    
    def scan(self):
        """Auto-detect component completion. Auto-inits if not yet initialized."""
        if not self.data_file.exists():
            print(f"{Colors.YELLOW}No data file found — running init first...{Colors.RESET}")
            self.init()
            print()
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        print(f"\n{Colors.BOLD}🔍 Scanning components...{Colors.RESET}\n")
        
        updated = []
        for comp_id, comp_data in data['components'].items():
            detected = self._detect_component_status(comp_id)
            
            if detected and detected != comp_data['status']:
                old_status = comp_data['status']
                comp_data['status'] = detected
                updated.append((comp_id, old_status, detected))
                
                # Format status with color
                if detected == 'completed':
                    status_str = f"{Colors.GREEN}completed{Colors.RESET}"
                elif detected == 'in-progress':
                    status_str = f"{Colors.BLUE}in-progress{Colors.RESET}"
                else:
                    status_str = detected
                
                print(f"  ✓ {comp_data['name']:<35} {Colors.GRAY}{old_status}{Colors.RESET} → {status_str}")
        
        if updated:
            with open(self.data_file, 'w') as f:
                json.dump(data, f, indent=2)
            print(f"\n{Colors.GREEN}✓ Updated {len(updated)} component(s){Colors.RESET}\n")
        else:
            print(f"{Colors.GRAY}No changes detected{Colors.RESET}\n")
    
    def complete(self, comp_id: str):
        """Manually mark component as completed"""
        if not self.data_file.exists():
            print(f"{Colors.RED}✗ Not initialized{Colors.RESET}")
            return
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        if comp_id not in data['components']:
            print(f"{Colors.RED}✗ Unknown component: {comp_id}{Colors.RESET}")
            print(f"\n{Colors.CYAN}Available components:{Colors.RESET}")
            for cid in sorted(data['components'].keys()):
                print(f"  • {cid}")
            return
        
        data['components'][comp_id]['status'] = 'completed'
        
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        name = data['components'][comp_id]['name']
        print(f"{Colors.GREEN}✓ Marked {name} as completed{Colors.RESET}")
    
    def tree(self):
        """Show architecture tree with numbered interactive details"""
        if not self.data_file.exists():
            self.init()
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        # Go directly to numbered interactive view
        self._tree_numbered_view(data)
    
    def _tree_numbered_view(self, data):
        """Original tree format with numbers and interactive details window"""
        import sys
        
        # Build component numbering map
        comp_number_map = {}
        number = 1
        
        for phase_name in ['Core System', 'Services', 'Interface', 'Monitoring', 'Security', 'Updates', 'Infrastructure']:
            phases = {}
            for comp_id, comp in data['components'].items():
                phase = comp['phase']
                if phase not in phases:
                    phases[phase] = []
                phases[phase].append((comp_id, comp))
            
            if phase_name in phases:
                for comp_id, comp in sorted(phases[phase_name], key=lambda x: x[1]['name']):
                    comp_number_map[number] = (comp_id, comp, phase_name)
                    number += 1
        
        def clear_screen():
            sys.stdout.write('\033[2J\033[H')
            sys.stdout.flush()
        
        def draw_tree():
            """Draw tree in ORIGINAL format with numbers added"""
            # Group by phase
            phases = {}
            for comp_id, comp in data['components'].items():
                phase = comp['phase']
                if phase not in phases:
                    phases[phase] = []
                phases[phase].append((comp_id, comp))
            
            # Calculate progress
            total = len(data['components'])
            completed = sum(1 for c in data['components'].values() if c['status'] == 'completed')
            progress = (completed / total * 100) if total > 0 else 0
            
            # Header - ORIGINAL FORMAT
            print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
            print(f"{Colors.BOLD}PSO ARCHITECTURE & PROGRESS{Colors.RESET}")
            print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
            
            # Overall progress - ORIGINAL FORMAT
            print(f"{Colors.BOLD}Overall Progress:{Colors.RESET}")
            bar_width = 50
            filled = int(progress / 100 * bar_width)
            bar = f"{Colors.GREEN}{'█' * filled}{'░' * (bar_width - filled)}{Colors.RESET}"
            print(f" {progress:5.1f}% [{bar}]\n\n")
            
            # Track line numbers for cursor positioning later
            current_line = 8  # After header and overall progress
            
            # Render each phase - ORIGINAL FORMAT
            number = 1
            for phase_name in ['Core System', 'Services', 'Interface', 'Monitoring', 'Security', 'Updates', 'Infrastructure']:
                if phase_name not in phases:
                    continue
                
                phase_comps = phases[phase_name]
                phase_completed = sum(1 for _, c in phase_comps if c['status'] == 'completed')
                phase_total = len(phase_comps)
                phase_pct = (phase_completed / phase_total * 100) if phase_total > 0 else 0
                
                # Phase header with progress - ORIGINAL FORMAT
                bar_width_phase = 25
                filled_phase = int(phase_pct / 100 * bar_width_phase)
                bar_phase = f"{Colors.GREEN}{'█' * filled_phase}{'░' * (bar_width_phase - filled_phase)}{Colors.RESET}"
                
                print(f"{Colors.BOLD}[{phase_name}]{Colors.RESET}".ljust(45) + f"{phase_pct:5.1f}% [{bar_phase}]")
                print(f"{Colors.GRAY}{'─' * 70}{Colors.RESET}")
                current_line += 2
                
                # Components - ORIGINAL FORMAT with numbers added
                for comp_id, comp in sorted(phase_comps, key=lambda x: x[1]['name']):
                    status_icon = {
                        'completed': f'{Colors.GREEN}✓{Colors.RESET}',
                        'in-progress': f'{Colors.BLUE}→{Colors.RESET}',
                        'not-started': f'{Colors.GRAY}○{Colors.RESET}',
                        'blocked': f'{Colors.RED}✗{Colors.RESET}'
                    }.get(comp['status'], f'{Colors.GRAY}○{Colors.RESET}')
                    
                    status_text = {
                        'completed': f'{Colors.GREEN}DONE{Colors.RESET}',
                        'in-progress': f'{Colors.BLUE}IN PROGRESS{Colors.RESET}',
                        'not-started': f'{Colors.GRAY}NOT STARTED{Colors.RESET}',
                        'blocked': f'{Colors.RED}BLOCKED{Colors.RESET}'
                    }.get(comp['status'], f'{Colors.GRAY}NOT STARTED{Colors.RESET}')
                    
                    # ONLY CHANGE: Add number before status icon
                    print(f" {Colors.YELLOW}{number:2d}{Colors.RESET}. {status_icon} {comp['name']:<40} {status_text}")
                    current_line += 1
                    number += 1
                
                print()
                current_line += 1
            
            return current_line
        
        def clear_details_area():
            """Clear the details window area"""
            # Clear columns 85-115, rows 8-38
            for row in range(8, 39):
                sys.stdout.write(f'\033[{row};85H\033[K')
            sys.stdout.flush()
        
        def clear_prompt_area(last_line):
            """Clear the prompt area to prevent duplication"""
            # Clear 3 lines for prompt area
            for i in range(3):
                sys.stdout.write(f'\033[{last_line + 2 + i};1H\033[K')
            sys.stdout.flush()
        
        def draw_details_window(num):
            """Draw details window with FULL FRAME on far right side"""
            if num not in comp_number_map:
                return
            
            comp_id, comp, phase = comp_number_map[num]
            
            # Clear details area
            clear_details_area()
            
            # Details window position: FAR RIGHT
            start_col = 85  # Moved from 75 to 85 (further right)
            start_row = 10
            
            details = []
            width = 30  # Frame width
            
            # FULL FRAME - Top
            details.append(f"{Colors.BOLD}╔{'═' * width}╗{Colors.RESET}")
            details.append(f"{Colors.BOLD}║{' COMPONENT DETAILS ':^{width}}║{Colors.RESET}")
            details.append(f"{Colors.BOLD}╠{'═' * width}╣{Colors.RESET}")
            
            # Name
            name = comp['name'][:width-2]
            padding = width - len(comp['name']) if len(comp['name']) < width else 0
            details.append(f"{Colors.BOLD}║ {name}{' ' * (width - len(name) - 1)}║{Colors.RESET}")
            details.append(f"{Colors.BOLD}╠{'═' * width}╣{Colors.RESET}")
            
            # Phase
            details.append(f"║ {Colors.GRAY}Phase:{Colors.RESET}{' ' * (width - 7)}║")
            phase_text = phase[:width-4]
            details.append(f"║   {phase_text}{' ' * (width - len(phase_text) - 3)}║")
            details.append(f"║{' ' * width}║")
            
            # Status
            status_colors = {
                'completed': Colors.GREEN,
                'in-progress': Colors.BLUE,
                'not-started': Colors.GRAY,
                'blocked': Colors.RED
            }
            status_color = status_colors.get(comp['status'], Colors.GRAY)
            details.append(f"║ {Colors.GRAY}Status:{Colors.RESET}{' ' * (width - 8)}║")
            status_text = comp['status'].upper()
            status_display = f"{status_color}{status_text}{Colors.RESET}"
            status_plain_len = len(status_text)
            details.append(f"║   {status_display}{' ' * (width - status_plain_len - 3)}║")
            details.append(f"║{' ' * width}║")
            
            # Description
            details.append(f"║ {Colors.GRAY}Description:{Colors.RESET}{' ' * (width - 13)}║")
            words = comp['description'].split()
            line = ""
            desc_lines = []
            for word in words:
                if len(line) + len(word) + 1 <= width - 4:
                    line += word + " "
                else:
                    if line:
                        desc_lines.append(line.strip())
                    line = word + " "
            if line:
                desc_lines.append(line.strip())
            
            for desc_line in desc_lines:
                details.append(f"║   {desc_line}{' ' * (width - len(desc_line) - 3)}║")
            details.append(f"║{' ' * width}║")
            
            # File
            arch_info = self.ARCHITECTURE.get(comp_id, {})
            if 'file' in arch_info:
                details.append(f"║ {Colors.GRAY}File:{Colors.RESET}{' ' * (width - 6)}║")
                fpath = arch_info['file']
                if len(fpath) > width - 4:
                    fpath = "..." + fpath[-(width-7):]
                details.append(f"║   {fpath}{' ' * (width - len(fpath) - 3)}║")
                details.append(f"║{' ' * width}║")
            
            # Threshold
            if 'size_threshold' in arch_info:
                details.append(f"║ {Colors.GRAY}Threshold:{Colors.RESET}{' ' * (width - 11)}║")
                thresh_text = f"{arch_info['size_threshold']} bytes"
                details.append(f"║   {thresh_text}{' ' * (width - len(thresh_text) - 3)}║")
            
            # FULL FRAME - Bottom
            details.append(f"{Colors.BOLD}╚{'═' * width}╝{Colors.RESET}")
            
            # Print details at position
            for i, line in enumerate(details):
                row = start_row + i
                sys.stdout.write(f'\033[{row};{start_col}H{line}')
            
            sys.stdout.flush()
        
        # Main display loop
        clear_screen()
        
        # Draw tree once
        last_line = draw_tree()
        
        # Input loop
        while True:
            # Clear prompt area to prevent duplication
            clear_prompt_area(last_line)
            
            # Position cursor for prompt
            sys.stdout.write(f'\033[{last_line + 2};1H')
            sys.stdout.write(f"{Colors.GRAY}{'─' * 79}{Colors.RESET}\n")
            sys.stdout.write(f"{Colors.YELLOW}Enter number (1-{len(comp_number_map)}) for details, 'q' to quit: {Colors.RESET}")
            sys.stdout.flush()
            
            user_input = input().strip().lower()
            
            if user_input == 'q':
                break
            
            try:
                num = int(user_input)
                if 1 <= num <= len(comp_number_map):
                    draw_details_window(num)
                else:
                    sys.stdout.write(f'\033[{last_line + 4};1H{Colors.RED}Invalid number (1-{len(comp_number_map)}){Colors.RESET}     ')
                    sys.stdout.flush()
            except ValueError:
                if user_input:
                    sys.stdout.write(f'\033[{last_line + 4};1H{Colors.RED}Enter a number or q{Colors.RESET}     ')
                    sys.stdout.flush()
        
        # Exit
        clear_screen()
        self._render_tree_static(data)
    
    def _render_tree_static(self, data):
        """Render the static tree view"""
        # Group by phase
        phases = {}
        for comp_id, comp in data['components'].items():
            phase = comp['phase']
            if phase not in phases:
                phases[phase] = []
            phases[phase].append((comp_id, comp))
        
        # Calculate progress
        total = len(data['components'])
        completed = sum(1 for c in data['components'].values() if c['status'] == 'completed')
        in_progress = sum(1 for c in data['components'].values() if c['status'] == 'in-progress')
        progress = (completed / total * 100) if total > 0 else 0
        
        # Header
        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}PSO ARCHITECTURE & PROGRESS{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
        
        # Overall progress
        print(f"{Colors.BOLD}Overall Progress:{Colors.RESET}")
        bar_width = 50
        filled = int(progress / 100 * bar_width)
        bar = f"{Colors.GREEN}{'█' * filled}{'░' * (bar_width - filled)}{Colors.RESET}"
        print(f" {progress:5.1f}% [{bar}]\n\n")
        
        # Render each phase
        for phase_name in ['Core System', 'Services', 'Interface', 'Monitoring', 'Security', 'Updates', 'Infrastructure']:
            if phase_name not in phases:
                continue
            
            phase_comps = phases[phase_name]
            phase_completed = sum(1 for _, c in phase_comps if c['status'] == 'completed')
            phase_total = len(phase_comps)
            phase_pct = (phase_completed / phase_total * 100) if phase_total > 0 else 0
            
            # Phase header with progress
            bar_width_phase = 25
            filled_phase = int(phase_pct / 100 * bar_width_phase)
            bar_phase = f"{Colors.GREEN}{'█' * filled_phase}{'░' * (bar_width_phase - filled_phase)}{Colors.RESET}"
            
            print(f"{Colors.BOLD}[{phase_name}]{Colors.RESET}".ljust(45) + f"{phase_pct:5.1f}% [{bar_phase}]")
            print(f"{Colors.GRAY}{'─' * 70}{Colors.RESET}")
            
            # Components
            for comp_id, comp in sorted(phase_comps, key=lambda x: x[1]['name']):
                status_icon = {
                    'completed': f'{Colors.GREEN}✓{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}→{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}○{Colors.RESET}',
                    'blocked': f'{Colors.RED}✗{Colors.RESET}'
                }.get(comp['status'], f'{Colors.GRAY}○{Colors.RESET}')
                
                status_text = {
                    'completed': f'{Colors.GREEN}DONE{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}IN PROGRESS{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}NOT STARTED{Colors.RESET}',
                    'blocked': f'{Colors.RED}BLOCKED{Colors.RESET}'
                }.get(comp['status'], f'{Colors.GRAY}NOT STARTED{Colors.RESET}')
                
                print(f"  {status_icon} {comp['name']:<43} {status_text}")
            
            print()
    
    def _tree_interactive_mode(self, data):
        """Interactive mode with numbered selection - simple and reliable"""
        import sys
        
        # Build numbered component list
        component_list = []
        number = 1
        
        for phase_name in ['Core System', 'Services', 'Interface', 'Monitoring', 'Security', 'Updates', 'Infrastructure']:
            phase_comps = [(cid, c) for cid, c in data['components'].items() if c['phase'] == phase_name]
            for comp_id, comp in sorted(phase_comps, key=lambda x: x[1]['name']):
                component_list.append((number, comp_id, comp, phase_name))
                number += 1
        
        def clear_screen():
            """Clear screen"""
            print('\033[2J\033[H', end='', flush=True)
        
        def show_tree_with_numbers():
            """Display tree with numbers"""
            current_phase = None
            
            for num, comp_id, comp, phase in component_list:
                # Phase header
                if phase != current_phase:
                    current_phase = phase
                    if num > 1:
                        print()
                    
                    # Calculate phase progress
                    phase_comps = [c for n, cid, c, p in component_list if p == phase]
                    phase_completed = sum(1 for c in phase_comps if c['status'] == 'completed')
                    phase_total = len(phase_comps)
                    phase_pct = (phase_completed / phase_total * 100) if phase_total > 0 else 0
                    
                    print(f"{Colors.BOLD}[{phase}]{Colors.RESET} {phase_pct:.0f}%")
                    print(f"{Colors.GRAY}{'─' * 40}{Colors.RESET}")
                
                # Status icon
                icons = {
                    'completed': f'{Colors.GREEN}✓{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}→{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}○{Colors.RESET}',
                    'blocked': f'{Colors.RED}✗{Colors.RESET}'
                }
                icon = icons.get(comp['status'], f'{Colors.GRAY}○{Colors.RESET}')
                
                # Component line
                name = comp['name'][:35]  # Truncate if too long
                print(f" {Colors.YELLOW}{num:2d}{Colors.RESET}. {icon} {name}")
        
        def show_details(num, comp_id, comp, phase):
            """Show details for selected component"""
            details = []
            
            details.append(f"{Colors.BOLD}┌{'─' * 34}┐{Colors.RESET}")
            details.append(f"{Colors.BOLD}│{' COMPONENT DETAILS ':^34}│{Colors.RESET}")
            details.append(f"{Colors.BOLD}└{'─' * 34}┘{Colors.RESET}")
            details.append("")
            
            # Name
            name = comp['name'][:32]
            details.append(f"{Colors.BOLD}{name}{Colors.RESET}")
            details.append(f"{Colors.GRAY}{'─' * 34}{Colors.RESET}")
            details.append("")
            
            # Phase
            details.append(f"{Colors.GRAY}Phase:{Colors.RESET}")
            details.append(f"  {phase}")
            details.append("")
            
            # Status
            status_colors = {
                'completed': Colors.GREEN,
                'in-progress': Colors.BLUE,
                'not-started': Colors.GRAY,
                'blocked': Colors.RED
            }
            status_color = status_colors.get(comp['status'], Colors.GRAY)
            details.append(f"{Colors.GRAY}Status:{Colors.RESET}")
            details.append(f"  {status_color}{comp['status'].upper()}{Colors.RESET}")
            details.append("")
            
            # Description (word-wrap)
            details.append(f"{Colors.GRAY}Description:{Colors.RESET}")
            words = comp['description'].split()
            line = ""
            for word in words:
                if len(line) + len(word) + 1 <= 32:
                    line += word + " "
                else:
                    if line:
                        details.append(f"  {line.strip()}")
                    line = word + " "
            if line:
                details.append(f"  {line.strip()}")
            details.append("")
            
            # File path from ARCHITECTURE
            arch_info = self.ARCHITECTURE.get(comp_id, {})
            if 'file' in arch_info:
                details.append(f"{Colors.GRAY}File:{Colors.RESET}")
                fpath = arch_info['file']
                if len(fpath) > 32:
                    fpath = "..." + fpath[-29:]
                details.append(f"  {fpath}")
                details.append("")
            
            # Size threshold
            if 'size_threshold' in arch_info:
                details.append(f"{Colors.GRAY}Threshold:{Colors.RESET}")
                details.append(f"  {arch_info['size_threshold']} bytes")
                details.append("")
            
            # Detection method
            if 'detect' in arch_info:
                details.append(f"{Colors.GRAY}Detection:{Colors.RESET}")
                details.append(f"  {arch_info['detect']}")
            
            return details
        
        # Main loop
        current_selection = None
        
        while True:
            clear_screen()
            
            # Header
            print(f"{Colors.BOLD}PSO INTERACTIVE TREE - Numbered Selection{Colors.RESET}")
            print(f"{Colors.GRAY}{'═' * 79}{Colors.RESET}\n")
            
            # Build tree lines
            tree_lines = []
            current_phase = None
            
            for num, comp_id, comp, phase in component_list:
                if phase != current_phase:
                    current_phase = phase
                    if tree_lines:
                        tree_lines.append("")
                    
                    phase_comps = [c for n, cid, c, p in component_list if p == phase]
                    phase_completed = sum(1 for c in phase_comps if c['status'] == 'completed')
                    phase_total = len(phase_comps)
                    phase_pct = (phase_completed / phase_total * 100) if phase_total > 0 else 0
                    
                    tree_lines.append(f"{Colors.BOLD}[{phase}]{Colors.RESET} {phase_pct:.0f}%")
                    tree_lines.append(f"{Colors.GRAY}{'─' * 40}{Colors.RESET}")
                
                icons = {
                    'completed': f'{Colors.GREEN}✓{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}→{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}○{Colors.RESET}',
                    'blocked': f'{Colors.RED}✗{Colors.RESET}'
                }
                icon = icons.get(comp['status'], f'{Colors.GRAY}○{Colors.RESET}')
                
                name = comp['name'][:32]
                tree_lines.append(f" {Colors.YELLOW}{num:2d}{Colors.RESET}. {icon} {name}")
            
            # Get details if selection exists
            details_lines = []
            if current_selection is not None:
                # Find the component
                for num, comp_id, comp, phase in component_list:
                    if num == current_selection:
                        details_lines = show_details(num, comp_id, comp, phase)
                        break
            
            # Print tree and details side by side
            max_lines = max(len(tree_lines), len(details_lines))
            
            for i in range(max_lines):
                # Get tree line
                if i < len(tree_lines):
                    tree_line = tree_lines[i]
                else:
                    tree_line = ""
                
                # Get details line
                if i < len(details_lines):
                    details_line = details_lines[i]
                else:
                    details_line = ""
                
                # Calculate padding (strip ANSI codes for width)
                import re
                tree_display_width = len(re.sub(r'\033\[[0-9;]*m', '', tree_line))
                padding = max(0, 44 - tree_display_width)
                
                # Print complete line
                print(tree_line + (' ' * padding) + details_line)
            
            # Prompt
            print(f"\n{Colors.GRAY}{'─' * 79}{Colors.RESET}")
            print(f"{Colors.YELLOW}Enter number (1-{len(component_list)}) to view details, or 'q' to quit:{Colors.RESET} ", end='', flush=True)
            
            # Get input
            user_input = input().strip().lower()
            
            if user_input == 'q':
                break
            
            # Try to parse as number
            try:
                num = int(user_input)
                if 1 <= num <= len(component_list):
                    current_selection = num
                else:
                    print(f"{Colors.RED}Invalid number. Press Enter to continue...{Colors.RESET}")
                    input()
            except ValueError:
                if user_input:  # Only show error if they typed something
                    print(f"{Colors.RED}Please enter a number or 'q'. Press Enter to continue...{Colors.RESET}")
                    input()
        
        # Exit: clear screen and show normal tree
        clear_screen()
        self._render_tree_static(data)

    def tree_interactive(self):
        """Interactive tree with component details panel"""
        if not self.data_file.exists():
            print(f"{Colors.RED}✗ Not initialized{Colors.RESET}")
            return
        
        import sys
        import tty
        import termios
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        # Group by phase
        phases = {}
        for comp_id, comp in data['components'].items():
            phase = comp['phase']
            if phase not in phases:
                phases[phase] = []
            phases[phase].append((comp_id, comp))
        
        # Calculate progress
        total = len(data['components'])
        completed = sum(1 for c in data['components'].values() if c['status'] == 'completed')
        progress = (completed / total * 100) if total > 0 else 0
        
        # Build component list for navigation
        component_list = []
        for phase_name in ['Core System', 'Services', 'Interface', 'Monitoring', 'Security', 'Updates', 'Infrastructure']:
            if phase_name in phases:
                for comp_id, comp in sorted(phases[phase_name], key=lambda x: x[1]['name']):
                    component_list.append((comp_id, comp, phase_name))
        
        selected_idx = 0
        
        def render_screen():
            # Clear screen
            print('\033[2J\033[H', end='')
            
            # Header
            print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}")
            print(f"{Colors.BOLD}PSO ARCHITECTURE & PROGRESS (Interactive){Colors.RESET}")
            print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
            print(f"{Colors.BOLD}Overall Progress:{Colors.RESET}")
            bar_width = 50
            filled = int(progress / 100 * bar_width)
            bar = f"{Colors.GREEN}{'█' * filled}{'░' * (bar_width - filled)}{Colors.RESET}"
            print(f" {progress:5.1f}% [{bar}]\n")
            
            # Split screen layout
            left_width = 45
            right_start = 48
            
            # Track current line for positioning
            line_idx = 0
            
            # Render left side (tree) and right side (details) simultaneously
            selected_comp_id, selected_comp, selected_phase = component_list[selected_idx]
            
            # Left side: Component tree
            current_phase = None
            display_lines = []
            
            idx = 0
            for comp_id, comp, phase_name in component_list:
                # Phase header
                if phase_name != current_phase:
                    current_phase = phase_name
                    phase_comps = [c for c in component_list if c[2] == phase_name]
                    phase_completed = sum(1 for _, c, _ in phase_comps if c['status'] == 'completed')
                    phase_total = len(phase_comps)
                    phase_pct = (phase_completed / phase_total * 100) if phase_total > 0 else 0
                    
                    bar_width_phase = 25
                    filled_phase = int(phase_pct / 100 * bar_width_phase)
                    bar_phase = f"{Colors.GREEN}{'█' * filled_phase}{'░' * (bar_width_phase - filled_phase)}{Colors.RESET}"
                    
                    display_lines.append('')
                    display_lines.append(f"{Colors.BOLD}[{phase_name}]{Colors.RESET} {phase_pct:5.1f}% [{bar_phase}]")
                    display_lines.append(f"{Colors.GRAY}{'─' * 44}{Colors.RESET}")
                
                # Component line
                status_icon = {
                    'completed': f'{Colors.GREEN}✓{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}→{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}○{Colors.RESET}',
                    'blocked': f'{Colors.RED}✗{Colors.RESET}'
                }.get(comp['status'], f'{Colors.GRAY}○{Colors.RESET}')
                
                status_text = {
                    'completed': f'{Colors.GREEN}DONE{Colors.RESET}',
                    'in-progress': f'{Colors.BLUE}IN PROGRESS{Colors.RESET}',
                    'not-started': f'{Colors.GRAY}NOT STARTED{Colors.RESET}',
                    'blocked': f'{Colors.RED}BLOCKED{Colors.RESET}'
                }.get(comp['status'], f'{Colors.GRAY}NOT STARTED{Colors.RESET}')
                
                # Highlight selected
                if idx == selected_idx:
                    name_display = f"{Colors.BOLD}{Colors.YELLOW}► {comp['name']}{Colors.RESET}"
                else:
                    name_display = comp['name']
                
                # Truncate if needed
                name_truncated = name_display[:38] if len(comp['name']) <= 38 else comp['name'][:35] + "..."
                
                display_lines.append(f"  {status_icon} {name_truncated}")
                idx += 1
            
            # Print left side
            for line in display_lines:
                print(line)
            
            # Position cursor for right side (details panel)
            # Move cursor up to start of details area
            lines_to_move = len(display_lines) + 1
            print(f'\033[{lines_to_move}A', end='')  # Move up
            print(f'\033[{right_start}C', end='')    # Move right
            
            # Right side: Component details
            print(f"{Colors.BOLD}┌{'─' * 30}┐{Colors.RESET}")
            print(f'\033[{right_start}C{Colors.BOLD}│ COMPONENT DETAILS{" " * 12}│{Colors.RESET}')
            print(f'\033[{right_start}C{Colors.BOLD}└{"─" * 30}┘{Colors.RESET}')
            print(f'\033[{right_start}C')
            
            # Component name
            print(f'\033[{right_start}C{Colors.BOLD}{selected_comp["name"]}{Colors.RESET}')
            print(f'\033[{right_start}C{Colors.GRAY}{"─" * 30}{Colors.RESET}')
            print(f'\033[{right_start}C')
            
            # Phase
            print(f'\033[{right_start}C{Colors.GRAY}Phase:{Colors.RESET}')
            print(f'\033[{right_start}C  {selected_phase}')
            print(f'\033[{right_start}C')
            
            # Status
            status_color = {
                'completed': Colors.GREEN,
                'in-progress': Colors.BLUE,
                'not-started': Colors.GRAY,
                'blocked': Colors.RED
            }.get(selected_comp['status'], Colors.GRAY)
            print(f'\033[{right_start}C{Colors.GRAY}Status:{Colors.RESET}')
            print(f'\033[{right_start}C  {status_color}{selected_comp["status"].upper()}{Colors.RESET}')
            print(f'\033[{right_start}C')
            
            # Description (word wrap)
            print(f'\033[{right_start}C{Colors.GRAY}Description:{Colors.RESET}')
            desc = selected_comp['description']
            words = desc.split()
            lines = []
            current_line = []
            current_length = 0
            
            for word in words:
                if current_length + len(word) + 1 <= 28:
                    current_line.append(word)
                    current_length += len(word) + 1
                else:
                    if current_line:
                        lines.append(' '.join(current_line))
                    current_line = [word]
                    current_length = len(word)
            
            if current_line:
                lines.append(' '.join(current_line))
            
            for line in lines:
                print(f'\033[{right_start}C  {line}')
            
            # Get additional info from ARCHITECTURE
            arch_info = self.ARCHITECTURE.get(selected_comp_id, {})
            
            if 'file' in arch_info:
                print(f'\033[{right_start}C')
                print(f'\033[{right_start}C{Colors.GRAY}File:{Colors.RESET}')
                print(f'\033[{right_start}C  {arch_info["file"]}')
            
            if 'size_threshold' in arch_info:
                print(f'\033[{right_start}C')
                print(f'\033[{right_start}C{Colors.GRAY}Size Threshold:{Colors.RESET}')
                print(f'\033[{right_start}C  {arch_info["size_threshold"]} bytes')
            
            # Move cursor to bottom
            print(f'\n\n')
            
            # Controls
            print(f"{Colors.BOLD}Controls:{Colors.RESET} ↑/↓ Navigate | q Quit | Enter View Full Info")
        
        # Initial render
        render_screen()
        
        # Input loop
        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        
        try:
            tty.setraw(fd)
            
            while True:
                ch = sys.stdin.read(1)
                
                # Quit
                if ch == 'q':
                    break
                
                # Arrow keys (escape sequences)
                if ch == '\x1b':
                    ch2 = sys.stdin.read(1)
                    if ch2 == '[':
                        ch3 = sys.stdin.read(1)
                        if ch3 == 'A':  # Up
                            selected_idx = max(0, selected_idx - 1)
                            render_screen()
                        elif ch3 == 'B':  # Down
                            selected_idx = min(len(component_list) - 1, selected_idx + 1)
                            render_screen()
                
                # Enter - show full info
                elif ch == '\r' or ch == '\n':
                    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                    comp_id, _, _ = component_list[selected_idx]
                    self.info(comp_id)
                    input("\nPress Enter to return...")
                    tty.setraw(fd)
                    render_screen()
        
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
            print()

    
    def status(self):
        """Show progress summary"""
        if not self.data_file.exists():
            self.init()
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        total = len(data['components'])
        by_status = {}
        for comp in data['components'].values():
            status = comp['status']
            by_status[status] = by_status.get(status, 0) + 1
        
        print(f"\n{Colors.BOLD}PSO Development Status{Colors.RESET}")
        print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
        print(f"Total Components:  {total}")
        print(f"{Colors.GREEN}Completed:{Colors.RESET}         {by_status.get('completed', 0)}")
        print(f"{Colors.BLUE}In Progress:{Colors.RESET}       {by_status.get('in-progress', 0)}")
        print(f"{Colors.GRAY}Not Started:{Colors.RESET}       {by_status.get('not-started', 0)}")
        if 'blocked' in by_status:
            print(f"{Colors.RED}Blocked:{Colors.RESET}           {by_status.get('blocked', 0)}")
        
        completed_pct = by_status.get('completed', 0) * 100 // total
        print(f"\nProgress: {completed_pct}%")
        print()
    
    def update(self, comp_id: str, status: str):
        """Manually update component status"""
        valid = ['not-started', 'in-progress', 'completed', 'blocked']
        
        if status not in valid:
            print(f"{Colors.RED}✗ Invalid status: {status}{Colors.RESET}")
            print(f"Valid: {', '.join(valid)}")
            return
        
        if not self.data_file.exists():
            print(f"{Colors.RED}✗ Not initialized{Colors.RESET}")
            return
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        if comp_id not in data['components']:
            print(f"{Colors.RED}✗ Unknown component: {comp_id}{Colors.RESET}")
            return
        
        data['components'][comp_id]['status'] = status
        
        with open(self.data_file, 'w') as f:
            json.dump(data, f, indent=2)
        
        print(f"{Colors.GREEN}✓ Updated {comp_id} to {status}{Colors.RESET}")
    
    def info(self, comp_id: str):
        """Show component details"""
        if not self.data_file.exists():
            print(f"{Colors.RED}✗ Not initialized{Colors.RESET}")
            return
        
        with open(self.data_file) as f:
            data = json.load(f)
        
        if comp_id not in data['components']:
            print(f"{Colors.RED}✗ Component not found: {comp_id}{Colors.RESET}")
            return
        
        comp = data['components'][comp_id]
        
        print(f"\n{Colors.BOLD}{comp['name']}{Colors.RESET}")
        print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
        print(f"ID:          {comp_id}")
        print(f"Phase:       {comp['phase']}")
        print(f"Status:      {comp['status']}")
        print(f"Description: {comp['description']}")
        print()
    
    def architecture(self):
        """Display complete system architecture"""
        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.BOLD}COMPLETE SYSTEM ARCHITECTURE{Colors.RESET}")
        print(f"{Colors.BOLD}{'=' * 80}{Colors.RESET}\n")
        
        architecture = """Personal-Server-OS/
│
├── CORE SYSTEM LAYER
│   ├── Installation & Bootstrap
│   │   ├── core/installer.py
│   │   └── Service installation with manifest support
│   │
│   ├── Service Manager
│   │   ├── core/service_manager.py
│   │   └── Start/stop/restart services (Docker + systemd)
│   │
│   ├── Dependency Resolver
│   │   ├── core/dependency_resolver.py
│   │   └── Calculate install order and check conflicts
│   │
│   ├── Configuration Manager
│   │   ├── core/config_manager.py
│   │   └── Template engine, env vars, validation
│   │
│   ├── Data Layer (SQLite)
│   │   ├── core/database.py
│   │   └── SQLite databases for services, health, users
│   │
│   ├── Backup System
│   │   ├── core/backup_manager.py
│   │   └── Automated backups with retention policies
│   │
│   ├── Reverse Proxy Manager
│   │   └── Auto-configure Caddy/Traefik, SSL/TLS
│   │
│   └── Resource Manager
│       └── Resource quotas and limits
│
├── SERVICES LAYER
│   ├── Service Manifest System
│   │   ├── core/manifest.py
│   │   └── JSON schema for service definitions
│   │
│   ├── Services Catalog
│   │   ├── services/
│   │   └── Library of installable services
│   │
│   ├── Service Discovery
│   │   └── Internal DNS, service-to-service communication
│   │
│   └── Migration & Import Tools
│       └── Import Docker Compose, migrate platforms
│
├── INTERFACE LAYER
│   ├── CLI Tool
│   │   ├── pso
│   │   └── Command-line interface
│   │
│   ├── Interactive Menu
│   │   ├── pso-menu
│   │   └── Guided menu interface with tier management
│   │
│   ├── Web Dashboard
│   │   ├── web/static/
│   │   └── Web-based control panel
│   │
│   └── REST API
│       ├── web/api.py
│       └── HTTP API for remote management
│
├── MONITORING LAYER
│   ├── Health Monitor
│   │   └── Continuous health checks and uptime monitoring
│   │
│   ├── Metrics Collection
│   │   └── Prometheus-compatible metrics
│   │
│   ├── Notification Service
│   │   └── Email/SMS/webhook alerts
│   │
│   ├── Grafana Integration
│   │   └── Metrics visualization and dashboards
│   │
│   └── Log Aggregator
│       └── Centralized log collection, search, and tailing
│
├── SECURITY LAYER
│   ├── Authentication System
│   │   └── User accounts, password hashing, sessions
│   │
│   ├── Access Control (RBAC)
│   │   └── Role-based permissions
│   │
│   ├── Network Security
│   │   └── Firewall management and port control
│   │
│   ├── Secrets Management
│   │   └── Encrypted storage for API keys
│   │
│   └── Audit Logging
│       └── Track all system changes and access
│
├── UPDATES LAYER
│   ├── Update Monitor Service
│   │   └── Isolated container checking for updates
│   │
│   ├── Update Security Layer
│   │   └── TLS, signature verification
│   │
│   └── Update Processing
│       └── Download, verify, apply updates
│
└── INFRASTRUCTURE LAYER
    ├── Port Manager
    │   ├── core/port_manager.py
    │   └── Port allocation and conflict detection
    │
    ├── Network Manager
    │   └── Internal networking and DNS
    │
    └── Storage Manager
        └── Volume management and quotas
"""
        
        print(architecture)
        print(f"\n{Colors.BOLD}{'=' * 80}{Colors.RESET}")
        print(f"{Colors.YELLOW}Tip: Run './pso dev tree' to see current component status{Colors.RESET}\n")

def main():
    pso = PSO()
    
    if len(sys.argv) < 2:
        print(f"\n{Colors.BOLD}PSO - Personal Server OS Tracker{Colors.RESET}\n")
        print(f"{Colors.BOLD}Available Commands:{Colors.RESET}")
        print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
        print(f"  {Colors.GREEN}init{Colors.RESET}                    Initialize project")
        print(f"  {Colors.GREEN}scan{Colors.RESET}                    Auto-detect component progress")
        print(f"  {Colors.GREEN}tree{Colors.RESET}                    Show architecture tree with progress")
        print(f"  {Colors.GREEN}tree-detail{Colors.RESET}             Interactive tree with component details")
        print(f"  {Colors.GREEN}architecture{Colors.RESET}            Show complete detailed architecture")
        print(f"  {Colors.GREEN}status{Colors.RESET}                  Show progress summary")
        print(f"  {Colors.GREEN}update <id> <status>{Colors.RESET}    Update component status")
        print(f"  {Colors.GREEN}complete <id>{Colors.RESET}           Mark component as completed")
        print(f"  {Colors.GREEN}info <id>{Colors.RESET}               Show component details")
        print(f"  {Colors.GREEN}help{Colors.RESET}                    Show this help message")
        print()
        print(f"{Colors.BOLD}Examples:{Colors.RESET}")
        print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
        print(f"  python pso.py init")
        print(f"  python pso.py scan")
        print(f"  python pso.py tree")
        print(f"  python pso.py tree-detail          # Interactive with details panel")
        print(f"  python pso.py architecture")
        print(f"  python pso.py status")
        print(f"  python pso.py complete web-ui")
        print(f"  python pso.py update installer in-progress")
        print(f"  python pso.py info installer")
        print()
        print(f"{Colors.BOLD}Valid Statuses:{Colors.RESET}")
        print(f"{Colors.GRAY}{'─' * 60}{Colors.RESET}")
        print(f"  {Colors.GRAY}not-started{Colors.RESET}   - Not yet started")
        print(f"  {Colors.BLUE}in-progress{Colors.RESET}   - Currently working on it")
        print(f"  {Colors.GREEN}completed{Colors.RESET}      - Finished")
        print(f"  {Colors.RED}blocked{Colors.RESET}        - Cannot proceed")
        print()
        return
    
    cmd = sys.argv[1]
    
    if cmd == 'init':
        pso.init()
    elif cmd == 'scan':
        pso.scan()
    elif cmd == 'tree':
        pso.tree()
    elif cmd == 'tree-detail' or cmd == 'detail':
        pso.tree_interactive()
    elif cmd == 'architecture' or cmd == 'arch':
        pso.architecture()
    elif cmd == 'status':
        pso.status()
    elif cmd == 'complete':
        if len(sys.argv) < 3:
            print(f"{Colors.RED}Usage: python pso.py complete <component-id>{Colors.RESET}")
            print("Example: python pso.py complete web-ui")
        else:
            pso.complete(sys.argv[2])
    elif cmd == 'update':
        if len(sys.argv) < 4:
            print(f"{Colors.RED}Usage: python pso.py update <id> <status>{Colors.RESET}")
            print("Statuses: not-started, in-progress, completed, blocked")
        else:
            pso.update(sys.argv[2], sys.argv[3])
    elif cmd == 'info':
        if len(sys.argv) < 3:
            print(f"{Colors.RED}Usage: python pso.py info <component-id>{Colors.RESET}")
        else:
            pso.info(sys.argv[2])
    elif cmd == 'help':
        sys.argv = sys.argv[:1]
        main()
    else:
        print(f"{Colors.RED}Unknown command: {cmd}{Colors.RESET}")
        print("Run 'python pso.py help' for usage information")

if __name__ == '__main__':
    main()