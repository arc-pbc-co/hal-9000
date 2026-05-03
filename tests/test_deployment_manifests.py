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
        "worker",
        "docs",
    }

    assert expected_services <= set(services)
    assert services["postgres"]["image"].startswith("pgvector/pgvector")
    assert services["object-store"]["image"].startswith("minio/minio")
    assert services["migrate"]["command"] == ["python", "-m", "alembic", "upgrade", "head"]
    assert "gateway" in services["gateway"]["command"]
    assert "work-queue" in services["worker"]["command"]
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
