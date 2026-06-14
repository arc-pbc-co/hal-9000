"""Tests for shared security helpers."""

from hal9000.security import (
    REDACTION,
    ChainedSecretManager,
    EnvSecretManager,
    MappingSecretManager,
    provider_secret_names,
    redact_mapping,
    redact_secret,
    resolve_provider_secret,
    secret_value,
)


def test_redact_secret_preserves_empty_values():
    """Only configured secret values should become redaction markers."""
    assert redact_secret(None) is None
    assert redact_secret("") == ""
    assert redact_secret("secret") == REDACTION


def test_redact_mapping_recurses_without_mutating_input():
    """Secret-looking keys should be redacted recursively."""
    payload = {
        "token": "abc",
        "nested": {
            "api_key": "key",
            "visible": "ok",
            "items": [{"client-secret": "hidden"}, {"name": "public"}],
        },
    }

    redacted = redact_mapping(payload)

    assert redacted["token"] == REDACTION
    assert redacted["nested"]["api_key"] == REDACTION
    assert redacted["nested"]["visible"] == "ok"
    assert redacted["nested"]["items"][0]["client-secret"] == REDACTION
    assert payload["token"] == "abc"


def test_secret_manager_resolves_provider_candidates(monkeypatch):
    """Provider adapters should resolve secrets without hard-coding env reads."""
    monkeypatch.delenv("HF_TOKEN", raising=False)
    manager = MappingSecretManager({"HF_TOKEN": "hf-managed"})

    secret = resolve_provider_secret("huggingface", secret_manager=manager)

    assert secret is not None
    assert secret.value == "hf-managed"
    assert secret.to_dict()["value"] == REDACTION
    assert "HF_TOKEN" in provider_secret_names("huggingface")
    assert "GEMINI_API_KEY" in provider_secret_names("gemini")


def test_chained_secret_manager_prefers_first_source(monkeypatch):
    """Override managers should win over later environment-backed managers."""
    monkeypatch.setenv("OPENAI_API_KEY", "env-openai")
    manager = ChainedSecretManager(
        MappingSecretManager({"OPENAI_API_KEY": "override-openai"}, source="override"),
        EnvSecretManager(),
    )

    assert secret_value("openai", secret_manager=manager) == "override-openai"
