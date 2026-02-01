"""Tests for gateway message router."""

from collections.abc import AsyncGenerator

import pytest

from hal9000.gateway.protocol import GatewayMessage, MessageType
from hal9000.gateway.router import (
    Router,
    create_router_with_defaults,
    echo_handler,
    streaming_handler,
)
from hal9000.gateway.session import Session


async def simple_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Simple test handler that yields one response."""
    yield GatewayMessage.create_response(
        session_id=session.id,
        payload={"handled": True, "type": message.type},
    )


async def multi_response_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Handler that yields multiple responses."""
    for i in range(3):
        yield GatewayMessage.create_response(
            session_id=session.id,
            payload={"index": i},
        )


async def error_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Handler that raises an exception."""
    raise ValueError("Test error")
    yield  # type: ignore  # Make it a generator


class TestRouter:
    """Tests for Router class."""

    @pytest.fixture
    def router(self) -> Router:
        """Create a fresh Router for each test."""
        return Router()

    @pytest.fixture
    def session(self) -> Session:
        """Create a test session."""
        return Session(id="test-session")

    def test_register_handler(self, router: Router) -> None:
        """Test registering a handler."""
        router.register(MessageType.COMMAND, simple_handler)
        assert router.has_handler(MessageType.COMMAND)

    def test_register_multiple_handlers(self, router: Router) -> None:
        """Test registering multiple handlers."""
        router.register(MessageType.COMMAND, simple_handler)
        router.register(MessageType.QUERY, simple_handler)
        router.register(MessageType.FEEDBACK, simple_handler)

        types = router.get_registered_types()
        assert MessageType.COMMAND in types
        assert MessageType.QUERY in types
        assert MessageType.FEEDBACK in types

    def test_unregister_handler(self, router: Router) -> None:
        """Test unregistering a handler."""
        router.register(MessageType.COMMAND, simple_handler)
        assert router.has_handler(MessageType.COMMAND)

        result = router.unregister(MessageType.COMMAND)
        assert result is True
        assert not router.has_handler(MessageType.COMMAND)

    def test_unregister_not_found(self, router: Router) -> None:
        """Test unregistering non-existent handler."""
        result = router.unregister(MessageType.COMMAND)
        assert result is False

    def test_has_handler(self, router: Router) -> None:
        """Test checking for registered handler."""
        assert not router.has_handler(MessageType.COMMAND)
        router.register(MessageType.COMMAND, simple_handler)
        assert router.has_handler(MessageType.COMMAND)

    def test_get_registered_types_empty(self, router: Router) -> None:
        """Test getting registered types when empty."""
        types = router.get_registered_types()
        assert types == []

    @pytest.mark.asyncio
    async def test_route_to_handler(self, router: Router, session: Session) -> None:
        """Test routing a message to its handler."""
        router.register(MessageType.COMMAND, simple_handler)

        message = GatewayMessage(
            type=MessageType.COMMAND,
            session_id=session.id,
            payload={"action": "test"},
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].payload["handled"] is True

    @pytest.mark.asyncio
    async def test_route_with_string_type(
        self, router: Router, session: Session
    ) -> None:
        """Test routing when message type is a string."""
        router.register(MessageType.COMMAND, simple_handler)

        # Create message manually with string type
        message = GatewayMessage(
            type=MessageType.COMMAND,
            session_id=session.id,
        )
        # The model_config uses use_enum_values=True, so type will be a string

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1

    @pytest.mark.asyncio
    async def test_route_unknown_type(self, router: Router, session: Session) -> None:
        """Test routing with no registered handler."""
        message = GatewayMessage(
            type=MessageType.COMMAND,
            session_id=session.id,
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].type == "error"
        assert "NO_HANDLER" in str(responses[0].payload)

    @pytest.mark.asyncio
    async def test_route_with_default_handler(
        self, router: Router, session: Session
    ) -> None:
        """Test routing falls back to default handler."""
        router.register_default(simple_handler)

        message = GatewayMessage(
            type=MessageType.TOOL_CALL,
            session_id=session.id,
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].payload["handled"] is True

    @pytest.mark.asyncio
    async def test_route_multi_response(
        self, router: Router, session: Session
    ) -> None:
        """Test handler that yields multiple responses."""
        router.register(MessageType.COMMAND, multi_response_handler)

        message = GatewayMessage(
            type=MessageType.COMMAND,
            session_id=session.id,
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 3
        for i, resp in enumerate(responses):
            assert resp.payload["index"] == i

    @pytest.mark.asyncio
    async def test_route_handler_error(
        self, router: Router, session: Session
    ) -> None:
        """Test that handler errors are caught and returned."""
        router.register(MessageType.COMMAND, error_handler)

        message = GatewayMessage(
            type=MessageType.COMMAND,
            session_id=session.id,
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].type == "error"
        assert "HANDLER_ERROR" in str(responses[0].payload)
        assert "Test error" in responses[0].payload["error"]


class TestEchoHandler:
    """Tests for echo_handler."""

    @pytest.fixture
    def session(self) -> Session:
        """Create a test session."""
        return Session(id="echo-session")

    @pytest.mark.asyncio
    async def test_echo_handler(self, session: Session) -> None:
        """Test echo handler echoes payload."""
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"test": "data", "number": 42},
        )

        responses = []
        async for response in echo_handler(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].type == "response"
        assert responses[0].payload["echo"] == {"test": "data", "number": 42}
        assert responses[0].metadata["original_id"] == message.id


class TestStreamingHandler:
    """Tests for streaming_handler."""

    @pytest.fixture
    def session(self) -> Session:
        """Create a test session."""
        return Session(id="stream-session")

    @pytest.mark.asyncio
    async def test_streaming_handler(self, session: Session) -> None:
        """Test streaming handler chunks content."""
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"content": "Hello, World!", "chunk_size": 5},
        )

        responses = []
        async for response in streaming_handler(message, session):
            responses.append(response)

        # "Hello, World!" = 13 chars, chunk_size=5 -> 3 chunks + 1 stream_end
        assert len(responses) == 4

        # Check chunks
        assert responses[0].type == "stream_chunk"
        assert responses[0].payload["chunk"] == "Hello"
        assert responses[1].payload["chunk"] == ", Wor"
        assert responses[2].payload["chunk"] == "ld!"

        # Check stream end
        assert responses[3].type == "stream_end"
        assert responses[3].metadata["total_chunks"] == 3

    @pytest.mark.asyncio
    async def test_streaming_handler_empty_content(self, session: Session) -> None:
        """Test streaming handler with empty content."""
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"content": ""},
        )

        responses = []
        async for response in streaming_handler(message, session):
            responses.append(response)

        # Only stream_end for empty content
        assert len(responses) == 1
        assert responses[0].type == "stream_end"


class TestCreateRouterWithDefaults:
    """Tests for create_router_with_defaults."""

    def test_creates_router_with_query_handler(self) -> None:
        """Test that default router has query handler."""
        router = create_router_with_defaults()
        assert router.has_handler(MessageType.QUERY)

    @pytest.mark.asyncio
    async def test_default_query_handler_works(self) -> None:
        """Test that default query handler works."""
        router = create_router_with_defaults()
        session = Session(id="default-test")

        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"test": "query"},
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        assert responses[0].type == "response"
