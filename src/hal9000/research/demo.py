"""Demo data seeding for HAL full-team walkthroughs."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any

from hal9000.db.models import Document
from hal9000.db.store import ClaimEvidence, ResearchStore
from hal9000.research.annotations import ReviewAnnotationService
from hal9000.research.collaboration import CollaborationService
from hal9000.research.graph import ResearchGraphService
from hal9000.vector.embeddings import FakeEmbeddingProvider
from hal9000.vector.store import VectorRepository


@dataclass(frozen=True)
class DemoSeedResult:
    """Result of creating a leadership-demo dataset."""

    project_slug: str
    run_id: str
    document_id: str
    chunk_ids: list[str]
    claim_ids: list[str]
    output_ids: list[str]
    reviewer_email: str
    contributor_email: str
    notification_ids: list[str]
    collection_slug: str
    saved_search_name: str
    shared_view_slug: str
    sheets_targets: list[str]
    slack_commands: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-friendly result."""
        return asdict(self)


class DemoSeedService:
    """Create a complete demo loop from memory through review and audit."""

    def __init__(self, store: ResearchStore):
        """Initialize with the shared research store."""
        self.store = store
        self.session = store.session

    def seed(
        self,
        project_slug: str = "hal-demo",
        project_name: str = "HAL 9000 Team Demo",
        owner_email: str = "bwisk@arc-pbc.com",
        reviewer_email: str = "reviewer@example.com",
        contributor_email: str = "researcher@example.com",
    ) -> DemoSeedResult:
        """Seed a fresh staged demo run and supporting collaboration records."""
        project = self.store.get_project_by_slug(project_slug)
        if project is None:
            project = self.store.create_project(
                name=project_name,
                slug=project_slug,
                owner=owner_email,
                description="Seeded project for the HAL full-team demo.",
                visibility="firm",
            )

        reviewer = _ensure_user(self.store, reviewer_email, "Demo Reviewer")
        contributor = _ensure_user(self.store, contributor_email, "Demo Researcher")
        owner = _ensure_user(self.store, owner_email, "Demo Owner", global_role="admin")
        team = self.store.get_team_by_slug("hal-demo-reviewers") or self.store.create_team(
            "hal-demo-reviewers",
            name="HAL Demo Reviewers",
        )
        self.store.add_team_member(team, reviewer)
        self.store.add_team_member(team, owner, role="owner")
        self.store.grant_project_access(project, "team", team.id, "reviewer", granted_by=owner_email)
        self.store.grant_project_access(
            project,
            "user",
            contributor.id,
            "contributor",
            granted_by=owner_email,
        )

        run = self.store.create_run(
            objective=(
                "Demonstrate HAL's firm-wide research OS loop for source-backed "
                "single-crystal superalloy creep evidence."
            ),
            project=project,
            initiated_by=contributor_email,
            budget={"max_papers": 3, "max_downloads": 2, "max_llm_calls": 4},
            tool_policy={"allowed_tools": ["semantic_search", "review", "slack", "sheets"]},
        )
        self.store.append_run_event(
            run,
            "run.queued",
            message="Demo run queued for the full-team walkthrough.",
            actor=contributor_email,
            payload={"source": "demo-seed"},
        )
        self.store.update_run_status(
            run,
            "running",
            message="Demo worker started.",
            actor="hal-demo-seed",
        )

        tool_call = self.store.start_tool_call(
            run,
            "semantic_search",
            actor="hal-demo-seed",
            input={"query": "single crystal superalloy creep rupture evidence"},
        )
        self.store.finish_tool_call(
            tool_call,
            status="completed",
            output={"results": 2, "cost_usd": 0.0},
            cost_usd=0.0,
        )
        self.store.append_run_event(
            run,
            "acquisition.paper.processed",
            message="Demo source paper processed and chunked.",
            actor="hal-demo-seed",
            payload={"title": "Directional coarsening and creep in single crystal superalloys"},
        )

        document = _create_demo_document(self.store, run.id)
        chunk = self.store.add_document_chunk(
            document,
            content=(
                "Single crystal nickel superalloys show improved high-temperature "
                "creep resistance when gamma prime morphology remains stable under "
                "load. Directional coarsening can either reduce or preserve rupture "
                "life depending on temperature, stress, and alloy chemistry."
            ),
            chunk_index=0,
            run=run,
            char_start=0,
            char_end=292,
            token_count=44,
            extraction_metadata={
                "figures": [
                    {
                        "label": "Figure 2",
                        "caption": "Gamma prime raft morphology after 1000 hour creep exposure.",
                        "page": 5,
                    }
                ],
                "tables": [
                    {
                        "label": "Table 1",
                        "caption": "Rupture life across stress and temperature conditions.",
                        "page": 7,
                    }
                ],
            },
        )
        VectorRepository(self.session).embed_and_store_chunk(
            chunk,
            FakeEmbeddingProvider(),
            vector_uri=f"hal-demo://vectors/{chunk.id}",
        )

        claims = [
            self.store.add_claim_with_evidence(
                document,
                ClaimEvidence(
                    claim_text=(
                        "Stable gamma prime morphology is associated with improved creep "
                        "rupture performance in single crystal nickel superalloys."
                    ),
                    evidence_text="The source reports longer rupture life where gamma prime morphology remains stable.",
                    quote="Stable gamma prime morphology correlated with longer creep rupture life.",
                    locator="p. 7, Table 1",
                    source_url="https://example.com/hal-demo/superalloy-creep",
                    claim_type="finding",
                    confidence=0.86,
                    provenance={
                        "figures": [{"label": "Figure 2", "page": 5}],
                        "tables": [{"label": "Table 1", "page": 7}],
                    },
                ),
                chunk=chunk,
                run=run,
            ),
            self.store.add_claim_with_evidence(
                document,
                ClaimEvidence(
                    claim_text=(
                        "Rupture life comparisons require stress and temperature normalization "
                        "before cross-paper ranking."
                    ),
                    evidence_text="The paper compares rupture life at multiple stress-temperature points.",
                    quote="Rupture life varied strongly with stress and exposure temperature.",
                    locator="p. 8",
                    source_url="https://example.com/hal-demo/superalloy-creep",
                    claim_type="caveat",
                    confidence=0.78,
                ),
                chunk=chunk,
                run=run,
            ),
        ]

        outputs = _stage_demo_outputs(self.store, project, run, claims, contributor_email)
        self.store.update_run_status(
            run,
            "staged",
            message="Demo outputs staged for review.",
            actor="hal-demo-seed",
            payload={"output_ids": [output.id for output in outputs]},
        )

        ReviewAnnotationService(self.store).add_annotation(
            "output",
            outputs[0].id,
            body="Demo note: ask the team to inspect citation coverage and audit history.",
            author_email=reviewer_email,
            annotation_type="comment",
        )

        collaboration = CollaborationService(self.store)
        collection = collaboration.get_collection(project, "full-team-demo")
        if collection is None:
            collection = collaboration.create_collection(
                project,
                name="Full Team Demo",
                owner_email=owner_email,
            )
        collaboration.add_collection_item(
            collection,
            target_type="output",
            target_id=outputs[0].id,
            note="Use this source-backed brief in the live walkthrough.",
            added_by=owner_email,
        )
        saved_search = collaboration.save_search(
            project,
            name="Demo Creep Memory",
            query_text="single crystal superalloy creep rupture evidence",
            target="memory",
            owner_email=owner_email,
        )
        shared_view = collaboration.create_shared_view(
            project,
            name="Demo Review Dashboard",
            view_type="review_queue",
            config={"sections": ["queue", "audit", "sheets", "slack"]},
            owner_email=owner_email,
        )
        notifications = []
        for channel in ("in_app", "slack", "sheets"):
            notifications.extend(
                collaboration.create_review_ready_notifications(
                    run,
                    recipients=[reviewer_email],
                    channel=channel,
                )
            )

        ResearchGraphService(self.store).add_edge(
            source_type="claim",
            source_id=claims[0].id,
            relationship_type="supports",
            target_type="output",
            target_id=outputs[0].id,
            project=project,
            run=run,
            confidence=0.86,
            created_by="hal-demo-seed",
            evidence={"reason": "The demo brief directly cites this claim."},
        )

        self.store.record_audit_event(
            "demo.seeded",
            "run",
            run.id,
            project=project,
            run=run,
            actor_email=owner_email,
            payload={
                "reviewer_email": reviewer_email,
                "contributor_email": contributor_email,
                "output_ids": [output.id for output in outputs],
            },
        )

        return DemoSeedResult(
            project_slug=project.slug,
            run_id=run.id,
            document_id=document.id,
            chunk_ids=[chunk.id],
            claim_ids=[claim.id for claim in claims],
            output_ids=[output.id for output in outputs],
            reviewer_email=reviewer_email,
            contributor_email=contributor_email,
            notification_ids=[notification.id for notification in notifications],
            collection_slug=collection.slug,
            saved_search_name=saved_search.name,
            shared_view_slug=shared_view.slug,
            sheets_targets=["runs", "review_queue", "outputs", "audit"],
            slack_commands=[
                f"review {project.slug}",
                f"status {run.id}",
                f"promote {run.id} Ready for firm sharing.",
            ],
        )


def demo_seed_payload(result: DemoSeedResult) -> dict[str, Any]:
    """Return a JSON-friendly seed result."""
    return result.to_dict()


def _ensure_user(
    store: ResearchStore,
    email: str,
    display_name: str,
    global_role: str = "member",
):
    user = store.get_user_by_email(email)
    if user is None:
        return store.create_user(email, display_name=display_name, global_role=global_role)
    user.display_name = user.display_name or display_name
    if global_role == "admin":
        user.global_role = "admin"
    user.status = "active"
    store.session.flush()
    return user


def _create_demo_document(store: ResearchStore, run_id: str) -> Document:
    file_hash = hashlib.sha256(f"hal-demo:{run_id}".encode()).hexdigest()
    document = Document(
        source_path=f"hal-demo://sources/{run_id}/superalloy-creep.pdf",
        source_type="demo",
        file_hash=file_hash,
        title="Directional coarsening and creep in single crystal superalloys",
        authors=json.dumps(["HAL Demo Source Team"]),
        year=2026,
        doi=f"10.0000/hal-demo.{run_id[:8]}",
        abstract=(
            "Demo source describing creep rupture evidence, gamma prime morphology, "
            "and normalized comparison caveats for nickel superalloys."
        ),
        full_text="Demo full text for HAL memory search and source-rich output rendering.",
        status="completed",
        page_count=9,
        source_identifier=f"doi:10.0000/hal-demo.{run_id[:8]}",
        source_version="v1",
        version_group_key="hal-demo-superalloy-creep",
        normalized_doi=f"10.0000/hal-demo.{run_id[:8]}",
        citation_key=f"haldemo{run_id[:8]}",
        normalized_citation=(
            "HAL Demo Source Team (2026). Directional coarsening and creep in "
            "single crystal superalloys."
        ),
        source_quality_score=0.82,
        source_quality_label="high",
        source_quality_json=json.dumps(
            {
                "allowed_use": True,
                "compliance_reviewed": True,
                "license": "HAL demo synthetic source",
            },
            sort_keys=True,
        ),
    )
    store.session.add(document)
    store.session.flush()
    return document


def _stage_demo_outputs(store, project, run, claims, contributor_email: str):
    citation_1 = f"[C1:{claims[0].id[:8]}]"
    citation_2 = f"[C2:{claims[1].id[:8]}]"
    brief = store.stage_output(
        "Demo Source-Backed Research Brief",
        "research_brief",
        project=project,
        run=run,
        created_by=contributor_email,
        source={"claim_ids": [claim.id for claim in claims]},
        content=(
            "# Demo Source-Backed Research Brief\n\n"
            f"- {claims[0].claim_text} {citation_1}\n"
            f"- {claims[1].claim_text} {citation_2}\n\n"
            "## Demo Talking Point\n\n"
            "HAL can move from shared memory to staged outputs, Slack review, "
            "Sheets dashboards, and an audit trail without leaving the canonical store."
        ),
    )
    evidence_table = store.stage_output(
        "Demo Evidence Table",
        "evidence_table",
        project=project,
        run=run,
        created_by=contributor_email,
        source={"claim_ids": [claim.id for claim in claims]},
        content=(
            "| Claim | Evidence | Citation |\n"
            "| --- | --- | --- |\n"
            f"| Gamma prime morphology supports creep performance | Table 1 rupture life comparison | {citation_1} |\n"
            f"| Normalize rupture comparisons | Multi-condition stress/temperature caveat | {citation_2} |"
        ),
    )
    adam_context = store.stage_output(
        "Demo ADAM Experiment Context",
        "adam_context",
        project=project,
        run=run,
        created_by=contributor_email,
        format="json",
        source={"claim_ids": [claim.id for claim in claims]},
        content=json.dumps(
            {
                "context_id": f"hal-demo-{run.id}",
                "material_system": "single crystal nickel superalloys",
                "hypothesis": (
                    "Gamma prime morphology stability predicts improved creep rupture performance."
                ),
                "evidence_claim_ids": [claim.id for claim in claims],
                "recommended_next_experiment": (
                    "Compare normalized rupture life across two stress-temperature envelopes."
                ),
            },
            indent=2,
            sort_keys=True,
        ),
    )
    return [brief, evidence_table, adam_context]
