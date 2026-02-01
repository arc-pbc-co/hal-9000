"""Tests for gateway health check functionality."""

import pytest

from hal9000 import __version__
from hal9000.gateway.health import (
    HealthChecker,
    get_health_checker,
    health_handler,
)
from hal9000.gateway.protocol import GatewayMessage, MessageType
from hal9000.gateway.session import Session, SessionManager


class TestHealthChecker:
    """Tests for HealthChecker class."""

    def test_init_without_gateway(self):
        """Test initialization without gateway reference."""
        checker = HealthChecker()

        assert checker._gateway is None

    def test_init_with_gateway(self):
        """Test initialization with gateway reference."""
        # Using None as mock since we just test reference storage
        mock_gateway = object()
        checker = HealthChecker(gateway=mock_gateway)  # type: ignore

        assert checker._gateway is mock_gateway

    def test_set_gateway(self):
        """Test setting gateway reference after init."""
        checker = HealthChecker()
        mock_gateway = object()

        checker.set_gateway(mock_gateway)  # type: ignore

        assert checker._gateway is mock_gateway

    def test_get_health_status_without_gateway(self):
        """Test health status without gateway reference."""
        checker = HealthChecker()
        checker._gateway = None

        status = checker.get_health_status()

        assert status["status"] == "healthy"
        assert status["version"] == __version__
        assert "timestamp" in status
        assert "uptime_seconds" in status
        assert status["active_sessions"] == 0
        assert status["active_connections"] == 0
        assert status["is_running"] is True

    def test_get_health_status_with_gateway(self):
        """Test health status with gateway reference."""
        from hal9000.gateway.server import HALGateway

        gateway = HALGateway()
        checker = HealthChecker(gateway=gateway)

        status = checker.get_health_status()

        assert status["status"] == "healthy"
        assert status["version"] == __version__
        assert "uptime_seconds" in status
        assert status["active_sessions"] == 0
        assert status["active_connections"] == 0

    def test_health_status_version_matches(self):
        """Test that version matches package version."""
        checker = HealthChecker()

        status = checker.get_health_status()

        assert status["version"] == __version__

    @pytest.mark.asyncio
    async def test_handle_health_query(self):
        """Test handling health query message."""
        checker = HealthChecker()
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"query_type": "health"},
        )

        responses = []
        async for response in checker.handle_health_query(message, session):
            responses.append(response)

        assert len(responses) == 1
        response = responses[0]
        assert response.type == MessageType.RESPONSE
        assert response.session_id == session.id
        assert response.payload["status"] == "healthy"
        assert response.payload["version"] == __version__
        assert response.metadata["query_type"] == "health"


class TestGetHealthChecker:
    """Tests for get_health_checker function."""

    def test_returns_instance(self):
        """Test that get_health_checker returns an instance."""
        import hal9000.gateway.health as health_module
        health_module._health_checker = None

        checker = get_health_checker()

        assert isinstance(checker, HealthChecker)

    def test_returns_singleton(self):
        """Test that get_health_checker returns same instance."""
        import hal9000.gateway.health as health_module
        health_module._health_checker = None

        checker1 = get_health_checker()
        checker2 = get_health_checker()

        assert checker1 is checker2


class TestHealthHandler:
    """Tests for health_handler function."""

    @pytest.mark.asyncio
    async def test_health_query_returns_status(self):
        """Test that health query returns health status."""
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"query_type": "health"},
        )

        responses = []
        async for response in health_handler(message, session):
            responses.append(response)

        assert len(responses) == 1
        response = responses[0]
        assert response.type == MessageType.RESPONSE
        assert response.payload["status"] == "healthy"
        assert response.payload["version"] == __version__
        assert "uptime_seconds" in response.payload
        assert "active_sessions" in response.payload

    @pytest.mark.asyncio
    async def test_non_health_query_returns_echo(self):
        """Test that non-health queries fall back to echo."""
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"query_type": "other", "data": "test"},
        )

        responses = []
        async for response in health_handler(message, session):
            responses.append(response)

        assert len(responses) == 1
        response = responses[0]
        assert response.type == MessageType.RESPONSE
        assert "echo" in response.payload
        assert response.payload["echo"]["query_type"] == "other"
        assert response.payload["echo"]["data"] == "test"

    @pytest.mark.asyncio
    async def test_query_without_type_returns_echo(self):
        """Test that query without type returns echo."""
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"foo": "bar"},
        )

        responses = []
        async for response in health_handler(message, session):
            responses.append(response)

        assert len(responses) == 1
        response = responses[0]
        assert response.type == MessageType.RESPONSE
        assert "echo" in response.payload
        assert response.payload["echo"]["foo"] == "bar"

    @pytest.mark.asyncio
    async def test_empty_health_query(self):
        """Test health query with empty payload."""
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={},
        )

        responses = []
        async for response in health_handler(message, session):
            responses.append(response)

        # Empty payload falls back to echo
        assert len(responses) == 1
        assert "echo" in responses[0].payload


class TestHealthIntegration:
    """Integration tests for health check with gateway."""

    @pytest.mark.asyncio
    async def test_gateway_registers_with_health_checker(self):
        """Test that gateway sets itself on health checker."""
        from hal9000.gateway.server import HALGateway
        import hal9000.gateway.health as health_module

        # Reset health checker
        health_module._health_checker = None

        # Create gateway
        gateway = HALGateway()

        # Health checker should have gateway reference
        checker = get_health_checker()
        assert checker._gateway is gateway

    @pytest.mark.asyncio
    async def test_health_status_with_active_gateway(self):
        """Test health status reflects running gateway."""
        from hal9000.gateway.server import HALGateway
        import hal9000.gateway.health as health_module

        # Reset health checker
        health_module._health_checker = None

        gateway = HALGateway()
        await gateway.start()

        try:
            checker = get_health_checker()
            status = checker.get_health_status()

            assert status["is_running"] is True
            assert status["active_sessions"] == 0
            assert status["uptime_seconds"] >= 0
        finally:
            await gateway.stop()

    @pytest.mark.asyncio
    async def test_health_via_router(self):
        """Test health check through router."""
        from hal9000.gateway.router import create_router_with_defaults

        router = create_router_with_defaults()
        session = Session(id="test-session", channel="test")
        message = GatewayMessage(
            type=MessageType.QUERY,
            session_id=session.id,
            payload={"query_type": "health"},
        )

        responses = []
        async for response in router.route(message, session):
            responses.append(response)

        assert len(responses) == 1
        response = responses[0]
        assert response.payload["status"] == "healthy"
        assert response.payload["version"] == __version__
