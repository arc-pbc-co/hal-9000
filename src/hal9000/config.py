"""Configuration management for HAL 9000."""

from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SourcesConfig(BaseSettings):
    """Configuration for document sources."""

    local_paths: list[str] = Field(
        default_factory=lambda: ["~/Documents/Research", "~/Downloads/Papers"],
        description="Local filesystem paths to scan for PDFs",
    )
    watch_mode: bool = Field(
        default=False, description="Enable continuous watching of source directories"
    )


class GDriveConfig(BaseSettings):
    """Google Drive configuration."""

    enabled: bool = False
    credentials_path: Optional[str] = None
    folder_ids: list[str] = Field(default_factory=list)


class CloudConfig(BaseSettings):
    """Cloud storage configuration."""

    gdrive: GDriveConfig = Field(default_factory=GDriveConfig)


class ObsidianConfig(BaseSettings):
    """Obsidian vault configuration."""

    vault_path: str = Field(
        default="~/ObsidianVault/HAL9000Research",
        description="Path to the Obsidian vault",
    )
    templates_path: str = Field(
        default="./templates/obsidian", description="Path to note templates"
    )
    create_canvas: bool = Field(
        default=True, description="Generate Obsidian Canvas files for mind maps"
    )
    auto_link: bool = Field(
        default=True, description="Automatically create links between related documents"
    )


class ADAMConfig(BaseSettings):
    """ADAM Platform configuration."""

    enabled: bool = Field(default=True, description="Enable ADAM context generation")
    output_path: str = Field(
        default="./adam_contexts", description="Output path for ADAM context files"
    )
    default_domain: str = Field(
        default="materials_science", description="Default research domain"
    )
    # Future: API configuration when live integration is available
    api_url: Optional[str] = None
    api_key: Optional[str] = None


class ProcessingConfig(BaseSettings):
    """Document processing configuration."""

    chunk_size: int = Field(
        default=50000, description="Characters per chunk for RLM processing"
    )
    max_concurrent_calls: int = Field(
        default=5, description="Maximum concurrent LLM calls"
    )
    cache_enabled: bool = Field(default=True, description="Enable processing cache")
    cache_path: str = Field(default="./.hal9000_cache", description="Cache directory")


class TaxonomyConfig(BaseSettings):
    """Taxonomy configuration."""

    auto_extend: bool = Field(
        default=True, description="Automatically extend taxonomy with new topics"
    )
    base_file: str = Field(
        default="./config/materials_science_taxonomy.yaml",
        description="Base taxonomy file",
    )


class DatabaseConfig(BaseSettings):
    """Database configuration."""

    url: str = Field(
        default="sqlite:///./hal9000.db", description="Database connection URL"
    )


class Settings(BaseSettings):
    """Main HAL 9000 settings."""

    model_config = SettingsConfigDict(
        env_prefix="HAL9000_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Sub-configurations
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    adam: ADAMConfig = Field(default_factory=ADAMConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    taxonomy: TaxonomyConfig = Field(default_factory=TaxonomyConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)

    # Anthropic API configuration
    anthropic_api_key: Optional[str] = Field(
        default=None, description="Anthropic API key (can also use ANTHROPIC_API_KEY env)"
    )

    # Logging
    log_level: str = Field(default="INFO", description="Logging level")
    verbose: bool = Field(default=False, description="Enable verbose output")

    def get_vault_path(self) -> Path:
        """Get expanded vault path."""
        return Path(self.obsidian.vault_path).expanduser()

    def get_local_paths(self) -> list[Path]:
        """Get expanded local source paths."""
        return [Path(p).expanduser() for p in self.sources.local_paths]

    def get_cache_path(self) -> Path:
        """Get expanded cache path."""
        return Path(self.processing.cache_path).expanduser()


def load_settings(config_file: Optional[Path] = None) -> Settings:
    """Load settings from environment and optional config file."""
    import yaml

    settings = Settings()

    if config_file and config_file.exists():
        with open(config_file) as f:
            config_data = yaml.safe_load(f)
            if config_data and "hal9000" in config_data:
                # Merge YAML config with settings
                settings = Settings(**config_data["hal9000"])

    return settings


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None


def get_settings() -> Settings:
    """Get the global settings instance."""
    global _settings
    if _settings is None:
        _settings = load_settings()
    return _settings
