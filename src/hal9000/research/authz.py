"""Authorization helpers for firm-wide research workflows."""

from __future__ import annotations

from dataclasses import dataclass

from hal9000.db.models import ResearchProject, ResearchRun, UserAccount
from hal9000.db.store import ResearchStore


class AuthorizationError(PermissionError):
    """Raised when a user cannot perform a requested research action."""


@dataclass(frozen=True)
class AuthorizedActor:
    """Resolved user account for an authorized request."""

    user: UserAccount
    required_role: str


class ResearchAuthorizer:
    """Authorize user access to research projects and runs."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store

    def resolve_user(self, email: str) -> UserAccount:
        """Resolve an active user by email."""
        user = self.store.get_user_by_email(email)
        if user is None:
            raise AuthorizationError(f"Unknown research user: {email}")
        if user.status != "active":
            raise AuthorizationError(f"Research user is not active: {email}")
        return user

    def require_project_role(
        self,
        project: ResearchProject | None,
        actor_email: str,
        required_role: str,
    ) -> AuthorizedActor:
        """Require a project role for an actor."""
        user = self.resolve_user(actor_email)
        if project is None:
            if user.global_role == "admin":
                return AuthorizedActor(user=user, required_role=required_role)
            raise AuthorizationError("Project-scoped authorization requires a project")
        if not self.store.can_access_project(project, user, required_role):
            raise AuthorizationError(
                f"{user.email} needs {required_role} access to project {project.slug}"
            )
        return AuthorizedActor(user=user, required_role=required_role)

    def require_run_role(
        self,
        run: ResearchRun,
        actor_email: str,
        required_role: str,
    ) -> AuthorizedActor:
        """Require a project role for a run."""
        return self.require_project_role(run.project, actor_email, required_role)
