"""Small security helpers shared by deployment-facing surfaces."""

from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

REDACTION = "[redacted]"

SECRET_KEY_MARKERS = (
    "authorization",
    "api_key",
    "apikey",
    "access_key",
    "client_secret",
    "cookie",
    "password",
    "private_key",
    "refresh_token",
    "secret",
    "signature",
    "token",
)

PROVIDER_SECRET_CANDIDATES: dict[str, tuple[str, ...]] = {
    "anthropic": ("HAL9000_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY"),
    "openai": ("HAL9000_OPENAI_API_KEY", "OPENAI_API_KEY"),
    "gemini": ("HAL9000_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "google": ("HAL9000_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY"),
    "huggingface": ("INFERENCE_TOKEN", "HF_TOKEN", "HUGGING_FACE_HUB_TOKEN"),
    "github": ("GITHUB_TOKEN",),
    "semantic_scholar": (
        "HAL9000_ACQUISITION__SEMANTIC_SCHOLAR_API_KEY",
        "SEMANTIC_SCHOLAR_API_KEY",
    ),
    "slack": ("HAL9000_SLACK_SIGNING_SECRET",),
    "google_sheets": ("HAL9000_GOOGLE_SHEETS_TOKEN",),
    "smtp": ("HAL9000_SMTP_PASSWORD",),
    "local_llm": ("LOCAL_LLM_API_KEY",),
}


@dataclass(frozen=True)
class SecretValue:
    """Resolved secret value plus provenance safe to expose in diagnostics."""

    name: str
    value: str
    source: str = "unknown"

    def to_dict(self) -> dict[str, str]:
        """Return redacted diagnostic metadata for this secret."""
        return {
            "name": self.name,
            "value": REDACTION,
            "source": self.source,
        }


class SecretManager(Protocol):
    """Minimal secret manager contract used by provider adapters."""

    def get_secret(self, name: str) -> SecretValue | None:
        """Return a configured secret by name."""
        ...


class EnvSecretManager:
    """Resolve secrets from process environment variables."""

    def get_secret(self, name: str) -> SecretValue | None:
        """Return an environment secret when present and non-empty."""
        value = os.environ.get(name)
        if value is None or value == "":
            return None
        return SecretValue(name=name, value=value, source="env")


class MappingSecretManager:
    """Resolve secrets from an in-memory mapping for tests and adapters."""

    def __init__(self, secrets: Mapping[str, str | None], source: str = "mapping"):
        """Initialize with exact secret names."""
        self.secrets = dict(secrets)
        self.source = source

    def get_secret(self, name: str) -> SecretValue | None:
        """Return a mapped secret when present and non-empty."""
        value = self.secrets.get(name)
        if value is None or value == "":
            return None
        return SecretValue(name=name, value=value, source=self.source)


class ChainedSecretManager:
    """Resolve secrets through multiple managers in priority order."""

    def __init__(self, *managers: SecretManager | None):
        """Initialize with zero or more managers."""
        self.managers = [manager for manager in managers if manager is not None]

    def get_secret(self, name: str) -> SecretValue | None:
        """Return the first resolved secret."""
        for manager in self.managers:
            secret = manager.get_secret(name)
            if secret is not None:
                return secret
        return None


def is_secret_key(key: str) -> bool:
    """Return whether a mapping key should be treated as secret-bearing."""
    normalized = key.strip().lower().replace("-", "_")
    return any(marker in normalized for marker in SECRET_KEY_MARKERS)


def create_secret_manager_from_settings(
    settings: Any | None = None,
    *,
    overrides: Mapping[str, str | None] | None = None,
) -> SecretManager:
    """Create HAL's default provider secret manager.

    The current production implementation resolves named provider secrets from
    environment variables while allowing tests and app runtimes to inject an
    explicit first-priority mapping.
    """
    managers: list[SecretManager] = []
    if overrides:
        managers.append(MappingSecretManager(overrides, source="override"))
    inline = _inline_settings_secrets(settings)
    if inline:
        managers.append(MappingSecretManager(inline, source="settings"))
    managers.append(EnvSecretManager())
    return ChainedSecretManager(*managers)


def provider_secret_names(provider: str) -> tuple[str, ...]:
    """Return accepted secret names for a provider alias."""
    return PROVIDER_SECRET_CANDIDATES.get(_normalize_provider(provider), ())


def resolve_provider_secret(
    provider: str,
    *,
    secret_manager: SecretManager | None = None,
    explicit_value: str | None = None,
    extra_names: Sequence[str] | None = None,
    include_provider_names: bool = True,
) -> SecretValue | None:
    """Resolve one provider secret without exposing it in logs."""
    manager = secret_manager or EnvSecretManager()
    names = tuple(extra_names or ())
    if include_provider_names:
        names += provider_secret_names(provider)
    for name in names:
        secret = manager.get_secret(name)
        if secret is not None:
            return secret
    if explicit_value:
        return SecretValue(name=f"{_normalize_provider(provider)}:explicit", value=explicit_value, source="explicit")
    return None


def secret_value(
    provider: str,
    *,
    secret_manager: SecretManager | None = None,
    explicit_value: str | None = None,
    extra_names: Sequence[str] | None = None,
    include_provider_names: bool = True,
) -> str | None:
    """Resolve just the secret string for provider clients."""
    secret = resolve_provider_secret(
        provider,
        secret_manager=secret_manager,
        explicit_value=explicit_value,
        extra_names=extra_names,
        include_provider_names=include_provider_names,
    )
    return secret.value if secret is not None else None


def redact_secret(value: Any) -> Any:
    """Redact non-empty scalar or structured secret values."""
    if value is None or value == "":
        return value
    return REDACTION


def redact_mapping(payload: Any) -> Any:
    """Recursively redact secret-looking keys without mutating the input payload."""
    if isinstance(payload, Mapping):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            key_text = str(key)
            redacted[key_text] = redact_secret(value) if is_secret_key(key_text) else redact_mapping(value)
        return redacted
    if isinstance(payload, (str, bytes)):
        return payload
    if isinstance(payload, Sequence):
        return [redact_mapping(value) for value in payload]
    return payload


def _inline_settings_secrets(settings: Any | None) -> dict[str, str]:
    if settings is None:
        return {}
    secrets: dict[str, str] = {}
    _add_if_present(secrets, "HAL9000_ANTHROPIC_API_KEY", getattr(settings, "anthropic_api_key", None))

    acquisition = getattr(settings, "acquisition", None)
    if acquisition is not None:
        _add_if_present(
            secrets,
            "HAL9000_ACQUISITION__SEMANTIC_SCHOLAR_API_KEY",
            getattr(acquisition, "semantic_scholar_api_key", None),
        )

    app_gateway = getattr(settings, "app_gateway", None)
    if app_gateway is not None:
        _add_if_present(
            secrets,
            "HAL9000_SLACK_SIGNING_SECRET",
            getattr(app_gateway, "slack_signing_secret", None),
        )
        _add_if_present(
            secrets,
            "HAL9000_GOOGLE_SHEETS_TOKEN",
            getattr(app_gateway, "sheets_writeback_token", None),
        )
    return secrets


def _add_if_present(secrets: dict[str, str], name: str, value: Any) -> None:
    if isinstance(value, str) and value:
        secrets[name] = value


def _normalize_provider(provider: str) -> str:
    return provider.strip().lower().replace("-", "_")
