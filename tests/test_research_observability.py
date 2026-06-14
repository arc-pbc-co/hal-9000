"""Tests for research operations observability summaries."""

from pathlib import Path

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.observability import ResearchObservabilityService


def test_observability_summary_reports_queue_tools_and_failures(temp_directory: Path):
    """The observability service should condense run, queue, tool, and failure state."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'observability.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Ops", slug="ops")
        queued = store.create_run(objective="Queued run.", project=project)
        running = store.create_run(objective="Running run.", project=project)
        failed = store.create_run(objective="Failed run.", project=project)
        staged = store.create_run(objective="Staged run.", project=project)

        store.update_run_status(running, "running", actor="worker")
        store.update_run_status(failed, "running", actor="worker")
        failed.error_message = "pipeline failure"
        store.update_run_status(failed, "failed", message="pipeline failure", actor="worker")
        store.update_run_status(staged, "running", actor="worker")
        store.update_run_status(staged, "staged", actor="worker")
        store.append_run_event(
            staged,
            "worker.completed",
            message="Worker completed run execution.",
            actor="worker",
        )
        store.append_run_event(
            failed,
            "worker.phase.timeout",
            message="Worker phase timed out.",
            actor="worker",
        )

        completed_call = store.start_tool_call(
            staged,
            tool_name="llm.call",
            actor="worker",
        )
        store.finish_tool_call(completed_call, cost_usd=0.25)
        failed_call = store.start_tool_call(
            failed,
            tool_name="acquisition.acquire",
            actor="worker",
        )
        store.finish_tool_call(
            failed_call,
            status="failed",
            error_message="download failed",
            cost_usd=0.5,
        )
        session.commit()

        summary = ResearchObservabilityService(store).summarize(limit=5)

        assert summary.run_status_counts["queued"] == 1
        assert summary.run_status_counts["running"] == 1
        assert summary.run_status_counts["failed"] == 1
        assert summary.queue.queued == 1
        assert summary.queue.running == 1
        assert summary.queue.next_queued_runs[0].id == queued.id
        assert summary.tool_calls.total == 2
        assert summary.tool_calls.by_status == {"completed": 1, "failed": 1}
        assert summary.tool_calls.by_tool["acquisition.acquire"] == 1
        assert summary.tool_calls.total_cost_usd == 0.75
        assert summary.tool_calls.recent_failures[0].error_message == "download failed"
        assert summary.recent_failures[0].run.id == failed.id
        assert "worker.phase.timeout" in [
            event.event_type for event in summary.recent_worker_outcomes
        ]
        assert summary.to_dict()["queue"]["queued"] == 1
    finally:
        session.close()
