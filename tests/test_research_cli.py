"""CLI tests for research store workflows."""

from pathlib import Path

from click.testing import CliRunner

from hal9000.cli import cli
from hal9000.db.models import ResearchProgramRecord, ResearchRun, ResearchRunEvent, get_session
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
    assert "retrieved_context: 0" in execute_result.output

    session = get_session(f"sqlite:///{db_path}")
    try:
        run = session.get(ResearchRun, run_id)
        assert run.status == "staged"
        assert [event.sequence for event in run.events] == [1, 2, 3, 4, 5, 6, 7, 8]
        assert "retrieval.context.attached" in [event.event_type for event in run.events]
    finally:
        session.close()
