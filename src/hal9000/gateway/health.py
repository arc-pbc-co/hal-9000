"""Health check handler for the HAL-9000 Gateway.

This module provides health check functionality for monitoring
the gateway status and system health.
"""

from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any, Optional

from hal9000 import __version__
from hal9000.gateway.protocol import GatewayMessage
from hal9000.gateway.session import Session

if TYPE_CHECKING:
    from hal9000.gateway.server import HALGateway


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class HealthChecker:
    """Health check handler that can access gateway state.

    This class provides health check responses with current gateway
    status including uptime, active sessions, and version info.
    """

    def __init__(self, gateway: Optional["HALGateway"] = None) -> None:
        """Initialize the health checker.

        Args:
            gateway: Optional reference to the gateway for status info.
        """
        self._gateway = gateway
        self._started_at = utc_now()

    def set_gateway(self, gateway: "HALGateway") -> None:
        """Set the gateway reference.

        Args:
            gateway: The gateway instance to monitor.
        """
        self._gateway = gateway

    def get_health_status(self) -> dict[str, Any]:
        """Get current health status.

        Returns:
            Dictionary containing health status information.
        """
        status: dict[str, Any] = {
            "status": "healthy",
            "version": __version__,
            "timestamp": utc_now().isoformat(),
        }

        if self._gateway is not None:
            status.update({
                "uptime_seconds": self._gateway.uptime_seconds,
                "active_sessions": self._gateway.session_manager.session_count(),
                "active_connections": self._gateway.get_connection_count(),
                "is_running": self._gateway.is_running,
            })
        else:
            # Fallback when gateway reference not available
            uptime = (utc_now() - self._started_at).total_seconds()
            status.update({
                "uptime_seconds": uptime,
                "active_sessions": 0,
                "active_connections": 0,
                "is_running": True,
            })

        return status

    async def handle_health_query(
        self, message: GatewayMessage, session: Session
    ) -> AsyncGenerator[GatewayMessage, None]:
        """Handle a health check query.

        Args:
            message: The incoming health query message.
            session: The session making the request.

        Yields:
            Response message with health status.
        """
        health_data = self.get_health_status()

        yield GatewayMessage.create_response(
            session_id=session.id,
            payload=health_data,
            metadata={"query_type": "health", "original_id": message.id},
        )


# Global health checker instance
_health_checker: Optional[HealthChecker] = None


def get_health_checker() -> HealthChecker:
    """Get or create the global health checker instance.

    Returns:
        The health checker instance.
    """
    global _health_checker
    if _health_checker is None:
        _health_checker = HealthChecker()
    return _health_checker


async def health_handler(
    message: GatewayMessage, session: Session
) -> AsyncGenerator[GatewayMessage, None]:
    """Handler function for health queries.

    This handler checks if the query is a health check and responds
    with system status. For other queries, it falls through to echo.

    Args:
        message: The incoming message.
        session: The session making the request.

    Yields:
        Response messages.
    """
    query_type = message.payload.get("query_type", "")

    if query_type == "health":
        checker = get_health_checker()
        async for response in checker.handle_health_query(message, session):
            yield response
    else:
        # Fall back to echo behavior for other queries
        yield GatewayMessage.create_response(
            session_id=session.id,
            payload={"echo": message.payload},
            metadata={"original_id": message.id},
        )
