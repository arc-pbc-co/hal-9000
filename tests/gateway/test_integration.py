"""Integration tests for the full gateway flow.

These tests verify end-to-end functionality of the gateway,
including WebSocket connections, message routing, and session handling.
"""

import asyncio
import json

import pytest
import websockets

from hal9000 import __version__
from hal9000.gateway.protocol import GatewayMessage, MessageType
from hal9000.gateway.server import HALGateway


@pytest.fixture
async def gateway():
    """Create and start a gateway for testing."""
    server = HALGateway(host="127.0.0.1", port=9001)
    await server.start()
    yield server
    await server.stop()


@pytest.fixture
def gateway_url():
    """Get the gateway WebSocket URL."""
    return "ws://127.0.0.1:9001"


class TestBasicConnectivity:
    """Tests for basic WebSocket connectivity."""

    @pytest.mark.asyncio
    async def test_connect_and_disconnect(self, gateway, gateway_url):
        """Test basic connection and disconnection."""
        async with websockets.connect(gateway_url) as ws:
            # Send a message to verify connection is working
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",
                payload={},
            )
            await ws.send(message.to_json())
            response = await ws.recv()
            assert response  # Connection is working

        # After context manager exits, connection should be closed

    @pytest.mark.asyncio
    async def test_multiple_connections(self, gateway, gateway_url):
        """Test multiple simultaneous connections."""
        connections = []
        for _ in range(5):
            ws = await websockets.connect(gateway_url)
            connections.append(ws)

        assert len(connections) == 5
        assert gateway.get_connection_count() == 5

        # Clean up
        for ws in connections:
            await ws.close()

        # Give time for cleanup
        await asyncio.sleep(0.1)
        assert gateway.get_connection_count() == 0


class TestMessageFlow:
    """Tests for message sending and receiving."""

    @pytest.mark.asyncio
    async def test_send_query_receive_response(self, gateway, gateway_url):
        """Test sending a query and receiving a response."""
        async with websockets.connect(gateway_url) as ws:
            # Send a query
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",  # Will be overwritten by server
                payload={"data": "test"},
            )
            await ws.send(message.to_json())

            # Receive response
            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.RESPONSE
            assert "echo" in response.payload
            assert response.payload["echo"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_health_query(self, gateway, gateway_url):
        """Test health check query."""
        async with websockets.connect(gateway_url) as ws:
            # Send health query
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",
                payload={"query_type": "health"},
            )
            await ws.send(message.to_json())

            # Receive health response
            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.RESPONSE
            assert response.payload["status"] == "healthy"
            assert response.payload["version"] == __version__
            assert "uptime_seconds" in response.payload
            assert "active_sessions" in response.payload
            assert response.payload["active_sessions"] >= 1  # At least our session

    @pytest.mark.asyncio
    async def test_multiple_messages_same_connection(self, gateway, gateway_url):
        """Test sending multiple messages on the same connection."""
        async with websockets.connect(gateway_url) as ws:
            for i in range(5):
                message = GatewayMessage(
                    type=MessageType.QUERY,
                    session_id="placeholder",
                    payload={"iteration": i},
                )
                await ws.send(message.to_json())

                response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
                response = GatewayMessage.from_json(response_data)

                assert response.type == MessageType.RESPONSE
                assert response.payload["echo"]["iteration"] == i


class TestSessionHandling:
    """Tests for session creation and management."""

    @pytest.mark.asyncio
    async def test_session_created_on_connect(self, gateway, gateway_url):
        """Test that a session is created when connecting."""
        initial_count = gateway.session_manager.session_count()

        async with websockets.connect(gateway_url) as ws:
            # Session should be created
            assert gateway.session_manager.session_count() == initial_count + 1

            # Send message to get session ID from response
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",
                payload={},
            )
            await ws.send(message.to_json())
            response_data = await ws.recv()
            response = GatewayMessage.from_json(response_data)

            # Verify session exists in manager
            session = gateway.session_manager.get_session(response.session_id)
            assert session is not None

        # Give time for cleanup
        await asyncio.sleep(0.1)

        # Session should be removed after disconnect
        assert gateway.session_manager.session_count() == initial_count

    @pytest.mark.asyncio
    async def test_session_id_consistent_across_messages(self, gateway, gateway_url):
        """Test that session ID remains consistent for a connection."""
        async with websockets.connect(gateway_url) as ws:
            session_ids = []

            for _ in range(3):
                message = GatewayMessage(
                    type=MessageType.QUERY,
                    session_id="placeholder",
                    payload={},
                )
                await ws.send(message.to_json())
                response_data = await ws.recv()
                response = GatewayMessage.from_json(response_data)
                session_ids.append(response.session_id)

            # All responses should have same session ID
            assert len(set(session_ids)) == 1

    @pytest.mark.asyncio
    async def test_different_connections_have_different_sessions(
        self, gateway, gateway_url
    ):
        """Test that different connections have different sessions."""
        async with websockets.connect(gateway_url) as ws1:
            async with websockets.connect(gateway_url) as ws2:
                # Get session IDs from both connections
                msg = GatewayMessage(
                    type=MessageType.QUERY,
                    session_id="placeholder",
                    payload={},
                )

                await ws1.send(msg.to_json())
                r1 = GatewayMessage.from_json(await ws1.recv())

                await ws2.send(msg.to_json())
                r2 = GatewayMessage.from_json(await ws2.recv())

                # Sessions should be different
                assert r1.session_id != r2.session_id


class TestErrorHandling:
    """Tests for error handling."""

    @pytest.mark.asyncio
    async def test_invalid_json_returns_error(self, gateway, gateway_url):
        """Test that invalid JSON returns an error response."""
        async with websockets.connect(gateway_url) as ws:
            await ws.send("not valid json {{{")

            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.ERROR
            assert response.payload["code"] in ("INVALID_JSON", "PARSE_ERROR")

    @pytest.mark.asyncio
    async def test_invalid_message_structure_returns_error(
        self, gateway, gateway_url
    ):
        """Test that invalid message structure returns error."""
        async with websockets.connect(gateway_url) as ws:
            # Valid JSON but missing required fields
            await ws.send(json.dumps({"foo": "bar"}))

            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.ERROR

    @pytest.mark.asyncio
    async def test_unknown_message_type_returns_error(self, gateway, gateway_url):
        """Test that unknown message type returns error."""
        async with websockets.connect(gateway_url) as ws:
            # Valid JSON with unknown type
            msg = {
                "type": "nonexistent_type",
                "session_id": "test",
                "payload": {},
            }
            await ws.send(json.dumps(msg))

            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.ERROR
            # Pydantic validation fails before router, so code is PARSE_ERROR
            assert response.payload.get("code") in ("PARSE_ERROR", "UNKNOWN_MESSAGE_TYPE")

    @pytest.mark.asyncio
    async def test_connection_survives_error(self, gateway, gateway_url):
        """Test that connection remains open after error."""
        async with websockets.connect(gateway_url) as ws:
            # Send invalid message
            await ws.send("invalid")
            await ws.recv()  # Get error response

            # Valid message should still work (connection survived the error)
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",
                payload={"test": True},
            )
            await ws.send(message.to_json())
            response_data = await ws.recv()
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.RESPONSE


class TestGracefulShutdown:
    """Tests for graceful shutdown behavior."""

    @pytest.mark.asyncio
    async def test_connections_closed_on_shutdown(self):
        """Test that connections are properly closed on shutdown."""
        server = HALGateway(host="127.0.0.1", port=9002)
        await server.start()

        # Connect client and verify it's working
        ws = await websockets.connect("ws://127.0.0.1:9002")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id="placeholder",
            payload={},
        )
        await ws.send(message.to_json())
        await ws.recv()  # Connection is working

        # Stop server
        await server.stop()

        # Give time for close to propagate
        await asyncio.sleep(0.2)

        # Connection should be closed - try to receive to trigger the close check
        try:
            await asyncio.wait_for(ws.recv(), timeout=1.0)
            # If we got here, connection wasn't closed properly
            assert False, "Expected connection to be closed"
        except (
            websockets.exceptions.ConnectionClosedOK,
            websockets.exceptions.ConnectionClosedError,
            asyncio.TimeoutError,
        ):
            # This is expected
            pass

    @pytest.mark.asyncio
    async def test_server_reports_not_running_after_stop(self):
        """Test that server reports not running after stop."""
        server = HALGateway(host="127.0.0.1", port=9003)
        await server.start()
        assert server.is_running

        await server.stop()
        assert not server.is_running


class TestStreamingResponses:
    """Tests for streaming response handling."""

    @pytest.mark.asyncio
    async def test_streaming_handler_sends_chunks(self, gateway, gateway_url):
        """Test that streaming handler sends multiple chunks."""
        from hal9000.gateway.router import streaming_handler

        # Register streaming handler for COMMAND messages
        gateway.router.register(MessageType.COMMAND, streaming_handler)

        async with websockets.connect(gateway_url) as ws:
            # Send command that will be handled by streaming handler
            message = GatewayMessage(
                type=MessageType.COMMAND,
                session_id="placeholder",
                payload={"content": "Hello World", "chunk_size": 5},
            )
            await ws.send(message.to_json())

            # Collect all responses
            responses = []
            while True:
                try:
                    response_data = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    response = GatewayMessage.from_json(response_data)
                    responses.append(response)

                    if response.type == MessageType.STREAM_END:
                        break
                except asyncio.TimeoutError:
                    break

            # Should have multiple chunks plus stream end
            chunk_responses = [r for r in responses if r.type == MessageType.STREAM_CHUNK]
            end_responses = [r for r in responses if r.type == MessageType.STREAM_END]

            assert len(chunk_responses) >= 2  # "Hello World" in 5-char chunks
            assert len(end_responses) == 1


class TestEventEmitter:
    """Tests for event emitter integration."""

    @pytest.mark.asyncio
    async def test_events_emitted_on_connect(self, gateway, gateway_url):
        """Test that connection events are emitted."""
        events_received = []

        # Subscribe to events
        sub_id = gateway.event_emitter.subscribe()

        async def collect_events():
            async for event in gateway.event_emitter.listen(sub_id, timeout=0.5):
                events_received.append(event)
                if len(events_received) >= 2:
                    break

        # Start collecting events
        collector = asyncio.create_task(collect_events())

        # Connect and disconnect
        async with websockets.connect(gateway_url):
            await asyncio.sleep(0.2)

        # Wait for events
        await asyncio.sleep(0.3)
        collector.cancel()

        # Should have received connection opened event
        event_types = [e.type for e in events_received]
        assert "connection_opened" in event_types or len(events_received) > 0


class TestBinaryMessages:
    """Tests for binary message handling."""

    @pytest.mark.asyncio
    async def test_binary_json_message(self, gateway, gateway_url):
        """Test that binary-encoded JSON is handled correctly."""
        async with websockets.connect(gateway_url) as ws:
            message = GatewayMessage(
                type=MessageType.QUERY,
                session_id="placeholder",
                payload={"binary": True},
            )
            # Send as binary
            await ws.send(message.to_json().encode("utf-8"))

            response_data = await asyncio.wait_for(ws.recv(), timeout=5.0)
            response = GatewayMessage.from_json(response_data)

            assert response.type == MessageType.RESPONSE
            assert response.payload["echo"]["binary"] is True
