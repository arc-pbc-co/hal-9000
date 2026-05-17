# Gateway API Reference

The Gateway module provides WebSocket-based communication for HAL-9000, enabling real-time interaction with clients through a message-based protocol.

## Overview

The gateway provides:
- WebSocket server for client connections
- Session management with research context tracking
- Message routing with handler registration
- Event streaming for real-time updates
- Health check endpoints
- Optional database persistence for sessions

## Quick Start

```python
from hal9000.gateway import HALGateway

# Create and start the gateway
gateway = HALGateway(host="127.0.0.1", port=9000)
await gateway.start()

# Run until shutdown
await gateway.run_forever()
```

Or via CLI:
```bash
hal gateway start --host 127.0.0.1 --port 9000
```

## Protocol

### Message Types

All messages follow the `GatewayMessage` format:

```python
from hal9000.gateway import GatewayMessage, MessageType

message = GatewayMessage(
    type=MessageType.QUERY,
    session_id="session-uuid",
    payload={"query_type": "health"},
    metadata={"trace_id": "abc123"}
)
```

#### Client → Gateway

| Type | Description |
|------|-------------|
| `COMMAND` | Execute an action |
| `QUERY` | Request information |
| `TOOL_CALL` | Invoke a registered tool |
| `FEEDBACK` | Provide feedback on results |
| `ADAM_PROMPT` | Send ADAM-specific research prompt |
| `ADAM_CONTEXT` | Update ADAM context |
| `ADAM_FEEDBACK` | Provide ADAM feedback |

#### Gateway → Client

| Type | Description |
|------|-------------|
| `RESPONSE` | Single response message |
| `STREAM_CHUNK` | Streaming response chunk |
| `STREAM_END` | End of streaming response |
| `TOOL_RESULT` | Result from tool execution |
| `ERROR` | Error response |

### Health Check

Query the gateway health status:

```json
{
    "type": "query",
    "session_id": "any",
    "payload": {"query_type": "health"}
}
```

Response:
```json
{
    "type": "response",
    "session_id": "session-uuid",
    "payload": {
        "status": "healthy",
        "version": "0.1.0",
        "uptime_seconds": 3600.5,
        "active_sessions": 5,
        "active_connections": 3,
        "is_running": true
    }
}
```

### Agent Sessions

The default gateway router exposes HAL agent sessions through `COMMAND`
messages. The WebSocket connection still has its normal gateway `session_id`;
agent runtime state is addressed with `payload.agent_session_id`.

Create a session:

```json
{
    "type": "command",
    "session_id": "placeholder",
    "payload": {
        "action": "agent.create",
        "agent_session_id": "research-chat-1",
        "system_prompt": "You are HAL."
    }
}
```

Submit a turn:

```json
{
    "type": "command",
    "session_id": "placeholder",
    "payload": {
        "action": "agent.submit",
        "agent_session_id": "research-chat-1",
        "text": "Search memory for creep-resistant nickel superalloys."
    }
}
```

Resolve an approval:

```json
{
    "type": "command",
    "session_id": "placeholder",
    "payload": {
        "action": "agent.approve",
        "agent_session_id": "research-chat-1",
        "approval_id": "approval-uuid",
        "approved": true,
        "actor": "reviewer@example.com",
        "reason": "Within run policy."
    }
}
```

Other supported actions are `agent.interrupt`, `agent.compact`,
`agent.replay`, and `agent.history`. `agent.replay` returns the HAL
`AgentEvent` stream with sequence numbers and accepts `after_sequence` and
`limit`; `agent.history` returns HAL-owned provider-neutral messages and
accepts `include_system`.

When `agent.create` includes a `run_id`, the gateway mirrors emitted
`AgentEvent` payloads into that run's append-only ledger as
`agent.gateway.event` records. After a gateway restart, clients can recover the
event stream and latest history snapshot without a live runtime by passing both
`agent_session_id` and `run_id` to `agent.replay` or `agent.history`:

```json
{
    "type": "command",
    "session_id": "placeholder",
    "payload": {
        "action": "agent.replay",
        "agent_session_id": "research-chat-1",
        "run_id": "research-run-uuid",
        "after_sequence": 12
    }
}
```

### HTTP App Gateway

The app gateway serves deployment-facing HTTP routes for non-CLI apps:

| Route | Purpose |
| --- | --- |
| `GET /` or `GET /ui` | Browser HAL cockpit |
| `GET /health` | Liveness probe |
| `GET /ready` | Database and integration-secret readiness |
| `GET /api/frontend/config` | Cockpit model and route configuration |
| `GET /api/frontend/review` | Review queue/detail panel payloads |
| `GET /api/frontend/evidence` | Run evidence panel payloads |
| `GET /api/frontend/graph` | Project or run graph panel payloads |
| `GET /api/agent/sessions` | Live agent session snapshots |
| `POST /api/agent/session` | Create a browser-facing HAL agent session |
| `POST /api/agent/submit` | Submit chat text into a HAL agent session |
| `POST /api/agent/approve` | Resolve a pending tool approval |
| `POST /api/agent/interrupt` | Interrupt an active agent turn |
| `POST /api/agent/compact` | Request token-aware context compaction |
| `GET /api/agent/replay` | Replay live or durable agent events |
| `GET /api/agent/history` | Read provider-neutral agent message history |
| `POST /slack/command` | Slack slash-command ingress |
| `POST /slack/action` | Slack interactive action ingress |
| `POST /slack/event` | Slack Events API callback ingress |
| `POST /sheets/writeback` | Token-gated Sheets writeback ingress |

The browser cockpit is a lightweight first graft over the approved HAL runtime.
It uses the REST agent endpoints for sessions, chat submission, event replay,
approvals, interrupts, compaction, and per-session model metadata. The HAL
panels reuse existing review, evidence, and graph services rather than owning
research state in the frontend.

Slack signatures are verified when a signing secret is configured. Slack event
callbacks support `url_verification` plus app-mention/message callbacks for
channel commands such as `summary <run_id>` and `exports <run_id>`. Accepted
channel callbacks create durable Slack notifications that can be posted through
the delivery worker with channel and thread metadata preserved.

Sheets writeback is disabled unless `app_gateway.sheets_writeback_enabled` is true and
a bearer token is configured. Accepted Sheets payloads are applied through HAL's
authorized review, annotation, and run-queue services.

Supported Sheets writeback actions:

| Action | Required fields | Effect |
| --- | --- | --- |
| `add_comment` | `actor_email`, `target_type`, `target_id`, `body` | Adds an authorized output or claim annotation |
| `review_run` | `actor_email`, `run_id`, `decision` | Promotes, rejects, or requests changes for a staged run |
| `queue_run` | `actor_email`, `project_slug`, `objective` | Queues a project-scoped run and records `run.queued` |

Example:

```json
{
  "action": "queue_run",
  "actor_email": "reviewer@example.com",
  "project_slug": "firm-research",
  "objective": "Refresh the May competitive brief."
}
```

## Classes

### HALGateway

The main WebSocket server class.

```python
class HALGateway:
    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        router: Optional[Router] = None,
        session_manager: Optional[SessionManager] = None,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None
```

#### Methods

| Method | Description |
|--------|-------------|
| `start()` | Start the WebSocket server |
| `stop()` | Stop the server gracefully |
| `run_forever()` | Run until shutdown signal |
| `send_to_session(session_id, message)` | Send message to specific session |
| `broadcast(message)` | Send message to all sessions |

#### Properties

| Property | Type | Description |
|----------|------|-------------|
| `is_running` | `bool` | Server running status |
| `uptime_seconds` | `float` | Time since server started |

### AgentGatewaySessionManager

Creates queue-driven HAL agent sessions for gateway clients.

```python
class AgentGatewaySessionManager:
    async def create_session(
        session_id: str | None = None,
        gateway_session_id: str | None = None,
        user_id: str | None = None,
        run_id: str | None = None,
        system_prompt: str | None = None,
        messages: list[dict] | None = None,
    ) -> AgentGatewaySession
```

`AgentGatewaySession` exposes `submit`, `approve`, `interrupt`, `compact`,
`replay`, `history`, and `shutdown`. The gateway wrapper does not execute tools
directly; it queues `AgentOperation` objects into `AgentSessionRuntime`, so
approvals, compaction, and tool accounting stay inside HAL's agent event model.
`AgentRunLedger` mirrors run-bound sessions into `ResearchRunEvent` for durable
replay across process restarts.

### Session

Represents a client session with research context.

```python
@dataclass
class Session:
    id: str
    channel: str = "websocket"
    created_at: datetime
    user_id: Optional[str] = None
    context: ResearchContext
    conversation_history: list[dict]
    active_tools: list[str]
```

#### Methods

| Method | Description |
|--------|-------------|
| `to_context_window()` | Generate ADAM-compatible context dict |
| `add_message(message)` | Add message to conversation history |
| `to_dict()` | Serialize session to dict |
| `from_dict(data)` | Deserialize session from dict |

### ResearchContext

Tracks research state during a session.

```python
@dataclass
class ResearchContext:
    documents_analyzed: list[str]
    extracted_knowledge: dict[str, Any]
    materials_of_interest: list[str]
    active_hypotheses: list[dict]
    adam_interactions: list[dict]
```

### SessionManager

Manages active sessions.

```python
class SessionManager:
    def create_session(
        channel: str = "websocket",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session

    def get_session(session_id: str) -> Optional[Session]
    def remove_session(session_id: str) -> bool
    def list_sessions() -> list[Session]
    def session_count() -> int
```

### PersistentSessionManager

Session manager with database persistence.

```python
class PersistentSessionManager(SessionManager):
    def __init__(
        database_url: str = "sqlite:///./hal9000.db",
        session_timeout_minutes: int = 60,
        auto_save: bool = True,
    ) -> None

    def load_sessions() -> int  # Load from DB
    def save_session(session_id: str) -> bool
    def save_all_sessions() -> int
    def cleanup_expired_sessions() -> int
```

### Router

Routes messages to handlers.

```python
class Router:
    def register(message_type: MessageType, handler: MessageHandler) -> None
    def unregister(message_type: MessageType) -> bool
    def has_handler(message_type: MessageType) -> bool

    async def route(
        message: GatewayMessage,
        session: Session
    ) -> AsyncGenerator[GatewayMessage, None]
```

#### Handler Signature

```python
async def my_handler(
    message: GatewayMessage,
    session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    # Process message
    yield GatewayMessage.create_response(
        session_id=session.id,
        payload={"result": "data"}
    )
```

### EventEmitter

Pub/sub event system for gateway events.

```python
class EventEmitter:
    def subscribe(
        subscriber_id: Optional[str] = None,
        event_types: Optional[set[EventType]] = None,
        session_id: Optional[str] = None,
    ) -> str  # Returns subscription ID

    def unsubscribe(subscriber_id: str) -> bool

    async def emit(event: GatewayEvent) -> int

    async def listen(
        subscriber_id: str,
        timeout: Optional[float] = None
    ) -> AsyncGenerator[GatewayEvent, None]
```

#### Event Types

```python
class EventType(str, Enum):
    # Connection events
    CONNECTION_OPENED = "connection_opened"
    CONNECTION_CLOSED = "connection_closed"
    CONNECTION_ERROR = "connection_error"

    # Session events
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_DESTROYED = "session_destroyed"

    # Message events
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    MESSAGE_ERROR = "message_error"

    # Processing events
    PROCESSING_STARTED = "processing_started"
    PROCESSING_PROGRESS = "processing_progress"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"

    # ADAM events
    ADAM_QUERY_STARTED = "adam_query_started"
    ADAM_RESPONSE_CHUNK = "adam_response_chunk"
    ADAM_RESPONSE_COMPLETED = "adam_response_completed"

    # Tool events
    TOOL_INVOKED = "tool_invoked"
    TOOL_RESULT = "tool_result"

    # System events
    SYSTEM_STATUS = "system_status"
    SYSTEM_ERROR = "system_error"
```

## Configuration

Gateway settings via environment variables or config file:

```yaml
hal9000:
  gateway:
    host: "127.0.0.1"
    port: 9000
    max_connections: 100
    session_timeout_minutes: 60
```

Environment variables:
```bash
HAL9000_GATEWAY__HOST=0.0.0.0
HAL9000_GATEWAY__PORT=8080
HAL9000_GATEWAY__MAX_CONNECTIONS=50
HAL9000_GATEWAY__SESSION_TIMEOUT_MINUTES=30
```

## Example: Custom Handler

```python
from hal9000.gateway import (
    HALGateway, Router, MessageType,
    GatewayMessage, Session
)
from collections.abc import AsyncGenerator

async def search_handler(
    message: GatewayMessage,
    session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Handle search queries."""
    query = message.payload.get("query", "")

    # Stream results
    for i, result in enumerate(search_results(query)):
        yield GatewayMessage.create_stream_chunk(
            session_id=session.id,
            chunk=result,
            metadata={"index": i}
        )

    yield GatewayMessage.create_stream_end(
        session_id=session.id,
        metadata={"total": len(results)}
    )

# Create router and register handler
router = Router()
router.register(MessageType.COMMAND, search_handler)

# Create gateway with custom router
gateway = HALGateway(router=router)
```

## WebSocket Client Example

```python
import asyncio
import websockets
import json

async def client():
    async with websockets.connect("ws://127.0.0.1:9000") as ws:
        # Send health query
        message = {
            "type": "query",
            "session_id": "placeholder",
            "payload": {"query_type": "health"}
        }
        await ws.send(json.dumps(message))

        # Receive response
        response = json.loads(await ws.recv())
        print(f"Status: {response['payload']['status']}")
        print(f"Version: {response['payload']['version']}")

asyncio.run(client())
```

## Database Schema

The `GatewaySession` model for persistence:

| Column | Type | Description |
|--------|------|-------------|
| `id` | `VARCHAR(36)` | Primary key (UUID) |
| `channel` | `VARCHAR(50)` | Connection channel |
| `user_id` | `VARCHAR(256)` | Optional user identifier |
| `context` | `TEXT` | JSON research context |
| `conversation_history` | `TEXT` | JSON message history |
| `active_tools` | `TEXT` | JSON list of active tools |
| `created_at` | `DATETIME` | Session creation time |
| `last_active` | `DATETIME` | Last activity timestamp |
