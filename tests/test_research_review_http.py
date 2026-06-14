"""Tests for the lightweight HTTP review UI adapter."""

from __future__ import annotations

from pathlib import Path
from threading import Thread
from types import SimpleNamespace

import httpx

from hal9000.db.models import ResearchRun, get_session, init_db
from hal9000.db.store import ResearchStore
from hal9000.research.review_http import create_review_http_server


def test_review_http_adapter_serves_authorized_review_workflow(temp_directory: Path):
    """HTTP adapter should expose queue, detail, comments, and decisions."""
    db_url = f"sqlite:///{temp_directory / 'review_http.db'}"
    run_id, output_id = _seed_review_run(db_url)
    server, thread = _start_review_server(db_url)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"

    try:
        with httpx.Client(base_url=base_url) as client:
            health = client.get("/health")
            assert health.status_code == 200
            assert health.json() == {"status": "ok"}

            queue = client.get(
                "/api/review-queue",
                params={"reviewer": "reviewer@example.com", "project_slug": "http-review"},
            )
            assert queue.status_code == 200
            assert [item["run_id"] for item in queue.json()] == [run_id]

            detail = client.get(
                "/api/review-detail",
                params={"run_id": run_id, "reviewer": "reviewer@example.com"},
            )
            assert detail.status_code == 200
            assert detail.json()["outputs"][0]["id"] == output_id

            comment = client.post(
                "/api/review-comment",
                json={
                    "target_type": "output",
                    "target_id": output_id,
                    "author": "reviewer@example.com",
                    "annotation_type": "change_request",
                    "body": "Add citation coverage.",
                },
            )
            assert comment.status_code == 201
            annotation_id = comment.json()["id"]

            comments = client.get(
                "/api/review-comments",
                params={
                    "target_type": "output",
                    "target_id": output_id,
                    "viewer": "reviewer@example.com",
                },
            )
            assert comments.status_code == 200
            assert comments.json()[0]["body"] == "Add citation coverage."

            resolved = client.post(
                "/api/review-comment/resolve",
                json={"annotation_id": annotation_id, "resolver": "reviewer@example.com"},
            )
            assert resolved.status_code == 200
            assert resolved.json()["status"] == "resolved"

            review = client.post(
                "/api/review-run",
                json={
                    "run_id": run_id,
                    "decision": "promote",
                    "reviewer": "reviewer@example.com",
                    "rationale": "Ready.",
                },
            )
            assert review.status_code == 201
            assert review.json()["status"] == "promoted"

            audit = client.get(
                "/api/audit-events",
                params={"run_id": run_id, "reviewer": "reviewer@example.com"},
            )
            assert audit.status_code == 200
            assert audit.json()[0]["action"] == "run.promoted"

            dashboard = client.get(
                "/api/audit-dashboard",
                params={
                    "run_id": run_id,
                    "reviewer": "reviewer@example.com",
                    "action": "run.promoted",
                },
            )
            assert dashboard.status_code == 200
            assert dashboard.json()["summary"]["by_action"] == {"run.promoted": 1}

        session = get_session(db_url)
        try:
            assert session.get(ResearchRun, run_id).status == "promoted"
        finally:
            session.close()
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_review_http_adapter_maps_unauthorized_requests_to_forbidden(temp_directory: Path):
    """Permission failures should return HTTP 403 for UI clients."""
    db_url = f"sqlite:///{temp_directory / 'review_http_denied.db'}"
    run_id, _ = _seed_review_run(db_url)
    _, session_factory = init_db(db_url)
    session = session_factory()
    try:
        ResearchStore(session).create_user("outsider@example.com")
        session.commit()
    finally:
        session.close()

    server, thread = _start_review_server(db_url)
    base_url = f"http://{server.server_address[0]}:{server.server_address[1]}"
    try:
        with httpx.Client(base_url=base_url) as client:
            response = client.get(
                "/api/review-detail",
                params={"run_id": run_id, "reviewer": "outsider@example.com"},
            )
            assert response.status_code == 403
            assert "needs reviewer access" in response.json()["error"]
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def _seed_review_run(db_url: str) -> tuple[str, str]:
    _, session_factory = init_db(db_url)
    session = session_factory()
    try:
        store = ResearchStore(session)
        project = store.create_project("HTTP Review", "http-review")
        reviewer = store.create_user("reviewer@example.com")
        team = store.create_team("reviewers")
        store.add_team_member(team, reviewer)
        store.grant_project_access(project, "team", team.id, "reviewer")
        run = store.create_run("Review the HTTP adapter output.", project=project)
        store.update_run_status(run, "staged", actor="worker")
        output = store.stage_output(
            title="HTTP Review Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief\n\nEvidence-backed content.",
        )
        session.commit()
        return run.id, output.id
    finally:
        session.close()


def _start_review_server(db_url: str):
    settings = SimpleNamespace(database=SimpleNamespace(url=db_url))
    server = create_review_http_server(settings, "127.0.0.1", 0)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, thread
