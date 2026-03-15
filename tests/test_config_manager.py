"""
Tests for Configuration Manager

Tests:
- User input collection
- Template rendering
- Config file generation
- Environment file generation
- Config validation
- Backup and restore
"""

import pytest
import tempfile
import shutil
from pathlib import Path
from unittest.mock import patch
import sys

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from core.config_manager import ConfigManager, ConfigValidationError


class TestConfigManager:
    """Test Configuration Manager functionality"""
    
    @pytest.fixture
    def temp_dir(self):
        """Create a temporary directory for tests"""
        temp = tempfile.mkdtemp()
        yield Path(temp)
        shutil.rmtree(temp)
    
    @pytest.fixture
    def config_manager(self, temp_dir):
        """Create a ConfigManager instance with temp directory"""
        return ConfigManager(data_dir=temp_dir)
    
    def test_initialization(self, config_manager, temp_dir):
        """Test ConfigManager initialization"""
        assert config_manager.data_dir == temp_dir
        assert config_manager.data_dir.exists()
        assert config_manager.backup_dir.exists()
    
    def test_collect_inputs_non_interactive(self, config_manager):
        """Test non-interactive input collection (uses defaults)"""
        schema = [
            {
                "name": "email",
                "type": "string",
                "default": "test@example.com",
                "required": False
            },
            {
                "name": "port",
                "type": "int",
                "default": 8080
            }
        ]
        
        inputs = config_manager.collect_user_inputs(schema, interactive=False)
        
        assert inputs['email'] == 'test@example.com'
        assert inputs['port'] == 8080
    
    def test_collect_inputs_required_no_default(self, config_manager):
        """Test that required inputs without defaults raise error"""
        schema = [
            {
                "name": "password",
                "type": "password",
                "required": True
                # No default!
            }
        ]
        
        with pytest.raises(ConfigValidationError):
            config_manager.collect_user_inputs(schema, interactive=False)
    
    @patch('builtins.input', return_value='user@test.com')
    def test_prompt_user_string(self, mock_input, config_manager):
        """Test string input prompting"""
        value = config_manager._prompt_user(
            name="email",
            description="Email address",
            input_type="string",
            required=True
        )
        assert value == 'user@test.com'
    
    @patch('builtins.input', return_value='')
    def test_prompt_user_default(self, mock_input, config_manager):
        """Test that default is used when input is empty"""
        value = config_manager._prompt_user(
            name="port",
            description="Port number",
            input_type="int",
            default=3000
        )
        assert value == 3000
    
    @patch('builtins.input', side_effect=['invalid', '8080'])
    def test_prompt_user_int_validation(self, mock_input, config_manager):
        """Test integer type validation (retries on invalid)"""
        value = config_manager._prompt_user(
            name="port",
            description="Port number",
            input_type="int",
            required=True
        )
        assert value == 8080
        assert mock_input.call_count == 2  # Failed once, then succeeded
    
    @patch('builtins.input', return_value='yes')
    def test_prompt_user_bool(self, mock_input, config_manager):
        """Test boolean input handling"""
        value = config_manager._prompt_user(
            name="ssl",
            description="Enable SSL",
            input_type="bool"
        )
        assert value is True
    
    @patch('builtins.input', side_effect=['invalid', 'option2'])
    def test_prompt_user_choice(self, mock_input, config_manager):
        """Test choice validation"""
        value = config_manager._prompt_user(
            name="mode",
            description="Select mode",
            input_type="choice",
            options=['option1', 'option2', 'option3'],
            required=True
        )
        assert value == 'option2'
        assert mock_input.call_count == 2
    
    @patch('builtins.input', side_effect=['invalid-email', 'valid@email.com'])
    def test_prompt_user_regex_validation(self, mock_input, config_manager):
        """Test regex validation"""
        value = config_manager._prompt_user(
            name="email",
            description="Email",
            input_type="string",
            validation=r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
            required=True
        )
        assert value == 'valid@email.com'
        assert mock_input.call_count == 2
    
    def test_render_template_simple(self, config_manager):
        """Test simple template rendering"""
        template = "Hello {{ name }}!"
        variables = {"name": "World"}
        
        result = config_manager.render_template(template, variables)
        assert result == "Hello World!"
    
    def test_render_template_complex(self, config_manager):
        """Test complex template with conditionals and loops"""
        template = """
# Config for {{ service }}
port = {{ port }}
{% if ssl_enabled %}
ssl = true
ssl_port = 443
{% endif %}
{% for user in users %}
user = {{ user }}
{% endfor %}
"""
        variables = {
            "service": "nginx",
            "port": 80,
            "ssl_enabled": True,
            "users": ["admin", "user1", "user2"]
        }
        
        result = config_manager.render_template(template, variables)
        assert "nginx" in result
        assert "ssl = true" in result
        assert "user = admin" in result
    
    def test_generate_config_file(self, config_manager, temp_dir):
        """Test config file generation from template"""
        # Create a template file
        template_path = temp_dir / 'template.conf'
        with open(template_path, 'w') as f:
            f.write("server_name = {{ server_name }}\nport = {{ port }}")
        
        # Generate config
        output_path = temp_dir / 'test-service' / 'config.conf'
        variables = {"server_name": "myserver", "port": 8080}
        
        result_path = config_manager.generate_config_file(
            service_id='test-service',
            template_path=template_path,
            output_path=output_path,
            variables=variables,
            backup=False
        )
        
        assert result_path.exists()
        content = result_path.read_text()
        assert "server_name = myserver" in content
        assert "port = 8080" in content
    
    def test_generate_env_file(self, config_manager, temp_dir):
        """Test .env file generation"""
        variables = {
            "database_url": "postgresql://localhost/db",
            "api_key": "secret123",
            "debug": "true"
        }
        
        env_path = config_manager.generate_env_file(
            service_id='test-service',
            variables=variables
        )
        
        assert env_path.exists()
        content = env_path.read_text()
        assert "DATABASE_URL=postgresql://localhost/db" in content
        assert "API_KEY=secret123" in content
        assert "DEBUG=true" in content
    
    def test_backup_config(self, config_manager, temp_dir):
        """Test config file backup"""
        # Create a config file
        config_dir = config_manager.get_service_config_dir('test-service')
        config_file = config_dir / 'test.conf'
        config_file.write_text("original content")
        
        # Backup it
        backup_path = config_manager.backup_config('test-service', config_file)
        
        assert backup_path.exists()
        assert backup_path.read_text() == "original content"
        assert 'test.conf' in backup_path.name
        assert '.backup' in backup_path.name
    
    def test_restore_config(self, config_manager, temp_dir):
        """Test config restore from backup"""
        # Create and backup a config
        config_dir = config_manager.get_service_config_dir('test-service')
        config_file = config_dir / 'test.conf'
        config_file.write_text("original content")
        
        backup_path = config_manager.backup_config('test-service', config_file)
        
        # Modify the config
        config_file.write_text("modified content")
        
        # Restore from backup
        restored = config_manager.restore_config('test-service', 'test.conf')
        
        assert restored.read_text() == "original content"
    
    def test_list_backups(self, config_manager, temp_dir):
        """Test listing backups for a service"""
        # Create and backup a config multiple times
        config_dir = config_manager.get_service_config_dir('test-service')
        config_file = config_dir / 'test.conf'
        
        config_file.write_text("version 1")
        config_manager.backup_config('test-service', config_file)
        
        import time
        time.sleep(1.1)  # Ensure different timestamps (second-precision filenames)
        
        config_file.write_text("version 2")
        config_manager.backup_config('test-service', config_file)
        
        # List backups
        backups = config_manager.list_backups('test-service')
        
        assert len(backups) == 2
        assert backups[0]['config_name'] == 'test.conf'
        assert backups[0]['timestamp'] > backups[1]['timestamp']  # Most recent first
    
    def test_validate_config_exists(self, config_manager, temp_dir):
        """Test config validation - file exists"""
        config_file = temp_dir / 'test.conf'
        config_file.write_text("some content")
        
        is_valid, error = config_manager.validate_config(config_file, {})
        
        assert is_valid is True
        assert error is None
    
    def test_validate_config_missing(self, config_manager, temp_dir):
        """Test config validation - file missing"""
        config_file = temp_dir / 'nonexistent.conf'
        
        is_valid, error = config_manager.validate_config(config_file, {})
        
        assert is_valid is False
        assert "not found" in error.lower()
    
    def test_validate_config_empty(self, config_manager, temp_dir):
        """Test config validation - empty file"""
        config_file = temp_dir / 'empty.conf'
        config_file.write_text("")
        
        is_valid, error = config_manager.validate_config(config_file, {})
        
        assert is_valid is False
        assert "empty" in error.lower()
    
    def test_get_service_config_dir(self, config_manager):
        """Test getting service config directory"""
        config_dir = config_manager.get_service_config_dir('my-service')
        
        assert config_dir.exists()
        assert config_dir.name == 'my-service'
        assert config_dir.parent == config_manager.data_dir
    
    def test_delete_service_configs_keep_backups(self, config_manager):
        """Test deleting service configs while keeping backups"""
        # Create config and backup
        config_dir = config_manager.get_service_config_dir('test-service')
        config_file = config_dir / 'test.conf'
        config_file.write_text("test")
        
        backup_path = config_manager.backup_config('test-service', config_file)
        
        # Delete configs
        config_manager.delete_service_configs('test-service', keep_backups=True)
        
        assert not config_dir.exists()
        assert backup_path.exists()
    
    def test_delete_service_configs_delete_backups(self, config_manager):
        """Test deleting service configs including backups"""
        # Create config and backup
        config_dir = config_manager.get_service_config_dir('test-service')
        config_file = config_dir / 'test.conf'
        config_file.write_text("test")
        
        backup_path = config_manager.backup_config('test-service', config_file)
        
        # Delete everything
        config_manager.delete_service_configs('test-service', keep_backups=False)
        
        assert not config_dir.exists()
        assert not backup_path.parent.exists()
    
    def test_generate_config_with_backup(self, config_manager, temp_dir):
        """Test that generating config creates backup of existing file"""
        # Create template
        template_path = temp_dir / 'template.conf'
        template_path.write_text("version = {{ version }}")
        
        output_path = temp_dir / 'test-service' / 'config.conf'
        
        # Generate first version
        config_manager.generate_config_file(
            'test-service', template_path, output_path,
            {'version': 1}, backup=True
        )
        
        # Generate second version (should backup first)
        config_manager.generate_config_file(
            'test-service', template_path, output_path,
            {'version': 2}, backup=True
        )
        
        # Check current version
        assert "version = 2" in output_path.read_text()
        
        # Check backup exists
        backups = config_manager.list_backups('test-service')
        assert len(backups) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])