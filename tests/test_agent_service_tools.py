"""Tests for HAL service tools exposed to the agent runtime."""

import json
from pathlib import Path

import pytest

from hal9000.agent import (
    AgentToolContext,
    AgentToolRouter,
    build_hal_service_tools,
    create_hal_service_tool_router,
)
from hal9000.db.models import Document, ExtractedClaim, ResearchOutput, init_db
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research import load_program
from hal9000.research.acquisition import WorkerAcquisitionResult
from hal9000.storage import LocalObjectStore
from hal9000.vector import FakeEmbeddingProvider


class FakeAcquisitionRunner:
    """Fake acquisition runner for service-tool tests."""

    def __init__(self):
        self.calls = []

    def acquire(self, topic: str, max_papers: int):
        self.calls.append({"topic": topic, "max_papers": max_papers})
        return WorkerAcquisitionResult(
            papers_found=max_papers,
            papers_downloaded=max_papers,
            papers_processed=max_papers,
            document_ids=["doc-1", "doc-2"][:max_papers],
        )


class FakeHFResearchClient:
    """Fake HF discovery client for service-tool tests."""

    def __init__(self):
        self.calls = []

    async def search_papers(self, *, query: str, limit: int):
        self.calls.append(("search_papers", query, limit))
        return [
            {
                "id": "2501.00001",
                "title": "Transformer Agents for Superalloy Literature Review",
                "authors": [{"name": "Grace Hopper"}],
                "year": 2025,
                "summary": "Agentic literature review improves superalloy evidence triage.",
                "abstract": "Agentic literature review improves superalloy evidence triage.",
            },
            {
                "id": "2501.00002",
                "title": "Dataset Grounding for Creep Resistance Models",
                "authors": ["Ada Lovelace"],
                "year": 2025,
                "summary": "Dataset grounding reduces unsupported creep model claims.",
                "abstract": "Dataset grounding reduces unsupported creep model claims.",
            },
        ][:limit]

    async def paper_details(self, *, arxiv_id: str):
        self.calls.append(("paper_details", arxiv_id))
        return {
            "id": arxiv_id,
            "title": "Detailed HAL Research Paper",
            "summary": "Detailed paper metadata can seed HAL evidence.",
            "abstract": "Detailed paper metadata can seed HAL evidence.",
        }

    async def paper_resources(self, *, arxiv_id: str, limit: int):
        self.calls.append(("paper_resources", arxiv_id, limit))
        return {
            "datasets": [{"id": "hal/superalloy-creep"}],
            "models": [{"id": "hal/creep-ranker"}],
        }

    async def inspect_dataset(self, *, dataset: str, config: str | None, split: str | None, sample_rows: int):
        self.calls.append(("inspect_dataset", dataset, config, split, sample_rows))
        return {
            "dataset": dataset,
            "config": config or "default",
            "split": split or "train",
            "first_rows": [{"composition": "Ni-base", "rupture_hours": 1000}],
        }

    async def search_docs(self, *, endpoint: str, query: str | None, max_results: int):
        self.calls.append(("search_docs", endpoint, query, max_results))
        return {
            "endpoint": endpoint,
            "query": query,
            "matches": [{"line": 12, "text": "SFTConfig accepts dataset_text_field."}],
        }

    async def fetch_doc(self, *, url: str):
        self.calls.append(("fetch_doc", url))
        return {"url": url, "content": "# Trainer\nUse current parameters."}

    async def github_find_examples(self, *, repo: str, org: str, keyword: str | None, max_results: int):
        self.calls.append(("github_find_examples", repo, org, keyword, max_results))
        return {
            "repo": f"{org}/{repo}",
            "examples": [{"path": "examples/scripts/sft.py"}],
        }

    async def github_read_file(
        self,
        *,
        repo: str,
        path: str,
        ref: str,
        line_start: int | None,
        line_end: int | None,
    ):
        self.calls.append(("github_read_file", repo, path, ref, line_start, line_end))
        return {
            "repo": repo,
            "path": path,
            "content": "from trl import SFTTrainer\n",
        }

    async def hf_repo_action(self, **kwargs):
        self.calls.append(("hf_repo_action", kwargs))
        if kwargs["operation"] == "upload_file":
            return {
                "operation": "upload_file",
                "repo_id": kwargs["repo_id"],
                "repo_type": kwargs["repo_type"],
                "path": kwargs["path"],
                "url": f"https://huggingface.co/{kwargs['repo_id']}/blob/main/{kwargs['path']}",
            }
        return {
            "operation": kwargs["operation"],
            "repo_id": kwargs["repo_id"],
            "repo_type": kwargs["repo_type"],
            "url": f"https://huggingface.co/{kwargs['repo_id']}",
        }

    async def hf_job_action(self, **kwargs):
        self.calls.append(("hf_job_action", kwargs))
        if kwargs["operation"] == "submit":
            return {
                "operation": "job_info",
                "job_id": "job-123",
                "status": "RUNNING",
                "job_url": "https://huggingface.co/jobs/test/job-123",
            }
        if kwargs["operation"] == "schedule":
            return {
                "operation": "scheduled_job_info",
                "scheduled_job_id": "scheduled-123",
                "status": "scheduled",
                "schedule": kwargs["schedule"],
                "scheduled_job_url": "https://huggingface.co/jobs/test/scheduled-123",
            }
        if kwargs["operation"].startswith("scheduled_"):
            return {
                "operation": kwargs["operation"],
                "scheduled_job_id": kwargs.get("scheduled_job_id") or "scheduled-123",
                "status": "observed",
                "schedule": kwargs.get("schedule") or "@daily",
                "scheduled_job_url": "https://huggingface.co/jobs/test/scheduled-123",
            }
        return {
            "operation": kwargs["operation"],
            "job_id": kwargs["job_id"],
            "status": "OBSERVED",
            "job_url": f"https://huggingface.co/jobs/test/{kwargs['job_id']}",
        }

    async def hf_sandbox_smoke(self, **kwargs):
        self.calls.append(("hf_sandbox_smoke", kwargs))
        return {
            "status": "passed",
            "executed": True,
            "mode": "python" if kwargs.get("script") else "command",
            "artifact_uri": "https://huggingface.co/spaces/hal/smoke/logs",
            "checks": [{"name": "tiny_run", "status": "passed"}],
        }

    async def hf_sandbox_action(self, **kwargs):
        self.calls.append(("hf_sandbox_action", kwargs))
        sandbox_id = kwargs.get("sandbox_id") or "sandbox-123"
        result = {
            "operation": kwargs["operation"],
            "sandbox_id": sandbox_id,
            "status": "ready",
            "artifact_uri": f"https://huggingface.co/spaces/hal/{sandbox_id}",
        }
        if kwargs["operation"] == "run_command":
            result["exit_code"] = 0
            result["stdout"] = "sandbox command ok"
        if kwargs["operation"] == "read_file":
            result["content"] = "sandbox file content"
        return result

    async def hf_harvest_artifacts(self, **kwargs):
        self.calls.append(("hf_harvest_artifacts", kwargs))
        artifacts = [{"uri": uri, "source": "explicit"} for uri in kwargs.get("artifact_uris", [])]
        for path in kwargs.get("paths", []):
            artifacts.append(
                {
                    "uri": f"https://huggingface.co/{kwargs['repo_id']}/resolve/main/{path}",
                    "path": path,
                    "source": "hub_repo",
                }
            )
        return {
            "job_id": kwargs.get("job_id"),
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "artifact_uri": artifacts[0]["uri"] if artifacts else None,
        }

    async def hf_download_artifact(self, **kwargs):
        self.calls.append(("hf_download_artifact", kwargs))
        artifact = kwargs["artifact"]
        name = artifact.get("path") or artifact.get("uri", "artifact").rstrip("/").rsplit("/", 1)[-1]
        content = f"downloaded artifact: {artifact.get('uri')}".encode()
        return {
            "uri": artifact.get("uri"),
            "filename": name,
            "content": content,
            "content_type": "text/plain",
            "size_bytes": len(content),
            "sha256": "fake-sha",
        }


def _research_context(temp_directory: Path, allowed_tools: list[str] | None = None):
    _, session_factory = init_db(f"sqlite:///{temp_directory / 'agent_tools.db'}")
    session = session_factory()
    store = ResearchStore(session)
    project = store.create_project(name="Agent Tools", slug="agent-tools")
    program = store.save_program(
        load_program(Path(__file__).resolve().parents[1] / "templates/research/programs/literature-review.md"),
        project=project,
    )
    run = store.create_run(
        objective="Study creep resistance in single crystal superalloys.",
        project=project,
        program=program,
        budget={"max_papers": 3},
        tool_policy={"allowed_tools": allowed_tools or _all_policy_tools()},
    )
    context = AgentToolContext(
        store=store,
        run=run,
        actor="agent-tools-test@example.com",
        metadata={
            "embedding_provider": FakeEmbeddingProvider(dimension=8),
            "object_store": LocalObjectStore(temp_directory / "objects"),
        },
    )
    return session, store, project, run, context


def _all_policy_tools() -> list[str]:
    return [
        "acquire",
        "process",
        "semantic_search",
        "output",
        "export",
        "adam",
        "review",
        "graph",
        "hf_research",
        "hf_compute",
    ]


def _document(session, *, title: str = "Creep Paper") -> Document:
    document = Document(
        source_path=f"/papers/{title}.pdf",
        source_type="local",
        file_hash=(title.lower().replace(" ", "-") + "-hash").ljust(64, "0")[:64],
        title=title,
        summary="Single crystal structure improves creep resistance at high temperature.",
        findings=json.dumps(
            [
                "Single crystal structure improves creep resistance at high temperature.",
                "Gamma prime precipitates influence creep deformation mechanisms.",
            ]
        ),
        full_text=(
            "Single crystal structure improves creep resistance at high temperature. "
            "Gamma prime precipitates influence creep deformation mechanisms."
        ),
        status="completed",
    )
    session.add(document)
    session.flush()
    return document


def _router() -> AgentToolRouter:
    return create_hal_service_tool_router()


def test_build_hal_service_tools_declares_expected_policy_and_approval_flags():
    """HAL service tools should expose stable names, policies, and approval gates."""
    tools = {tool.name: tool for tool in build_hal_service_tools()}

    assert set(tools) == {
        "hal_acquire",
        "hal_process_pdf",
        "hal_search_memory",
        "hal_stage_outputs",
        "hal_export_run",
        "hal_build_adam_context",
        "hal_review_output",
        "hal_graph_edge",
        "hal_hf_papers",
        "hal_hf_dataset",
        "hal_hf_docs",
        "hal_github_examples",
        "hal_hf_repo",
        "hal_hf_job",
        "hal_hf_sandbox_smoke",
        "hal_hf_sandbox",
        "hal_hf_harvest_artifacts",
    }
    assert tools["hal_search_memory"].requires_approval is False
    assert tools["hal_search_memory"].policy_name == "semantic_search"
    assert tools["hal_hf_papers"].requires_approval is False
    assert tools["hal_hf_papers"].policy_name == "hf_research"
    assert tools["hal_hf_repo"].requires_approval is True
    assert tools["hal_hf_repo"].policy_name == "hf_compute"
    assert tools["hal_hf_job"].requires_approval is True
    assert tools["hal_hf_job"].policy_name == "hf_compute"
    assert tools["hal_hf_sandbox_smoke"].requires_approval is True
    assert tools["hal_hf_sandbox_smoke"].policy_name == "hf_compute"
    assert tools["hal_hf_sandbox"].requires_approval is True
    assert tools["hal_hf_sandbox"].policy_name == "hf_compute"
    assert tools["hal_hf_harvest_artifacts"].requires_approval is True
    assert tools["hal_hf_harvest_artifacts"].policy_name == "hf_compute"
    assert all(
        tool.requires_approval
        for name, tool in tools.items()
        if name
        not in {
            "hal_search_memory",
            "hal_hf_papers",
            "hal_hf_dataset",
            "hal_hf_docs",
            "hal_github_examples",
        }
    )


@pytest.mark.asyncio
async def test_hal_acquire_uses_attached_runner_and_budget(temp_directory: Path):
    """hal_acquire should route through the acquisition runner seam."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["acquire"],
    )
    runner = FakeAcquisitionRunner()
    context.metadata["acquisition_runner"] = runner

    try:
        result = await _router().call_tool(
            "hal_acquire",
            {"topic": "single crystal creep", "max_papers": 2},
            context=context,
        )
        session.commit()

        assert result.success is True
        assert runner.calls == [{"topic": "single crystal creep", "max_papers": 2}]
        assert result.payload["papers_processed"] == 2
        assert "agent.acquire.completed" in [event.event_type for event in run.events]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_process_pdf_prepares_existing_document(temp_directory: Path):
    """hal_process_pdf should chunk, embed, and extract first-pass claims."""
    session, store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["process"],
    )
    document = _document(session)

    try:
        result = await _router().call_tool(
            "hal_process_pdf",
            {"document_id": document.id, "chunk_size": 80, "chunk_overlap": 10},
            context=context,
        )
        session.commit()

        assert result.success is True
        assert result.payload["document_id"] == document.id
        assert len(result.payload["chunk_ids"]) >= 1
        assert len(result.payload["embedding_ids"]) == len(result.payload["chunk_ids"])
        assert len(result.payload["claim_ids"]) == 2
        assert store.list_run_events(run)[-1].event_type == "agent.tool.completed"
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_search_memory_returns_claim_output_and_chunk_results(temp_directory: Path):
    """hal_search_memory should search HAL memory without approval."""
    session, store, project, run, context = _research_context(
        temp_directory,
        allowed_tools=["semantic_search"],
    )
    document = _document(session)

    try:
        # Prepare memory records directly because this run policy allows only search.
        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=0,
            content=document.full_text or "",
            token_count=12,
        )
        from hal9000.vector import VectorRepository

        VectorRepository(session).embed_and_store_chunk(
            chunk,
            context.metadata["embedding_provider"],
        )
        store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text="Single crystal structure improves creep resistance.",
                evidence_text="Single crystal structure improves creep resistance at high temperature.",
            ),
        )
        store.stage_output(
            title="Creep Resistance Brief",
            output_type="research_brief",
            project=project,
            run=run,
            content="Single crystal turbine materials show better creep resistance.",
        )

        result = await _router().call_tool(
            "hal_search_memory",
            {"query": "creep resistance", "targets": ["chunks", "claims", "outputs"], "limit": 5},
            context=context,
        )

        target_types = {
            item.get("target_type") or "chunk"
            for item in result.payload["results"]
        }

        assert result.success is True
        assert result.payload["result_count"] >= 3
        assert {"chunk", "claim", "output"} <= target_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_stage_adam_review_export_and_graph_tools(temp_directory: Path):
    """The mutating HAL service tools should compose through the store ledger."""
    session, store, _project, run, context = _research_context(temp_directory)
    document = _document(session)

    try:
        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=0,
            content=document.full_text or "",
            token_count=12,
        )
        store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text="Single crystal structure improves creep resistance.",
                evidence_text="Single crystal structure improves creep resistance at high temperature.",
                claim_type="finding",
            ),
        )

        stage_result = await _router().call_tool(
            "hal_stage_outputs",
            {"include_run_report": True},
            context=context,
        )
        adam_result = await _router().call_tool(
            "hal_build_adam_context",
            {"topic_focus": "creep resistance"},
            context=context,
        )
        review_result = await _router().call_tool(
            "hal_review_output",
            {
                "decision": "promote",
                "rationale": "Source-backed and ready for export.",
                "reviewer": "reviewer@example.com",
            },
            context=context,
        )
        export_result = await _router().call_tool(
            "hal_export_run",
            {"targets": ["json"], "statuses": ["promoted"], "artifact_prefix": "agent-test-exports"},
            context=context,
        )
        graph_result = await _router().call_tool(
            "hal_graph_edge",
            {
                "source_type": "run",
                "source_id": run.id,
                "relationship_type": "studies_material",
                "target_type": "material",
                "target_id": "single-crystal-superalloy",
                "confidence": 0.8,
                "evidence": {"source": "agent test"},
            },
            context=context,
        )
        session.commit()

        assert stage_result.success is True
        assert len(stage_result.payload["output_ids"]) == 4
        assert adam_result.success is True
        adam_output = session.get(ResearchOutput, adam_result.payload["output_id"])
        assert json.loads(adam_output.content)["output_type"] == "adam_context"
        assert review_result.success is True
        assert run.status == "promoted"
        assert export_result.payload["exports"][0]["output_count"] == len(run.outputs)
        assert graph_result.payload["relationship_type"] == "studies_material"
        assert "outputs.exported" in [event.event_type for event in run.events]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_papers_imports_documents_chunks_and_claims(temp_directory: Path):
    """HF paper discovery should enter HAL as canonical research records."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_research"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        result = await _router().call_tool(
            "hal_hf_papers",
            {"operation": "search", "query": "superalloy agents", "limit": 2},
            context=context,
        )
        session.commit()

        documents = session.query(Document).filter_by(source_type="huggingface_paper").all()
        claims = session.query(ExtractedClaim).filter_by(run_id=run.id).all()

        assert result.success is True
        assert result.payload["document_count"] == 2
        assert [call[0] for call in client.calls] == ["search_papers"]
        assert {document.source_identifier for document in documents} == {
            "arxiv:2501.00001",
            "arxiv:2501.00002",
        }
        assert len(claims) == 2
        assert "agent.hf.papers.imported" in [event.event_type for event in run.events]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_resource_docs_dataset_and_github_tools_stage_outputs(temp_directory: Path):
    """HF docs, dataset, resources, and GitHub examples should stage HAL outputs."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_research"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        resources = await _router().call_tool(
            "hal_hf_papers",
            {"operation": "find_resources", "arxiv_id": "2501.00001"},
            context=context,
        )
        dataset = await _router().call_tool(
            "hal_hf_dataset",
            {"dataset": "hal/superalloy-creep", "sample_rows": 1},
            context=context,
        )
        docs = await _router().call_tool(
            "hal_hf_docs",
            {"operation": "search", "endpoint": "trl", "query": "SFTConfig"},
            context=context,
        )
        examples = await _router().call_tool(
            "hal_github_examples",
            {"operation": "find_examples", "repo": "trl", "keyword": "sft"},
            context=context,
        )
        session.commit()

        output_types = {
            output.output_type
            for output in session.query(ResearchOutput).filter_by(run_id=run.id).all()
        }
        event_types = [event.event_type for event in run.events]

        assert resources.success is True
        assert dataset.success is True
        assert docs.success is True
        assert examples.success is True
        assert {
            "hf_paper_resources",
            "hf_dataset_profile",
            "hf_docs_result",
            "github_example_result",
        } <= output_types
        assert "agent.hf.paper_resources.staged" in event_types
        assert "agent.hf.dataset.profiled" in event_types
        assert "agent.hf.docs.captured" in event_types
        assert "agent.github.examples.captured" in event_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_compute_tools_stage_outputs_after_policy_allows(temp_directory: Path):
    """Approved HF compute handlers should preserve side-effect results as HAL outputs."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        repo_result = await _router().call_tool(
            "hal_hf_repo",
            {
                "operation": "upload_file",
                "repo_id": "hal/superalloy-agent-artifacts",
                "repo_type": "model",
                "path": "reports/summary.md",
                "content": "# HAL Summary\nSource-backed.",
                "commit_message": "Upload HAL summary",
            },
            context=context,
        )
        job_result = await _router().call_tool(
            "hal_hf_job",
            {
                "operation": "submit",
                "command": ["python", "-c", "print('HAL job')"],
                "image": "python:3.12",
                "hardware_flavor": "cpu-basic",
                "timeout": "30m",
                "env": {"PUBLIC_FLAG": "1"},
            },
            context=context,
        )
        session.commit()

        outputs = session.query(ResearchOutput).filter_by(run_id=run.id).all()
        output_types = {output.output_type for output in outputs}
        repo_output = next(output for output in outputs if output.output_type == "hf_repo_action")
        job_output = next(output for output in outputs if output.output_type == "hf_job_submission")
        repo_content = json.loads(repo_output.content)
        job_content = json.loads(job_output.content)
        event_types = [event.event_type for event in run.events]

        assert repo_result.success is True
        assert job_result.success is True
        assert {"hf_repo_action", "hf_job_submission"} <= output_types
        assert repo_output.artifact_uri.endswith("/reports/summary.md")
        assert job_output.artifact_uri == "https://huggingface.co/jobs/test/job-123"
        assert "content" not in repo_content["request"]
        assert "content_sha256" in repo_content["request"]
        assert job_content["request"]["env_keys"] == ["PUBLIC_FLAG"]
        assert any(call[0] == "hf_repo_action" for call in client.calls)
        assert any(call[0] == "hf_job_action" for call in client.calls)
        assert "agent.hf.repo_action.completed" in event_types
        assert "agent.hf.job.submitted" in event_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_compute_policy_blocks_side_effects(temp_directory: Path):
    """HF compute tools should fail before side effects when policy does not allow them."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_research"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        result = await _router().call_tool(
            "hal_hf_job",
            {"operation": "cancel", "job_id": "job-123"},
            context=context,
        )
        session.commit()

        assert result.success is False
        assert "not allowed" in result.output
        assert [call for call in client.calls if call[0] == "hf_job_action"] == []
        assert "agent.tool.failed" in [event.event_type for event in run.events]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_smoke_gate_and_artifact_harvest_stage_outputs(temp_directory: Path):
    """GPU/model jobs should be gated by smoke records and harvest artifact manifests."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        smoke = await _router().call_tool(
            "hal_hf_sandbox_smoke",
            {
                "script": "import torch\nprint('tiny smoke')",
                "dependencies": ["torch"],
                "hardware_flavor": "a10g-small",
                "expected_signal": "tiny smoke",
            },
            context=context,
        )
        job = await _router().call_tool(
            "hal_hf_job",
            {
                "operation": "submit",
                "command": ["python", "-c", "import torch; print('train')"],
                "image": "pytorch/pytorch:2.6.0-cuda12.4-cudnn9-devel",
                "hardware_flavor": "a10g-small",
                "timeout": "2h",
                "smoke_test_output_id": smoke.payload["output_id"],
            },
            context=context,
        )
        harvest = await _router().call_tool(
            "hal_hf_harvest_artifacts",
            {
                "job_id": job.payload["job_id"],
                "artifact_uris": ["https://huggingface.co/hal/model/blob/main/README.md"],
                "repo_id": "hal/model",
                "paths": ["metrics.json"],
                "description": "Smoke-tested job outputs.",
            },
            context=context,
        )
        session.commit()

        outputs = session.query(ResearchOutput).filter_by(run_id=run.id).all()
        output_types = {output.output_type for output in outputs}
        job_output = next(output for output in outputs if output.output_type == "hf_job_submission")
        job_content = json.loads(job_output.content)
        event_types = [event.event_type for event in run.events]

        assert smoke.success is True
        assert job.success is True
        assert harvest.success is True
        assert {
            "hf_sandbox_smoke",
            "hf_job_submission",
            "hf_artifact_harvest",
        } <= output_types
        assert job_content["smoke_gate"]["smoke_test_output_id"] == smoke.payload["output_id"]
        assert harvest.payload["artifact_count"] == 2
        assert any(call[0] == "hf_sandbox_smoke" for call in client.calls)
        assert any(call[0] == "hf_harvest_artifacts" for call in client.calls)
        assert "agent.hf.sandbox_smoke.completed" in event_types
        assert "agent.hf.artifacts.harvested" in event_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_artifact_harvest_downloads_to_object_store(temp_directory: Path):
    """Artifact harvest should optionally materialize HF artifacts in HAL object storage."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client
    object_store = context.metadata["object_store"]

    try:
        harvest = await _router().call_tool(
            "hal_hf_harvest_artifacts",
            {
                "job_id": "job-123",
                "artifact_uris": ["https://huggingface.co/hal/model/resolve/main/README.md"],
                "repo_id": "hal/model",
                "paths": ["metrics.json"],
                "description": "Downloadable job/repo outputs.",
                "store_artifacts": True,
                "artifact_prefix": "hf-downloads",
                "max_bytes": 1024,
            },
            context=context,
        )
        session.commit()

        output = session.query(ResearchOutput).filter_by(run_id=run.id, output_type="hf_artifact_harvest").one()
        content = json.loads(output.content)
        stored = content["result"]["stored_artifacts"]
        errors = content["result"]["storage_errors"]
        event_types = [event.event_type for event in run.events]

        assert harvest.success is True
        assert harvest.payload["artifact_count"] == 2
        assert harvest.payload["stored_artifact_count"] == 2
        assert harvest.payload["storage_error_count"] == 0
        assert len(stored) == 2
        assert errors == []
        assert output.artifact_uri == stored[0]["object_uri"]
        assert content["request"]["store_artifacts"] is True
        assert content["request"]["artifact_prefix"] == "hf-downloads"
        assert object_store.get_bytes(stored[0]["object_key"]).startswith(b"downloaded artifact:")
        assert object_store.get_bytes(stored[1]["object_key"]).startswith(b"downloaded artifact:")
        assert all(item["sha256"] for item in stored)
        assert [call[0] for call in client.calls].count("hf_download_artifact") == 2
        assert "agent.hf.artifacts.harvested" in event_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_scheduled_job_and_trackio_seed_stage_outputs(temp_directory: Path):
    """Scheduled HF Jobs should scrub secrets and seed Trackio dashboard records."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        scheduled = await _router().call_tool(
            "hal_hf_job",
            {
                "operation": "schedule",
                "command": ["python", "-c", "print('nightly refresh')"],
                "image": "python:3.12",
                "hardware_flavor": "cpu-basic",
                "timeout": "45m",
                "schedule": "@daily",
                "namespace": "hal",
                "labels": {"purpose": "nightly-refresh"},
                "secrets": {"HF_TOKEN": "$HF_TOKEN"},
                "trackio_space_id": "hal/trackio",
                "trackio_project": "creep-nightly",
            },
            context=context,
        )
        observed = await _router().call_tool(
            "hal_hf_job",
            {
                "operation": "scheduled_status",
                "scheduled_job_id": scheduled.payload["scheduled_job_id"],
                "namespace": "hal",
            },
            context=context,
        )
        session.commit()

        outputs = session.query(ResearchOutput).filter_by(run_id=run.id).all()
        scheduled_output = next(output for output in outputs if output.output_type == "hf_scheduled_job")
        trackio_output = next(output for output in outputs if output.output_type == "hf_trackio_dashboard")
        observation_output = next(
            output for output in outputs if output.output_type == "hf_scheduled_job_observation"
        )
        scheduled_content = json.loads(scheduled_output.content)
        trackio_content = json.loads(trackio_output.content)
        event_types = [event.event_type for event in run.events]
        schedule_call = next(call for call in client.calls if call[1]["operation"] == "schedule")

        assert scheduled.success is True
        assert observed.success is True
        assert scheduled.payload["scheduled_job_id"] == "scheduled-123"
        assert scheduled.payload["trackio"]["output_id"] == trackio_output.id
        assert scheduled_content["request"]["schedule"] == "@daily"
        assert scheduled_content["request"]["secret_keys"] == ["HF_TOKEN"]
        assert "secrets" not in scheduled_content["request"]
        assert scheduled_content["request"]["labels"] == {"purpose": "nightly-refresh"}
        assert trackio_content["dashboard_url"] == "https://huggingface.co/spaces/hal/trackio"
        assert trackio_content["env"] == {
            "TRACKIO_SPACE_ID": "hal/trackio",
            "TRACKIO_PROJECT": "creep-nightly",
        }
        assert observation_output.artifact_uri.endswith("/scheduled-123")
        assert schedule_call[1]["secrets"] == {"HF_TOKEN": "$HF_TOKEN"}
        assert "agent.hf.job.scheduled" in event_types
        assert "agent.hf.scheduled_job.observed" in event_types
        assert "agent.hf.trackio.dashboard_seeded" in event_types
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_gpu_job_requires_smoke_or_skip_reason(temp_directory: Path):
    """GPU/model-loading submissions should fail before client calls without smoke evidence."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        result = await _router().call_tool(
            "hal_hf_job",
            {
                "operation": "submit",
                "command": ["python", "-c", "import torch; print('train')"],
                "hardware_flavor": "a10g-small",
            },
            context=context,
        )
        session.commit()

        assert result.success is False
        assert "smoke_test_output_id or skip_smoke_reason" in result.output
        assert [call for call in client.calls if call[0] == "hf_job_action"] == []
        assert "agent.tool.failed" in [event.event_type for event in run.events]
    finally:
        session.close()


@pytest.mark.asyncio
async def test_hal_hf_sandbox_lifecycle_stages_approved_actions(temp_directory: Path):
    """Remote sandbox lifecycle calls should be staged and scrub write content."""
    session, _store, _project, run, context = _research_context(
        temp_directory,
        allowed_tools=["hf_compute"],
    )
    client = FakeHFResearchClient()
    context.metadata["hf_research_client"] = client

    try:
        create = await _router().call_tool(
            "hal_hf_sandbox",
            {
                "operation": "create",
                "image": "python:3.12",
                "hardware_flavor": "cpu-basic",
                "env": {"PUBLIC_FLAG": "1"},
            },
            context=context,
        )
        sandbox_id = create.payload["sandbox_id"]
        run_command = await _router().call_tool(
            "hal_hf_sandbox",
            {
                "operation": "run_command",
                "sandbox_id": sandbox_id,
                "command": ["python", "-c", "print('ok')"],
            },
            context=context,
        )
        write = await _router().call_tool(
            "hal_hf_sandbox",
            {
                "operation": "write_file",
                "sandbox_id": sandbox_id,
                "path": "/app/train.py",
                "content": "print('secret-ish training code')",
            },
            context=context,
        )
        delete = await _router().call_tool(
            "hal_hf_sandbox",
            {"operation": "delete", "sandbox_id": sandbox_id},
            context=context,
        )
        session.commit()

        outputs = session.query(ResearchOutput).filter_by(run_id=run.id).all()
        sandbox_outputs = [output for output in outputs if output.output_type == "hf_sandbox_action"]
        write_output = next(
            output
            for output in sandbox_outputs
            if json.loads(output.content)["operation"] == "write_file"
        )
        write_content = json.loads(write_output.content)
        event_types = [event.event_type for event in run.events]

        assert create.success is True
        assert run_command.success is True
        assert write.success is True
        assert delete.success is True
        assert len(sandbox_outputs) == 4
        assert write_content["request"]["content_sha256"]
        assert "content" not in write_content["request"]
        assert any(call[0] == "hf_sandbox_action" for call in client.calls)
        assert event_types.count("agent.hf.sandbox_action.completed") == 4
    finally:
        session.close()
