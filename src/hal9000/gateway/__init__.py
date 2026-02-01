"""Gateway module for HAL-9000 WebSocket communication."""

from hal9000.gateway.protocol import (
    ADAMPromptPayload,
    GatewayMessage,
    MessageType,
)

__all__ = [
    "MessageType",
    "GatewayMessage",
    "ADAMPromptPayload",
]
