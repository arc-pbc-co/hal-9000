"""Tests for authorized review workflow service."""

from pathlib import Path

import pytest

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.authz import AuthorizationError
from hal9000.research.review import ResearchReviewService


def test_review_service_filters_queue_and_records_authorized_decision(temp_directory: Path):
    """Review service should expose only runs the reviewer can review."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'review_api.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Authorized", slug="authorized")
        other_project = store.create_project(name="Private", slug="private")
        reviewer = store.create_user("reviewer@example.com")
        team = store.create_team("reviewers")
        store.add_team_member(team, reviewer)
        store.grant_project_access(project, "team", team.id, "reviewer")

        run = store.create_run("Review authorized run.", project=project)
        other_run = store.create_run("Review private run.", project=other_project)
        for candidate in (run, other_run):
            store.update_run_status(candidate, "staged", actor="worker")
            store.stage_output(
                title=f"Brief {candidate.id[:8]}",
                output_type="research_brief",
                project=candidate.project,
                run=candidate,
                content="# Brief",
            )
        session.commit()

        service = ResearchReviewService(store)
        queue = service.list_review_queue("reviewer@example.com")

        assert [item.run_id for item in queue] == [run.id]

        detail = service.get_review_detail(run, "reviewer@example.com")
        assert detail.run_id == run.id
        assert detail.outputs[0].content == "# Brief"

        result = service.review_run(
            run,
            decision="promote",
            reviewer_email="reviewer@example.com",
            rationale="Ready.",
        )
        session.commit()

        assert result.run.status == "promoted"
        assert run.outputs[0].status == "promoted"
    finally:
        session.close()


def test_review_service_rejects_unauthorized_reviewer(temp_directory: Path):
    """Review decisions should require reviewer project access."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'review_denied.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Protected", slug="protected")
        store.create_user("viewer@example.com")
        run = store.create_run("Protected run.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        store.stage_output(
            title="Protected Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        session.commit()

        service = ResearchReviewService(store)

        with pytest.raises(AuthorizationError, match="needs reviewer access"):
            service.review_run(
                run,
                decision="promote",
                reviewer_email="viewer@example.com",
            )
    finally:
        session.close()
