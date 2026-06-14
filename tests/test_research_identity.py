"""Tests for OIDC identity mapping."""

from pathlib import Path

import pytest

from hal9000.config import AuthConfig
from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.identity import IdentityMappingError, OIDCIdentityMapper


def test_oidc_identity_mapper_creates_user_and_syncs_teams(temp_directory: Path):
    """Verified OIDC claims should map into HAL users and team memberships."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'identity_map.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        mapper = OIDCIdentityMapper(
            store,
            AuthConfig(
                admin_groups=["hal:admins"],
                team_group_prefix="hal:",
            ),
        )

        result = mapper.map_claims(
            {
                "sub": "oidc-subject-1",
                "email": "Researcher@Example.com",
                "name": "Researcher",
                "groups": ["hal:materials", "hal:admins", "external-group"],
            }
        )
        session.commit()

        assert result.created is True
        assert result.user.email == "researcher@example.com"
        assert result.user.external_subject == "oidc-subject-1"
        assert result.user.global_role == "admin"
        assert result.synced_team_slugs == ["admins", "materials"]
        assert store.get_team_by_slug("materials").memberships[0].user_id == result.user.id
    finally:
        session.close()


def test_oidc_identity_mapper_rejects_subject_mismatch(temp_directory: Path):
    """An existing user with a different subject should not be silently remapped."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'identity_mismatch.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        store.create_user("researcher@example.com", external_subject="subject-a")
        mapper = OIDCIdentityMapper(store)

        with pytest.raises(IdentityMappingError, match="subject does not match"):
            mapper.map_claims(
                {
                    "sub": "subject-b",
                    "email": "researcher@example.com",
                    "name": "Researcher",
                }
            )
    finally:
        session.close()
