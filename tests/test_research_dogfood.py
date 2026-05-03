"""Dogfood tests for checked-in research programs."""

from pathlib import Path

from hal9000.db.models import init_db
from hal9000.db.store import ResearchStore
from hal9000.research import ResearchOutputGenerator, load_program


def test_checked_in_programs_run_through_shared_store_dogfood(temp_directory: Path):
    """Both starter programs should save, queue, run, and stage outputs."""
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'dogfood.db'}")
    session = session_factory()

    try:
        repo_root = Path(__file__).resolve().parents[1]
        program_paths = [
            repo_root / "templates/research/programs/literature-review.md",
            repo_root / "templates/research/programs/adam-experiment-context.md",
        ]

        store = ResearchStore(session)
        generator = ResearchOutputGenerator(store)
        project = store.create_project(
            name="HAL Dogfood",
            slug="hal-dogfood",
            owner="hal@example.com",
        )

        runs = []
        for program_path in program_paths:
            program = load_program(program_path)
            record = store.save_program(program, project=project)
            run = store.create_run(
                objective=record.objective,
                project=project,
                program=record,
                initiated_by="dogfood-test",
            )
            store.append_run_event(
                run,
                event_type="run.queued",
                message="Dogfood run queued.",
                actor="dogfood-test",
            )
            store.update_run_status(
                run,
                status="running",
                message="Dogfood worker started.",
                actor="dogfood-test",
            )
            staged = generator.stage_contract_outputs(
                run,
                created_by="dogfood-test",
            )
            generator.stage_run_report(run, created_by="dogfood-test")
            runs.append((run, staged))

        session.commit()

        assert len(project.programs) == 2
        assert len(project.runs) == 2
        assert all(run.status == "staged" for run, _ in runs)
        assert [len(staged.outputs) for _, staged in runs] == [3, 3]
        assert len(project.outputs) == 8  # 3 contract outputs + 1 run report per run

        for run, staged in runs:
            event_types = [event.event_type for event in store.list_run_events(run)]
            assert event_types[:4] == [
                "run.queued",
                "run.running",
                "outputs.staged",
                "run.staged",
            ]
            assert "output.run_report.staged" in event_types
            assert all(output.run_id == run.id for output in staged.outputs)
    finally:
        session.close()
