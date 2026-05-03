"""CLI tests for research store workflows."""

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import (
    ResearchProgramRecord,
    ResearchProject,
    ResearchRun,
    ResearchRunEvent,
    get_session,
)
from hal9000.research import render_program_template


def _write_config(temp_directory: Path) -> tuple[Path, Path]:
    """Write a test config and return config path plus database path."""
    db_path = temp_directory / "hal_research_cli.db"
    config_path = temp_directory / "config.yaml"
    config_path.write_text(
        f"""hal9000:
  database:
    url: sqlite:///{db_path}
"""
    )
    return config_path, db_path


def test_research_cli_project_program_and_run_flow(temp_directory: Path):
    """Research CLI commands should drive the shared store workflow."""
    config_path, db_path = _write_config(temp_directory)
    program_path = temp_directory / "program.md"
    program_path.write_text(
        render_program_template(
            name="CLI Program",
            objective="Queue a CLI-backed run.",
            owner="research@example.com",
        )
    )

    runner = CliRunner()

    create_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "create-project",
            "cli-project",
            "--name",
            "CLI Project",
        ],
        obj={},
    )
    assert create_result.exit_code == 0, create_result.output
    assert "Research project created" in create_result.output

    save_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "save-program",
            str(program_path),
            "--project-slug",
            "cli-project",
        ],
        obj={},
    )
    assert save_result.exit_code == 0, save_result.output
    assert "Research program saved" in save_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        program = session.query(ResearchProgramRecord).filter_by(name="CLI Program").one()
        program_id = program.id
    finally:
        session.close()

    queue_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "queue-run",
            "--program-id",
            program_id,
            "--initiated-by",
            "tester@example.com",
        ],
        obj={},
    )
    assert queue_result.exit_code == 0, queue_result.output
    assert "Research run queued" in queue_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        run = session.query(ResearchRun).one()
        run_id = run.id
        assert run.status == "queued"
        assert run.program_id == program_id
        assert run.project.slug == "cli-project"
        assert run.initiated_by == "tester@example.com"
        assert session.query(ResearchRunEvent).count() == 1
    finally:
        session.close()

    list_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "runs",
            "--project-slug",
            "cli-project",
        ],
        obj={},
    )
    assert list_result.exit_code == 0, list_result.output
    assert "CLI Program" in list_result.output
    assert "queued" in list_result.output

    observe_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "observe",
        ],
        obj={},
    )
    assert observe_result.exit_code == 0, observe_result.output
    assert "Research Operations" in observe_result.output
    assert "Queue Health" in observe_result.output

    observe_json_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "observe",
            "--json",
        ],
        obj={},
    )
    assert observe_json_result.exit_code == 0, observe_json_result.output
    assert '"run_status_counts"' in observe_json_result.output
    assert '"queue"' in observe_json_result.output

    log_event_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "log-run-event",
            run_id,
            "--event-type",
            "tool.search",
            "--message",
            "Search started.",
            "--actor",
            "worker",
            "--payload-json",
            '{"query": "superalloy creep"}',
        ],
        obj={},
    )
    assert log_event_result.exit_code == 0, log_event_result.output
    assert "tool.search #2" in log_event_result.output

    update_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "update-run",
            run_id,
            "--status",
            "running",
            "--message",
            "Worker started.",
            "--actor",
            "worker",
        ],
        obj={},
    )
    assert update_result.exit_code == 0, update_result.output
    assert "status: running" in update_result.output

    run_log_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "run-log",
            run_id,
        ],
        obj={},
    )
    assert run_log_result.exit_code == 0, run_log_result.output
    assert "run.queued" in run_log_result.output
    assert "tool.search" in run_log_result.output
    assert "run.running" in run_log_result.output

    execute_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "execute-run",
            run_id,
            "--actor",
            "cli-worker",
        ],
        obj={},
    )
    assert execute_result.exit_code == 0, execute_result.output
    assert "Research run executed" in execute_result.output
    assert "status: staged" in execute_result.output
    assert "corpus_documents: 0" in execute_result.output
    assert "retrieved_context: 0" in execute_result.output

    summary_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "run-summary",
            run_id,
        ],
        obj={},
    )
    assert summary_result.exit_code == 0, summary_result.output
    assert "Run Summary" in summary_result.output
    assert "Budget Usage" in summary_result.output
    assert "Reviewer Notes" in summary_result.output
    assert "research_brief" in summary_result.output

    json_summary_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "run-summary",
            run_id,
            "--json",
        ],
        obj={},
    )
    assert json_summary_result.exit_code == 0, json_summary_result.output
    assert '"run_id"' in json_summary_result.output
    assert '"status": "staged"' in json_summary_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        run = session.get(ResearchRun, run_id)
        assert run.status == "staged"
        assert [event.sequence for event in run.events] == list(range(1, 11))
        assert "retrieval.context.attached" in [event.event_type for event in run.events]
        assert "corpus.prepared" in [event.event_type for event in run.events]
    finally:
        session.close()

    review_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "review-run",
            run_id,
            "--decision",
            "promote",
            "--reviewer",
            "reviewer@example.com",
            "--rationale",
            "Ready for sharing.",
        ],
        obj={},
    )
    assert review_result.exit_code == 0, review_result.output
    assert "Research run reviewed" in review_result.output
    assert "status: promoted" in review_result.output
    assert "outputs_reviewed: 4" in review_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        run = session.get(ResearchRun, run_id)
        assert run.status == "promoted"
        assert [output.status for output in run.outputs] == ["promoted"] * 4
        assert run.events[-1].event_type == "run.promoted"
    finally:
        session.close()


def test_research_cli_bootstrap_is_idempotent(temp_directory: Path):
    """Bootstrap should create a firm project and reuse starter programs."""
    config_path, db_path = _write_config(temp_directory)
    program_dir = Path(__file__).resolve().parents[1] / "templates" / "research" / "programs"
    runner = CliRunner()

    first_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "bootstrap",
            "--project-slug",
            "arc-research",
            "--project-name",
            "Arc Research",
            "--owner",
            "research@example.com",
            "--program-dir",
            str(program_dir),
        ],
        obj={},
    )
    assert first_result.exit_code == 0, first_result.output
    assert "Research bootstrap complete" in first_result.output
    assert "programs_created: 2" in first_result.output
    assert "programs_existing: 0" in first_result.output

    second_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "bootstrap",
            "--project-slug",
            "arc-research",
            "--program-dir",
            str(program_dir),
        ],
        obj={},
    )
    assert second_result.exit_code == 0, second_result.output
    assert "programs_created: 0" in second_result.output
    assert "programs_existing: 2" in second_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        assert session.query(ResearchProject).filter_by(slug="arc-research").count() == 1
        assert session.query(ResearchProgramRecord).count() == 2
    finally:
        session.close()


def test_research_cli_cancel_and_work_queue(temp_directory: Path):
    """CLI should cancel queued runs and execute queued runs through the worker command."""
    config_path, db_path = _write_config(temp_directory)
    program_path = temp_directory / "program.md"
    program_path.write_text(
        render_program_template(
            name="Queue Program",
            objective="Run through the queue worker.",
            owner="research@example.com",
        )
    )
    runner = CliRunner()

    create_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "create-project",
            "queue-project",
        ],
        obj={},
    )
    assert create_result.exit_code == 0, create_result.output

    save_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "save-program",
            str(program_path),
            "--project-slug",
            "queue-project",
        ],
        obj={},
    )
    assert save_result.exit_code == 0, save_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        program = session.query(ResearchProgramRecord).filter_by(name="Queue Program").one()
        program_id = program.id
    finally:
        session.close()

    cancel_queue_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "queue-run",
            "--program-id",
            program_id,
        ],
        obj={},
    )
    assert cancel_queue_result.exit_code == 0, cancel_queue_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        cancelled_run_id = session.query(ResearchRun).one().id
    finally:
        session.close()

    cancel_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "cancel-run",
            cancelled_run_id,
            "--actor",
            "tester@example.com",
        ],
        obj={},
    )
    assert cancel_result.exit_code == 0, cancel_result.output
    assert "status: cancelled" in cancel_result.output

    queue_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "queue-run",
            "--program-id",
            program_id,
        ],
        obj={},
    )
    assert queue_result.exit_code == 0, queue_result.output

    worker_result = runner.invoke(
        cli,
        [
            "--config",
            str(config_path),
            "research",
            "work-queue",
            "--limit",
            "1",
        ],
        obj={},
    )
    assert worker_result.exit_code == 0, worker_result.output
    assert "Queued worker processed 1 run" in worker_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        statuses = sorted(run.status for run in session.query(ResearchRun).all())
        assert statuses == ["cancelled", "staged"]
    finally:
        session.close()
