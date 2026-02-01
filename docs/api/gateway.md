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
