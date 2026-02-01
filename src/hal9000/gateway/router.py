"""Message routing for the HAL-9000 Gateway.

This module provides message routing functionality, dispatching
incoming messages to registered handlers based on message type.
"""

import logging
from collections.abc import AsyncGenerator, Callable
from typing import Optional

from hal9000.gateway.health import health_handler
from hal9000.gateway.protocol import GatewayMessage, MessageType
from hal9000.gateway.session import Session

logger = logging.getLogger(__name__)

# Type alias for message handlers
# Handlers receive a message and session, and yield response messages
MessageHandler = Callable[
    [GatewayMessage, Session], AsyncGenerator[GatewayMessage, None]
]


class Router:
    """Routes messages to appropriate handlers based on message type.

    The router maintains a registry of handlers for each message type
    and dispatches incoming messages accordingly.
    """

    def __init__(self) -> None:
        """Initialize the router."""
        self._handlers: dict[MessageType, MessageHandler] = {}
        self._default_handler: Optional[MessageHandler] = None

    def register(
        self, message_type: MessageType, handler: MessageHandler
    ) -> None:
        """Register a handler for a message type.

        Args:
            message_type: The type of message to handle.
            handler: Async generator function that handles the message.
        """
        self._handlers[message_type] = handler
        logger.debug(f"Registered handler for {message_type.value}")

    def register_default(self, handler: MessageHandler) -> None:
        """Register a default handler for unhandled message types.

        Args:
            handler: Async generator function that handles unmatched messages.
        """
        self._default_handler = handler
        logger.debug("Registered default handler")

    def unregister(self, message_type: MessageType) -> bool:
        """Unregister a handler for a message type.

        Args:
            message_type: The message type to unregister.

        Returns:
            True if the handler was removed, False if not found.
        """
        if message_type in self._handlers:
            del self._handlers[message_type]
            logger.debug(f"Unregistered handler for {message_type.value}")
            return True
        return False

    def has_handler(self, message_type: MessageType) -> bool:
        """Check if a handler is registered for a message type.

        Args:
            message_type: The message type to check.

        Returns:
            True if a handler is registered.
        """
        return message_type in self._handlers

    def get_registered_types(self) -> list[MessageType]:
        """Get list of message types with registered handlers.

        Returns:
            List of MessageType values that have handlers.
        """
        return list(self._handlers.keys())

    async def route(
        self, message: GatewayMessage, session: Session
    ) -> AsyncGenerator[GatewayMessage, None]:
        """Route a message to its handler and yield responses.

        Args:
            message: The incoming gateway message.
            session: The session associated with the message.

        Yields:
            Response messages from the handler.
        """
        # Get the message type - handle both string and enum
        message_type = message.type
        if isinstance(message_type, str):
            try:
                message_type = MessageType(message_type)
            except ValueError:
                # Unknown message type string
                yield GatewayMessage.create_error(
                    session_id=session.id,
                    error=f"Unknown message type: {message.type}",
                    code="UNKNOWN_MESSAGE_TYPE",
                )
                return

        # Look up handler
        handler = self._handlers.get(message_type)

        if handler is None:
            # Try default handler
            if self._default_handler is not None:
                handler = self._default_handler
            else:
                # No handler found - return error
                yield GatewayMessage.create_error(
                    session_id=session.id,
                    error=f"No handler registered for message type: {message_type.value}",
                    code="NO_HANDLER",
                )
                return

        # Execute handler and yield responses
        try:
            async for response in handler(message, session):
                yield response
        except Exception as e:
            logger.exception(f"Handler error for {message_type.value}: {e}")
            yield GatewayMessage.create_error(
                session_id=session.id,
                error=f"Handler error: {str(e)}",
                code="HANDLER_ERROR",
            )


async def echo_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Simple echo handler for testing.

    Echoes the message payload back as a response.
    """
    yield GatewayMessage.create_response(
        session_id=session.id,
        payload={"echo": message.payload},
        metadata={"original_id": message.id},
    )


async def streaming_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Example streaming handler for testing.

    Streams back multiple chunks followed by a stream end.
    """
    content = message.payload.get("content", "")
    chunk_size = message.payload.get("chunk_size", 10)

    # Stream content in chunks
    for i in range(0, len(content), chunk_size):
        chunk = content[i : i + chunk_size]
        yield GatewayMessage.create_stream_chunk(
            session_id=session.id,
            chunk=chunk,
            metadata={"chunk_index": i // chunk_size},
        )

    # Signal stream end
    yield GatewayMessage.create_stream_end(
        session_id=session.id,
        metadata={"total_chunks": (len(content) + chunk_size - 1) // chunk_size},
    )


def create_router_with_defaults() -> Router:
    """Create a router with default handlers for common message types.

    Returns:
        A Router instance with basic handlers registered.
    """
    router = Router()

    # Register health handler for queries (supports health checks and echo fallback)
    router.register(MessageType.QUERY, health_handler)

    return router
