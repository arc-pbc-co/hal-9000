"""Unit tests for configuration module."""

from pathlib import Path

from hal9000.config import (
    ADAMConfig,
    CloudConfig,
    DatabaseConfig,
    GatewayConfig,
    GDriveConfig,
    ObsidianConfig,
    ProcessingConfig,
    Settings,
    SourcesConfig,
    TaxonomyConfig,
    get_settings,
    load_settings,
)


class TestSourcesConfig:
    """Tests for SourcesConfig."""

    def test_default_values(self):
        """Test default configuration values."""
        config = SourcesConfig()

        assert len(config.local_paths) == 2
        assert config.watch_mode is False

    def test_custom_values(self):
        """Test custom configuration values."""
        config = SourcesConfig(
            local_paths=["/custom/path"],
            watch_mode=True
        )

        assert config.local_paths == ["/custom/path"]
        assert config.watch_mode is True


class TestGDriveConfig:
    """Tests for GDriveConfig."""

    def test_default_values(self):
        """Test default values."""
        config = GDriveConfig()

        assert config.enabled is False
        assert config.credentials_path is None
        assert config.folder_ids == []

    def test_custom_values(self):
        """Test custom values."""
        config = GDriveConfig(
            enabled=True,
            credentials_path="/path/to/creds.json",
            folder_ids=["folder1", "folder2"]
        )

        assert config.enabled is True
        assert config.credentials_path == "/path/to/creds.json"
        assert len(config.folder_ids) == 2


class TestCloudConfig:
    """Tests for CloudConfig."""

    def test_default_values(self):
        """Test default nested config."""
        config = CloudConfig()

        assert isinstance(config.gdrive, GDriveConfig)
        assert config.gdrive.enabled is False


class TestObsidianConfig:
    """Tests for ObsidianConfig."""

    def test_default_values(self):
        """Test default values."""
        config = ObsidianConfig()

        assert "HAL9000" in config.vault_path
        assert config.create_canvas is True
        assert config.auto_link is True

    def test_custom_values(self):
        """Test custom values."""
        config = ObsidianConfig(
            vault_path="/custom/vault",
            create_canvas=False,
            auto_link=False
        )

        assert config.vault_path == "/custom/vault"
        assert config.create_canvas is False
        assert config.auto_link is False


class TestADAMConfig:
    """Tests for ADAMConfig."""

    def test_default_values(self):
        """Test default values."""
        config = ADAMConfig()

        assert config.enabled is True
        assert config.default_domain == "materials_science"
        assert config.api_url is None
        assert config.api_key is None

    def test_custom_values(self):
        """Test custom values."""
        config = ADAMConfig(
            enabled=False,
            output_path="/custom/output",
            api_url="https://adam.api.com",
            api_key="secret"
        )

        assert config.enabled is False
        assert config.output_path == "/custom/output"
        assert config.api_url == "https://adam.api.com"


class TestProcessingConfig:
    """Tests for ProcessingConfig."""

    def test_default_values(self):
        """Test default values."""
        config = ProcessingConfig()

        assert config.chunk_size == 50000
        assert config.max_concurrent_calls == 5
        assert config.cache_enabled is True

    def test_custom_values(self):
        """Test custom values."""
        config = ProcessingConfig(
            chunk_size=100000,
            max_concurrent_calls=10,
            cache_enabled=False
        )

        assert config.chunk_size == 100000
        assert config.max_concurrent_calls == 10
        assert config.cache_enabled is False


class TestTaxonomyConfig:
    """Tests for TaxonomyConfig."""

    def test_default_values(self):
        """Test default values."""
        config = TaxonomyConfig()

        assert config.auto_extend is True
        assert "materials_science_taxonomy" in config.base_file

    def test_custom_values(self):
        """Test custom values."""
        config = TaxonomyConfig(
            auto_extend=False,
            base_file="/custom/taxonomy.yaml"
        )

        assert config.auto_extend is False
        assert config.base_file == "/custom/taxonomy.yaml"


class TestDatabaseConfig:
    """Tests for DatabaseConfig."""

    def test_default_values(self):
        """Test default values."""
        config = DatabaseConfig()

        assert "sqlite" in config.url
        assert "hal9000.db" in config.url

    def test_custom_values(self):
        """Test custom values."""
        config = DatabaseConfig(
            url="postgresql://localhost:5432/hal9000"
        )

        assert "postgresql" in config.url


class TestGatewayConfig:
    """Tests for GatewayConfig."""

    def test_default_values(self):
        """Test default values."""
        config = GatewayConfig()

        assert config.host == "127.0.0.1"
        assert config.port == 9000
        assert config.max_connections == 100
        assert config.session_timeout_minutes == 60

    def test_custom_values(self):
        """Test custom values."""
        config = GatewayConfig(
            host="0.0.0.0",
            port=8080,
            max_connections=50,
            session_timeout_minutes=30
        )

        assert config.host == "0.0.0.0"
        assert config.port == 8080
        assert config.max_connections == 50
        assert config.session_timeout_minutes == 30


class TestSettings:
    """Tests for main Settings class."""

    def test_default_values(self):
        """Test default settings."""
        settings = Settings()

        assert isinstance(settings.sources, SourcesConfig)
        assert isinstance(settings.cloud, CloudConfig)
        assert isinstance(settings.obsidian, ObsidianConfig)
        assert isinstance(settings.adam, ADAMConfig)
        assert isinstance(settings.processing, ProcessingConfig)
        assert isinstance(settings.taxonomy, TaxonomyConfig)
        assert isinstance(settings.database, DatabaseConfig)
        assert isinstance(settings.gateway, GatewayConfig)
        assert settings.log_level == "INFO"
        assert settings.verbose is False

    def test_get_vault_path(self):
        """Test get_vault_path method."""
        settings = Settings()
        vault_path = settings.get_vault_path()

        assert isinstance(vault_path, Path)
        # Should expand user directory
        assert "~" not in str(vault_path)

    def test_get_local_paths(self):
        """Test get_local_paths method."""
        settings = Settings()
        paths = settings.get_local_paths()

        assert isinstance(paths, list)
        assert all(isinstance(p, Path) for p in paths)
        # Should expand user directories
        for path in paths:
            assert "~" not in str(path)

    def test_get_cache_path(self):
        """Test get_cache_path method."""
        settings = Settings()
        cache_path = settings.get_cache_path()

        assert isinstance(cache_path, Path)

    def test_custom_settings(self):
        """Test creating settings with custom values."""
        settings = Settings(
            log_level="DEBUG",
            verbose=True,
            anthropic_api_key="test-key"
        )

        assert settings.log_level == "DEBUG"
        assert settings.verbose is True
        assert settings.anthropic_api_key == "test-key"


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_without_config_file(self):
        """Test loading settings without config file."""
        settings = load_settings()

        assert isinstance(settings, Settings)

    def test_load_with_nonexistent_file(self, temp_directory: Path):
        """Test loading with nonexistent config file."""
        config_path = temp_directory / "nonexistent.yaml"
        settings = load_settings(config_path)

        # Should return default settings
        assert isinstance(settings, Settings)

    def test_load_with_yaml_file(self, temp_directory: Path):
        """Test loading with YAML config file."""
        import yaml

        config_data = {
            "hal9000": {
                "log_level": "DEBUG",
                "verbose": True,
            }
        }

        config_path = temp_directory / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        settings = load_settings(config_path)

        assert settings.log_level == "DEBUG"
        assert settings.verbose is True

    def test_load_with_nested_config(self, temp_directory: Path):
        """Test loading nested configuration."""
        import yaml

        config_data = {
            "hal9000": {
                "processing": {
                    "chunk_size": 75000,
                    "max_concurrent_calls": 3,
                }
            }
        }

        config_path = temp_directory / "config.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        settings = load_settings(config_path)

        assert settings.processing.chunk_size == 75000
        assert settings.processing.max_concurrent_calls == 3


class TestGetSettings:
    """Tests for get_settings function."""

    def test_get_settings_returns_instance(self):
        """Test that get_settings returns a Settings instance."""
        # Reset the global settings
        import hal9000.config as config_module
        config_module._settings = None

        settings = get_settings()

        assert isinstance(settings, Settings)

    def test_get_settings_singleton(self):
        """Test that get_settings returns the same instance."""
        import hal9000.config as config_module
        config_module._settings = None

        settings1 = get_settings()
        settings2 = get_settings()

        assert settings1 is settings2

    def test_get_settings_respects_config_file(self, temp_directory: Path):
        """Test get_settings can be reloaded from a specific config file."""
        import yaml

        import hal9000.config as config_module

        config_module._settings = None
        config_module._settings_config_path = None

        config_data = {
            "hal9000": {
                "log_level": "WARNING",
            }
        }
        config_path = temp_directory / "settings.yaml"
        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        settings = get_settings(config_file=config_path, force_reload=True)
        assert settings.log_level == "WARNING"


class TestEnvironmentVariables:
    """Tests for environment variable configuration."""

    def test_env_var_prefix(self, monkeypatch):
        """Test that HAL9000_ prefix is used for env vars."""
        monkeypatch.setenv("HAL9000_LOG_LEVEL", "ERROR")

        settings = Settings()

        assert settings.log_level == "ERROR"

    def test_env_var_verbose(self, monkeypatch):
        """Test verbose setting from environment."""
        monkeypatch.setenv("HAL9000_VERBOSE", "true")

        settings = Settings()

        assert settings.verbose is True

    def test_env_var_api_key(self, monkeypatch):
        """Test API key from environment."""
        monkeypatch.setenv("HAL9000_ANTHROPIC_API_KEY", "test-api-key")

        settings = Settings()

        assert settings.anthropic_api_key == "test-api-key"

    def test_env_var_api_key_unprefixed(self, monkeypatch):
        """Test ANTHROPIC_API_KEY alias support."""
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-api-key-unprefixed")

        settings = Settings()

        assert settings.anthropic_api_key == "test-api-key-unprefixed"

    def test_env_var_gateway_host(self, monkeypatch):
        """Test gateway host from environment."""
        monkeypatch.setenv("HAL9000_GATEWAY__HOST", "0.0.0.0")

        settings = Settings()

        assert settings.gateway.host == "0.0.0.0"

    def test_env_var_gateway_port(self, monkeypatch):
        """Test gateway port from environment."""
        monkeypatch.setenv("HAL9000_GATEWAY__PORT", "8080")

        settings = Settings()

        assert settings.gateway.port == 8080
