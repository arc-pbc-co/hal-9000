"""Tests for gateway WebSocket server."""

import asyncio
import json

import pytest
import websockets

from hal9000.gateway.events import EventEmitter
from hal9000.gateway.protocol import GatewayMessage, MessageType
from hal9000.gateway.router import Router
from hal9000.gateway.server import HALGateway
from hal9000.gateway.session import SessionManager


class TestHALGateway:
    """Tests for HALGateway class."""

    @pytest.fixture
    def gateway(self) -> HALGateway:
        """Create a gateway instance for testing."""
        return HALGateway(host="127.0.0.1", port=0)  # Port 0 = auto-assign

    def test_create_gateway_with_defaults(self) -> None:
        """Test creating gateway with default settings."""
        gateway = HALGateway()
        assert gateway.host == "127.0.0.1"
        assert gateway.port == 9000
        assert gateway.router is not None
        assert gateway.session_manager is not None
        assert gateway.event_emitter is not None

    def test_create_gateway_with_custom_settings(self) -> None:
        """Test creating gateway with custom settings."""
        router = Router()
        session_manager = SessionManager()
        event_emitter = EventEmitter()

        gateway = HALGateway(
            host="0.0.0.0",
            port=8080,
            router=router,
            session_manager=session_manager,
            event_emitter=event_emitter,
        )

        assert gateway.host == "0.0.0.0"
        assert gateway.port == 8080
        assert gateway.router is router
        assert gateway.session_manager is session_manager
        assert gateway.event_emitter is event_emitter

    def test_is_running_before_start(self, gateway: HALGateway) -> None:
        """Test is_running returns False before start."""
        assert gateway.is_running is False

    def test_uptime_before_start(self, gateway: HALGateway) -> None:
        """Test uptime is 0 before start."""
        assert gateway.uptime_seconds == 0.0

    def test_connection_count_initial(self, gateway: HALGateway) -> None:
        """Test connection count is 0 initially."""
        assert gateway.get_connection_count() == 0

    @pytest.mark.asyncio
    async def test_start_and_stop(self) -> None:
        """Test starting and stopping the server."""
        gateway = HALGateway(host="127.0.0.1", port=0)

        await gateway.start()
        assert gateway.is_running is True
        assert gateway.uptime_seconds > 0

        await gateway.stop()
        assert gateway.is_running is False

    @pytest.mark.asyncio
    async def test_connect_and_receive_response(self) -> None:
        """Test connecting and receiving a response."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        # Get the actual port assigned
        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                # Send a query message
                message = GatewayMessage(
                    type=MessageType.QUERY,
                    session_id="test",
                    payload={"test": "data"},
                )
                await ws.send(message.to_json())

                # Receive response
                response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = GatewayMessage.from_json(response_raw)

                # Default router echoes queries
                assert response.type == "response"
                assert "echo" in response.payload
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self) -> None:
        """Test that invalid JSON returns an error response."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                # Send invalid JSON
                await ws.send("not valid json{")

                # Should receive error
                response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = GatewayMessage.from_json(response_raw)

                assert response.type == "error"
                # Accept either error code - depends on where parsing fails
                assert response.payload["code"] in ("INVALID_JSON", "PARSE_ERROR")
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_session_created_on_connect(self) -> None:
        """Test that a session is created when a client connects."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            assert gateway.session_manager.session_count() == 0

            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                # Give server time to process connection
                await asyncio.sleep(0.1)
                assert gateway.session_manager.session_count() == 1
                assert gateway.get_connection_count() == 1

                # Send a message to keep connection alive
                message = GatewayMessage(
                    type=MessageType.QUERY,
                    session_id="test",
                    payload={},
                )
                await ws.send(message.to_json())
                await ws.recv()

            # After disconnect
            await asyncio.sleep(0.1)
            assert gateway.session_manager.session_count() == 0
            assert gateway.get_connection_count() == 0
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_multiple_connections(self) -> None:
        """Test multiple simultaneous connections."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws1:
                await asyncio.sleep(0.1)
                assert gateway.get_connection_count() == 1

                async with websockets.connect(f"ws://127.0.0.1:{port}") as ws2:
                    await asyncio.sleep(0.1)
                    assert gateway.get_connection_count() == 2

                    # Both should be able to send/receive
                    for ws in [ws1, ws2]:
                        msg = GatewayMessage(
                            type=MessageType.QUERY,
                            session_id="test",
                            payload={"from": "client"},
                        )
                        await ws.send(msg.to_json())
                        await ws.recv()

                # ws2 closed
                await asyncio.sleep(0.1)
                assert gateway.get_connection_count() == 1

            # ws1 closed
            await asyncio.sleep(0.1)
            assert gateway.get_connection_count() == 0
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_send_to_session(self) -> None:
        """Test sending a message to a specific session."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws:
                await asyncio.sleep(0.1)

                # Get the session ID
                sessions = gateway.session_manager.list_sessions()
                assert len(sessions) == 1
                session_id = sessions[0].id

                # Send message to session
                message = GatewayMessage.create_response(
                    session_id=session_id,
                    payload={"server_push": True},
                )

                result = await gateway.send_to_session(session_id, message)
                assert result is True

                # Client should receive it
                response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = GatewayMessage.from_json(response_raw)
                assert response.payload["server_push"] is True

        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_send_to_nonexistent_session(self) -> None:
        """Test sending to a session that doesn't exist."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        try:
            message = GatewayMessage.create_response(
                session_id="nonexistent",
                payload={},
            )

            result = await gateway.send_to_session("nonexistent", message)
            assert result is False
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_broadcast(self) -> None:
        """Test broadcasting a message to all connections."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            async with websockets.connect(f"ws://127.0.0.1:{port}") as ws1:
                async with websockets.connect(f"ws://127.0.0.1:{port}") as ws2:
                    await asyncio.sleep(0.1)

                    # Broadcast message
                    message = GatewayMessage(
                        type=MessageType.RESPONSE,
                        session_id="broadcast",
                        payload={"broadcast": True},
                    )

                    count = await gateway.broadcast(message)
                    assert count == 2

                    # Both clients should receive
                    for ws in [ws1, ws2]:
                        response_raw = await asyncio.wait_for(ws.recv(), timeout=5.0)
                        response = GatewayMessage.from_json(response_raw)
                        assert response.payload["broadcast"] is True
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_graceful_shutdown_closes_connections(self) -> None:
        """Test that shutdown closes all connections gracefully."""
        gateway = HALGateway(host="127.0.0.1", port=0)
        await gateway.start()

        port = gateway._server.sockets[0].getsockname()[1]  # type: ignore

        try:
            ws = await websockets.connect(f"ws://127.0.0.1:{port}")
            await asyncio.sleep(0.1)
            assert gateway.get_connection_count() == 1

            # Stop the server
            await gateway.stop()

            # Connection should be closed
            with pytest.raises(websockets.exceptions.ConnectionClosed):
                await ws.recv()
        except websockets.exceptions.ConnectionClosed:
            # Expected - server closed connection
            pass
        finally:
            if gateway.is_running:
                await gateway.stop()
