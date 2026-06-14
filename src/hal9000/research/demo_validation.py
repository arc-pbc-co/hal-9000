"""Staging demo validation for HAL release readiness."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from hal9000.db.store import ResearchStore
from hal9000.research.collaboration import CollaborationService
from hal9000.research.compliance import ResearchComplianceService
from hal9000.research.demo import DemoSeedService
from hal9000.research.sheets import SheetsSyncService
from hal9000.vector.embeddings import FakeEmbeddingProvider
from hal9000.vector.store import VectorRepository


@dataclass(frozen=True)
class StagingDemoValidationResult:
    """Result of validating a staging demo dataset."""

    project_slug: str
    run_id: str
    checks: dict[str, bool]
    issues: list[str]

    @property
    def passed(self) -> bool:
        """Return whether all validation checks passed."""
        return all(self.checks.values()) and not self.issues

    def to_dict(self) -> dict[str, Any]:
        """Serialize the validation result for CLI output."""
        return {
            "passed": self.passed,
            "project_slug": self.project_slug,
            "run_id": self.run_id,
            "checks": dict(self.checks),
            "issues": list(self.issues),
        }


class StagingDemoValidator:
    """Seed and validate the full-team demo path in a staging-like store."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store

    def validate(
        self,
        *,
        project_slug: str = "hal-staging-demo",
        reviewer_email: str = "reviewer@example.com",
        contributor_email: str = "researcher@example.com",
        owner_email: str = "owner@example.com",
    ) -> StagingDemoValidationResult:
        """Seed and validate a demo walkthrough dataset."""
        seed = DemoSeedService(self.store).seed(
            project_slug=project_slug,
            reviewer_email=reviewer_email,
            contributor_email=contributor_email,
            owner_email=owner_email,
        )
        run = self.store.get_run(seed.run_id)
        project = self.store.get_project_by_slug(seed.project_slug)
        if run is None or project is None:
            raise ValueError("demo seed did not create a project and run")

        vector = VectorRepository(self.store.session)
        provider = FakeEmbeddingProvider()
        checks = {
            "run_staged": run.status == "staged",
            "outputs_staged": len(run.outputs) >= 3,
            "claims_extracted": len(run.claims) >= 2,
            "review_queue_visible": bool(
                SheetsSyncService(self.store).values_for_project_view(
                    project,
                    target="review_queue",
                    reviewer_email=reviewer_email,
                )[1:]
            ),
            "memory_search": bool(
                vector.search_memory(
                    "single crystal superalloy creep",
                    provider,
                    targets={"claims", "outputs"},
                    project_id=project.id,
                    limit=5,
                )
            ),
            "notifications_ready": bool(
                CollaborationService(self.store).list_notifications(project=project)
            ),
        }
        compliance = ResearchComplianceService(self.store.session).check()
        checks["compliance_high_clear"] = compliance.high_count == 0

        issues = [name for name, passed in checks.items() if not passed]
        if compliance.high_count:
            issues.extend(issue.code for issue in compliance.issues if issue.severity == "high")

        return StagingDemoValidationResult(
            project_slug=seed.project_slug,
            run_id=seed.run_id,
            checks=checks,
            issues=issues,
        )
