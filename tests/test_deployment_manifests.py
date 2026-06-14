"""Tests for deployment manifest structure."""

from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]


def test_compose_manifest_defines_required_services():
    """Compose should describe the first firmwide runtime stack."""
    compose_path = REPO_ROOT / "deploy" / "compose.yaml"
    compose = yaml.safe_load(compose_path.read_text())

    services = compose["services"]
    expected_services = {
        "postgres",
        "object-store",
        "object-store-init",
        "migrate",
        "bootstrap",
        "gateway",
        "app-gateway",
        "worker",
        "docs",
    }

    assert expected_services <= set(services)
    assert services["postgres"]["image"].startswith("pgvector/pgvector")
    assert services["object-store"]["image"].startswith("minio/minio")
    assert services["migrate"]["command"] == ["python", "-m", "alembic", "upgrade", "head"]
    assert "gateway" in services["gateway"]["command"]
    assert services["app-gateway"]["command"][-4:] == [
        "--host",
        "0.0.0.0",
        "--port",
        "9101",
    ]
    app_gateway_env = services["app-gateway"]["environment"]
    assert "HAL9000_APP_GATEWAY__SLACK_REQUIRED" in app_gateway_env
    assert "HAL9000_APP_GATEWAY__SHEETS_WRITEBACK_ENABLED" in app_gateway_env
    assert "HAL9000_RETENTION__ENABLED" in compose["x-hal-env"]
    assert "HF_TOKEN" in compose["x-hal-env"]
    assert "worker-service" in services["worker"]["command"]
    assert "--poll-seconds" in services["worker"]["command"]
    assert services["docs"]["ports"] == ["${HAL9000_DOCS_PORT:-8000}:8000"]
    assert "postgres-data" in compose["volumes"]
    assert "object-store-data" in compose["volumes"]


def test_dockerfile_installs_runtime_extras():
    """The runtime image should include production, storage, and docs extras."""
    dockerfile = (REPO_ROOT / "Dockerfile").read_text()

    assert "python:3.12-slim" in dockerfile
    assert ".[postgres,s3,docs]" in dockerfile
    assert "COPY migrations ./migrations" in dockerfile
    assert 'CMD ["hal", "--help"]' in dockerfile
