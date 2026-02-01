# HAL-9000 → ADAM Research Assistant Refactoring Plan

## Executive Summary

Transform HAL-9000 from a CLI-based literature processing tool into a **gateway-orchestrated research assistant** inspired by OpenClaw's architecture, purpose-built for materials science research and ADAM platform integration.

**Goal**: Create a system that ingests research, synthesizes knowledge, and outputs structured prompts and context windows to drive ADAM's autonomous discovery-to-production workflow.

---

## Part 1: Architecture Comparison & Vision

### Current HAL-9000 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI (Click)                              │
├─────────────────────────────────────────────────────────────────┤
│  scan │ process │ batch │ acquire │ init-vault │ status        │
├───────┴─────────┴───────┴─────────┴────────────┴───────────────┤
│                                                                  │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐        │
│  │ Ingest   │  │   RLM    │  │ Classify │  │ Obsidian │        │
│  │ (PDF)    │→ │Processor │→ │          │→ │ Export   │        │
│  └──────────┘  └──────────┘  └──────────┘  └──────────┘        │
│       ↑                                          ↓              │
│  ┌──────────┐                            ┌──────────────┐       │
│  │Acquisition│                           │ ADAM Context │       │
│  │ Pipeline │                            │   Builder    │       │
│  └──────────┘                            └──────────────┘       │
│                                                                  │
│                    ┌─────────────────┐                          │
│                    │ SQLite Database │                          │
│                    └─────────────────┘                          │
└─────────────────────────────────────────────────────────────────┘
```

**Strengths**: RLM chunking, materials science taxonomy, ADAM context generation foundation
**Limitations**: CLI-only, no streaming, no multi-channel, no real-time orchestration

### Target Architecture (OpenClaw-Inspired)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           HAL-9000 Gateway                                   │
│                      (WebSocket: ws://127.0.0.1:9000)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐        │
│  │   Session   │  │   Routing   │  │    Tool     │  │   Event     │        │
│  │   Manager   │  │   Engine    │  │  Executor   │  │  Streamer   │        │
│  └─────────────┘  └─────────────┘  └─────────────┘  └─────────────┘        │
│         │                │                │                │                │
├─────────┴────────────────┴────────────────┴────────────────┴────────────────┤
│                              Skill Registry                                  │
├──────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐    │
│  │  Literature  │  │  Materials   │  │   ADAM       │  │  Knowledge   │    │
│  │    Skill     │  │    Skill     │  │ Orchestrator │  │    Graph     │    │
│  │              │  │              │  │    Skill     │  │    Skill     │    │
│  │ • Search     │  │ • Property   │  │              │  │              │    │
│  │ • Ingest     │  │   Lookup     │  │ • Prompt Gen │  │ • Obsidian   │    │
│  │ • RLM Parse  │  │ • Structure  │  │ • Context    │  │ • Neo4j      │    │
│  │ • Summarize  │  │   Predict    │  │   Windows    │  │ • Semantic   │    │
│  │ • Cite       │  │ • Process    │  │ • Cell Route │  │   Search     │    │
│  │              │  │   Match      │  │ • Feedback   │  │              │    │
│  └──────────────┘  └──────────────┘  └──────────────┘  └──────────────┘    │
│                                                                              │
├──────────────────────────────────────────────────────────────────────────────┤
│                              Channel Adapters                                │
├────────┬────────┬────────┬────────┬────────┬────────┬────────┬──────────────┤
│  CLI   │  Web   │ Slack  │ Teams  │  API   │ ADAM   │ Jupyter│   Matrix     │
│        │  UI    │        │        │        │ Direct │        │              │
└────────┴────────┴────────┴────────┴────────┴────────┴────────┴──────────────┘
         │         │                           │
         ▼         ▼                           ▼
┌─────────────┐ ┌─────────────────┐  ┌─────────────────────────────────────┐
│ Researchers │ │ Research Canvas │  │         ADAM Platform               │
│ & Engineers │ │  (Visual UI)    │  │  ┌─────────────────────────────┐   │
└─────────────┘ └─────────────────┘  │  │       Production Cells       │   │
                                      │  ├─────────┬─────────┬─────────┤   │
                                      │  │  Metal  │ Ceramic │ Polymer │   │
                                      │  │  Cells  │  Cells  │  Cells  │   │
                                      │  └─────────┴─────────┴─────────┘   │
                                      └─────────────────────────────────────┘
```

---

## Part 2: Phased Implementation Plan

### Phase 1: Gateway Foundation (Weeks 1-3)

#### 1.1 Core Gateway Implementation

**New Module**: `src/hal9000/gateway/`

```
gateway/
├── __init__.py
├── server.py          # WebSocket server (asyncio + websockets)
├── session.py         # Session state management
├── router.py          # Message routing to skills
├── events.py          # Event types and streaming
└── protocol.py        # Message protocol definitions
```

**Key Components**:

```python
# gateway/protocol.py
from enum import Enum
from pydantic import BaseModel
from typing import Any, Optional
from datetime import datetime

class MessageType(str, Enum):
    # Client → Gateway
    COMMAND = "command"
    QUERY = "query"
    TOOL_CALL = "tool_call"
    FEEDBACK = "feedback"

    # Gateway → Client
    RESPONSE = "response"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    TOOL_RESULT = "tool_result"
    ERROR = "error"

    # ADAM-specific
    ADAM_PROMPT = "adam_prompt"
    ADAM_CONTEXT = "adam_context"
    ADAM_FEEDBACK = "adam_feedback"

class GatewayMessage(BaseModel):
    id: str
    type: MessageType
    session_id: str
    timestamp: datetime
    payload: dict[str, Any]
    metadata: Optional[dict[str, Any]] = None

class ADAMPromptPayload(BaseModel):
    """Structured prompt for ADAM platform"""
    prompt_id: str
    prompt_type: str  # discovery, synthesis, characterization, production
    target_cell: Optional[str]  # metal, ceramic, polymer
    context_window: dict[str, Any]
    priority: str
    constraints: list[str]
    expected_outputs: list[str]
```

```python
# gateway/server.py
import asyncio
import websockets
from typing import Callable

class HALGateway:
    def __init__(self, host: str = "127.0.0.1", port: int = 9000):
        self.host = host
        self.port = port
        self.sessions: dict[str, Session] = {}
        self.skill_registry: SkillRegistry = SkillRegistry()
        self.router: Router = Router(self.skill_registry)

    async def start(self):
        async with websockets.serve(self.handle_connection, self.host, self.port):
            await asyncio.Future()  # Run forever

    async def handle_connection(self, websocket):
        session = await self.create_session(websocket)
        try:
            async for message in websocket:
                response = await self.router.route(session, message)
                await self.stream_response(websocket, response)
        finally:
            await self.cleanup_session(session)

    async def stream_response(self, websocket, response_generator):
        """Stream responses chunk by chunk (OpenClaw-style)"""
        async for chunk in response_generator:
            await websocket.send(chunk.model_dump_json())
```

#### 1.2 Session Management

```python
# gateway/session.py
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import uuid

@dataclass
class ResearchContext:
    """Accumulated research context for a session"""
    documents_analyzed: list[str] = field(default_factory=list)
    extracted_knowledge: dict[str, Any] = field(default_factory=dict)
    materials_of_interest: list[str] = field(default_factory=list)
    active_hypotheses: list[dict] = field(default_factory=list)
    adam_interactions: list[dict] = field(default_factory=list)

@dataclass
class Session:
    id: str
    channel: str  # cli, web, slack, adam_direct
    created_at: datetime
    user_id: Optional[str] = None
    context: ResearchContext = field(default_factory=ResearchContext)
    conversation_history: list[dict] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)

    def to_context_window(self) -> dict:
        """Export session state as ADAM context window"""
        return {
            "session_id": self.id,
            "research_context": {
                "documents": self.context.documents_analyzed,
                "knowledge": self.context.extracted_knowledge,
                "materials": self.context.materials_of_interest,
                "hypotheses": self.context.active_hypotheses
            },
            "conversation_summary": self._summarize_conversation(),
            "pending_experiments": self._extract_pending_experiments()
        }
```

#### 1.3 Migrate Existing Functionality

Convert existing CLI commands to gateway-routable operations:

| CLI Command | Gateway Operation | Skill |
|-------------|-------------------|-------|
| `hal scan` | `literature.scan` | LiteratureSkill |
| `hal process` | `literature.process` | LiteratureSkill |
| `hal batch` | `literature.batch` | LiteratureSkill |
| `hal acquire` | `literature.acquire` | LiteratureSkill |
| `hal init-vault` | `knowledge.init_vault` | KnowledgeGraphSkill |
| `hal status` | `system.status` | SystemSkill |

---

### Phase 2: Skill System (Weeks 4-6)

#### 2.1 Skill Framework

**New Module**: `src/hal9000/skills/`

```
skills/
├── __init__.py
├── base.py            # Abstract skill interface
├── registry.py        # Skill discovery and registration
├── executor.py        # Skill execution engine
│
├── literature/        # Literature research skill
│   ├── __init__.py
│   ├── skill.py
│   ├── tools.py
│   └── prompts.py
│
├── materials/         # Materials science skill
│   ├── __init__.py
│   ├── skill.py
│   ├── property_lookup.py
│   ├── structure_predict.py
│   └── process_match.py
│
├── adam/              # ADAM orchestration skill
│   ├── __init__.py
│   ├── skill.py
│   ├── prompt_generator.py
│   ├── context_builder.py
│   ├── cell_router.py
│   └── feedback_handler.py
│
└── knowledge/         # Knowledge graph skill
    ├── __init__.py
    ├── skill.py
    ├── obsidian.py
    ├── neo4j.py
    └── semantic.py
```

```python
# skills/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator, Any
from pydantic import BaseModel

class ToolDefinition(BaseModel):
    name: str
    description: str
    parameters: dict[str, Any]
    returns: dict[str, Any]

class SkillManifest(BaseModel):
    name: str
    version: str
    description: str
    tools: list[ToolDefinition]
    required_capabilities: list[str]
    adam_compatible: bool = False

class BaseSkill(ABC):
    @property
    @abstractmethod
    def manifest(self) -> SkillManifest:
        pass

    @abstractmethod
    async def execute(
        self,
        tool_name: str,
        params: dict,
        session: "Session"
    ) -> AsyncGenerator[dict, None]:
        """Execute a tool, yielding streaming results"""
        pass

    def get_adam_tools(self) -> list[ToolDefinition]:
        """Return tools that can generate ADAM prompts"""
        return [t for t in self.manifest.tools if t.name.startswith("adam_")]
```

#### 2.2 ADAM Orchestrator Skill (Core Innovation)

```python
# skills/adam/skill.py
from ..base import BaseSkill, SkillManifest, ToolDefinition

class ADAMOrchestratorSkill(BaseSkill):
    """
    Core skill for generating ADAM platform prompts and context windows.

    This skill transforms research insights into actionable instructions
    for the autonomous discovery-to-production pipeline.
    """

    @property
    def manifest(self) -> SkillManifest:
        return SkillManifest(
            name="adam_orchestrator",
            version="1.0.0",
            description="Generate prompts and context windows for ADAM platform",
            adam_compatible=True,
            tools=[
                ToolDefinition(
                    name="generate_discovery_prompt",
                    description="Generate a materials discovery prompt for ADAM",
                    parameters={
                        "research_goal": "str - High-level research objective",
                        "material_class": "str - Target material class",
                        "constraints": "list[str] - Process/material constraints",
                        "prior_knowledge": "Optional[str] - Session context to include"
                    },
                    returns={"adam_prompt": "ADAMPrompt", "context_window": "dict"}
                ),
                ToolDefinition(
                    name="generate_synthesis_prompt",
                    description="Generate a synthesis/fabrication prompt",
                    parameters={
                        "target_material": "str - Material to synthesize",
                        "target_properties": "dict - Desired properties",
                        "available_precursors": "list[str]",
                        "cell_type": "str - metal|ceramic|polymer"
                    },
                    returns={"adam_prompt": "ADAMPrompt", "process_parameters": "dict"}
                ),
                ToolDefinition(
                    name="generate_characterization_prompt",
                    description="Generate characterization experiment prompt",
                    parameters={
                        "sample_description": "str",
                        "properties_to_measure": "list[str]",
                        "available_instruments": "list[str]"
                    },
                    returns={"adam_prompt": "ADAMPrompt", "measurement_plan": "dict"}
                ),
                ToolDefinition(
                    name="build_context_window",
                    description="Build comprehensive context window from session",
                    parameters={
                        "session_id": "str",
                        "include_literature": "bool",
                        "include_experiments": "bool",
                        "window_size": "int - Max tokens"
                    },
                    returns={"context_window": "dict", "token_count": "int"}
                ),
                ToolDefinition(
                    name="route_to_cell",
                    description="Determine optimal production cell for task",
                    parameters={
                        "material_type": "str",
                        "process_requirements": "list[str]",
                        "volume": "str - prototype|batch|production"
                    },
                    returns={"cell_assignment": "str", "rationale": "str"}
                ),
                ToolDefinition(
                    name="process_adam_feedback",
                    description="Process feedback from ADAM execution",
                    parameters={
                        "prompt_id": "str",
                        "execution_results": "dict",
                        "success": "bool"
                    },
                    returns={"updated_context": "dict", "next_steps": "list[str]"}
                )
            ]
        )
```

#### 2.3 Prompt Generation Engine

```python
# skills/adam/prompt_generator.py
from typing import Optional
from pydantic import BaseModel
from enum import Enum

class CellType(str, Enum):
    METAL = "metal"
    CERAMIC = "ceramic"
    POLYMER = "polymer"
    HYBRID = "hybrid"

class PromptType(str, Enum):
    DISCOVERY = "discovery"
    SYNTHESIS = "synthesis"
    CHARACTERIZATION = "characterization"
    OPTIMIZATION = "optimization"
    SCALE_UP = "scale_up"
    PRODUCTION = "production"

class ADAMPrompt(BaseModel):
    """Structured prompt for ADAM platform consumption"""
    prompt_id: str
    prompt_type: PromptType

    # Core instruction
    objective: str
    detailed_instructions: str

    # Context
    context_window: dict  # Full context for LLM driving ADAM
    literature_support: list[dict]  # Relevant papers/findings

    # Constraints and parameters
    material_constraints: list[str]
    process_constraints: list[str]
    safety_constraints: list[str]

    # Routing
    target_cell: Optional[CellType]
    cell_capabilities_required: list[str]

    # Expected outcomes
    success_criteria: list[str]
    expected_outputs: list[str]
    measurement_requirements: list[str]

    # Metadata
    priority: str  # critical, high, medium, low
    estimated_duration: Optional[str]
    depends_on: list[str]  # Other prompt IDs

class PromptGenerator:
    """
    Generates structured ADAM prompts from research context.

    Uses Claude to synthesize research findings into actionable
    experimental instructions.
    """

    DISCOVERY_TEMPLATE = """
    You are generating an experimental discovery prompt for ADAM, an autonomous
    materials science platform. Based on the research context provided, create
    a structured experimental plan.

    RESEARCH CONTEXT:
    {context_window}

    RESEARCH GOAL:
    {research_goal}

    MATERIAL CLASS:
    {material_class}

    CONSTRAINTS:
    {constraints}

    Generate a detailed experimental discovery prompt that includes:
    1. Clear objective statement
    2. Specific experimental steps
    3. Material specifications
    4. Process parameters to explore
    5. Success criteria
    6. Safety considerations

    Output as structured JSON matching the ADAMPrompt schema.
    """

    async def generate_discovery_prompt(
        self,
        research_goal: str,
        material_class: str,
        constraints: list[str],
        session: "Session"
    ) -> ADAMPrompt:
        # Build context window from session
        context = session.to_context_window()

        # Generate via Claude
        response = await self.llm.generate(
            self.DISCOVERY_TEMPLATE.format(
                context_window=context,
                research_goal=research_goal,
                material_class=material_class,
                constraints=constraints
            )
        )

        # Parse and validate
        return ADAMPrompt.model_validate_json(response)
```

#### 2.4 Context Window Builder

```python
# skills/adam/context_builder.py
from typing import Optional
from dataclasses import dataclass

@dataclass
class ContextWindow:
    """
    Optimized context window for ADAM LLM consumption.

    Structured to provide maximum relevant information within token limits.
    """
    # Session identity
    session_summary: str
    research_objective: str

    # Literature context
    relevant_papers: list[dict]  # title, key_findings, methods
    extracted_knowledge: dict    # Aggregated RLM results

    # Materials context
    materials_of_interest: list[dict]
    known_properties: dict
    structure_predictions: list[dict]

    # Experimental context
    prior_experiments: list[dict]
    successful_approaches: list[str]
    failed_approaches: list[str]

    # ADAM state
    available_cells: list[dict]
    cell_capabilities: dict
    active_processes: list[dict]

    # Constraints
    budget_remaining: Optional[float]
    time_constraints: Optional[str]
    material_inventory: dict

    def to_prompt_context(self, max_tokens: int = 100000) -> str:
        """Serialize to optimized string for LLM context"""
        # Priority-ordered sections
        sections = [
            ("OBJECTIVE", self.research_objective),
            ("KEY FINDINGS", self._format_findings()),
            ("MATERIALS", self._format_materials()),
            ("PRIOR EXPERIMENTS", self._format_experiments()),
            ("AVAILABLE RESOURCES", self._format_resources()),
            ("CONSTRAINTS", self._format_constraints()),
        ]

        result = []
        token_count = 0

        for header, content in sections:
            section_text = f"\n## {header}\n{content}\n"
            section_tokens = self._estimate_tokens(section_text)

            if token_count + section_tokens > max_tokens:
                # Truncate this section
                remaining = max_tokens - token_count
                section_text = self._truncate_to_tokens(section_text, remaining)

            result.append(section_text)
            token_count += section_tokens

            if token_count >= max_tokens:
                break

        return "\n".join(result)

class ContextWindowBuilder:
    """Builds optimized context windows from session state"""

    def __init__(self, session: "Session", db: "Database"):
        self.session = session
        self.db = db
        self.rlm_processor = RLMProcessor()

    async def build(
        self,
        include_literature: bool = True,
        include_experiments: bool = True,
        include_adam_state: bool = True,
        max_tokens: int = 100000
    ) -> ContextWindow:
        """Build comprehensive context window"""

        context = ContextWindow(
            session_summary=self._summarize_session(),
            research_objective=self.session.context.get("objective", "")
        )

        if include_literature:
            # Get relevant documents from session
            doc_ids = self.session.context.documents_analyzed
            docs = await self.db.get_documents(doc_ids)

            # Use RLM to extract most relevant findings
            context.relevant_papers = [
                {
                    "title": d.title,
                    "key_findings": d.rlm_results.get("findings", [])[:5],
                    "methods": d.rlm_results.get("methods", [])[:3]
                }
                for d in docs
            ]
            context.extracted_knowledge = self._aggregate_knowledge(docs)

        if include_experiments:
            context.prior_experiments = await self._get_experiment_history()
            context.successful_approaches = self._extract_successes()
            context.failed_approaches = self._extract_failures()

        if include_adam_state:
            context.available_cells = await self._get_cell_status()
            context.cell_capabilities = await self._get_cell_capabilities()
            context.material_inventory = await self._get_inventory()

        return context
```

---

### Phase 3: Channel Adapters (Weeks 7-9)

#### 3.1 Channel Framework

```python
# channels/base.py
from abc import ABC, abstractmethod
from typing import AsyncGenerator

class ChannelAdapter(ABC):
    """Base class for communication channel adapters"""

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def connect(self) -> None:
        pass

    @abstractmethod
    async def receive(self) -> AsyncGenerator[dict, None]:
        """Receive messages from channel"""
        pass

    @abstractmethod
    async def send(self, message: dict) -> None:
        """Send message to channel"""
        pass

    @abstractmethod
    async def stream(self, generator: AsyncGenerator) -> None:
        """Stream response chunks to channel"""
        pass
```

#### 3.2 Channel Implementations

| Channel | Purpose | Priority |
|---------|---------|----------|
| `CLIChannel` | Backward-compatible CLI interface | P0 |
| `WebChannel` | Research canvas web UI | P0 |
| `ADAMChannel` | Direct ADAM platform integration | P0 |
| `SlackChannel` | Team collaboration | P1 |
| `JupyterChannel` | Notebook integration | P1 |
| `APIChannel` | Programmatic access | P1 |
| `TeamsChannel` | Enterprise integration | P2 |

#### 3.3 ADAM Direct Channel

```python
# channels/adam.py
class ADAMChannel(ChannelAdapter):
    """
    Direct integration with ADAM platform.

    Handles bidirectional communication:
    - Sends prompts/context windows to ADAM
    - Receives execution feedback
    - Streams status updates
    """

    name = "adam_direct"

    def __init__(self, adam_endpoint: str, auth_token: str):
        self.endpoint = adam_endpoint
        self.auth = auth_token
        self.ws: Optional[WebSocket] = None

    async def send_prompt(self, prompt: ADAMPrompt) -> str:
        """Send structured prompt to ADAM, return execution ID"""
        message = {
            "type": "execute_prompt",
            "prompt": prompt.model_dump(),
            "context_window": prompt.context_window
        }
        await self.ws.send(json.dumps(message))

        # Wait for acknowledgment
        response = await self.ws.recv()
        return json.loads(response)["execution_id"]

    async def receive_feedback(self) -> AsyncGenerator[dict, None]:
        """Stream feedback from ADAM execution"""
        async for message in self.ws:
            data = json.loads(message)
            if data["type"] == "execution_update":
                yield data
            elif data["type"] == "execution_complete":
                yield data
                break
```

---

### Phase 4: Research Canvas UI (Weeks 10-12)

#### 4.1 Web Interface Architecture

```
ui/
├── package.json
├── vite.config.ts
├── tailwind.config.js
│
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   │
│   ├── components/
│   │   ├── Canvas/
│   │   │   ├── ResearchCanvas.tsx      # Main canvas component
│   │   │   ├── NodeTypes/
│   │   │   │   ├── PaperNode.tsx       # Literature node
│   │   │   │   ├── MaterialNode.tsx    # Material/property node
│   │   │   │   ├── ExperimentNode.tsx  # Experiment node
│   │   │   │   ├── ADAMPromptNode.tsx  # Generated prompt node
│   │   │   │   └── InsightNode.tsx     # AI insight node
│   │   │   ├── EdgeTypes/
│   │   │   │   ├── CitationEdge.tsx
│   │   │   │   ├── CausalEdge.tsx
│   │   │   │   └── SequenceEdge.tsx
│   │   │   └── Controls/
│   │   │       ├── ZoomControls.tsx
│   │   │       ├── FilterPanel.tsx
│   │   │       └── LayoutSelector.tsx
│   │   │
│   │   ├── Chat/
│   │   │   ├── ChatPanel.tsx           # Research assistant chat
│   │   │   ├── MessageList.tsx
│   │   │   ├── PromptInput.tsx
│   │   │   └── StreamingResponse.tsx
│   │   │
│   │   ├── ADAM/
│   │   │   ├── ADAMPanel.tsx           # ADAM control panel
│   │   │   ├── PromptPreview.tsx       # Preview generated prompts
│   │   │   ├── CellStatus.tsx          # Production cell status
│   │   │   ├── ExecutionLog.tsx        # Execution history
│   │   │   └── FeedbackViewer.tsx      # ADAM feedback display
│   │   │
│   │   ├── Literature/
│   │   │   ├── SearchPanel.tsx
│   │   │   ├── PaperViewer.tsx
│   │   │   ├── CitationGraph.tsx
│   │   │   └── FindingsPanel.tsx
│   │   │
│   │   └── Materials/
│   │       ├── MaterialsExplorer.tsx
│   │       ├── PropertyViewer.tsx
│   │       └── ProcessSelector.tsx
│   │
│   ├── hooks/
│   │   ├── useGateway.ts              # WebSocket connection
│   │   ├── useSession.ts              # Session state
│   │   ├── useStreaming.ts            # Streaming responses
│   │   └── useADAM.ts                 # ADAM integration
│   │
│   ├── stores/
│   │   ├── sessionStore.ts            # Zustand session store
│   │   ├── canvasStore.ts             # Canvas state
│   │   └── adamStore.ts               # ADAM state
│   │
│   └── lib/
│       ├── gateway.ts                 # Gateway client
│       ├── types.ts                   # TypeScript types
│       └── utils.ts
```

#### 4.2 Research Canvas Component

```tsx
// components/Canvas/ResearchCanvas.tsx
import ReactFlow, {
  Node, Edge, Background, Controls, MiniMap
} from 'reactflow';
import { useCallback, useEffect } from 'react';
import { useCanvasStore } from '@/stores/canvasStore';
import { useGateway } from '@/hooks/useGateway';

// Custom node types for research workflow
const nodeTypes = {
  paper: PaperNode,
  material: MaterialNode,
  experiment: ExperimentNode,
  adamPrompt: ADAMPromptNode,
  insight: InsightNode,
};

const edgeTypes = {
  citation: CitationEdge,
  causal: CausalEdge,
  sequence: SequenceEdge,
};

export function ResearchCanvas() {
  const { nodes, edges, addNode, updateNode, removeNode } = useCanvasStore();
  const { sendMessage, subscribe } = useGateway();

  // Subscribe to gateway events
  useEffect(() => {
    const unsubscribe = subscribe('canvas_update', (event) => {
      if (event.type === 'new_node') {
        addNode(event.node);
      } else if (event.type === 'update_node') {
        updateNode(event.nodeId, event.data);
      }
    });

    return unsubscribe;
  }, []);

  // Handle node interactions
  const onNodeDoubleClick = useCallback((event: any, node: Node) => {
    if (node.type === 'paper') {
      // Open paper details panel
      sendMessage({
        type: 'query',
        payload: { action: 'get_paper_details', paperId: node.id }
      });
    } else if (node.type === 'adamPrompt') {
      // Preview and edit ADAM prompt
      sendMessage({
        type: 'query',
        payload: { action: 'preview_adam_prompt', promptId: node.id }
      });
    }
  }, [sendMessage]);

  // Generate ADAM prompt from selection
  const generateADAMPrompt = useCallback(async () => {
    const selectedNodes = nodes.filter(n => n.selected);

    await sendMessage({
      type: 'tool_call',
      payload: {
        skill: 'adam_orchestrator',
        tool: 'generate_discovery_prompt',
        params: {
          context_nodes: selectedNodes.map(n => n.id),
          include_literature: true
        }
      }
    });
  }, [nodes, sendMessage]);

  return (
    <div className="h-full w-full">
      <ReactFlow
        nodes={nodes}
        edges={edges}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onNodeDoubleClick={onNodeDoubleClick}
        fitView
      >
        <Background />
        <Controls />
        <MiniMap />
      </ReactFlow>

      {/* Floating action button for ADAM prompt generation */}
      <button
        onClick={generateADAMPrompt}
        className="absolute bottom-4 right-4 bg-blue-600 text-white px-4 py-2 rounded-lg"
      >
        Generate ADAM Prompt
      </button>
    </div>
  );
}
```

#### 4.3 ADAM Control Panel

```tsx
// components/ADAM/ADAMPanel.tsx
import { useState } from 'react';
import { useADAM } from '@/hooks/useADAM';
import { ADAMPrompt, CellStatus } from '@/lib/types';

export function ADAMPanel() {
  const {
    cells,
    activePrompts,
    executionHistory,
    sendPrompt,
    cancelExecution
  } = useADAM();

  const [selectedPrompt, setSelectedPrompt] = useState<ADAMPrompt | null>(null);

  return (
    <div className="flex flex-col h-full bg-gray-900 text-white">
      {/* Cell Status Grid */}
      <div className="p-4 border-b border-gray-700">
        <h3 className="text-sm font-semibold mb-2">Production Cells</h3>
        <div className="grid grid-cols-3 gap-2">
          {cells.map(cell => (
            <CellStatusCard key={cell.id} cell={cell} />
          ))}
        </div>
      </div>

      {/* Active Prompts */}
      <div className="flex-1 overflow-auto p-4">
        <h3 className="text-sm font-semibold mb-2">Pending Prompts</h3>
        {activePrompts.map(prompt => (
          <PromptCard
            key={prompt.prompt_id}
            prompt={prompt}
            onSelect={() => setSelectedPrompt(prompt)}
            onExecute={() => sendPrompt(prompt)}
            onCancel={() => cancelExecution(prompt.prompt_id)}
          />
        ))}
      </div>

      {/* Prompt Preview/Editor */}
      {selectedPrompt && (
        <PromptEditor
          prompt={selectedPrompt}
          onSave={(updated) => {
            setSelectedPrompt(updated);
          }}
          onClose={() => setSelectedPrompt(null)}
        />
      )}
    </div>
  );
}
```

---

### Phase 5: Enhanced Intelligence (Weeks 13-16)

#### 5.1 Advanced RLM Processor

Upgrade from frequency-based aggregation to semantic clustering:

```python
# rlm/advanced_processor.py
from sklearn.cluster import HDBSCAN
from sentence_transformers import SentenceTransformer

class AdvancedRLMProcessor:
    """
    Enhanced RLM with semantic clustering and knowledge synthesis.
    """

    def __init__(self):
        self.embedder = SentenceTransformer('all-MiniLM-L6-v2')
        self.clusterer = HDBSCAN(min_cluster_size=3)

    async def aggregate_with_clustering(
        self,
        chunk_results: list[ChunkResult]
    ) -> AggregatedResult:
        """Aggregate results using semantic clustering"""

        # Collect all findings
        all_findings = []
        for result in chunk_results:
            all_findings.extend(result.findings)

        # Embed findings
        embeddings = self.embedder.encode(all_findings)

        # Cluster semantically similar findings
        clusters = self.clusterer.fit_predict(embeddings)

        # Generate representative summary for each cluster
        clustered_findings = {}
        for i, cluster_id in enumerate(clusters):
            if cluster_id not in clustered_findings:
                clustered_findings[cluster_id] = []
            clustered_findings[cluster_id].append(all_findings[i])

        # Synthesize each cluster
        synthesized = []
        for cluster_id, findings in clustered_findings.items():
            if cluster_id == -1:  # Noise
                continue
            summary = await self._synthesize_cluster(findings)
            synthesized.append(summary)

        return AggregatedResult(
            findings=synthesized,
            clusters=clustered_findings,
            confidence_scores=self._compute_confidence(clustered_findings)
        )
```

#### 5.2 Materials Property Prediction

```python
# skills/materials/property_predict.py
class MaterialsPropertyPredictor:
    """
    Predict material properties using literature knowledge
    and ML models.
    """

    async def predict_properties(
        self,
        material_formula: str,
        synthesis_conditions: dict,
        session: "Session"
    ) -> dict:
        # Get relevant literature from session context
        relevant_papers = await self._find_similar_materials(
            material_formula,
            session.context.documents_analyzed
        )

        # Extract reported properties
        known_properties = self._extract_properties(relevant_papers)

        # Generate prediction prompt
        prediction = await self.llm.generate(
            self.PROPERTY_PREDICTION_PROMPT.format(
                material=material_formula,
                conditions=synthesis_conditions,
                literature_data=known_properties
            )
        )

        return {
            "predicted_properties": prediction,
            "confidence": self._compute_confidence(relevant_papers),
            "supporting_literature": relevant_papers
        }
```

#### 5.3 Experiment Feedback Loop

```python
# skills/adam/feedback_handler.py
class FeedbackHandler:
    """
    Process ADAM execution feedback to improve future prompts.
    """

    async def process_feedback(
        self,
        prompt_id: str,
        execution_results: dict,
        success: bool,
        session: "Session"
    ) -> dict:
        # Store feedback in session context
        session.context.adam_interactions.append({
            "prompt_id": prompt_id,
            "results": execution_results,
            "success": success,
            "timestamp": datetime.utcnow()
        })

        if not success:
            # Analyze failure
            failure_analysis = await self._analyze_failure(
                prompt_id,
                execution_results
            )

            # Generate corrective suggestions
            corrections = await self._suggest_corrections(
                failure_analysis,
                session.context
            )

            return {
                "status": "failure_analyzed",
                "failure_analysis": failure_analysis,
                "suggested_corrections": corrections,
                "updated_context": session.to_context_window()
            }
        else:
            # Extract successful parameters for future reference
            learned_params = await self._extract_success_factors(
                prompt_id,
                execution_results
            )

            # Update knowledge base
            await self._update_knowledge_base(learned_params)

            return {
                "status": "success_recorded",
                "learned_parameters": learned_params,
                "next_steps": await self._suggest_next_steps(session)
            }
```

---

## Part 3: Data Model Evolution

### Current → Target Schema Changes

```python
# db/models.py - Updated schema

class Session(Base):
    """NEW: Persistent session tracking"""
    __tablename__ = "sessions"

    id = Column(String, primary_key=True)
    channel = Column(String)
    user_id = Column(String, nullable=True)
    created_at = Column(DateTime)
    last_active = Column(DateTime)

    # Research context (JSON)
    context = Column(JSON)
    conversation_history = Column(JSON)

    # Relationships
    documents = relationship("Document", secondary="session_documents")
    adam_prompts = relationship("ADAMPrompt", back_populates="session")

class ADAMPrompt(Base):
    """NEW: Generated ADAM prompts"""
    __tablename__ = "adam_prompts"

    id = Column(String, primary_key=True)
    session_id = Column(String, ForeignKey("sessions.id"))
    prompt_type = Column(String)

    # Prompt content
    objective = Column(Text)
    detailed_instructions = Column(Text)
    context_window = Column(JSON)

    # Constraints
    material_constraints = Column(JSON)
    process_constraints = Column(JSON)

    # Routing
    target_cell = Column(String)

    # Execution tracking
    status = Column(String)  # draft, sent, executing, completed, failed
    execution_id = Column(String, nullable=True)
    execution_results = Column(JSON, nullable=True)

    # Relationships
    session = relationship("Session", back_populates="adam_prompts")
    source_documents = relationship("Document", secondary="prompt_documents")

class ADAMExecution(Base):
    """NEW: ADAM execution history"""
    __tablename__ = "adam_executions"

    id = Column(String, primary_key=True)
    prompt_id = Column(String, ForeignKey("adam_prompts.id"))

    started_at = Column(DateTime)
    completed_at = Column(DateTime, nullable=True)

    cell_used = Column(String)
    process_parameters = Column(JSON)

    success = Column(Boolean)
    results = Column(JSON)
    artifacts = Column(JSON)  # File references, measurements, etc.

    # Feedback processing
    feedback_processed = Column(Boolean, default=False)
    learned_parameters = Column(JSON, nullable=True)
```

---

## Part 4: Migration Strategy

### Incremental Migration Path

```
Week 1-2:   Gateway skeleton + existing CLI as first channel
Week 3-4:   Skill framework + migrate existing modules to skills
Week 5-6:   ADAM Orchestrator skill (core value-add)
Week 7-8:   Web channel + basic React UI
Week 9-10:  Research canvas + ADAM panel
Week 11-12: Enhanced RLM + feedback loop
Week 13-14: Additional channels (Slack, API)
Week 15-16: Polish, testing, documentation
```

### Backward Compatibility

The CLI interface will be preserved as a channel adapter:

```python
# channels/cli.py
class CLIChannel(ChannelAdapter):
    """Backward-compatible CLI interface"""

    async def run_legacy_command(self, command: str, args: list):
        """Map legacy CLI commands to gateway operations"""
        command_map = {
            "scan": ("literature", "scan"),
            "process": ("literature", "process"),
            "batch": ("literature", "batch"),
            "acquire": ("literature", "acquire"),
        }

        skill, tool = command_map[command]
        return await self.gateway.execute(skill, tool, args)
```

---

## Part 5: ADAM Integration Specification

### Context Window Format for ADAM

```json
{
  "version": "1.0",
  "session_id": "uuid",
  "timestamp": "ISO8601",

  "research_context": {
    "objective": "Develop high-entropy alloy with superior strength-ductility balance",
    "material_focus": ["HEA", "CoCrFeNiMn", "refractory alloys"],

    "literature_summary": {
      "papers_analyzed": 47,
      "key_insights": [
        "Lattice distortion correlates with yield strength",
        "Optimal annealing temperature: 800-900°C",
        "Mn content >20% reduces ductility"
      ],
      "methodologies": ["arc melting", "SPS", "rolling"],
      "knowledge_gaps": ["Fatigue behavior under cyclic loading"]
    },

    "prior_experiments": [
      {
        "id": "exp-001",
        "date": "2025-01-15",
        "material": "CoCrFeNi",
        "process": "arc_melt → homogenize → roll",
        "outcome": "success",
        "measured_properties": {
          "yield_strength_mpa": 450,
          "elongation_pct": 35
        }
      }
    ]
  },

  "prompt": {
    "type": "synthesis",
    "objective": "Synthesize CoCrFeNiMn0.5 alloy with target yield strength >500 MPa",

    "instructions": [
      "1. Prepare elemental powders in stoichiometric ratio",
      "2. Arc melt under Ar atmosphere, flip 5x for homogeneity",
      "3. Anneal at 850°C for 24h",
      "4. Cold roll to 50% reduction",
      "5. Final anneal at 800°C for 1h"
    ],

    "constraints": {
      "materials": ["Co", "Cr", "Fe", "Ni", "Mn powders, 99.9% purity"],
      "process": ["Ar atmosphere required", "Max temp 1600°C"],
      "safety": ["Mn dust hazard - use fume hood"]
    },

    "success_criteria": [
      "Single-phase FCC structure (XRD)",
      "Yield strength ≥500 MPa",
      "Elongation ≥30%"
    ],

    "required_characterization": [
      "XRD", "SEM-EDS", "tensile test"
    ]
  },

  "routing": {
    "target_cell": "metal",
    "estimated_duration": "48h",
    "priority": "high"
  }
}
```

### ADAM Feedback Format

```json
{
  "execution_id": "exec-uuid",
  "prompt_id": "prompt-uuid",
  "status": "completed",

  "timeline": [
    {"step": "arc_melt", "status": "success", "duration_min": 45},
    {"step": "homogenize", "status": "success", "duration_min": 1440},
    {"step": "roll", "status": "success", "duration_min": 30}
  ],

  "results": {
    "sample_id": "HEA-2025-001",
    "characterization": {
      "XRD": {
        "phase": "FCC",
        "lattice_param_A": 3.59,
        "file": "s3://adam-data/xrd/HEA-2025-001.xy"
      },
      "tensile": {
        "yield_strength_mpa": 523,
        "ultimate_strength_mpa": 687,
        "elongation_pct": 32
      }
    }
  },

  "success": true,
  "notes": "Target properties achieved. Sample stored in location B-12."
}
```

---

## Part 6: Success Metrics

| Metric | Current | Target |
|--------|---------|--------|
| Time to generate ADAM prompt | Manual (hours) | <30 seconds |
| Literature context utilization | Single-document | Multi-document synthesis |
| Prompt success rate | N/A | >80% first-attempt |
| Feedback loop closure | None | Automated learning |
| User interfaces | CLI only | CLI + Web + Slack + API |
| ADAM integration | Export JSON | Real-time bidirectional |

---

## Appendix: File Structure (Final)

```
hal-9000/
├── src/
│   └── hal9000/
│       ├── __init__.py
│       ├── cli.py                    # Legacy CLI (preserved)
│       ├── config.py
│       │
│       ├── gateway/                  # NEW: Core gateway
│       │   ├── __init__.py
│       │   ├── server.py
│       │   ├── session.py
│       │   ├── router.py
│       │   ├── events.py
│       │   └── protocol.py
│       │
│       ├── skills/                   # NEW: Skill system
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── registry.py
│       │   │
│       │   ├── literature/           # Migrated from existing
│       │   ├── materials/            # NEW
│       │   ├── adam/                 # NEW: Core ADAM skill
│       │   └── knowledge/            # Migrated + enhanced
│       │
│       ├── channels/                 # NEW: Channel adapters
│       │   ├── __init__.py
│       │   ├── base.py
│       │   ├── cli.py
│       │   ├── web.py
│       │   ├── adam.py
│       │   ├── slack.py
│       │   └── api.py
│       │
│       ├── rlm/                      # Enhanced
│       │   ├── processor.py
│       │   ├── advanced_processor.py # NEW
│       │   └── prompts.py
│       │
│       ├── ingest/                   # Preserved
│       ├── acquisition/              # Preserved
│       ├── categorize/               # Preserved
│       ├── obsidian/                 # Preserved
│       └── db/                       # Enhanced
│
├── ui/                               # NEW: Web interface
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── components/
│       ├── hooks/
│       ├── stores/
│       └── lib/
│
├── tests/
├── docs/
├── pyproject.toml
└── README.md
```

---

## Getting Started (Post-Refactor)

```bash
# Start the gateway
hal gateway start

# Legacy CLI still works
hal scan /path/to/papers

# Or use the web UI
hal ui start
# Open http://localhost:3000

# Generate ADAM prompt via CLI
hal adam generate-prompt \
  --objective "Synthesize novel thermoelectric material" \
  --material-class "skutterudites" \
  --include-literature

# Send directly to ADAM
hal adam send --prompt-id <id>
```

---

*This plan transforms HAL-9000 from a document processing tool into an intelligent research orchestration platform, purpose-built for driving autonomous materials discovery through ADAM.*
