"""Gateway module for HAL-9000 WebSocket communication."""

from hal9000.gateway.protocol import (
    ADAMPromptPayload,
    GatewayMessage,
    MessageType,
)
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
]
