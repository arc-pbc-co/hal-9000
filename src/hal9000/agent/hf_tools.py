"""Hugging Face research tools exposed through HAL's agent boundary."""

from __future__ import annotations

import asyncio
import hashlib
import inspect
import json
import re
from typing import Any
from urllib.parse import unquote, urlsplit

import httpx

from hal9000.agent.tools import AgentToolContext, AgentToolResult, AgentToolRouter, AgentToolSpec
from hal9000.db.models import Document, DocumentChunk, ResearchOutput, ResearchRun, utc_now
from hal9000.db.store import ClaimEvidence
from hal9000.security import SecretManager, secret_value
from hal9000.storage import create_object_store_from_settings

HF_API = "https://huggingface.co/api"
HF_BASE = "https://huggingface.co"
HF_DOCS_BASE = "https://huggingface.co/docs"
DATASETS_SERVER = "https://datasets-server.huggingface.co"
GITHUB_API = "https://api.github.com"
GITHUB_RAW = "https://raw.githubusercontent.com"

MAX_LIMIT = 50
MAX_OUTPUT_CHARS = 60000
MAX_DOC_FETCH_CHARS = 120000
MAX_ARTIFACT_BYTES = 50 * 1024 * 1024
HF_JOB_OPERATIONS = [
    "submit",
    "schedule",
    "status",
    "logs",
    "cancel",
    "scheduled_list",
    "scheduled_status",
    "scheduled_suspend",
    "scheduled_resume",
    "scheduled_delete",
]
HF_JOB_LAUNCH_OPERATIONS = {"submit", "schedule"}
HF_SCHEDULED_JOB_OPERATIONS = {
    "scheduled_list",
    "scheduled_status",
    "scheduled_suspend",
    "scheduled_resume",
    "scheduled_delete",
}


def build_hal_hf_research_tools() -> list[AgentToolSpec]:
    """Return read-only HF research tools that persist findings into HAL."""
    return [
        AgentToolSpec(
            name="hal_hf_papers",
            description=(
                "Discover Hugging Face papers and linked resources, then store findings as "
                "HAL documents, chunks, claims, or staged outputs."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["search", "paper_details", "find_resources"],
                    },
                    "query": {"type": "string"},
                    "arxiv_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                },
                "required": ["operation"],
            },
            handler=hal_hf_papers,
            policy_name="hf_research",
            requires_approval=False,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_dataset",
            description=(
                "Inspect a Hugging Face dataset and stage the schema, splits, sample rows, "
                "and parquet metadata as a HAL run output."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "dataset": {"type": "string"},
                    "config": {"type": "string"},
                    "split": {"type": "string"},
                    "sample_rows": {"type": "integer", "minimum": 1, "maximum": 10},
                    "run_id": {"type": "string"},
                },
                "required": ["dataset"],
            },
            handler=hal_hf_dataset,
            policy_name="hf_research",
            requires_approval=False,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_docs",
            description=(
                "Search or fetch Hugging Face documentation and stage the captured material "
                "as a HAL run output."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["search", "fetch"]},
                    "endpoint": {"type": "string"},
                    "query": {"type": "string"},
                    "url": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                    "run_id": {"type": "string"},
                },
                "required": ["operation"],
            },
            handler=hal_hf_docs,
            policy_name="hf_research",
            requires_approval=False,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_github_examples",
            description=(
                "Find or read implementation examples from GitHub and stage them as HAL "
                "research outputs for later review."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": ["find_examples", "read_file"]},
                    "repo": {"type": "string"},
                    "org": {"type": "string"},
                    "keyword": {"type": "string"},
                    "path": {"type": "string"},
                    "ref": {"type": "string"},
                    "max_results": {"type": "integer", "minimum": 1, "maximum": MAX_LIMIT},
                    "line_start": {"type": "integer", "minimum": 1},
                    "line_end": {"type": "integer", "minimum": 1},
                    "run_id": {"type": "string"},
                },
                "required": ["operation", "repo"],
            },
            handler=hal_github_examples,
            policy_name="hf_research",
            requires_approval=False,
            source="huggingface",
        ),
    ]


def build_hal_hf_compute_tools() -> list[AgentToolSpec]:
    """Return approval-gated HF compute and repo tools."""
    return [
        AgentToolSpec(
            name="hal_hf_repo",
            description=(
                "Create, upload, or delete files in Hugging Face Hub repos after "
                "approval, then stage the Hub artifact link in HAL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["create_repo", "upload_file", "delete_files"],
                    },
                    "repo_id": {"type": "string"},
                    "repo_type": {"type": "string", "enum": ["model", "dataset", "space"]},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "patterns": {"type": "array", "items": {"type": "string"}},
                    "revision": {"type": "string"},
                    "create_pr": {"type": "boolean"},
                    "commit_message": {"type": "string"},
                    "private": {"type": "boolean"},
                    "space_sdk": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["operation", "repo_id"],
            },
            handler=hal_hf_repo,
            policy_name="hf_compute",
            requires_approval=True,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_job",
            description=(
                "Submit, schedule, inspect, read logs for, or cancel a Hugging Face Job "
                "after approval, preserving job IDs and artifact links in the HAL run ledger."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {"type": "string", "enum": HF_JOB_OPERATIONS},
                    "script": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "image": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "hardware_flavor": {"type": "string"},
                    "timeout": {"type": "string"},
                    "env": {"type": "object"},
                    "secrets": {"type": "object"},
                    "labels": {"type": "object"},
                    "namespace": {"type": "string"},
                    "job_id": {"type": "string"},
                    "scheduled_job_id": {"type": "string"},
                    "schedule": {"type": "string"},
                    "include_suspended": {"type": "boolean"},
                    "trackio_space_id": {"type": "string"},
                    "trackio_project": {"type": "string"},
                    "smoke_test_output_id": {"type": "string"},
                    "skip_smoke_reason": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["operation"],
            },
            handler=hal_hf_job,
            policy_name="hf_compute",
            requires_approval=True,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_sandbox_smoke",
            description=(
                "Run or record a bounded sandbox smoke test before HF Jobs submission, "
                "then stage the result as HAL evidence for the compute run."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "script": {"type": "string"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "image": {"type": "string"},
                    "dependencies": {"type": "array", "items": {"type": "string"}},
                    "hardware_flavor": {"type": "string"},
                    "timeout": {"type": "string"},
                    "env": {"type": "object"},
                    "expected_signal": {"type": "string"},
                    "run_id": {"type": "string"},
                },
            },
            handler=hal_hf_sandbox_smoke,
            policy_name="hf_compute",
            requires_approval=True,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_sandbox",
            description=(
                "Manage an approved remote HF sandbox lifecycle: create, inspect, run "
                "commands, read/write files, and delete, with every action staged in HAL."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "operation": {
                        "type": "string",
                        "enum": ["create", "status", "run_command", "read_file", "write_file", "delete"],
                    },
                    "sandbox_id": {"type": "string"},
                    "image": {"type": "string"},
                    "hardware_flavor": {"type": "string"},
                    "timeout": {"type": "string"},
                    "env": {"type": "object"},
                    "command": {"type": "array", "items": {"type": "string"}},
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "run_id": {"type": "string"},
                },
                "required": ["operation"],
            },
            handler=hal_hf_sandbox,
            policy_name="hf_compute",
            requires_approval=True,
            source="huggingface",
        ),
        AgentToolSpec(
            name="hal_hf_harvest_artifacts",
            description=(
                "Harvest HF job/repo artifact links into HAL as a reviewable manifest, "
                "optionally downloading them into HAL object storage."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "job_id": {"type": "string"},
                    "artifact_uris": {"type": "array", "items": {"type": "string"}},
                    "repo_id": {"type": "string"},
                    "repo_type": {"type": "string", "enum": ["model", "dataset", "space"]},
                    "paths": {"type": "array", "items": {"type": "string"}},
                    "description": {"type": "string"},
                    "store_artifacts": {"type": "boolean"},
                    "artifact_prefix": {"type": "string"},
                    "max_bytes": {"type": "integer", "minimum": 1},
                    "run_id": {"type": "string"},
                },
            },
            handler=hal_hf_harvest_artifacts,
            policy_name="hf_compute",
            requires_approval=True,
            source="huggingface",
        ),
    ]


def create_hal_hf_research_tool_router() -> AgentToolRouter:
    """Create an AgentToolRouter populated only with HF research tools."""
    return AgentToolRouter(build_hal_hf_research_tools())


def create_hal_hf_compute_tool_router() -> AgentToolRouter:
    """Create an AgentToolRouter populated only with approval-gated HF compute tools."""
    return AgentToolRouter(build_hal_hf_compute_tools())


async def hal_hf_papers(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Discover HF papers and persist imported findings into HAL."""
    store = _require_store(context)
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    limit = _limit(arguments.get("limit"))
    client = _hf_research_client(context)

    if operation == "search":
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ValueError("hal_hf_papers search requires query")
        papers = await client.search_papers(query=query, limit=limit)
        documents = [
            _upsert_hf_paper_document(store, run, paper, context.actor, query=query)
            for paper in _coerce_items(papers)
        ]
        payload = {
            "operation": operation,
            "query": query,
            "run_id": run.id,
            "document_count": len(documents),
            "documents": [_document_payload(document) for document in documents],
        }
        store.append_run_event(
            run,
            event_type="agent.hf.papers.imported",
            message=f"Imported {len(documents)} Hugging Face paper result(s) for: {query}",
            actor=context.actor,
            payload=payload,
        )
        return AgentToolResult.ok(
            f"Imported {len(documents)} Hugging Face paper result(s) for '{query}'.",
            payload=payload,
        )

    if operation == "paper_details":
        arxiv_id = _required_arxiv_id(arguments)
        paper = await client.paper_details(arxiv_id=arxiv_id)
        document = _upsert_hf_paper_document(store, run, paper, context.actor)
        payload = {
            "operation": operation,
            "arxiv_id": arxiv_id,
            "run_id": run.id,
            "document_count": 1,
            "documents": [_document_payload(document)],
        }
        store.append_run_event(
            run,
            event_type="agent.hf.paper.imported",
            message=f"Imported Hugging Face paper details for arXiv:{arxiv_id}.",
            actor=context.actor,
            payload=payload,
        )
        return AgentToolResult.ok(
            f"Imported Hugging Face paper details for arXiv:{arxiv_id}.",
            payload=payload,
        )

    if operation == "find_resources":
        arxiv_id = _required_arxiv_id(arguments)
        resources = await client.paper_resources(arxiv_id=arxiv_id, limit=limit)
        output = _stage_json_output(
            context,
            run,
            title=f"HF Paper Resources: {arxiv_id}",
            output_type="hf_paper_resources",
            payload={
                "operation": operation,
                "arxiv_id": arxiv_id,
                "resources": resources,
            },
            source={"generator": "hal_hf_papers", "operation": operation, "arxiv_id": arxiv_id},
        )
        payload = {
            "operation": operation,
            "arxiv_id": arxiv_id,
            "run_id": run.id,
            "output_id": output.id,
            "resource_counts": {
                key: len(value) for key, value in resources.items() if isinstance(value, list)
            },
        }
        store.append_run_event(
            run,
            event_type="agent.hf.paper_resources.staged",
            message=f"Staged Hugging Face resources linked to arXiv:{arxiv_id}.",
            actor=context.actor,
            payload=payload,
        )
        return AgentToolResult.ok(
            f"Staged Hugging Face resources linked to arXiv:{arxiv_id}.",
            payload=payload,
        )

    raise ValueError("hal_hf_papers operation must be search, paper_details, or find_resources")


async def hal_hf_dataset(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Inspect a Hugging Face dataset and stage the profile into HAL."""
    run = _resolve_run(context, arguments.get("run_id"))
    dataset = str(arguments.get("dataset") or "").strip()
    if not dataset:
        raise ValueError("hal_hf_dataset requires dataset")
    client = _hf_research_client(context)
    profile = await client.inspect_dataset(
        dataset=dataset,
        config=_optional_str(arguments.get("config")),
        split=_optional_str(arguments.get("split")),
        sample_rows=min(int(arguments.get("sample_rows") or 3), 10),
    )
    output = _stage_json_output(
        context,
        run,
        title=f"HF Dataset Profile: {dataset}",
        output_type="hf_dataset_profile",
        payload={"dataset": dataset, "profile": profile},
        source={"generator": "hal_hf_dataset", "dataset": dataset},
    )
    payload = {
        "run_id": run.id,
        "dataset": dataset,
        "output_id": output.id,
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.dataset.profiled",
        message=f"Staged Hugging Face dataset profile for {dataset}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Staged Hugging Face dataset profile for {dataset}.",
        payload=payload,
    )


async def hal_hf_docs(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Search or fetch HF docs and stage the result into HAL."""
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    client = _hf_research_client(context)

    if operation == "search":
        endpoint = str(arguments.get("endpoint") or "").strip()
        if not endpoint:
            raise ValueError("hal_hf_docs search requires endpoint")
        result = await client.search_docs(
            endpoint=endpoint,
            query=_optional_str(arguments.get("query")),
            max_results=_limit(arguments.get("max_results"), default=20),
        )
        title = f"HF Docs Search: {endpoint}"
        source = {"generator": "hal_hf_docs", "operation": operation, "endpoint": endpoint}
    elif operation == "fetch":
        url = str(arguments.get("url") or "").strip()
        if not url:
            raise ValueError("hal_hf_docs fetch requires url")
        result = await client.fetch_doc(url=url)
        title = f"HF Docs Fetch: {url[:80]}"
        source = {"generator": "hal_hf_docs", "operation": operation, "url": url}
    else:
        raise ValueError("hal_hf_docs operation must be search or fetch")

    output = _stage_json_output(
        context,
        run,
        title=title,
        output_type="hf_docs_result",
        payload={"operation": operation, "result": result},
        source=source,
    )
    payload = {
        "run_id": run.id,
        "operation": operation,
        "output_id": output.id,
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.docs.captured",
        message=f"Staged Hugging Face docs result from {operation}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Staged Hugging Face docs result from {operation}.",
        payload=payload,
    )


async def hal_github_examples(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Find or read GitHub examples and stage the result into HAL."""
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    repo = str(arguments.get("repo") or "").strip()
    if not repo:
        raise ValueError("hal_github_examples requires repo")
    client = _hf_research_client(context)

    if operation == "find_examples":
        result = await client.github_find_examples(
            repo=repo,
            org=str(arguments.get("org") or "huggingface"),
            keyword=_optional_str(arguments.get("keyword")),
            max_results=_limit(arguments.get("max_results"), default=20),
        )
        title = f"GitHub Examples: {repo}"
        source = {"generator": "hal_github_examples", "operation": operation, "repo": repo}
    elif operation == "read_file":
        path = str(arguments.get("path") or "").strip()
        if not path:
            raise ValueError("hal_github_examples read_file requires path")
        result = await client.github_read_file(
            repo=repo,
            path=path,
            ref=str(arguments.get("ref") or "HEAD"),
            line_start=_optional_int(arguments.get("line_start")),
            line_end=_optional_int(arguments.get("line_end")),
        )
        title = f"GitHub Example File: {repo}/{path}"
        source = {
            "generator": "hal_github_examples",
            "operation": operation,
            "repo": repo,
            "path": path,
        }
    else:
        raise ValueError("hal_github_examples operation must be find_examples or read_file")

    output = _stage_json_output(
        context,
        run,
        title=title,
        output_type="github_example_result",
        payload={"operation": operation, "repo": repo, "result": result},
        source=source,
    )
    payload = {
        "run_id": run.id,
        "operation": operation,
        "repo": repo,
        "output_id": output.id,
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.github.examples.captured",
        message=f"Staged GitHub example result from {operation}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Staged GitHub example result from {operation}.",
        payload=payload,
    )


async def hal_hf_repo(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Run an approved Hugging Face repo side effect and stage the result."""
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    repo_id = str(arguments.get("repo_id") or "").strip()
    if not repo_id:
        raise ValueError("hal_hf_repo requires repo_id")
    if operation not in {"create_repo", "upload_file", "delete_files"}:
        raise ValueError("hal_hf_repo operation must be create_repo, upload_file, or delete_files")
    if operation == "upload_file" and not arguments.get("path"):
        raise ValueError("hal_hf_repo upload_file requires path")
    if operation == "upload_file" and arguments.get("content") is None:
        raise ValueError("hal_hf_repo upload_file requires content")
    if operation == "delete_files" and not arguments.get("patterns"):
        raise ValueError("hal_hf_repo delete_files requires patterns")

    client = _hf_research_client(context)
    result = await client.hf_repo_action(
        operation=operation,
        repo_id=repo_id,
        repo_type=str(arguments.get("repo_type") or "model"),
        path=_optional_str(arguments.get("path")),
        content=arguments.get("content"),
        patterns=_coerce_str_list(arguments.get("patterns")),
        revision=_optional_str(arguments.get("revision")),
        create_pr=bool(arguments.get("create_pr")),
        commit_message=_optional_str(arguments.get("commit_message")),
        private=arguments.get("private"),
        space_sdk=_optional_str(arguments.get("space_sdk")),
    )
    request = _repo_request_summary(arguments)
    output = _stage_json_output(
        context,
        run,
        title=f"HF Repo Action: {operation} {repo_id}",
        output_type="hf_repo_action",
        payload={
            "operation": operation,
            "repo_id": repo_id,
            "request": request,
            "result": result,
        },
        source={"generator": "hal_hf_repo", "operation": operation, "repo_id": repo_id},
        artifact_uri=_artifact_uri(result),
    )
    payload = {
        "run_id": run.id,
        "operation": operation,
        "repo_id": repo_id,
        "output_id": output.id,
        "artifact_uri": output.artifact_uri,
        "result": _public_result_summary(result),
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.repo_action.completed",
        message=f"Completed approved Hugging Face repo action: {operation} {repo_id}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Completed approved Hugging Face repo action {operation} for {repo_id}.",
        payload=payload,
    )


async def hal_hf_job(arguments: dict[str, Any], context: AgentToolContext) -> AgentToolResult:
    """Run an approved Hugging Face Jobs operation and stage the result."""
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    if operation not in HF_JOB_OPERATIONS:
        raise ValueError(f"hal_hf_job operation must be one of: {', '.join(HF_JOB_OPERATIONS)}")
    if operation in HF_JOB_LAUNCH_OPERATIONS:
        script = _optional_str(arguments.get("script"))
        command = arguments.get("command")
        if bool(script) == bool(command):
            raise ValueError(f"hal_hf_job {operation} requires exactly one of script or command")
        if operation == "schedule" and not _optional_str(arguments.get("schedule")):
            raise ValueError("hal_hf_job schedule requires schedule")
        smoke = _resolve_job_smoke_gate(context, run, arguments)
    elif operation in HF_SCHEDULED_JOB_OPERATIONS:
        if operation != "scheduled_list" and not _optional_str(arguments.get("scheduled_job_id")):
            raise ValueError(f"hal_hf_job {operation} requires scheduled_job_id")
        smoke = None
    elif not _optional_str(arguments.get("job_id")):
        raise ValueError(f"hal_hf_job {operation} requires job_id")
    else:
        smoke = None

    client = _hf_research_client(context)
    result = await client.hf_job_action(
        operation=operation,
        script=_optional_str(arguments.get("script")),
        command=_coerce_str_list(arguments.get("command")),
        image=_optional_str(arguments.get("image")),
        dependencies=_coerce_str_list(arguments.get("dependencies")),
        hardware_flavor=str(arguments.get("hardware_flavor") or "cpu-basic"),
        timeout=str(arguments.get("timeout") or "30m"),
        env=_safe_env(arguments.get("env")),
        secrets=_safe_str_map(arguments.get("secrets"), field_name="secrets"),
        labels=_safe_str_map(arguments.get("labels"), field_name="labels"),
        namespace=_optional_str(arguments.get("namespace")),
        job_id=_optional_str(arguments.get("job_id")),
        scheduled_job_id=_optional_str(arguments.get("scheduled_job_id")),
        schedule=_optional_str(arguments.get("schedule")),
        include_suspended=bool(arguments.get("include_suspended")),
        trackio_space_id=_optional_str(arguments.get("trackio_space_id")),
        trackio_project=_optional_str(arguments.get("trackio_project")),
    )
    output_type = _hf_job_output_type(operation)
    job_id = _optional_str(result.get("job_id") if isinstance(result, dict) else None) or _optional_str(
        arguments.get("job_id")
    )
    scheduled_job_id = _optional_str(
        result.get("scheduled_job_id") if isinstance(result, dict) else None
    ) or _optional_str(arguments.get("scheduled_job_id"))
    output = _stage_json_output(
        context,
        run,
        title=f"HF Job {operation}: {job_id or scheduled_job_id or 'pending'}",
        output_type=output_type,
        payload={
            "operation": operation,
            "job_id": job_id,
            "scheduled_job_id": scheduled_job_id,
            "request": _job_request_summary(arguments),
            "smoke_gate": smoke,
            "result": result,
        },
        source={
            "generator": "hal_hf_job",
            "operation": operation,
            "job_id": job_id,
            "scheduled_job_id": scheduled_job_id,
        },
        artifact_uri=_artifact_uri(result),
    )
    trackio_seed = _stage_trackio_dashboard_seed(
        context,
        run,
        arguments,
        job_id=job_id,
        scheduled_job_id=scheduled_job_id,
    )
    event_type = _hf_job_event_type(operation)
    payload = {
        "run_id": run.id,
        "operation": operation,
        "job_id": job_id,
        "scheduled_job_id": scheduled_job_id,
        "output_id": output.id,
        "artifact_uri": output.artifact_uri,
        "trackio": trackio_seed,
        "result": _public_result_summary(result),
    }
    _require_store(context).append_run_event(
        run,
        event_type=event_type,
        message=f"Completed approved Hugging Face job operation: {operation}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Completed approved Hugging Face job operation {operation}.",
        payload=payload,
    )


async def hal_hf_sandbox_smoke(
    arguments: dict[str, Any],
    context: AgentToolContext,
) -> AgentToolResult:
    """Run or record a bounded sandbox smoke test for HF compute."""
    run = _resolve_run(context, arguments.get("run_id"))
    script = _optional_str(arguments.get("script"))
    command = _coerce_str_list(arguments.get("command"))
    if bool(script) == bool(command):
        raise ValueError("hal_hf_sandbox_smoke requires exactly one of script or command")
    client = _hf_research_client(context)
    result = await client.hf_sandbox_smoke(
        script=script,
        command=command,
        image=_optional_str(arguments.get("image")),
        dependencies=_coerce_str_list(arguments.get("dependencies")),
        hardware_flavor=str(arguments.get("hardware_flavor") or "cpu-basic"),
        timeout=str(arguments.get("timeout") or "15m"),
        env=_safe_env(arguments.get("env")),
        expected_signal=_optional_str(arguments.get("expected_signal")),
    )
    request = _smoke_request_summary(arguments)
    output = _stage_json_output(
        context,
        run,
        title=f"HF Sandbox Smoke: {request.get('mode', 'compute')}",
        output_type="hf_sandbox_smoke",
        payload={
            "request": request,
            "result": result,
        },
        source={"generator": "hal_hf_sandbox_smoke", "status": _smoke_status(result)},
        artifact_uri=_artifact_uri(result),
    )
    payload = {
        "run_id": run.id,
        "output_id": output.id,
        "artifact_uri": output.artifact_uri,
        "status": _smoke_status(result),
        "result": _public_result_summary(result),
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.sandbox_smoke.completed",
        message=f"Recorded HF sandbox smoke result: {payload['status']}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Recorded HF sandbox smoke result {output.id}: {payload['status']}.",
        payload=payload,
    )


async def hal_hf_sandbox(
    arguments: dict[str, Any],
    context: AgentToolContext,
) -> AgentToolResult:
    """Execute an approved remote sandbox lifecycle action and stage it in HAL."""
    run = _resolve_run(context, arguments.get("run_id"))
    operation = str(arguments.get("operation") or "").strip()
    if operation not in {"create", "status", "run_command", "read_file", "write_file", "delete"}:
        raise ValueError("hal_hf_sandbox operation must be create, status, run_command, read_file, write_file, or delete")
    if operation != "create" and not _optional_str(arguments.get("sandbox_id")):
        raise ValueError(f"hal_hf_sandbox {operation} requires sandbox_id")
    if operation == "run_command" and not arguments.get("command"):
        raise ValueError("hal_hf_sandbox run_command requires command")
    if operation in {"read_file", "write_file"} and not _optional_str(arguments.get("path")):
        raise ValueError(f"hal_hf_sandbox {operation} requires path")
    if operation == "write_file" and arguments.get("content") is None:
        raise ValueError("hal_hf_sandbox write_file requires content")

    client = _hf_research_client(context)
    result = await client.hf_sandbox_action(
        operation=operation,
        sandbox_id=_optional_str(arguments.get("sandbox_id")),
        image=_optional_str(arguments.get("image")),
        hardware_flavor=str(arguments.get("hardware_flavor") or "cpu-basic"),
        timeout=str(arguments.get("timeout") or "30m"),
        env=_safe_env(arguments.get("env")),
        command=_coerce_str_list(arguments.get("command")),
        path=_optional_str(arguments.get("path")),
        content=arguments.get("content"),
    )
    sandbox_id = _optional_str(
        result.get("sandbox_id") if isinstance(result, dict) else None
    ) or _optional_str(arguments.get("sandbox_id"))
    output = _stage_json_output(
        context,
        run,
        title=f"HF Sandbox {operation}: {sandbox_id or 'new'}",
        output_type="hf_sandbox_action",
        payload={
            "operation": operation,
            "sandbox_id": sandbox_id,
            "request": _sandbox_request_summary(arguments),
            "result": result,
        },
        source={"generator": "hal_hf_sandbox", "operation": operation, "sandbox_id": sandbox_id},
        artifact_uri=_artifact_uri(result),
    )
    payload = {
        "run_id": run.id,
        "operation": operation,
        "sandbox_id": sandbox_id,
        "output_id": output.id,
        "artifact_uri": output.artifact_uri,
        "result": _public_result_summary(result),
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.sandbox_action.completed",
        message=f"Completed approved HF sandbox action: {operation}.",
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Completed approved HF sandbox action {operation}.",
        payload=payload,
    )


async def hal_hf_harvest_artifacts(
    arguments: dict[str, Any],
    context: AgentToolContext,
) -> AgentToolResult:
    """Harvest HF compute artifacts into a HAL manifest output."""
    run = _resolve_run(context, arguments.get("run_id"))
    artifact_uris = _coerce_str_list(arguments.get("artifact_uris")) or []
    paths = _coerce_str_list(arguments.get("paths")) or []
    repo_id = _optional_str(arguments.get("repo_id"))
    job_id = _optional_str(arguments.get("job_id"))
    if not artifact_uris and not (repo_id and paths) and not job_id:
        raise ValueError("hal_hf_harvest_artifacts requires artifact_uris, repo_id+paths, or job_id")
    client = _hf_research_client(context)
    store_artifacts = bool(arguments.get("store_artifacts"))
    result = await client.hf_harvest_artifacts(
        artifact_uris=artifact_uris,
        repo_id=repo_id,
        repo_type=str(arguments.get("repo_type") or "model"),
        paths=paths,
        job_id=job_id,
        description=_optional_str(arguments.get("description")),
    )
    stored_artifacts = []
    storage_errors = []
    if store_artifacts:
        max_bytes = _optional_int(arguments.get("max_bytes")) or MAX_ARTIFACT_BYTES
        if max_bytes <= 0:
            raise ValueError("hal_hf_harvest_artifacts max_bytes must be greater than 0")
        stored_artifacts, storage_errors = await _store_hf_artifacts(
            context,
            client,
            run,
            result,
            artifact_prefix=_optional_str(arguments.get("artifact_prefix")),
            max_bytes=max_bytes,
        )
    result_payload = dict(result) if isinstance(result, dict) else {"result": result}
    if stored_artifacts or storage_errors or store_artifacts:
        result_payload["stored_artifacts"] = stored_artifacts
        result_payload["storage_errors"] = storage_errors
    output = _stage_json_output(
        context,
        run,
        title=f"HF Artifact Harvest: {job_id or repo_id or len(artifact_uris)}",
        output_type="hf_artifact_harvest",
        payload={
            "request": _artifact_harvest_request_summary(arguments),
            "result": result_payload,
        },
        source={"generator": "hal_hf_harvest_artifacts", "job_id": job_id, "repo_id": repo_id},
        artifact_uri=_stored_artifact_uri(stored_artifacts) or _artifact_uri(result),
    )
    payload = {
        "run_id": run.id,
        "job_id": job_id,
        "repo_id": repo_id,
        "output_id": output.id,
        "artifact_uri": output.artifact_uri,
        "artifact_count": _artifact_count(result),
        "stored_artifact_count": len(stored_artifacts),
        "storage_error_count": len(storage_errors),
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.artifacts.harvested",
        message=(
            f"Harvested {payload['artifact_count']} HF artifact reference(s); "
            f"stored {payload['stored_artifact_count']}."
        ),
        actor=context.actor,
        payload=payload,
    )
    return AgentToolResult.ok(
        f"Harvested {payload['artifact_count']} HF artifact reference(s); stored {payload['stored_artifact_count']}.",
        payload=payload,
    )


class HFResearchClient:
    """Small async client for HF discovery endpoints used by HAL tools."""

    def __init__(
        self,
        *,
        hf_token: str | None = None,
        github_token: str | None = None,
        sandbox_client: Any | None = None,
        timeout: float = 20.0,
    ):
        """Initialize the HTTP client wrapper."""
        self.hf_token = hf_token
        self.github_token = github_token
        self.sandbox_client = sandbox_client
        self.timeout = timeout

    async def search_papers(self, *, query: str, limit: int) -> list[dict[str, Any]]:
        """Search papers through the HF Hub paper API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{HF_API}/papers/search",
                params={"q": query, "limit": limit},
                headers=self._hf_headers(),
            )
            response.raise_for_status()
            data = response.json()
        return _coerce_items(data)[:limit]

    async def paper_details(self, *, arxiv_id: str) -> dict[str, Any]:
        """Fetch paper details from the HF Hub paper API."""
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.get(
                f"{HF_API}/papers/{arxiv_id}",
                headers=self._hf_headers(),
            )
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {"id": arxiv_id, "raw": data}

    async def paper_resources(self, *, arxiv_id: str, limit: int) -> dict[str, list[dict[str, Any]]]:
        """Fetch Hub models and datasets linked to a paper."""
        params = {
            "filter": f"arxiv:{arxiv_id}",
            "limit": limit,
            "sort": "downloads",
            "direction": -1,
        }
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            datasets_response = await client.get(
                f"{HF_API}/datasets",
                params=params,
                headers=self._hf_headers(),
            )
            models_response = await client.get(
                f"{HF_API}/models",
                params=params,
                headers=self._hf_headers(),
            )
            datasets_response.raise_for_status()
            models_response.raise_for_status()
            datasets = _coerce_items(datasets_response.json())[:limit]
            models = _coerce_items(models_response.json())[:limit]
        return {"datasets": datasets, "models": models}

    async def inspect_dataset(
        self,
        *,
        dataset: str,
        config: str | None = None,
        split: str | None = None,
        sample_rows: int = 3,
    ) -> dict[str, Any]:
        """Inspect a dataset through datasets-server endpoints."""
        headers = self._hf_headers()
        async with httpx.AsyncClient(timeout=self.timeout, headers=headers) as client:
            status_response = await client.get(
                f"{DATASETS_SERVER}/is-valid",
                params={"dataset": dataset},
            )
            splits_response = await client.get(
                f"{DATASETS_SERVER}/splits",
                params={"dataset": dataset},
            )
            parquet_response = await client.get(
                f"{DATASETS_SERVER}/parquet",
                params={"dataset": dataset},
            )
            status = _json_or_error(status_response)
            splits = _json_or_error(splits_response)
            parquet = _json_or_error(parquet_response)

            detected_config, detected_split = _detect_dataset_config_split(
                splits if isinstance(splits, dict) else {},
                config=config,
                split=split,
            )
            info_response = await client.get(
                f"{DATASETS_SERVER}/info",
                params={"dataset": dataset, "config": detected_config},
            )
            rows_response = await client.get(
                f"{DATASETS_SERVER}/first-rows",
                params={
                    "dataset": dataset,
                    "config": detected_config,
                    "split": detected_split,
                },
                timeout=max(self.timeout, 30.0),
            )
            info = _json_or_error(info_response)
            first_rows = _json_or_error(rows_response)

        return {
            "dataset": dataset,
            "config": detected_config,
            "split": detected_split,
            "sample_rows": sample_rows,
            "status": status,
            "splits": splits,
            "info": info,
            "first_rows": _trim_first_rows(first_rows, sample_rows),
            "parquet": parquet,
        }

    async def search_docs(
        self,
        *,
        endpoint: str,
        query: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Search HF docs by scanning the endpoint index and LLM page list."""
        urls = [
            f"{HF_DOCS_BASE}/{endpoint}/index.md",
            f"{HF_DOCS_BASE}/{endpoint}/llms.txt",
        ]
        matches = []
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for url in urls:
                response = await client.get(url, headers=self._hf_headers())
                if response.status_code >= 400:
                    continue
                matches.extend(
                    {
                        **match,
                        "source_url": url,
                    }
                    for match in _doc_matches(
                        response.text,
                        query=query,
                        limit=max_results,
                    )
                )
                if len(matches) >= max_results:
                    break
        return {
            "endpoint": endpoint,
            "query": query,
            "source_urls": urls,
            "matches": matches[:max_results],
        }

    async def fetch_doc(self, *, url: str) -> dict[str, Any]:
        """Fetch a markdown HF docs page."""
        fetch_url = _docs_markdown_url(url)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(fetch_url, headers=self._hf_headers())
            response.raise_for_status()
            content = response.text
        return {
            "url": url,
            "source_url": fetch_url,
            "content": _truncate_text(content, MAX_DOC_FETCH_CHARS),
            "truncated": len(content) > MAX_DOC_FETCH_CHARS,
        }

    async def github_find_examples(
        self,
        *,
        repo: str,
        org: str = "huggingface",
        keyword: str | None = None,
        max_results: int = 20,
    ) -> dict[str, Any]:
        """Find likely example files in a GitHub repository tree."""
        owner_repo = _owner_repo(repo, org=org)
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(
                f"{GITHUB_API}/repos/{owner_repo}/git/trees/HEAD",
                params={"recursive": 1},
                headers=self._github_headers(),
            )
            response.raise_for_status()
            tree = response.json().get("tree", [])
        candidates = [
            item
            for item in tree
            if item.get("type") == "blob" and _looks_like_example_path(str(item.get("path") or ""))
        ]
        if keyword:
            keyword_lower = keyword.lower()
            candidates = [
                item
                for item in candidates
                if keyword_lower in str(item.get("path") or "").lower()
            ]
        examples = [
            {
                "path": item.get("path"),
                "url": f"https://github.com/{owner_repo}/blob/HEAD/{item.get('path')}",
                "size": item.get("size"),
            }
            for item in candidates[:max_results]
        ]
        return {
            "repo": owner_repo,
            "keyword": keyword,
            "example_count": len(examples),
            "examples": examples,
        }

    async def github_read_file(
        self,
        *,
        repo: str,
        path: str,
        ref: str = "HEAD",
        line_start: int | None = None,
        line_end: int | None = None,
    ) -> dict[str, Any]:
        """Read a file from GitHub raw content."""
        owner_repo = _owner_repo(repo)
        raw_url = f"{GITHUB_RAW}/{owner_repo}/{ref}/{path}"
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            response = await client.get(raw_url, headers=self._github_headers())
            response.raise_for_status()
            content = response.text
        selected = _slice_lines(content, line_start=line_start, line_end=line_end)
        return {
            "repo": owner_repo,
            "path": path,
            "ref": ref,
            "url": f"https://github.com/{owner_repo}/blob/{ref}/{path}",
            "line_start": line_start,
            "line_end": line_end,
            "content": _truncate_text(selected, MAX_DOC_FETCH_CHARS),
            "truncated": len(selected) > MAX_DOC_FETCH_CHARS,
        }

    async def hf_repo_action(
        self,
        *,
        operation: str,
        repo_id: str,
        repo_type: str = "model",
        path: str | None = None,
        content: Any | None = None,
        patterns: list[str] | None = None,
        revision: str | None = None,
        create_pr: bool = False,
        commit_message: str | None = None,
        private: Any | None = None,
        space_sdk: str | None = None,
    ) -> dict[str, Any]:
        """Execute an approved HF Hub repo mutation through huggingface_hub."""
        api = self._hf_api()
        revision = revision or "main"
        if operation == "create_repo":
            kwargs = {
                "repo_id": repo_id,
                "repo_type": repo_type,
                "private": bool(private),
                "exist_ok": True,
            }
            if repo_type == "space" and space_sdk:
                kwargs["space_sdk"] = space_sdk
            result = await asyncio.to_thread(api.create_repo, **kwargs)
            return {
                "operation": operation,
                "repo_id": repo_id,
                "repo_type": repo_type,
                "url": str(result),
            }
        if operation == "upload_file":
            if path is None or content is None:
                raise ValueError("upload_file requires path and content")
            file_bytes = content.encode("utf-8") if isinstance(content, str) else content
            result = await asyncio.to_thread(
                api.upload_file,
                path_or_fileobj=file_bytes,
                path_in_repo=path,
                repo_id=repo_id,
                repo_type=repo_type,
                revision=revision,
                commit_message=commit_message or f"Upload {path}",
                create_pr=create_pr,
            )
            url = getattr(result, "pr_url", None) or f"{_hub_repo_url(repo_id, repo_type)}/blob/{revision}/{path}"
            return {
                "operation": operation,
                "repo_id": repo_id,
                "repo_type": repo_type,
                "path": path,
                "revision": revision,
                "create_pr": create_pr,
                "url": url,
            }
        if operation == "delete_files":
            if not patterns:
                raise ValueError("delete_files requires patterns")
            await asyncio.to_thread(
                api.delete_files,
                repo_id=repo_id,
                delete_patterns=patterns,
                repo_type=repo_type,
                revision=revision,
                commit_message=commit_message or f"Delete {', '.join(patterns)}",
                create_pr=create_pr,
            )
            return {
                "operation": operation,
                "repo_id": repo_id,
                "repo_type": repo_type,
                "patterns": patterns,
                "revision": revision,
                "create_pr": create_pr,
                "url": _hub_repo_url(repo_id, repo_type),
            }
        raise ValueError(f"Unsupported HF repo operation: {operation}")

    async def hf_job_action(
        self,
        *,
        operation: str,
        script: str | None = None,
        command: list[str] | None = None,
        image: str | None = None,
        dependencies: list[str] | None = None,
        hardware_flavor: str = "cpu-basic",
        timeout: str = "30m",
        env: dict[str, str] | None = None,
        secrets: dict[str, str] | None = None,
        labels: dict[str, str] | None = None,
        namespace: str | None = None,
        job_id: str | None = None,
        scheduled_job_id: str | None = None,
        schedule: str | None = None,
        include_suspended: bool = False,
        trackio_space_id: str | None = None,
        trackio_project: str | None = None,
    ) -> dict[str, Any]:
        """Execute an approved HF Jobs operation through huggingface_hub."""
        jobs = self._hf_jobs_module()
        env = dict(env or {})
        if trackio_space_id:
            env["TRACKIO_SPACE_ID"] = trackio_space_id
        if trackio_project:
            env["TRACKIO_PROJECT"] = trackio_project

        if operation in {"submit", "schedule"}:
            if bool(script) == bool(command):
                raise ValueError(f"{operation} requires exactly one of script or command")
            if operation == "schedule" and not schedule:
                raise ValueError("schedule requires schedule")
            if script:
                method_name = "create_scheduled_uv_job" if operation == "schedule" else "run_uv_job"
                run = getattr(jobs, method_name, None)
                if run is None:
                    raise ValueError(f"Installed huggingface_hub does not expose {method_name}")
                kwargs = {
                    "dependencies": dependencies or None,
                    "env": env or None,
                    "secrets": secrets or None,
                    "labels": labels or None,
                    "flavor": hardware_flavor,
                    "timeout": timeout,
                    "namespace": namespace,
                    "image": image,
                    "token": self.hf_token,
                }
                if operation == "schedule":
                    kwargs["schedule"] = schedule
                job = await asyncio.to_thread(
                    _call_with_supported_kwargs,
                    run,
                    script,
                    **kwargs,
                )
            else:
                method_name = "create_scheduled_job" if operation == "schedule" else "run_job"
                run = getattr(jobs, method_name, None)
                if run is None:
                    raise ValueError(f"Installed huggingface_hub does not expose {method_name}")
                kwargs = {
                    "image": image or "python:3.12",
                    "command": command,
                    "env": env or None,
                    "secrets": secrets or None,
                    "labels": labels or None,
                    "flavor": hardware_flavor,
                    "timeout": timeout,
                    "namespace": namespace,
                    "token": self.hf_token,
                }
                if operation == "schedule":
                    kwargs["schedule"] = schedule
                job = await asyncio.to_thread(
                    _call_with_supported_kwargs,
                    run,
                    **kwargs,
                )
            if operation == "schedule":
                payload = _scheduled_job_info_payload(job)
                payload["operation"] = "scheduled_job_info"
                payload["schedule"] = payload.get("schedule") or schedule
                return payload
            return _job_info_payload(job)

        if operation in HF_SCHEDULED_JOB_OPERATIONS:
            if operation == "scheduled_list":
                list_scheduled_jobs = getattr(jobs, "list_scheduled_jobs", None)
                if list_scheduled_jobs is None:
                    raise ValueError("Installed huggingface_hub does not expose list_scheduled_jobs")
                scheduled_jobs = await asyncio.to_thread(
                    lambda: list(
                        _call_with_supported_kwargs(
                            list_scheduled_jobs,
                            include_suspended=include_suspended,
                            namespace=namespace,
                            token=self.hf_token,
                        )
                    )
                )
                return {
                    "operation": operation,
                    "scheduled_job_count": len(scheduled_jobs),
                    "scheduled_jobs": [_scheduled_job_info_payload(job) for job in scheduled_jobs],
                }
            if not scheduled_job_id:
                raise ValueError(f"{operation} requires scheduled_job_id")
            method_name = {
                "scheduled_status": "inspect_scheduled_job",
                "scheduled_suspend": "suspend_scheduled_job",
                "scheduled_resume": "resume_scheduled_job",
                "scheduled_delete": "delete_scheduled_job",
            }[operation]
            method = getattr(jobs, method_name, None)
            if method is None:
                raise ValueError(f"Installed huggingface_hub does not expose {method_name}")
            scheduled_job = await asyncio.to_thread(
                _call_with_supported_kwargs,
                method,
                scheduled_job_id,
                namespace=namespace,
                token=self.hf_token,
            )
            payload = _scheduled_job_info_payload(scheduled_job)
            payload["operation"] = operation
            payload["scheduled_job_id"] = payload.get("scheduled_job_id") or scheduled_job_id
            return payload

        if not job_id:
            raise ValueError(f"{operation} requires job_id")
        if operation == "status":
            inspect_job = getattr(jobs, "inspect_job", None)
            if inspect_job is None:
                raise ValueError("Installed huggingface_hub does not expose inspect_job")
            return _job_info_payload(
                await asyncio.to_thread(
                    _call_with_supported_kwargs,
                    inspect_job,
                    job_id=job_id,
                    namespace=namespace,
                    token=self.hf_token,
                )
            )
        if operation == "logs":
            fetch_job_logs = getattr(jobs, "fetch_job_logs", None)
            if fetch_job_logs is None:
                raise ValueError("Installed huggingface_hub does not expose fetch_job_logs")
            logs = await asyncio.to_thread(
                lambda: list(
                    _call_with_supported_kwargs(
                        fetch_job_logs,
                        job_id=job_id,
                        namespace=namespace,
                        token=self.hf_token,
                    )
                )
            )
            return {
                "operation": operation,
                "job_id": job_id,
                "logs": _truncate_text("\n".join(str(line) for line in logs), MAX_DOC_FETCH_CHARS),
            }
        if operation == "cancel":
            cancel_job = getattr(jobs, "cancel_job", None)
            if cancel_job is None:
                raise ValueError("Installed huggingface_hub does not expose cancel_job")
            await asyncio.to_thread(
                _call_with_supported_kwargs,
                cancel_job,
                job_id=job_id,
                namespace=namespace,
                token=self.hf_token,
            )
            return {"operation": operation, "job_id": job_id, "status": "cancel_requested"}
        raise ValueError(f"Unsupported HF Jobs operation: {operation}")

    async def hf_sandbox_smoke(
        self,
        *,
        script: str | None = None,
        command: list[str] | None = None,
        image: str | None = None,
        dependencies: list[str] | None = None,
        hardware_flavor: str = "cpu-basic",
        timeout: str = "15m",
        env: dict[str, str] | None = None,
        expected_signal: str | None = None,
    ) -> dict[str, Any]:
        """Record a bounded smoke check result for HF compute.

        A real HF sandbox runner can be injected through context metadata by
        supplying a client with this method. The default client performs static
        validation only, which still gives HAL a durable preflight record.
        """
        if bool(script) == bool(command):
            raise ValueError("sandbox smoke requires exactly one of script or command")
        if self.sandbox_client is not None and hasattr(self.sandbox_client, "hf_sandbox_smoke"):
            return await self.sandbox_client.hf_sandbox_smoke(
                script=script,
                command=command,
                image=image,
                dependencies=dependencies,
                hardware_flavor=hardware_flavor,
                timeout=timeout,
                env=env,
                expected_signal=expected_signal,
            )
        mode = "python" if script else "command"
        checks = []
        status = "static_passed"
        if script and _looks_like_inline_python(script):
            try:
                compile(script, "<hal-hf-sandbox-smoke>", "exec")
                checks.append({"name": "python_syntax", "status": "passed"})
            except SyntaxError as exc:
                status = "failed"
                checks.append(
                    {
                        "name": "python_syntax",
                        "status": "failed",
                        "message": f"{exc.msg} at line {exc.lineno}",
                    }
                )
        else:
            checks.append({"name": "request_recorded", "status": "passed"})
        return {
            "status": status,
            "executed": False,
            "mode": mode,
            "image": image,
            "hardware_flavor": hardware_flavor,
            "timeout": timeout,
            "dependencies": dependencies or [],
            "env_keys": sorted((env or {}).keys()),
            "expected_signal": expected_signal,
            "checks": checks,
        }

    async def hf_sandbox_action(
        self,
        *,
        operation: str,
        sandbox_id: str | None = None,
        image: str | None = None,
        hardware_flavor: str = "cpu-basic",
        timeout: str = "30m",
        env: dict[str, str] | None = None,
        command: list[str] | None = None,
        path: str | None = None,
        content: Any | None = None,
    ) -> dict[str, Any]:
        """Execute a remote sandbox lifecycle action through an injected backend."""
        if self.sandbox_client is None or not hasattr(self.sandbox_client, "hf_sandbox_action"):
            raise ValueError(
                "HF sandbox lifecycle actions require context.metadata['hf_sandbox_client'] "
                "or an hf_research_client with hf_sandbox_action"
            )
        return await self.sandbox_client.hf_sandbox_action(
            operation=operation,
            sandbox_id=sandbox_id,
            image=image,
            hardware_flavor=hardware_flavor,
            timeout=timeout,
            env=env,
            command=command,
            path=path,
            content=content,
        )

    async def hf_harvest_artifacts(
        self,
        *,
        artifact_uris: list[str] | None = None,
        repo_id: str | None = None,
        repo_type: str = "model",
        paths: list[str] | None = None,
        job_id: str | None = None,
        description: str | None = None,
    ) -> dict[str, Any]:
        """Build a HAL artifact manifest from HF job and repo references."""
        artifacts = []
        for uri in artifact_uris or []:
            artifacts.append({"uri": uri, "source": "explicit"})
        if repo_id:
            for path in paths or []:
                artifacts.append(
                    {
                        "uri": f"{_hub_repo_url(repo_id, repo_type)}/resolve/main/{path}",
                        "repo_id": repo_id,
                        "repo_type": repo_type,
                        "path": path,
                        "source": "hub_repo",
                    }
                )
        if job_id and not artifacts:
            artifacts.append(
                {
                    "uri": f"{HF_BASE}/jobs/{job_id}",
                    "job_id": job_id,
                    "source": "hf_job",
                }
            )
        return {
            "job_id": job_id,
            "repo_id": repo_id,
            "repo_type": repo_type,
            "description": description,
            "artifact_count": len(artifacts),
            "artifacts": artifacts,
            "artifact_uri": artifacts[0]["uri"] if artifacts else None,
        }

    async def hf_download_artifact(
        self,
        *,
        artifact: dict[str, Any],
        max_bytes: int = MAX_ARTIFACT_BYTES,
    ) -> dict[str, Any]:
        """Download a resolved HF artifact reference as bytes."""
        uri = _optional_str(artifact.get("uri") or artifact.get("url"))
        if not uri:
            raise ValueError("artifact requires uri")
        if not uri.startswith(("http://", "https://")):
            raise ValueError(f"artifact uri is not downloadable over HTTP: {uri}")
        chunks = []
        total = 0
        content_type = _optional_str(artifact.get("content_type"))
        async with httpx.AsyncClient(timeout=max(self.timeout, 60.0), follow_redirects=True) as client:
            async with client.stream("GET", uri, headers=self._hf_headers()) as response:
                response.raise_for_status()
                content_type = content_type or _optional_str(response.headers.get("content-type"))
                async for chunk in response.aiter_bytes():
                    total += len(chunk)
                    if total > max_bytes:
                        raise ValueError(f"artifact exceeds max_bytes={max_bytes}: {uri}")
                    chunks.append(chunk)
        data = b"".join(chunks)
        return {
            "uri": uri,
            "filename": _artifact_filename(artifact),
            "content": data,
            "content_type": content_type or "application/octet-stream",
            "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest(),
        }

    def _hf_api(self):
        if not self.hf_token:
            raise ValueError("HF compute actions require context.metadata['hf_token'] or HF_TOKEN")
        try:
            from huggingface_hub import HfApi
        except ImportError as exc:
            raise ValueError(
                "HF compute actions require the optional 'huggingface_hub' package"
            ) from exc
        return HfApi(token=self.hf_token)

    def _hf_jobs_module(self):
        if not self.hf_token:
            raise ValueError("HF Jobs actions require context.metadata['hf_token'] or HF_TOKEN")
        try:
            import huggingface_hub as jobs
        except ImportError as exc:
            raise ValueError("HF Jobs actions require the optional 'huggingface_hub' package") from exc
        return jobs

    def _hf_headers(self) -> dict[str, str]:
        if not self.hf_token:
            return {}
        return {"Authorization": f"Bearer {self.hf_token}"}

    def _github_headers(self) -> dict[str, str]:
        headers = {"Accept": "application/vnd.github+json"}
        if self.github_token:
            headers["Authorization"] = f"Bearer {self.github_token}"
        return headers


def _hf_research_client(context: AgentToolContext) -> Any:
    client = context.metadata.get("hf_research_client")
    if client is not None:
        return client
    secret_manager = _tool_secret_manager(context)
    hf_token = _optional_str(context.metadata.get("hf_token")) or secret_value(
        "huggingface",
        secret_manager=secret_manager,
    )
    github_token = _optional_str(context.metadata.get("github_token")) or secret_value(
        "github",
        secret_manager=secret_manager,
    )
    return HFResearchClient(
        hf_token=hf_token,
        github_token=github_token,
        sandbox_client=context.metadata.get("hf_sandbox_client"),
    )


def _tool_secret_manager(context: AgentToolContext) -> SecretManager | None:
    manager = context.metadata.get("secret_manager")
    return manager if hasattr(manager, "get_secret") else None


def _upsert_hf_paper_document(
    store: Any,
    run: ResearchRun,
    paper: dict[str, Any],
    actor: str,
    *,
    query: str | None = None,
) -> Document:
    paper_id = _paper_id(paper)
    source_identifier = f"arxiv:{paper_id}" if paper_id else f"hf-paper:{_stable_paper_key(paper)}"
    source_url = _paper_url(paper, paper_id=paper_id)
    file_hash = hashlib.sha256(source_identifier.encode("utf-8")).hexdigest()
    document = store.session.query(Document).filter_by(file_hash=file_hash).one_or_none()
    if document is None:
        document = Document(
            source_path=source_url,
            source_type="huggingface_paper",
            file_hash=file_hash,
            title=_paper_title(paper),
            authors=json.dumps(_paper_authors(paper), sort_keys=True),
            year=_optional_year(paper),
            doi=_optional_str(paper.get("doi")),
            abstract=_paper_abstract(paper),
            summary=_paper_summary(paper),
            findings=json.dumps(_paper_findings(paper), sort_keys=True),
            full_text=_paper_full_text(paper),
            status="completed",
            processed_at=utc_now(),
            acquisition_source="huggingface",
            acquisition_query=query,
            source_identifier=source_identifier,
            source_version="v1",
            version_group_key=source_identifier,
            refresh_policy="manual",
        )
        store.session.add(document)
        store.session.flush()
    else:
        document.title = document.title or _paper_title(paper)
        document.abstract = document.abstract or _paper_abstract(paper)
        document.summary = document.summary or _paper_summary(paper)
        document.full_text = document.full_text or _paper_full_text(paper)
        document.acquisition_query = document.acquisition_query or query
        document.updated_at = utc_now()
        store.session.flush()

    content = _paper_chunk_text(paper, document)
    chunk = None
    if content and not _has_run_chunk(store, document, run, content):
        chunk = store.add_document_chunk(
            document=document,
            run=run,
            chunk_index=_next_chunk_index(document),
            content=content,
            token_count=max(1, len(content.split())),
            extraction_metadata={
                "source": "hal_hf_papers",
                "source_identifier": source_identifier,
                "query": query,
            },
        )
    elif content:
        chunk = _matching_run_chunk(store, document, run, content)

    claim_text = _paper_claim_text(paper, document)
    if claim_text and not _has_run_claim(store, document, run, claim_text):
        store.add_claim_with_evidence(
            document=document,
            chunk=chunk,
            run=run,
            claim_evidence=ClaimEvidence(
                claim_text=claim_text,
                evidence_text=_paper_abstract(paper) or document.summary,
                quote=_paper_abstract(paper) or document.summary,
                source_url=source_url,
                claim_type="paper_summary",
                confidence=0.6,
                provenance={
                    "source": "hal_hf_papers",
                    "source_identifier": source_identifier,
                    "query": query,
                    "actor": actor,
                },
            ),
        )
    store.session.flush()
    return document


def _stage_json_output(
    context: AgentToolContext,
    run: ResearchRun,
    *,
    title: str,
    output_type: str,
    payload: dict[str, Any],
    source: dict[str, Any],
    artifact_uri: str | None = None,
):
    store = _require_store(context)
    return store.stage_output(
        title=title[:512],
        output_type=output_type,
        project=run.project,
        run=run,
        content=_json_content(payload),
        artifact_uri=artifact_uri,
        source={**source, "run_id": run.id},
        created_by=context.actor,
        format="json",
    )


def _stage_trackio_dashboard_seed(
    context: AgentToolContext,
    run: ResearchRun,
    arguments: dict[str, Any],
    *,
    job_id: str | None,
    scheduled_job_id: str | None,
) -> dict[str, Any] | None:
    space_id = _optional_str(arguments.get("trackio_space_id"))
    project = _optional_str(arguments.get("trackio_project"))
    if not space_id and not project:
        return None
    project = project or _default_trackio_project(run)
    dashboard_url = f"{HF_BASE}/spaces/{space_id}" if space_id else None
    payload = {
        "operation": "seed_dashboard",
        "space_id": space_id,
        "project": project,
        "job_id": job_id,
        "scheduled_job_id": scheduled_job_id,
        "dashboard_url": dashboard_url,
        "env": {
            key: value
            for key, value in {
                "TRACKIO_SPACE_ID": space_id,
                "TRACKIO_PROJECT": project,
            }.items()
            if value
        },
    }
    output = _stage_json_output(
        context,
        run,
        title=f"HF Trackio Dashboard Seed: {project}",
        output_type="hf_trackio_dashboard",
        payload=payload,
        source={
            "generator": "hal_hf_job",
            "operation": "trackio_dashboard_seed",
            "job_id": job_id,
            "scheduled_job_id": scheduled_job_id,
        },
        artifact_uri=dashboard_url,
    )
    result = {
        "output_id": output.id,
        "space_id": space_id,
        "project": project,
        "dashboard_url": dashboard_url,
    }
    _require_store(context).append_run_event(
        run,
        event_type="agent.hf.trackio.dashboard_seeded",
        message=f"Seeded HF Trackio dashboard metadata for {project}.",
        actor=context.actor,
        payload={**result, "run_id": run.id, "job_id": job_id, "scheduled_job_id": scheduled_job_id},
    )
    return result


def _default_trackio_project(run: ResearchRun) -> str:
    project_slug = _optional_str(getattr(getattr(run, "project", None), "slug", None))
    return project_slug or f"hal-run-{run.id[:8]}"


async def _store_hf_artifacts(
    context: AgentToolContext,
    client: Any,
    run: ResearchRun,
    result: Any,
    *,
    artifact_prefix: str | None,
    max_bytes: int,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    object_store = _object_store(context, tool_name="hal_hf_harvest_artifacts")
    artifacts = _result_artifacts(result)
    stored_artifacts = []
    storage_errors = []
    prefix = artifact_prefix or f"runs/{run.id}/hf-artifacts"
    for index, artifact in enumerate(artifacts):
        uri = _optional_str(artifact.get("uri") or artifact.get("url"))
        try:
            download = await client.hf_download_artifact(artifact=artifact, max_bytes=max_bytes)
            content = _download_content_bytes(download)
            key = _artifact_object_key(prefix, artifact, download, index)
            stored = await asyncio.to_thread(
                object_store.put_bytes,
                key,
                content,
                str(download.get("content_type") or "application/octet-stream"),
            )
            stored_artifacts.append(
                {
                    "uri": uri,
                    "source": artifact.get("source"),
                    "repo_id": artifact.get("repo_id"),
                    "repo_type": artifact.get("repo_type"),
                    "path": artifact.get("path"),
                    "object_key": stored.key,
                    "object_uri": stored.uri,
                    "size_bytes": stored.size_bytes,
                    "sha256": stored.sha256,
                    "content_type": stored.content_type,
                }
            )
        except Exception as exc:
            storage_errors.append(
                {
                    "uri": uri,
                    "path": artifact.get("path"),
                    "error_type": type(exc).__name__,
                    "message": str(exc),
                }
            )
    return stored_artifacts, storage_errors


def _object_store(context: AgentToolContext, *, tool_name: str):
    if object_store := context.metadata.get("object_store"):
        return object_store
    settings = context.metadata.get("settings")
    if settings is None:
        raise ValueError(f"{tool_name} with store_artifacts requires context.metadata['object_store'] or settings")
    return create_object_store_from_settings(settings)


def _result_artifacts(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, dict) and isinstance(result.get("artifacts"), list):
        return [artifact for artifact in result["artifacts"] if isinstance(artifact, dict)]
    return []


def _download_content_bytes(download: Any) -> bytes:
    if not isinstance(download, dict):
        raise ValueError("download result must be an object")
    content = download.get("content")
    if isinstance(content, bytes):
        return content
    if isinstance(content, bytearray):
        return bytes(content)
    if isinstance(content, str):
        return content.encode("utf-8")
    raise ValueError("download result requires bytes or text content")


def _artifact_object_key(
    prefix: str,
    artifact: dict[str, Any],
    download: dict[str, Any],
    index: int,
) -> str:
    filename = _safe_object_key_part(
        _optional_str(download.get("filename"))
        or _optional_str(artifact.get("path"))
        or _optional_str(artifact.get("uri"))
        or f"artifact-{index}"
    )
    return f"{_safe_object_prefix(prefix)}/{index:03d}-{filename}"


def _safe_object_prefix(prefix: str) -> str:
    parts = [_safe_object_key_part(part) for part in prefix.replace("\\", "/").split("/") if part.strip()]
    if not parts:
        raise ValueError("artifact_prefix must not be empty")
    return "/".join(parts)


def _safe_object_key_part(value: str) -> str:
    value = unquote(value).replace("\\", "/").rstrip("/")
    if "/" in value:
        value = value.rsplit("/", 1)[-1]
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", value).strip(".-")
    return value or "artifact"


def _stored_artifact_uri(stored_artifacts: list[dict[str, Any]]) -> str | None:
    if not stored_artifacts:
        return None
    return _optional_str(stored_artifacts[0].get("object_uri"))


def _require_store(context: AgentToolContext):
    if context.store is None:
        raise ValueError("HF research tools require AgentToolContext.store")
    return context.store


def _resolve_run(context: AgentToolContext, run_id: Any | None = None) -> ResearchRun:
    if run_id:
        run = _require_store(context).get_run(str(run_id))
        if run is None:
            raise ValueError(f"Research run not found: {run_id}")
        return run
    if context.run is None:
        raise ValueError("HF research tools require a research run")
    return context.run


def _limit(value: Any, *, default: int = 10) -> int:
    try:
        parsed = int(value or default)
    except (TypeError, ValueError):
        parsed = default
    return max(1, min(parsed, MAX_LIMIT))


def _optional_str(value: Any | None) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_int(value: Any | None) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_str_list(value: Any | None) -> list[str] | None:
    if value is None:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value]
    return [str(value)]


def _safe_env(value: Any | None) -> dict[str, str] | None:
    return _safe_str_map(value, field_name="env")


def _safe_str_map(value: Any | None, *, field_name: str) -> dict[str, str] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    return {str(key): str(item) for key, item in value.items()}


def _repo_request_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "operation": arguments.get("operation"),
        "repo_id": arguments.get("repo_id"),
        "repo_type": arguments.get("repo_type") or "model",
        "path": arguments.get("path"),
        "patterns": _coerce_str_list(arguments.get("patterns")),
        "revision": arguments.get("revision"),
        "create_pr": bool(arguments.get("create_pr")),
        "private": arguments.get("private"),
        "space_sdk": arguments.get("space_sdk"),
    }
    if arguments.get("content") is not None:
        content = str(arguments.get("content"))
        summary["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        summary["content_size_bytes"] = len(content.encode("utf-8"))
    return {key: value for key, value in summary.items() if value is not None}


def _job_request_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    script = _optional_str(arguments.get("script"))
    summary = {
        "operation": arguments.get("operation"),
        "command": _coerce_str_list(arguments.get("command")),
        "image": arguments.get("image"),
        "dependencies": _coerce_str_list(arguments.get("dependencies")),
        "hardware_flavor": arguments.get("hardware_flavor") or "cpu-basic",
        "timeout": arguments.get("timeout") or "30m",
        "namespace": arguments.get("namespace"),
        "job_id": arguments.get("job_id"),
        "scheduled_job_id": arguments.get("scheduled_job_id"),
        "schedule": arguments.get("schedule"),
        "include_suspended": bool(arguments.get("include_suspended")),
        "labels": _safe_str_map(arguments.get("labels"), field_name="labels"),
        "trackio_space_id": arguments.get("trackio_space_id"),
        "trackio_project": arguments.get("trackio_project"),
        "smoke_test_output_id": arguments.get("smoke_test_output_id"),
        "skip_smoke_reason": arguments.get("skip_smoke_reason"),
        "env_keys": sorted(str(key) for key in (arguments.get("env") or {}).keys())
        if isinstance(arguments.get("env") or {}, dict)
        else None,
        "secret_keys": sorted(str(key) for key in (arguments.get("secrets") or {}).keys())
        if isinstance(arguments.get("secrets") or {}, dict)
        else None,
    }
    if script is not None:
        summary["script_sha256"] = hashlib.sha256(script.encode("utf-8")).hexdigest()
        summary["script_size_bytes"] = len(script.encode("utf-8"))
    return {key: value for key, value in summary.items() if value is not None}


def _smoke_request_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    script = _optional_str(arguments.get("script"))
    command = _coerce_str_list(arguments.get("command"))
    summary = {
        "mode": "python" if script else "command",
        "command": command,
        "image": arguments.get("image"),
        "dependencies": _coerce_str_list(arguments.get("dependencies")),
        "hardware_flavor": arguments.get("hardware_flavor") or "cpu-basic",
        "timeout": arguments.get("timeout") or "15m",
        "expected_signal": arguments.get("expected_signal"),
        "env_keys": sorted(str(key) for key in (arguments.get("env") or {}).keys())
        if isinstance(arguments.get("env") or {}, dict)
        else None,
    }
    if script is not None:
        summary["script_sha256"] = hashlib.sha256(script.encode("utf-8")).hexdigest()
        summary["script_size_bytes"] = len(script.encode("utf-8"))
    return {key: value for key, value in summary.items() if value is not None}


def _artifact_harvest_request_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in {
            "job_id": arguments.get("job_id"),
            "artifact_uris": _coerce_str_list(arguments.get("artifact_uris")),
            "repo_id": arguments.get("repo_id"),
            "repo_type": arguments.get("repo_type") or "model",
            "paths": _coerce_str_list(arguments.get("paths")),
            "description": arguments.get("description"),
            "store_artifacts": bool(arguments.get("store_artifacts")),
            "artifact_prefix": arguments.get("artifact_prefix"),
            "max_bytes": arguments.get("max_bytes"),
        }.items()
        if value is not None
    }


def _hf_job_output_type(operation: str) -> str:
    if operation == "submit":
        return "hf_job_submission"
    if operation == "schedule":
        return "hf_scheduled_job"
    if operation in HF_SCHEDULED_JOB_OPERATIONS:
        return "hf_scheduled_job_observation"
    return "hf_job_observation"


def _hf_job_event_type(operation: str) -> str:
    return {
        "submit": "agent.hf.job.submitted",
        "schedule": "agent.hf.job.scheduled",
        "status": "agent.hf.job.observed",
        "logs": "agent.hf.job.logs_captured",
        "cancel": "agent.hf.job.cancelled",
        "scheduled_list": "agent.hf.scheduled_jobs.listed",
        "scheduled_status": "agent.hf.scheduled_job.observed",
        "scheduled_suspend": "agent.hf.scheduled_job.suspended",
        "scheduled_resume": "agent.hf.scheduled_job.resumed",
        "scheduled_delete": "agent.hf.scheduled_job.deleted",
    }[operation]


def _sandbox_request_summary(arguments: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "operation": arguments.get("operation"),
        "sandbox_id": arguments.get("sandbox_id"),
        "image": arguments.get("image"),
        "hardware_flavor": arguments.get("hardware_flavor") or "cpu-basic",
        "timeout": arguments.get("timeout") or "30m",
        "command": _coerce_str_list(arguments.get("command")),
        "path": arguments.get("path"),
        "env_keys": sorted(str(key) for key in (arguments.get("env") or {}).keys())
        if isinstance(arguments.get("env") or {}, dict)
        else None,
    }
    if arguments.get("content") is not None:
        content = str(arguments.get("content"))
        summary["content_sha256"] = hashlib.sha256(content.encode("utf-8")).hexdigest()
        summary["content_size_bytes"] = len(content.encode("utf-8"))
    return {key: value for key, value in summary.items() if value is not None}


def _resolve_job_smoke_gate(
    context: AgentToolContext,
    run: ResearchRun,
    arguments: dict[str, Any],
) -> dict[str, Any]:
    if not _job_requires_smoke(arguments):
        return {"required": False}
    smoke_output_id = _optional_str(arguments.get("smoke_test_output_id"))
    skip_reason = _optional_str(arguments.get("skip_smoke_reason"))
    if not smoke_output_id and not skip_reason:
        raise ValueError(
            "hal_hf_job submit requires smoke_test_output_id or skip_smoke_reason "
            "for GPU/model-loading jobs"
        )
    if skip_reason:
        return {"required": True, "skipped": True, "reason": skip_reason}
    output = _resolve_smoke_output(context, run, smoke_output_id)
    status = _smoke_output_status(output)
    if status == "failed":
        raise ValueError(f"Smoke test output failed and cannot gate job submission: {smoke_output_id}")
    return {
        "required": True,
        "skipped": False,
        "smoke_test_output_id": output.id,
        "status": status,
    }


def _job_requires_smoke(arguments: dict[str, Any]) -> bool:
    hardware = str(arguments.get("hardware_flavor") or "cpu-basic").lower()
    if hardware and not hardware.startswith("cpu"):
        return True
    haystack = " ".join(
        [
            _optional_str(arguments.get("script")) or "",
            " ".join(_coerce_str_list(arguments.get("command")) or []),
            " ".join(_coerce_str_list(arguments.get("dependencies")) or []),
        ]
    ).lower()
    markers = (
        "torch",
        "cuda",
        "transformers",
        "trl",
        "accelerate",
        "peft",
        "model_name_or_path",
        "bf16",
        "fp16",
        "flash_attn",
        "flash-attn",
    )
    return any(marker in haystack for marker in markers)


def _resolve_smoke_output(
    context: AgentToolContext,
    run: ResearchRun,
    smoke_output_id: str | None,
) -> ResearchOutput:
    if not smoke_output_id:
        raise ValueError("smoke_test_output_id is required")
    output = _require_store(context).session.get(ResearchOutput, smoke_output_id)
    if output is None:
        raise ValueError(f"Smoke test output not found: {smoke_output_id}")
    if output.run_id != run.id:
        raise ValueError(f"Smoke test output belongs to a different run: {smoke_output_id}")
    if output.output_type != "hf_sandbox_smoke":
        raise ValueError(f"Output is not an HF sandbox smoke record: {smoke_output_id}")
    return output


def _smoke_output_status(output: ResearchOutput) -> str | None:
    if not output.content:
        return None
    try:
        payload = json.loads(output.content)
    except json.JSONDecodeError:
        return None
    return _smoke_status(payload.get("result"))


def _smoke_status(result: Any) -> str | None:
    if isinstance(result, dict):
        return _optional_str(result.get("status") or result.get("state"))
    return None


def _artifact_count(result: Any) -> int:
    if isinstance(result, dict):
        if isinstance(result.get("artifact_count"), int):
            return int(result["artifact_count"])
        if isinstance(result.get("artifacts"), list):
            return len(result["artifacts"])
    return 0


def _artifact_filename(artifact: dict[str, Any]) -> str:
    path = _optional_str(artifact.get("path"))
    if path:
        return _safe_object_key_part(path)
    uri = _optional_str(artifact.get("uri") or artifact.get("url"))
    if uri:
        parsed = urlsplit(uri)
        name = _optional_str(parsed.path.rsplit("/", 1)[-1])
        if name:
            return _safe_object_key_part(name)
    return "artifact.bin"


def _artifact_uri(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    for key in ("artifact_uri", "url", "job_url", "scheduled_job_url", "repo_url", "pr_url", "dashboard_url"):
        value = _optional_str(result.get(key))
        if value:
            return value
    return None


def _public_result_summary(result: Any) -> dict[str, Any]:
    if not isinstance(result, dict):
        return {"result": str(result)}
    public_keys = {
        "operation",
        "repo_id",
        "repo_type",
        "path",
        "patterns",
        "revision",
        "create_pr",
        "job_id",
        "scheduled_job_id",
        "scheduled_job_count",
        "schedule",
        "status",
        "stage",
        "url",
        "job_url",
        "scheduled_job_url",
        "repo_url",
        "pr_url",
        "dashboard_url",
        "artifact_uri",
        "artifact_count",
        "sandbox_id",
    }
    return {key: value for key, value in result.items() if key in public_keys}


def _required_arxiv_id(arguments: dict[str, Any]) -> str:
    arxiv_id = str(arguments.get("arxiv_id") or "").strip()
    if not arxiv_id:
        raise ValueError("hal_hf_papers requires arxiv_id for this operation")
    return arxiv_id.removeprefix("arxiv:")


def _coerce_items(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, list):
        return [item for item in value if isinstance(item, dict)]
    if isinstance(value, dict):
        for key in ("papers", "results", "data", "items"):
            items = value.get(key)
            if isinstance(items, list):
                return [item for item in items if isinstance(item, dict)]
        return [value]
    return []


def _paper_id(paper: dict[str, Any]) -> str | None:
    for key in ("id", "paperId", "paper_id", "arxivId", "arxiv_id"):
        value = _optional_str(paper.get(key))
        if value:
            value = value.removeprefix("arxiv:").split("/")[-1]
            if value:
                return value
    external_ids = paper.get("externalIds") or paper.get("external_ids") or {}
    if isinstance(external_ids, dict):
        for key in ("ArXiv", "arXiv", "arxiv"):
            value = _optional_str(external_ids.get(key))
            if value:
                return value.removeprefix("arxiv:")
    url = _optional_str(paper.get("url") or paper.get("paperUrl"))
    if url and "/papers/" in url:
        return url.rstrip("/").split("/papers/", 1)[-1]
    return None


def _stable_paper_key(paper: dict[str, Any]) -> str:
    title = _paper_title(paper) or "untitled"
    return hashlib.sha256(title.encode("utf-8")).hexdigest()[:16]


def _paper_title(paper: dict[str, Any]) -> str | None:
    return _optional_str(paper.get("title") or paper.get("name"))


def _paper_authors(paper: dict[str, Any]) -> list[str]:
    authors = paper.get("authors") or paper.get("authorNames") or paper.get("author_names") or []
    if isinstance(authors, str):
        return [authors]
    if isinstance(authors, list):
        result = []
        for author in authors:
            if isinstance(author, str):
                result.append(author)
            elif isinstance(author, dict):
                name = _optional_str(author.get("name") or author.get("full_name"))
                if name:
                    result.append(name)
        return result
    return []


def _optional_year(paper: dict[str, Any]) -> int | None:
    year = paper.get("year") or paper.get("publishedAt") or paper.get("published_at")
    if isinstance(year, int):
        return year
    if isinstance(year, str) and len(year) >= 4 and year[:4].isdigit():
        return int(year[:4])
    return None


def _paper_abstract(paper: dict[str, Any]) -> str | None:
    return _optional_str(paper.get("abstract") or paper.get("summary"))


def _paper_summary(paper: dict[str, Any]) -> str | None:
    return _optional_str(
        paper.get("summary")
        or paper.get("tldr")
        or paper.get("tl_dr")
        or paper.get("ai_summary")
    )


def _paper_findings(paper: dict[str, Any]) -> list[str]:
    findings = paper.get("findings")
    if isinstance(findings, list):
        return [str(item) for item in findings if str(item).strip()]
    summary = _paper_summary(paper) or _paper_abstract(paper)
    return [summary] if summary else []


def _paper_full_text(paper: dict[str, Any]) -> str | None:
    parts = []
    for label, value in (
        ("Title", _paper_title(paper)),
        ("Abstract", _paper_abstract(paper)),
        ("Summary", _paper_summary(paper)),
    ):
        if value:
            parts.append(f"{label}: {value}")
    return "\n\n".join(parts) or None


def _paper_url(paper: dict[str, Any], *, paper_id: str | None) -> str:
    url = _optional_str(paper.get("url") or paper.get("paperUrl") or paper.get("paper_url"))
    if url:
        return url
    if paper_id:
        return f"{HF_BASE}/papers/{paper_id}"
    return f"{HF_BASE}/papers"


def _paper_chunk_text(paper: dict[str, Any], document: Document) -> str | None:
    return _optional_str(_paper_full_text(paper) or document.full_text or document.abstract or document.summary)


def _paper_claim_text(paper: dict[str, Any], document: Document) -> str | None:
    summary = _paper_summary(paper) or document.summary or document.abstract
    if summary:
        return _truncate_text(summary, 500)
    if document.title:
        return f"HF paper discovered: {document.title}"
    return None


def _document_payload(document: Document) -> dict[str, Any]:
    return {
        "id": document.id,
        "title": document.title,
        "source_type": document.source_type,
        "source_identifier": document.source_identifier,
        "source_path": document.source_path,
    }


def _has_run_chunk(store: Any, document: Document, run: ResearchRun, content: str) -> bool:
    return _matching_run_chunk(store, document, run, content) is not None


def _matching_run_chunk(store: Any, document: Document, run: ResearchRun, content: str):
    text_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return (
        store.session.query(DocumentChunk)
        .filter_by(document_id=document.id, run_id=run.id, text_hash=text_hash)
        .one_or_none()
    )


def _next_chunk_index(document: Document) -> int:
    return len(list(document.chunks or []))


def _has_run_claim(store: Any, document: Document, run: ResearchRun, claim_text: str) -> bool:
    from hal9000.db.models import ExtractedClaim

    return (
        store.session.query(ExtractedClaim)
        .filter_by(document_id=document.id, run_id=run.id, claim_text=claim_text)
        .one_or_none()
        is not None
    )


def _json_content(payload: dict[str, Any]) -> str:
    content = json.dumps(payload, indent=2, sort_keys=True, default=str)
    return _truncate_text(content, MAX_OUTPUT_CHARS)


def _json_or_error(response: httpx.Response) -> Any:
    try:
        response.raise_for_status()
        return response.json()
    except Exception as exc:
        return {"error": str(exc), "status_code": response.status_code}


def _detect_dataset_config_split(
    splits: dict[str, Any],
    *,
    config: str | None,
    split: str | None,
) -> tuple[str, str]:
    if config and split:
        return config, split
    first = {}
    split_items = splits.get("splits") if isinstance(splits, dict) else None
    if isinstance(split_items, list) and split_items:
        first = split_items[0] if isinstance(split_items[0], dict) else {}
    return config or str(first.get("config") or "default"), split or str(first.get("split") or "train")


def _trim_first_rows(first_rows: Any, sample_rows: int) -> Any:
    if not isinstance(first_rows, dict):
        return first_rows
    rows = first_rows.get("rows")
    if isinstance(rows, list):
        trimmed = dict(first_rows)
        trimmed["rows"] = rows[:sample_rows]
        return trimmed
    return first_rows


def _doc_matches(content: str, *, query: str | None, limit: int) -> list[dict[str, Any]]:
    lines = content.splitlines()
    if not query:
        matches = [
            {"line": index + 1, "text": line.strip()}
            for index, line in enumerate(lines)
            if line.lstrip().startswith("#")
        ]
        return matches[:limit]
    query_lower = query.lower()
    matches = []
    for index, line in enumerate(lines):
        if query_lower in line.lower():
            start = max(0, index - 2)
            end = min(len(lines), index + 3)
            matches.append(
                {
                    "line": index + 1,
                    "text": line.strip(),
                    "snippet": "\n".join(lines[start:end]).strip(),
                }
            )
        if len(matches) >= limit:
            break
    if matches:
        return matches

    tokens = _query_tokens(query)
    if not tokens:
        return []
    scored = []
    for index, line in enumerate(lines):
        lower = line.lower()
        score = sum(1 for token in tokens if token in lower)
        if score:
            start = max(0, index - 2)
            end = min(len(lines), index + 3)
            scored.append(
                (
                    score,
                    {
                        "line": index + 1,
                        "text": line.strip(),
                        "snippet": "\n".join(lines[start:end]).strip(),
                    },
                )
            )
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item for _score, item in scored[:limit]]


def _query_tokens(query: str) -> list[str]:
    raw_tokens = re.findall(r"[A-Z]+(?=[A-Z][a-z]|\d|\b)|[A-Z]?[a-z]+|\d+", query)
    tokens = [token.lower() for token in raw_tokens if len(token) >= 3]
    for token in list(tokens):
        if token.endswith("config") and len(token) > len("config"):
            tokens.append(token.removesuffix("config"))
    return tokens


def _docs_markdown_url(url: str) -> str:
    if url.endswith(".md") or ".md?" in url:
        return url
    if url.startswith(HF_DOCS_BASE):
        return f"{url.rstrip('/')}.md"
    return url


def _owner_repo(repo: str, *, org: str | None = None) -> str:
    repo = repo.strip().strip("/")
    if "/" in repo:
        return repo
    return f"{org or 'huggingface'}/{repo}"


def _hub_repo_url(repo_id: str, repo_type: str = "model") -> str:
    if repo_type == "model":
        return f"{HF_BASE}/{repo_id}"
    return f"{HF_BASE}/{repo_type}s/{repo_id}"


def _looks_like_inline_python(script: str) -> bool:
    if "\n" in script:
        return True
    stripped = script.strip()
    return stripped.startswith(("import ", "from ", "def ", "class ", "print("))


def _job_info_payload(job: Any) -> dict[str, Any]:
    status = getattr(job, "status", None)
    stage = getattr(status, "stage", None) if status is not None else None
    return {
        "operation": "job_info",
        "job_id": _optional_str(getattr(job, "id", None)),
        "status": _optional_str(str(stage)) if stage is not None else None,
        "url": _optional_str(getattr(job, "url", None)),
        "job_url": _optional_str(getattr(job, "url", None)),
        "owner": _optional_str(getattr(getattr(job, "owner", None), "name", None)),
        "docker_image": _optional_str(getattr(job, "docker_image", None)),
        "flavor": _optional_str(getattr(job, "flavor", None)),
    }


def _scheduled_job_info_payload(job: Any) -> dict[str, Any]:
    if job is None:
        return {}
    if isinstance(job, dict):
        payload = dict(job)
        if "id" in payload and "scheduled_job_id" not in payload:
            payload["scheduled_job_id"] = _optional_str(payload.get("id"))
        if "url" in payload and "scheduled_job_url" not in payload:
            payload["scheduled_job_url"] = _optional_str(payload.get("url"))
        return {key: value for key, value in payload.items() if value is not None}
    status = getattr(job, "status", None)
    stage = getattr(status, "stage", None) if status is not None else None
    return {
        key: value
        for key, value in {
            "operation": "scheduled_job_info",
            "scheduled_job_id": _optional_str(getattr(job, "id", None)),
            "schedule": _optional_str(getattr(job, "schedule", None)),
            "status": _optional_str(str(stage)) if stage is not None else _optional_str(getattr(job, "status", None)),
            "url": _optional_str(getattr(job, "url", None)),
            "scheduled_job_url": _optional_str(getattr(job, "url", None)),
            "owner": _optional_str(getattr(getattr(job, "owner", None), "name", None)),
            "docker_image": _optional_str(getattr(job, "docker_image", None)),
            "flavor": _optional_str(getattr(job, "flavor", None)),
            "suspended": getattr(job, "suspended", None),
        }.items()
        if value is not None
    }


def _call_with_supported_kwargs(func: Any, *args: Any, **kwargs: Any) -> Any:
    filtered = {key: value for key, value in kwargs.items() if value is not None}
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return func(*args, **filtered)
    if any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values()):
        return func(*args, **filtered)
    accepted = {
        name
        for name, parameter in signature.parameters.items()
        if parameter.kind in {inspect.Parameter.POSITIONAL_OR_KEYWORD, inspect.Parameter.KEYWORD_ONLY}
    }
    return func(*args, **{key: value for key, value in filtered.items() if key in accepted})


def _looks_like_example_path(path: str) -> bool:
    lower = path.lower()
    if not lower.endswith((".py", ".ipynb", ".md", ".js", ".ts", ".tsx")):
        return False
    return any(
        lower.startswith(prefix)
        or f"/{prefix}" in lower
        or lower.startswith(f"docs/{prefix}")
        for prefix in ("examples/", "example/", "scripts/", "tutorials/", "notebooks/", "recipes/")
    )


def _slice_lines(content: str, *, line_start: int | None, line_end: int | None) -> str:
    lines = content.splitlines()
    if line_start is None and line_end is None:
        return "\n".join(lines[:300])
    start = max(1, line_start or 1)
    end = min(len(lines), line_end or len(lines))
    return "\n".join(lines[start - 1 : end])


def _truncate_text(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[:limit]}\n\n[truncated]"
