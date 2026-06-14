"""Gateway module for HAL-9000 WebSocket communication."""

from hal9000.gateway.agent_ledger import AgentRunLedger
from hal9000.gateway.agent_session import (
    AgentGatewayError,
    AgentGatewaySession,
    AgentGatewaySessionManager,
    create_agent_session_command_handler,
)
from hal9000.gateway.events import (
    EventEmitter,
    EventType,
    GatewayEvent,
    Subscription,
)
from hal9000.gateway.health import (
    HealthChecker,
    get_health_checker,
    health_handler,
)
from hal9000.gateway.http import (
    create_gateway_http_server,
    run_gateway_http_server,
)
from hal9000.gateway.persistence import PersistentSessionManager
from hal9000.gateway.protocol import (
    ADAMPromptPayload,
    GatewayMessage,
    MessageType,
)
from hal9000.gateway.router import (
    Router,
    create_router_with_defaults,
    echo_handler,
    streaming_handler,
)
from hal9000.gateway.server import HALGateway
from hal9000.gateway.session import (
    ResearchContext,
    Session,
    SessionManager,
)

__all__ = [
    "MessageType",
    "GatewayMessage",
    "ADAMPromptPayload",
    "AgentRunLedger",
    "AgentGatewayError",
    "AgentGatewaySession",
    "AgentGatewaySessionManager",
    "create_agent_session_command_handler",
    "ResearchContext",
    "Session",
    "SessionManager",
    "PersistentSessionManager",
    "EventType",
    "GatewayEvent",
    "EventEmitter",
    "Subscription",
    "Router",
    "create_router_with_defaults",
    "echo_handler",
    "streaming_handler",
    "health_handler",
    "HealthChecker",
    "get_health_checker",
    "HALGateway",
    "create_gateway_http_server",
    "run_gateway_http_server",
]
