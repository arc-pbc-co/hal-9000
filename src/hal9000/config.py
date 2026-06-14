"""Configuration management for HAL 9000."""

import json
import os
from pathlib import Path
from typing import Any, Optional

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

SUPPORTED_ENVIRONMENTS = {"local", "staging", "production"}


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


class StorageConfig(BaseSettings):
    """Object storage configuration."""

    backend: str = Field(default="local", description="Object storage backend")
    root_path: str = Field(
        default="./.hal9000_objects",
        description="Root path for the local object storage backend",
    )
    bucket: Optional[str] = Field(default=None, description="S3-compatible bucket name")
    prefix: str = Field(default="", description="Optional S3-compatible object key prefix")
    region: Optional[str] = Field(default=None, description="S3-compatible storage region")
    endpoint_url: Optional[str] = Field(
        default=None,
        description="Optional S3-compatible endpoint URL for non-AWS storage",
    )


class VectorConfig(BaseSettings):
    """Vector storage and embedding configuration."""

    backend: str = Field(default="pgvector", description="Vector storage backend")
    embedding_provider: str = Field(default="fake", description="Embedding provider name")
    embedding_dimension: int = Field(default=1536, description="Embedding vector dimension")
    embedding_model: Optional[str] = Field(default=None, description="Embedding model name")
    retrieval_limit: int = Field(default=5, description="Default semantic retrieval result limit")


class AcquisitionConfig(BaseSettings):
    """Paper acquisition configuration."""

    download_dir: str = Field(
        default="~/Documents/Research/Acquired",
        description="Directory for downloaded papers",
    )
    default_sources: list[str] = Field(
        default_factory=lambda: ["semantic_scholar", "arxiv"],
        description="Default search providers to use",
    )
    max_concurrent_downloads: int = Field(
        default=3, description="Maximum concurrent downloads"
    )
    rate_limit_seconds: float = Field(
        default=1.0, description="Minimum seconds between API requests"
    )
    semantic_scholar_api_key: Optional[str] = Field(
        default=None, description="Semantic Scholar API key for higher rate limits"
    )
    unpaywall_email: Optional[str] = Field(
        default=None, description="Email for Unpaywall API (required for OA resolution)"
    )
    auto_process: bool = Field(
        default=True, description="Automatically process downloaded papers"
    )
    auto_generate_notes: bool = Field(
        default=True, description="Automatically generate Obsidian notes"
    )
    relevance_threshold: float = Field(
        default=0.5, description="Minimum relevance score for papers (0-1)"
    )


class GatewayConfig(BaseSettings):
    """Gateway WebSocket server configuration."""

    host: str = Field(
        default="127.0.0.1", description="Host address to bind to"
    )
    port: int = Field(
        default=9000, description="Port number to listen on"
    )
    max_connections: int = Field(
        default=100, description="Maximum concurrent connections"
    )
    session_timeout_minutes: int = Field(
        default=60, description="Session timeout in minutes (0 = no timeout)"
    )


class AppGatewayConfig(BaseSettings):
    """HTTP app gateway configuration for Slack and Sheets-facing routes."""

    slack_required: bool = Field(
        default=False,
        description="Require Slack request signing for staging/production readiness checks",
    )
    slack_signing_secret: Optional[str] = Field(
        default=None,
        description="Slack signing secret for request verification",
    )
    sheets_writeback_enabled: bool = Field(
        default=False,
        description="Enable the inbound Google Sheets writeback webhook route",
    )
    sheets_writeback_token: Optional[str] = Field(
        default=None,
        description="Bearer token accepted by the Sheets writeback webhook route",
    )


class AuthConfig(BaseSettings):
    """Authentication and OIDC claim mapping configuration."""

    enabled: bool = Field(default=False, description="Enable authenticated shared access")
    provider: str = Field(default="oidc", description="Authentication provider type")
    oidc_issuer_url: Optional[str] = Field(default=None, description="OIDC issuer URL")
    oidc_audience: Optional[str] = Field(default=None, description="Expected OIDC audience")
    email_claim: str = Field(default="email", description="OIDC claim containing user email")
    subject_claim: str = Field(default="sub", description="OIDC claim containing stable subject")
    name_claim: str = Field(default="name", description="OIDC claim containing display name")
    groups_claim: str = Field(default="groups", description="OIDC claim containing group names")
    admin_groups: list[str] = Field(
        default_factory=list,
        description="OIDC groups that map users to global admin",
    )
    team_group_prefix: str = Field(
        default="hal:",
        description="Only groups with this prefix are synced as HAL team memberships",
    )


class AgentConfig(BaseSettings):
    """Agent runtime and model-provider configuration."""

    model_name: str = Field(
        default="anthropic/claude-opus-4-8",
        description="Default LiteLLM-compatible model id for HAL agent sessions",
    )
    reasoning_effort: Optional[str] = Field(
        default=None,
        description="Optional reasoning effort forwarded when the selected provider supports it",
    )
    max_tokens: int = Field(default=4096, description="Maximum tokens for agent model responses")
    timeout_seconds: float = Field(default=600.0, description="Model request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum provider attempts per model request")
    approval_timeout_seconds: Optional[float] = Field(
        default=None,
        description="Optional timeout for human approval of gated agent tools",
    )
    max_context_tokens: Optional[int] = Field(
        default=None,
        description="Estimated input-token budget that triggers agent context compaction",
    )
    compact_target_tokens: Optional[int] = Field(
        default=None,
        description="Estimated token target after agent context compaction",
    )
    compact_preserve_last: int = Field(
        default=8,
        description="Recent message count to preserve when compacting agent context",
    )
    hf_router_base_url: str = Field(
        default="https://router.huggingface.co/v1",
        description="OpenAI-compatible Hugging Face Router base URL",
    )


class RetentionConfig(BaseSettings):
    """Production retention policy for operational HAL records."""

    enabled: bool = Field(
        default=False,
        description="Allow explicit retention apply commands to delete expired records",
    )
    run_event_days: int = Field(
        default=365,
        ge=0,
        description="Days to retain research run ledger events",
    )
    tool_call_days: int = Field(
        default=365,
        ge=0,
        description="Days to retain durable tool-call accounting records",
    )
    notification_days: int = Field(
        default=180,
        ge=0,
        description="Days to retain collaboration notification rows",
    )
    audit_event_days: int = Field(
        default=730,
        ge=0,
        description="Days to retain review and collaboration audit events",
    )
    gateway_session_days: int = Field(
        default=30,
        ge=0,
        description="Days to retain persisted gateway sessions after last activity",
    )
    pdf_artifact_days: int = Field(
        default=2555,
        ge=0,
        description="Days to retain object-store PDFs and source artifacts",
    )
    output_artifact_days: int = Field(
        default=1095,
        ge=0,
        description="Days to retain generated output artifacts in object storage",
    )


class Settings(BaseSettings):
    """Main HAL 9000 settings."""

    model_config = SettingsConfigDict(
        env_prefix="HAL9000_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

    # Sub-configurations
    environment: str = Field(
        default="local",
        description="Deployment environment profile: local, staging, or production",
    )
    sources: SourcesConfig = Field(default_factory=SourcesConfig)
    cloud: CloudConfig = Field(default_factory=CloudConfig)
    obsidian: ObsidianConfig = Field(default_factory=ObsidianConfig)
    adam: ADAMConfig = Field(default_factory=ADAMConfig)
    processing: ProcessingConfig = Field(default_factory=ProcessingConfig)
    taxonomy: TaxonomyConfig = Field(default_factory=TaxonomyConfig)
    database: DatabaseConfig = Field(default_factory=DatabaseConfig)
    storage: StorageConfig = Field(default_factory=StorageConfig)
    vector: VectorConfig = Field(default_factory=VectorConfig)
    acquisition: AcquisitionConfig = Field(default_factory=AcquisitionConfig)
    gateway: GatewayConfig = Field(default_factory=GatewayConfig)
    app_gateway: AppGatewayConfig = Field(default_factory=AppGatewayConfig)
    auth: AuthConfig = Field(default_factory=AuthConfig)
    agent: AgentConfig = Field(default_factory=AgentConfig)
    retention: RetentionConfig = Field(default_factory=RetentionConfig)

    # Anthropic API configuration
    anthropic_api_key: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "HAL9000_ANTHROPIC_API_KEY",
            "ANTHROPIC_API_KEY",
        ),
        description="Anthropic API key (supports HAL9000_ANTHROPIC_API_KEY and ANTHROPIC_API_KEY)",
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

    def get_acquisition_dir(self) -> Path:
        """Get expanded acquisition download directory."""
        return Path(self.acquisition.download_dir).expanduser()

    def get_storage_path(self) -> Path:
        """Get expanded object storage root path."""
        return Path(self.storage.root_path).expanduser()

    def is_production(self) -> bool:
        """Return whether this configuration targets production."""
        return self.environment == "production"

    def profile_readiness_issues(self) -> list[str]:
        """Return configuration issues that should be fixed before deployment."""
        issues: list[str] = []
        environment = normalize_environment(self.environment)
        if self.environment != environment:
            issues.append(f"Unsupported environment profile: {self.environment}")
            return issues

        if environment in {"staging", "production"}:
            from hal9000.security import create_secret_manager_from_settings, secret_value

            secret_manager = create_secret_manager_from_settings(self)
            if not self.database.url.startswith("postgresql+psycopg://"):
                issues.append("database.url should use postgresql+psycopg:// for staging/production")
            if self.storage.backend != "s3":
                issues.append("storage.backend should be s3 for staging/production")
            if not self.storage.bucket:
                issues.append("storage.bucket is required for staging/production")
            if self.vector.backend != "pgvector":
                issues.append("vector.backend should be pgvector for staging/production")
            if self.auth.enabled:
                if not self.auth.oidc_issuer_url:
                    issues.append("auth.oidc_issuer_url is required when auth is enabled")
                if not self.auth.oidc_audience:
                    issues.append("auth.oidc_audience is required when auth is enabled")
            if self.app_gateway.slack_required and not secret_value(
                "slack",
                secret_manager=secret_manager,
            ):
                issues.append(
                    "app_gateway.slack_signing_secret is required when Slack is required"
                )
            if self.app_gateway.sheets_writeback_enabled and not secret_value(
                "google_sheets",
                secret_manager=secret_manager,
            ):
                issues.append(
                    "app_gateway.sheets_writeback_token is required when Sheets writeback is enabled"
                )

        return issues


def normalize_environment(environment: Optional[str]) -> str:
    """Normalize and validate an environment profile name."""
    normalized = (environment or "local").strip().lower()
    if normalized not in SUPPORTED_ENVIRONMENTS:
        supported = ", ".join(sorted(SUPPORTED_ENVIRONMENTS))
        raise ValueError(f"Unsupported HAL 9000 environment profile: {environment}. Supported: {supported}")
    return normalized


def profile_config_path(environment: str) -> Path:
    """Return the checked-in config path for an environment profile."""
    return Path(__file__).resolve().parents[2] / "config" / f"{normalize_environment(environment)}.yaml"


def load_settings(
    config_file: Optional[Path] = None,
    environment: Optional[str] = None,
) -> Settings:
    """Load settings from environment profile, optional config file, and env vars."""
    import yaml

    profile_name = _resolve_environment(environment)
    config_data: dict[str, Any] = {}

    if environment is not None or _profile_env_value() is not None:
        profile_path = profile_config_path(profile_name)
        config_data = _deep_merge(config_data, _load_yaml_settings(profile_path, yaml))

    config_data = _deep_merge(config_data, _load_yaml_settings(config_file, yaml))
    config_data = _deep_merge(config_data, _environment_overrides())
    if environment is not None:
        config_data["environment"] = profile_name

    if config_data:
        return Settings(**config_data)
    return Settings()


def _load_yaml_settings(config_file: Optional[Path], yaml_module) -> dict[str, Any]:
    if config_file and config_file.exists():
        with open(config_file) as f:
            config_data = yaml_module.safe_load(f)
            if config_data and "hal9000" in config_data:
                return config_data["hal9000"] or {}
    return {}


def _resolve_environment(environment: Optional[str]) -> str:
    return normalize_environment(environment or _profile_env_value() or "local")


def _profile_env_value() -> Optional[str]:
    return (
        os.getenv("HAL9000_PROFILE")
        or os.getenv("HAL9000_ENVIRONMENT")
        or os.getenv("HAL9000_ENV")
    )


def _environment_overrides() -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    prefix = "HAL9000_"
    for key, value in os.environ.items():
        if not key.startswith(prefix):
            continue
        raw_path = key[len(prefix) :]
        if raw_path in {"PROFILE", "ENV"}:
            continue
        path = [part.lower() for part in raw_path.split("__")]
        if path == ["environment"]:
            overrides["environment"] = normalize_environment(value)
            continue
        _set_nested(overrides, path, _parse_env_value(value))

    if "ANTHROPIC_API_KEY" in os.environ:
        overrides["anthropic_api_key"] = os.environ["ANTHROPIC_API_KEY"]
    return overrides


def _parse_env_value(value: str) -> Any:
    stripped = value.strip()
    if stripped.lower() in {"true", "false"}:
        return stripped.lower() == "true"
    if stripped.lower() == "null":
        return None
    if stripped.startswith(("[", "{")):
        try:
            return json.loads(stripped)
        except json.JSONDecodeError:
            return value
    return value


def _set_nested(target: dict[str, Any], path: list[str], value: Any) -> None:
    current = target
    for part in path[:-1]:
        child = current.get(part)
        if not isinstance(child, dict):
            child = {}
            current[part] = child
        current = child
    current[path[-1]] = value


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


# Global settings instance (lazy loaded)
_settings: Optional[Settings] = None
_settings_config_path: Optional[Path] = None
_settings_environment: Optional[str] = None


def _normalize_config_path(config_file: Optional[Path]) -> Optional[Path]:
    """Normalize config path for caching comparisons."""
    if config_file is None:
        return None
    return config_file.expanduser().resolve()


def get_settings(
    config_file: Optional[Path] = None,
    environment: Optional[str] = None,
    force_reload: bool = False,
) -> Settings:
    """Get the global settings instance.

    Args:
        config_file: Optional YAML config path to merge into settings.
        environment: Optional environment profile to load.
        force_reload: Force reload from environment/config even if cached.
    """
    global _settings
    global _settings_config_path
    global _settings_environment

    normalized_config = _normalize_config_path(config_file)
    normalized_environment = _resolve_environment(environment)
    should_reload = (
        force_reload
        or _settings is None
        or normalized_environment != _settings_environment
        or (
            normalized_config is not None
            and normalized_config != _settings_config_path
        )
    )

    if should_reload:
        _settings = load_settings(normalized_config, environment=environment)
        _settings_config_path = normalized_config
        _settings_environment = normalized_environment
    return _settings
