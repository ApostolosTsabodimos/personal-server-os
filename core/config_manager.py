"""
Configuration Manager for Personal Server OS

Handles:
- User input collection during installation
- Template rendering (Jinja2)
- Config file generation and validation
- Environment variable management
- Configuration rollback
"""

import json
import os
import re
from pathlib import Path
from typing import Dict, List, Any, Optional, Tuple
import shutil

try:
    from jinja2 import Environment, FileSystemLoader, Template, TemplateError
    JINJA2_AVAILABLE = True
except ImportError:
    JINJA2_AVAILABLE = False
    print("Warning: jinja2 not installed. Install with: pip install jinja2")


class ConfigValidationError(Exception):
    """Raised when configuration validation fails"""
    pass


class ConfigManager:
    """
    Manages configuration for PSO services
    
    Handles user input collection, template rendering, and config generation
    """
    
    def __init__(self, data_dir: Path = None):
        """
        Initialize Configuration Manager
        
        Args:
            data_dir: Base directory for configs (default: /var/pso/configs or ~/.pso_dev/configs)
        """
        if data_dir is None:
            # Always use ~/.pso_dev — no root required, consistent across dev and prod
            data_dir = Path.home() / '.pso_dev' / 'configs' 
        
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        
        # Backup directory for rollback
        self.backup_dir = self.data_dir / '.backups'
        self.backup_dir.mkdir(parents=True, exist_ok=True)
    
    def collect_user_inputs(self, 
                           input_schema: List[Dict[str, Any]], 
                           interactive: bool = True) -> Dict[str, Any]:
        """
        Collect user inputs based on schema
        
        Args:
            input_schema: List of input definitions from manifest
            interactive: If False, use defaults without prompting
        
        Returns:
            Dictionary of collected inputs
        
        Example input_schema:
        [
            {
                "name": "admin_email",
                "description": "Administrator email address",
                "type": "string",
                "required": true,
                "default": "admin@example.com",
                "validation": "^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\\.[a-zA-Z]{2,}$"
            }
        ]
        """
        collected = {}
        
        for input_def in input_schema:
            name = input_def['name']
            description = input_def.get('description', name)
            input_type = input_def.get('type', 'string')
            required = input_def.get('required', False)
            default = input_def.get('default')
            validation = input_def.get('validation')
            options = input_def.get('options')  # For choice/enum types
            
            if interactive:
                value = self._prompt_user(
                    name=name,
                    description=description,
                    input_type=input_type,
                    default=default,
                    required=required,
                    options=options,
                    validation=validation
                )
            else:
                # Non-interactive: use default or None
                value = default
                if required and value is None:
                    raise ConfigValidationError(
                        f"Required input '{name}' has no default value"
                    )
            
            collected[name] = value
        
        return collected
    
    def _prompt_user(self,
                    name: str,
                    description: str,
                    input_type: str,
                    default: Any = None,
                    required: bool = False,
                    options: List[str] = None,
                    validation: str = None) -> Any:
        """
        Prompt user for a single input
        
        Args:
            name: Input name/key
            description: Human-readable description
            input_type: Type (string, int, bool, password, choice)
            default: Default value
            required: Whether input is required
            options: List of valid options (for choice type)
            validation: Regex pattern for validation
        
        Returns:
            User's input (converted to appropriate type)
        """
        # Build prompt message
        prompt = f"\n{description}"
        
        if options:
            prompt += f"\nOptions: {', '.join(options)}"
        
        if default is not None:
            prompt += f" [default: {default}]"
        
        if required:
            prompt += " (required)"
        
        prompt += ": "
        
        # Special handling for different types
        while True:
            if input_type == 'password':
                import getpass
                value = getpass.getpass(prompt)
            else:
                value = input(prompt).strip()
            
            # Use default if empty and default exists
            if not value and default is not None:
                value = default
                break
            
            # Check required
            if required and not value:
                print(f"Error: {name} is required")
                continue
            
            # Validate based on type
            try:
                if input_type == 'int':
                    value = int(value)
                elif input_type == 'bool':
                    value = value.lower() in ('true', 'yes', '1', 'y')
                elif input_type == 'choice' and options:
                    if value not in options:
                        print(f"Error: Must be one of: {', '.join(options)}")
                        continue
                
                # Regex validation if provided
                if validation and isinstance(value, str):
                    if not re.match(validation, value):
                        print(f"Error: Invalid format for {name}")
                        continue
                
                break
            
            except ValueError as e:
                print(f"Error: Invalid {input_type} value")
                continue
        
        return value
    
    def render_template(self,
                       template_content: str,
                       variables: Dict[str, Any]) -> str:
        """
        Render a Jinja2 template with given variables
        
        Args:
            template_content: Template string
            variables: Dictionary of variables to inject
        
        Returns:
            Rendered template content
        
        Raises:
            TemplateError: If template rendering fails
        """
        if not JINJA2_AVAILABLE:
            raise ImportError("jinja2 is required for template rendering")
        
        try:
            template = Template(template_content)
            return template.render(**variables)
        except TemplateError as e:
            raise ConfigValidationError(f"Template rendering failed: {e}")
    
    def generate_config_file(self,
                            service_id: str,
                            template_path: Path,
                            output_path: Path,
                            variables: Dict[str, Any],
                            backup: bool = True) -> Path:
        """
        Generate a config file from a template
        
        Args:
            service_id: Service identifier (for backup naming)
            template_path: Path to template file
            output_path: Where to write the rendered config
            variables: Template variables
            backup: Whether to backup existing file
        
        Returns:
            Path to generated config file
        """
        # Backup existing file if it exists
        if backup and output_path.exists():
            self.backup_config(service_id, output_path)
        
        # Read template
        with open(template_path, 'r') as f:
            template_content = f.read()
        
        # Render template
        rendered = self.render_template(template_content, variables)
        
        # Create output directory if needed
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Write rendered config
        with open(output_path, 'w') as f:
            f.write(rendered)
        
        return output_path
    
    def generate_env_file(self,
                         service_id: str,
                         variables: Dict[str, Any],
                         output_path: Path = None) -> Path:
        """
        Generate a .env file from variables
        
        Args:
            service_id: Service identifier
            variables: Dictionary of environment variables
            output_path: Where to write the .env file
        
        Returns:
            Path to generated .env file
        """
        if output_path is None:
            output_path = self.data_dir / service_id / '.env'
        
        # Create directory
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Backup existing
        if output_path.exists():
            self.backup_config(service_id, output_path)
        
        # Write env file
        with open(output_path, 'w') as f:
            f.write("# Auto-generated by PSO Configuration Manager\n")
            f.write(f"# Service: {service_id}\n\n")
            for key, value in variables.items():
                # Convert to uppercase for env vars
                env_key = key.upper()
                f.write(f"{env_key}={value}\n")
        
        return output_path
    
    def validate_config(self,
                       config_path: Path,
                       validation_rules: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
        """
        Validate a configuration file
        
        Args:
            config_path: Path to config file
            validation_rules: Validation rules (e.g., required keys, format)
        
        Returns:
            (is_valid, error_message)
        """
        if not config_path.exists():
            return False, f"Config file not found: {config_path}"
        
        # For now, just check file exists and is readable
        # TODO: Add format-specific validation (JSON, YAML, INI, etc.)
        try:
            with open(config_path, 'r') as f:
                content = f.read()
            
            if not content.strip():
                return False, "Config file is empty"
            
            return True, None
        
        except Exception as e:
            return False, f"Config validation error: {e}"
    
    def backup_config(self, service_id: str, config_path: Path) -> Path:
        """
        Backup a configuration file
        
        Args:
            service_id: Service identifier
            config_path: Path to config file to backup
        
        Returns:
            Path to backup file
        """
        import time
        
        # Create service backup directory
        service_backup_dir = self.backup_dir / service_id
        service_backup_dir.mkdir(parents=True, exist_ok=True)
        
        # Generate backup filename with timestamp
        timestamp = int(time.time())
        backup_name = f"{config_path.name}.{timestamp}.backup"
        backup_path = service_backup_dir / backup_name
        
        # Copy file
        shutil.copy2(config_path, backup_path)
        
        return backup_path
    
    def restore_config(self,
                      service_id: str,
                      config_name: str,
                      timestamp: int = None) -> Path:
        """
        Restore a configuration file from backup
        
        Args:
            service_id: Service identifier
            config_name: Name of config file (e.g., 'nginx.conf')
            timestamp: Specific backup timestamp (None = most recent)
        
        Returns:
            Path to restored config file
        """
        service_backup_dir = self.backup_dir / service_id
        
        if not service_backup_dir.exists():
            raise FileNotFoundError(f"No backups found for {service_id}")
        
        # Find matching backups
        pattern = f"{config_name}.*.backup"
        backups = list(service_backup_dir.glob(pattern))
        
        if not backups:
            raise FileNotFoundError(f"No backups found for {config_name}")
        
        # Sort by timestamp (most recent first)
        backups.sort(reverse=True)
        
        if timestamp:
            # Find specific timestamp
            backup_file = service_backup_dir / f"{config_name}.{timestamp}.backup"
            if not backup_file.exists():
                raise FileNotFoundError(f"Backup not found: {backup_file}")
        else:
            # Use most recent
            backup_file = backups[0]
        
        # Restore to original location
        original_path = self.data_dir / service_id / config_name
        shutil.copy2(backup_file, original_path)
        
        return original_path
    
    def list_backups(self, service_id: str) -> List[Dict[str, Any]]:
        """
        List all backups for a service
        
        Args:
            service_id: Service identifier
        
        Returns:
            List of backup info dictionaries
        """
        service_backup_dir = self.backup_dir / service_id
        
        if not service_backup_dir.exists():
            return []
        
        backups = []
        for backup_file in service_backup_dir.glob('*.backup'):
            # Parse filename: config_name.timestamp.backup
            parts = backup_file.name.rsplit('.', 2)
            if len(parts) == 3:
                config_name = parts[0]
                timestamp = int(parts[1])
                
                backups.append({
                    'config_name': config_name,
                    'timestamp': timestamp,
                    'path': backup_file,
                    'size': backup_file.stat().st_size
                })
        
        return sorted(backups, key=lambda x: x['timestamp'], reverse=True)
    
    def get_service_config_dir(self, service_id: str) -> Path:
        """
        Get the configuration directory for a service
        
        Args:
            service_id: Service identifier
        
        Returns:
            Path to service config directory
        """
        config_dir = self.data_dir / service_id
        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir
    
    def delete_service_configs(self, service_id: str, keep_backups: bool = True):
        """
        Delete all configs for a service
        
        Args:
            service_id: Service identifier
            keep_backups: Whether to preserve backups
        """
        config_dir = self.data_dir / service_id
        if config_dir.exists():
            shutil.rmtree(config_dir)
        
        if not keep_backups:
            backup_dir = self.backup_dir / service_id
            if backup_dir.exists():
                shutil.rmtree(backup_dir)


# Example usage
if __name__ == '__main__':
    # Example: Collecting user inputs
    config_manager = ConfigManager()
    
    # Sample input schema (from a manifest)
    input_schema = [
        {
            "name": "admin_email",
            "description": "Administrator email address",
            "type": "string",
            "required": True,
            "default": "admin@localhost",
            "validation": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
        },
        {
            "name": "port",
            "description": "HTTP port",
            "type": "int",
            "required": True,
            "default": 8080
        },
        {
            "name": "enable_ssl",
            "description": "Enable SSL/TLS",
            "type": "bool",
            "default": False
        }
    ]
    
    print("Configuration Manager Test")
    print("=" * 50)
    
    # Test non-interactive mode (uses defaults)
    print("\nTesting non-interactive mode (using defaults)...")
    inputs = config_manager.collect_user_inputs(input_schema, interactive=False)
    print(f"Collected: {inputs}")
    
    # Test template rendering
    print("\nTesting template rendering...")
    template = """
# Configuration for {{ service_name }}
admin_email = {{ admin_email }}
port = {{ port }}
ssl_enabled = {{ enable_ssl }}
"""
    
    rendered = config_manager.render_template(template, {
        'service_name': 'test-service',
        **inputs
    })
    print(rendered)
    
    print("\nConfiguration Manager ready!")