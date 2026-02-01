"""Gateway module for HAL-9000 WebSocket communication."""

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
    "ResearchContext",
    "Session",
    "SessionManager",
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
]
