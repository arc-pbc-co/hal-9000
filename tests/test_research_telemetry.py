"""Tests for reviewer-facing research run telemetry summaries."""

from pathlib import Path

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research.telemetry import RunTelemetrySummarizer


def test_run_telemetry_summary_condenses_events_tools_outputs(temp_directory: Path):
    """The summarizer should turn run internals into a reviewer-facing summary."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'telemetry.db'}")
    session = session_factory()

    try:
        store = ResearchStore(session)
        project = store.create_project(name="Telemetry", slug="telemetry")
        run = store.create_run(
            objective="Summarize creep resistance evidence.",
            project=project,
            initiated_by="research@example.com",
            budget={
                "max_papers": 3,
                "max_downloads": 2,
                "max_llm_calls": 1,
                "max_runtime_minutes": 15,
            },
        )
        store.update_run_status(run, "running", actor="worker")
        store.append_run_event(
            run,
            "acquisition.paper.found",
            actor="worker",
            payload={
                "status": "found",
                "stage": "search",
                "title": "Creep Paper",
                "doi": "10.1234/creep",
                "source": "semantic_scholar",
                "relevance_score": 0.91,
            },
        )
        store.append_run_event(
            run,
            "acquisition.paper.downloaded",
            actor="worker",
            payload={
                "status": "downloaded",
                "stage": "download",
                "title": "Creep Paper",
                "doi": "10.1234/creep",
                "source": "semantic_scholar",
            },
        )
        store.append_run_event(
            run,
            "acquisition.paper.processed",
            actor="worker",
            payload={
                "status": "processed",
                "stage": "process",
                "title": "Creep Paper",
                "doi": "10.1234/creep",
                "source": "semantic_scholar",
                "document_id": "doc-1",
            },
        )
        store.append_run_event(
            run,
            "acquisition.paper.skipped",
            actor="worker",
            payload={
                "status": "skipped",
                "stage": "dedupe",
                "title": "Duplicate Paper",
                "reason": "duplicate",
            },
        )
        store.append_run_event(
            run,
            "acquisition.paper.failed",
            message="Paper download failed.",
            actor="worker",
            payload={
                "status": "failed",
                "stage": "download",
                "title": "Broken Paper",
                "reason": "download error",
            },
        )

        acquisition_call = store.start_tool_call(
            run,
            "acquisition.acquire",
            actor="worker",
            input={"topic": "creep", "max_papers": 2},
        )
        store.finish_tool_call(
            acquisition_call,
            output={
                "papers_found": 2,
                "papers_downloaded": 1,
                "papers_processed": 1,
                "duplicates_skipped": 1,
                "download_failures": 1,
            },
        )
        llm_call = store.start_tool_call(run, "llm.call", actor="worker")
        store.finish_tool_call(llm_call, output={"model": "fake"})
        failed_call = store.start_tool_call(run, "artifact.write", actor="worker")
        store.finish_tool_call(
            failed_call,
            status="failed",
            error_message="object store unavailable",
        )
        store.stage_output(
            title="Creep Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="# Brief",
            created_by="worker",
        )
        store.update_run_status(run, "staged", actor="worker")
        session.commit()

        summary = RunTelemetrySummarizer(store).summarize(run)

        assert summary.project_slug == "telemetry"
        assert summary.budget.max_downloads == 2
        assert summary.budget.papers_found == 2
        assert summary.budget.llm_calls_used == 1
        assert summary.acquisition.papers_downloaded == 1
        assert summary.acquisition.papers_processed == 1
        assert summary.acquisition.papers_skipped == 1
        assert summary.acquisition.papers_failed == 1
        assert summary.acquisition.paper_events[0].identifier == "10.1234/creep"
        assert summary.tool_call_count == 3
        assert summary.outputs[0].title == "Creep Brief"
        assert any("artifact.write" in warning for warning in summary.warnings)
        assert "Run is staged and ready for human review." in summary.reviewer_notes
        assert summary.to_dict()["acquisition"]["papers_failed"] == 1
    finally:
        session.close()
