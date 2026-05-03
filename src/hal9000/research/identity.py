"""OIDC claim-to-user mapping for HAL research access."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hal9000.config import AuthConfig
from hal9000.db.models import UserAccount
from hal9000.db.store import ResearchStore


class IdentityMappingError(ValueError):
    """Raised when verified identity claims cannot be mapped to a HAL user."""


@dataclass(frozen=True)
class OIDCUserMappingResult:
    """Result of mapping verified OIDC claims into HAL identity state."""

    user: UserAccount
    created: bool
    synced_team_slugs: list[str]


class OIDCIdentityMapper:
    """Map already-verified OIDC claims to HAL users and team memberships."""

    def __init__(self, store: ResearchStore, config: AuthConfig | None = None):
        """Initialize with the shared research store and auth config."""
        self.store = store
        self.config = config or AuthConfig()

    def map_claims(
        self,
        claims: dict[str, Any],
        auto_create: bool = True,
        sync_teams: bool = True,
    ) -> OIDCUserMappingResult:
        """Create or update a HAL user from verified OIDC claims."""
        email = self._claim_string(claims, self.config.email_claim)
        subject = self._claim_string(claims, self.config.subject_claim)
        display_name = self._claim_string(claims, self.config.name_claim, required=False)
        groups = self._claim_list(claims, self.config.groups_claim)

        user = self.store.get_user_by_email(email)
        created = False
        if user is None:
            if not auto_create:
                raise IdentityMappingError(f"HAL user does not exist for OIDC email: {email}")
            user = self.store.create_user(
                email=email,
                display_name=display_name,
                external_subject=subject,
                global_role=self._global_role(groups),
            )
            created = True
        else:
            if user.external_subject and user.external_subject != subject:
                raise IdentityMappingError("OIDC subject does not match existing HAL user")
            user.external_subject = subject
            if display_name:
                user.display_name = display_name
            user.global_role = self._global_role(groups)
            self.store.session.flush()

        synced_team_slugs = self._sync_team_memberships(user, groups) if sync_teams else []
        return OIDCUserMappingResult(
            user=user,
            created=created,
            synced_team_slugs=synced_team_slugs,
        )

    def _sync_team_memberships(self, user: UserAccount, groups: list[str]) -> list[str]:
        synced = []
        prefix = self.config.team_group_prefix
        for group in groups:
            if prefix and not group.startswith(prefix):
                continue
            team_slug = group.removeprefix(prefix).strip().lower()
            if not team_slug:
                continue
            team = self.store.get_team_by_slug(team_slug)
            if team is None:
                team = self.store.create_team(slug=team_slug)
            if not any(membership.user_id == user.id for membership in team.memberships):
                self.store.add_team_member(team, user)
            synced.append(team.slug)
        return sorted(set(synced))

    def _global_role(self, groups: list[str]) -> str:
        return "admin" if set(groups).intersection(self.config.admin_groups) else "member"

    def _claim_string(
        self,
        claims: dict[str, Any],
        claim_name: str,
        required: bool = True,
    ) -> str | None:
        value = claims.get(claim_name)
        if value is None:
            if required:
                raise IdentityMappingError(f"OIDC claim is required: {claim_name}")
            return None
        if not isinstance(value, str) or not value.strip():
            raise IdentityMappingError(f"OIDC claim must be a non-empty string: {claim_name}")
        return value.strip()

    def _claim_list(self, claims: dict[str, Any], claim_name: str) -> list[str]:
        value = claims.get(claim_name, [])
        if isinstance(value, str):
            return [value]
        if not isinstance(value, list):
            raise IdentityMappingError(f"OIDC claim must be a string or list: {claim_name}")
        groups = []
        for item in value:
            if isinstance(item, str) and item.strip():
                groups.append(item.strip())
        return groups
