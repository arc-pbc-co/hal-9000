"""Tests for review comments and annotations."""

from pathlib import Path

import pytest

from hal9000.db.models import Document, init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research.annotations import ReviewAnnotationService, annotation_payload
from hal9000.research.authz import AuthorizationError


def test_review_annotation_service_comments_on_outputs_and_claims(temp_directory: Path):
    """Authorized users should comment on outputs and claims and resolve comments."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'annotations.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project("Annotations", "annotations")
        reviewer = store.create_user("reviewer@example.com")
        team = store.create_team("reviewers")
        store.add_team_member(team, reviewer)
        store.grant_project_access(project, "team", team.id, "reviewer")
        run = store.create_run("Review annotations.", project=project)
        output = store.stage_output(
            title="Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        document = Document(
            source_path="/papers/source.pdf",
            source_type="local",
            file_hash="d" * 64,
            title="Source",
        )
        session.add(document)
        session.flush()
        claim = store.add_claim_with_evidence(
            document,
            ClaimEvidence(claim_text="Source-backed finding."),
            run=run,
        )
        session.commit()

        service = ReviewAnnotationService(store)
        output_comment = service.add_annotation(
            "output",
            output.id,
            body="Add one more citation.",
            author_email="reviewer@example.com",
            annotation_type="change_request",
        )
        claim_comment = service.add_annotation(
            "claim",
            claim.id,
            body="Check this quote.",
            author_email="reviewer@example.com",
        )
        session.commit()

        output_comments = service.list_annotations(
            "output",
            output.id,
            viewer_email="reviewer@example.com",
        )
        payload = annotation_payload(output_comments[0]).to_dict()

        assert payload["body"] == "Add one more citation."
        assert output_comment.project_id == project.id
        assert claim_comment.run_id == run.id

        resolved = service.resolve_annotation(
            output_comment.id,
            resolver_email="reviewer@example.com",
        )
        session.commit()

        assert resolved.status == "resolved"
        assert (
            service.list_annotations("output", output.id, viewer_email="reviewer@example.com")
            == []
        )
        assert len(
            service.list_annotations(
                "output",
                output.id,
                viewer_email="reviewer@example.com",
                include_resolved=True,
            )
        ) == 1
    finally:
        session.close()


def test_review_annotation_service_enforces_project_access(temp_directory: Path):
    """Unauthorized users should not be able to comment on review targets."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'annotation_denied.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project("Protected", "protected")
        store.create_user("outsider@example.com")
        run = store.create_run("Protected.", project=project)
        output = store.stage_output(
            title="Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
        )
        session.commit()

        with pytest.raises(AuthorizationError, match="needs contributor access"):
            ReviewAnnotationService(store).add_annotation(
                "output",
                output.id,
                body="I should not be able to add this.",
                author_email="outsider@example.com",
            )
    finally:
        session.close()
