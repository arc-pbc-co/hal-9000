"""Event streaming system for the HAL-9000 Gateway.

This module provides an async event emitter for streaming events
to subscribed clients in real-time.
"""

import asyncio
import uuid
from collections.abc import AsyncGenerator
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    """Types of events emitted by the gateway."""

    # Connection events
    CONNECTION_OPENED = "connection_opened"
    CONNECTION_CLOSED = "connection_closed"
    CONNECTION_ERROR = "connection_error"

    # Session events
    SESSION_CREATED = "session_created"
    SESSION_UPDATED = "session_updated"
    SESSION_DESTROYED = "session_destroyed"

    # Message events
    MESSAGE_RECEIVED = "message_received"
    MESSAGE_SENT = "message_sent"
    MESSAGE_ERROR = "message_error"

    # Processing events
    PROCESSING_STARTED = "processing_started"
    PROCESSING_PROGRESS = "processing_progress"
    PROCESSING_COMPLETED = "processing_completed"
    PROCESSING_FAILED = "processing_failed"

    # ADAM events
    ADAM_QUERY_STARTED = "adam_query_started"
    ADAM_RESPONSE_CHUNK = "adam_response_chunk"
    ADAM_RESPONSE_COMPLETED = "adam_response_completed"

    # Tool events
    TOOL_INVOKED = "tool_invoked"
    TOOL_RESULT = "tool_result"

    # System events
    SYSTEM_STATUS = "system_status"
    SYSTEM_ERROR = "system_error"


class GatewayEvent(BaseModel):
    """An event in the gateway event stream.

    Events are emitted for various gateway activities and can be
    subscribed to by clients for real-time updates.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique event identifier",
    )
    type: EventType = Field(..., description="The type of event")
    session_id: Optional[str] = Field(
        default=None, description="Session associated with this event"
    )
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="When the event occurred",
    )
    data: dict[str, Any] = Field(
        default_factory=dict, description="Event-specific data"
    )

    model_config = ConfigDict(use_enum_values=True)


class Subscription:
    """A subscription to the event stream."""

    def __init__(
        self,
        subscriber_id: str,
        event_types: Optional[set[EventType]] = None,
        session_id: Optional[str] = None,
    ) -> None:
        """Initialize subscription.

        Args:
            subscriber_id: Unique identifier for this subscription.
            event_types: Set of event types to receive. None means all types.
            session_id: Only receive events for this session. None means all sessions.
        """
        self.subscriber_id = subscriber_id
        self.event_types = event_types
        self.session_id = session_id
        self.queue: asyncio.Queue[GatewayEvent] = asyncio.Queue()
        self.active = True

    def matches(self, event: GatewayEvent) -> bool:
        """Check if this subscription should receive the event.

        Args:
            event: The event to check.

        Returns:
            True if the subscription matches the event.
        """
        if not self.active:
            return False

        # Check event type filter
        if self.event_types is not None:
            # Need to handle both enum and string values
            event_type_value = (
                event.type.value if isinstance(event.type, EventType) else event.type
            )
            matching_types = {
                et.value if isinstance(et, EventType) else et for et in self.event_types
            }
            if event_type_value not in matching_types:
                return False

        # Check session filter
        if self.session_id is not None and event.session_id != self.session_id:
            return False

        return True


class EventEmitter:
    """Async event emitter for the gateway.

    Provides publish/subscribe functionality for gateway events
    using asyncio queues for non-blocking event delivery.
    """

    def __init__(self) -> None:
        """Initialize the event emitter."""
        self._subscriptions: dict[str, Subscription] = {}
        self._lock = asyncio.Lock()

    async def emit(self, event: GatewayEvent) -> int:
        """Emit an event to all matching subscribers.

        Args:
            event: The event to emit.

        Returns:
            Number of subscribers that received the event.
        """
        count = 0
        async with self._lock:
            for subscription in self._subscriptions.values():
                if subscription.matches(event):
                    try:
                        subscription.queue.put_nowait(event)
                        count += 1
                    except asyncio.QueueFull:
                        # Skip if queue is full to avoid blocking
                        pass
        return count

    async def emit_event(
        self,
        event_type: EventType,
        data: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> GatewayEvent:
        """Convenience method to create and emit an event.

        Args:
            event_type: The type of event.
            data: Event data.
            session_id: Associated session ID.

        Returns:
            The emitted event.
        """
        event = GatewayEvent(
            type=event_type,
            session_id=session_id,
            data=data or {},
        )
        await self.emit(event)
        return event

    def subscribe(
        self,
        subscriber_id: Optional[str] = None,
        event_types: Optional[set[EventType]] = None,
        session_id: Optional[str] = None,
    ) -> str:
        """Subscribe to events.

        Args:
            subscriber_id: Optional specific ID for the subscription.
            event_types: Set of event types to receive. None means all.
            session_id: Only receive events for this session. None means all.

        Returns:
            The subscription ID.
        """
        sub_id = subscriber_id or str(uuid.uuid4())
        subscription = Subscription(
            subscriber_id=sub_id,
            event_types=event_types,
            session_id=session_id,
        )
        self._subscriptions[sub_id] = subscription
        return sub_id

    def unsubscribe(self, subscriber_id: str) -> bool:
        """Unsubscribe from events.

        Args:
            subscriber_id: The subscription ID to remove.

        Returns:
            True if the subscription was removed, False if not found.
        """
        if subscriber_id in self._subscriptions:
            self._subscriptions[subscriber_id].active = False
            del self._subscriptions[subscriber_id]
            return True
        return False

    async def listen(
        self, subscriber_id: str, timeout: Optional[float] = None
    ) -> AsyncGenerator[GatewayEvent, None]:
        """Listen for events as an async generator.

        Args:
            subscriber_id: The subscription ID to listen on.
            timeout: Optional timeout in seconds between events.

        Yields:
            Events matching the subscription filters.
        """
        subscription = self._subscriptions.get(subscriber_id)
        if subscription is None:
            return

        while subscription.active:
            try:
                if timeout is not None:
                    event = await asyncio.wait_for(
                        subscription.queue.get(), timeout=timeout
                    )
                else:
                    event = await subscription.queue.get()
                yield event
            except asyncio.TimeoutError:
                # Allow caller to handle timeout
                continue
            except asyncio.CancelledError:
                break

    def get_subscription(self, subscriber_id: str) -> Optional[Subscription]:
        """Get a subscription by ID.

        Args:
            subscriber_id: The subscription ID.

        Returns:
            The Subscription if found, None otherwise.
        """
        return self._subscriptions.get(subscriber_id)

    def subscription_count(self) -> int:
        """Get the number of active subscriptions.

        Returns:
            The count of active subscriptions.
        """
        return len(self._subscriptions)

    async def clear_all(self) -> int:
        """Remove all subscriptions.

        Returns:
            The number of subscriptions that were removed.
        """
        async with self._lock:
            count = len(self._subscriptions)
            for subscription in self._subscriptions.values():
                subscription.active = False
            self._subscriptions.clear()
            return count
