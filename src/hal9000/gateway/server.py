"""WebSocket server for the HAL-9000 Gateway.

This module provides the main WebSocket server that accepts client
connections and handles message routing.
"""

import asyncio
import json
import logging
import signal
from datetime import datetime, timezone
from typing import Any, Optional, Union

import websockets

from hal9000.gateway.events import EventEmitter, EventType
from hal9000.gateway.health import get_health_checker
from hal9000.gateway.protocol import GatewayMessage
from hal9000.gateway.router import Router, create_router_with_defaults
from hal9000.gateway.session import Session, SessionManager

logger = logging.getLogger(__name__)

# Type alias for websocket connection (works with websockets 12.x and 15.x)
WebSocketConnection = Any


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class HALGateway:
    """WebSocket gateway server for HAL-9000.

    Handles client connections, message routing, and session management.
    """

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 9000,
        router: Optional[Router] = None,
        session_manager: Optional[SessionManager] = None,
        event_emitter: Optional[EventEmitter] = None,
    ) -> None:
        """Initialize the gateway server.

        Args:
            host: Host address to bind to.
            port: Port number to listen on.
            router: Optional custom router. Creates default if not provided.
            session_manager: Optional session manager. Creates new if not provided.
            event_emitter: Optional event emitter. Creates new if not provided.
        """
        self.host = host
        self.port = port
        self.router = router or create_router_with_defaults()
        self.session_manager = session_manager or SessionManager()
        self.event_emitter = event_emitter or EventEmitter()

        self._server: Any = None  # websockets.WebSocketServer
        self._started_at: Optional[datetime] = None
        self._shutdown_event = asyncio.Event()
        self._connections: dict[str, WebSocketConnection] = {}

        # Set gateway reference on health checker
        get_health_checker().set_gateway(self)

    @property
    def uptime_seconds(self) -> float:
        """Get server uptime in seconds."""
        if self._started_at is None:
            return 0.0
        return (utc_now() - self._started_at).total_seconds()

    @property
    def is_running(self) -> bool:
        """Check if the server is running."""
        return self._server is not None and self._server.is_serving()

    async def start(self) -> None:
        """Start the WebSocket server."""
        logger.info(f"Starting HAL-9000 Gateway on ws://{self.host}:{self.port}")

        self._server = await websockets.serve(
            self._handle_connection,
            self.host,
            self.port,
        )

        self._started_at = utc_now()
        self._shutdown_event.clear()

        await self.event_emitter.emit_event(
            EventType.SYSTEM_STATUS,
            data={"status": "started", "host": self.host, "port": self.port},
        )

        logger.info(f"HAL-9000 Gateway started on ws://{self.host}:{self.port}")

    async def stop(self) -> None:
        """Stop the WebSocket server gracefully."""
        logger.info("Stopping HAL-9000 Gateway...")

        # Signal shutdown
        self._shutdown_event.set()

        # Close all connections
        for session_id, ws in list(self._connections.items()):
            try:
                await ws.close(1001, "Server shutting down")
            except Exception:
                pass

        # Stop the server
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

        await self.event_emitter.emit_event(
            EventType.SYSTEM_STATUS,
            data={"status": "stopped"},
        )

        logger.info("HAL-9000 Gateway stopped")

    async def run_forever(self) -> None:
        """Run the server until shutdown is requested."""
        await self.start()

        # Set up signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()

        def signal_handler() -> None:
            logger.info("Received shutdown signal")
            self._shutdown_event.set()

        try:
            for sig in (signal.SIGINT, signal.SIGTERM):
                loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handlers not available on Windows
            pass

        # Wait for shutdown
        await self._shutdown_event.wait()
        await self.stop()

    async def _handle_connection(
        self, websocket: WebSocketConnection
    ) -> None:
        """Handle a new WebSocket connection.

        Args:
            websocket: The WebSocket connection.
        """
        # Create a session for this connection
        session = self.session_manager.create_session(channel="websocket")
        self._connections[session.id] = websocket

        logger.info(f"New connection: session={session.id}")

        await self.event_emitter.emit_event(
            EventType.CONNECTION_OPENED,
            session_id=session.id,
            data={"remote": str(websocket.remote_address)},
        )

        try:
            async for raw_message in websocket:
                await self._handle_message(websocket, session, raw_message)
        except websockets.exceptions.ConnectionClosed as e:
            logger.info(f"Connection closed: session={session.id}, code={e.code}")
        except Exception as e:
            logger.exception(f"Connection error: session={session.id}, error={e}")
            await self.event_emitter.emit_event(
                EventType.CONNECTION_ERROR,
                session_id=session.id,
                data={"error": str(e)},
            )
        finally:
            # Clean up
            self._connections.pop(session.id, None)
            self.session_manager.remove_session(session.id)

            await self.event_emitter.emit_event(
                EventType.CONNECTION_CLOSED,
                session_id=session.id,
            )

            logger.info(f"Session ended: {session.id}")

    async def _handle_message(
        self,
        websocket: WebSocketConnection,
        session: Session,
        raw_message: Union[str, bytes],
    ) -> None:
        """Handle an incoming message.

        Args:
            websocket: The WebSocket connection.
            session: The session for this connection.
            raw_message: The raw message data.
        """
        # Parse message
        try:
            if isinstance(raw_message, bytes):
                raw_message = raw_message.decode("utf-8")

            message = GatewayMessage.from_json(raw_message)
            # Ensure session_id matches
            message.session_id = session.id

        except json.JSONDecodeError as e:
            logger.warning(f"Invalid JSON: {e}")
            error = GatewayMessage.create_error(
                session_id=session.id,
                error=f"Invalid JSON: {e}",
                code="INVALID_JSON",
            )
            await websocket.send(error.to_json())
            return
        except Exception as e:
            logger.warning(f"Message parse error: {e}")
            error = GatewayMessage.create_error(
                session_id=session.id,
                error=f"Message parse error: {e}",
                code="PARSE_ERROR",
            )
            await websocket.send(error.to_json())
            return

        await self.event_emitter.emit_event(
            EventType.MESSAGE_RECEIVED,
            session_id=session.id,
            data={"message_id": message.id, "type": message.type},
        )

        # Add to conversation history
        session.add_message({
            "id": message.id,
            "type": message.type,
            "payload": message.payload,
            "direction": "incoming",
        })

        # Route message and stream responses
        try:
            async for response in self.router.route(message, session):
                await websocket.send(response.to_json())

                session.add_message({
                    "id": response.id,
                    "type": response.type,
                    "direction": "outgoing",
                })

                await self.event_emitter.emit_event(
                    EventType.MESSAGE_SENT,
                    session_id=session.id,
                    data={"message_id": response.id, "type": response.type},
                )

        except websockets.exceptions.ConnectionClosed:
            raise  # Re-raise to handle in connection handler
        except Exception as e:
            logger.exception(f"Router error: {e}")
            error = GatewayMessage.create_error(
                session_id=session.id,
                error=f"Internal error: {e}",
                code="INTERNAL_ERROR",
            )
            await websocket.send(error.to_json())

    async def send_to_session(
        self, session_id: str, message: GatewayMessage
    ) -> bool:
        """Send a message to a specific session.

        Args:
            session_id: The target session ID.
            message: The message to send.

        Returns:
            True if the message was sent, False if session not found.
        """
        websocket = self._connections.get(session_id)
        if websocket is None:
            return False

        try:
            await websocket.send(message.to_json())
            return True
        except Exception as e:
            logger.error(f"Failed to send to session {session_id}: {e}")
            return False

    async def broadcast(self, message: GatewayMessage) -> int:
        """Broadcast a message to all connected sessions.

        Args:
            message: The message to broadcast.

        Returns:
            Number of sessions the message was sent to.
        """
        count = 0
        for session_id, websocket in list(self._connections.items()):
            try:
                # Update session_id in message for each recipient
                msg = GatewayMessage(
                    type=message.type,
                    session_id=session_id,
                    payload=message.payload,
                    metadata=message.metadata,
                )
                await websocket.send(msg.to_json())
                count += 1
            except Exception as e:
                logger.error(f"Broadcast failed for {session_id}: {e}")
        return count

    def get_connection_count(self) -> int:
        """Get the number of active connections."""
        return len(self._connections)
