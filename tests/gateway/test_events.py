"""Tests for gateway event streaming system."""

import asyncio
from datetime import datetime

import pytest

from hal9000.gateway.events import (
    EventEmitter,
    EventType,
    GatewayEvent,
    Subscription,
)


class TestEventType:
    """Tests for EventType enum."""

    def test_all_event_types_defined(self) -> None:
        """Verify all expected event types are defined."""
        expected = {
            "connection_opened",
            "connection_closed",
            "connection_error",
            "session_created",
            "session_updated",
            "session_destroyed",
            "message_received",
            "message_sent",
            "message_error",
            "processing_started",
            "processing_progress",
            "processing_completed",
            "processing_failed",
            "adam_query_started",
            "adam_response_chunk",
            "adam_response_completed",
            "tool_invoked",
            "tool_result",
            "system_status",
            "system_error",
        }
        actual = {et.value for et in EventType}
        assert actual == expected

    def test_event_type_is_string_enum(self) -> None:
        """Verify EventType values are strings."""
        for et in EventType:
            assert isinstance(et.value, str)


class TestGatewayEvent:
    """Tests for GatewayEvent model."""

    def test_create_event_with_required_fields(self) -> None:
        """Test creating an event with required fields."""
        event = GatewayEvent(type=EventType.SESSION_CREATED)
        assert event.id is not None
        assert event.type == EventType.SESSION_CREATED.value
        assert event.session_id is None
        assert event.timestamp is not None
        assert event.data == {}

    def test_create_event_with_all_fields(self) -> None:
        """Test creating an event with all fields."""
        timestamp = datetime(2026, 2, 1, 10, 0, 0)
        event = GatewayEvent(
            id="evt-123",
            type=EventType.MESSAGE_RECEIVED,
            session_id="sess-456",
            timestamp=timestamp,
            data={"message": "hello"},
        )
        assert event.id == "evt-123"
        assert event.type == EventType.MESSAGE_RECEIVED.value
        assert event.session_id == "sess-456"
        assert event.timestamp == timestamp
        assert event.data["message"] == "hello"

    def test_event_auto_generates_id(self) -> None:
        """Test that event IDs are auto-generated."""
        event1 = GatewayEvent(type=EventType.SYSTEM_STATUS)
        event2 = GatewayEvent(type=EventType.SYSTEM_STATUS)
        assert event1.id != event2.id

    def test_event_serialization(self) -> None:
        """Test event JSON serialization."""
        event = GatewayEvent(
            type=EventType.TOOL_RESULT,
            session_id="sess-test",
            data={"result": "success"},
        )
        json_str = event.model_dump_json()
        assert "tool_result" in json_str
        assert "sess-test" in json_str


class TestSubscription:
    """Tests for Subscription class."""

    def test_create_subscription_default(self) -> None:
        """Test creating subscription with defaults."""
        sub = Subscription(subscriber_id="sub-1")
        assert sub.subscriber_id == "sub-1"
        assert sub.event_types is None
        assert sub.session_id is None
        assert sub.active is True

    def test_create_subscription_with_filters(self) -> None:
        """Test creating subscription with filters."""
        sub = Subscription(
            subscriber_id="sub-2",
            event_types={EventType.SESSION_CREATED, EventType.SESSION_DESTROYED},
            session_id="sess-filter",
        )
        assert sub.event_types is not None
        assert EventType.SESSION_CREATED in sub.event_types
        assert sub.session_id == "sess-filter"

    def test_matches_no_filters(self) -> None:
        """Test matching with no filters (match all)."""
        sub = Subscription(subscriber_id="sub-all")
        event = GatewayEvent(
            type=EventType.MESSAGE_RECEIVED, session_id="any-session"
        )
        assert sub.matches(event) is True

    def test_matches_event_type_filter(self) -> None:
        """Test matching with event type filter."""
        sub = Subscription(
            subscriber_id="sub-type",
            event_types={EventType.MESSAGE_RECEIVED},
        )
        matching = GatewayEvent(type=EventType.MESSAGE_RECEIVED)
        non_matching = GatewayEvent(type=EventType.SESSION_CREATED)

        assert sub.matches(matching) is True
        assert sub.matches(non_matching) is False

    def test_matches_session_filter(self) -> None:
        """Test matching with session filter."""
        sub = Subscription(subscriber_id="sub-sess", session_id="target-session")
        matching = GatewayEvent(
            type=EventType.MESSAGE_RECEIVED, session_id="target-session"
        )
        non_matching = GatewayEvent(
            type=EventType.MESSAGE_RECEIVED, session_id="other-session"
        )

        assert sub.matches(matching) is True
        assert sub.matches(non_matching) is False

    def test_matches_combined_filters(self) -> None:
        """Test matching with both event type and session filters."""
        sub = Subscription(
            subscriber_id="sub-both",
            event_types={EventType.MESSAGE_RECEIVED},
            session_id="target",
        )

        # Matches both
        event1 = GatewayEvent(type=EventType.MESSAGE_RECEIVED, session_id="target")
        assert sub.matches(event1) is True

        # Wrong session
        event2 = GatewayEvent(type=EventType.MESSAGE_RECEIVED, session_id="other")
        assert sub.matches(event2) is False

        # Wrong type
        event3 = GatewayEvent(type=EventType.SESSION_CREATED, session_id="target")
        assert sub.matches(event3) is False

    def test_matches_inactive_subscription(self) -> None:
        """Test that inactive subscriptions don't match."""
        sub = Subscription(subscriber_id="sub-inactive")
        sub.active = False
        event = GatewayEvent(type=EventType.MESSAGE_RECEIVED)
        assert sub.matches(event) is False


class TestEventEmitter:
    """Tests for EventEmitter class."""

    @pytest.fixture
    def emitter(self) -> EventEmitter:
        """Create a fresh EventEmitter for each test."""
        return EventEmitter()

    def test_subscribe(self, emitter: EventEmitter) -> None:
        """Test subscribing to events."""
        sub_id = emitter.subscribe()
        assert sub_id is not None
        assert emitter.subscription_count() == 1

    def test_subscribe_with_custom_id(self, emitter: EventEmitter) -> None:
        """Test subscribing with a specific ID."""
        sub_id = emitter.subscribe(subscriber_id="custom-sub")
        assert sub_id == "custom-sub"

    def test_subscribe_with_filters(self, emitter: EventEmitter) -> None:
        """Test subscribing with filters."""
        sub_id = emitter.subscribe(
            event_types={EventType.SESSION_CREATED},
            session_id="sess-filter",
        )
        subscription = emitter.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.event_types is not None
        assert subscription.session_id == "sess-filter"

    def test_unsubscribe(self, emitter: EventEmitter) -> None:
        """Test unsubscribing."""
        sub_id = emitter.subscribe()
        assert emitter.subscription_count() == 1

        result = emitter.unsubscribe(sub_id)
        assert result is True
        assert emitter.subscription_count() == 0

    def test_unsubscribe_not_found(self, emitter: EventEmitter) -> None:
        """Test unsubscribing non-existent subscription."""
        result = emitter.unsubscribe("nonexistent")
        assert result is False

    @pytest.mark.asyncio
    async def test_emit_event(self, emitter: EventEmitter) -> None:
        """Test emitting an event."""
        sub_id = emitter.subscribe()
        event = GatewayEvent(type=EventType.SESSION_CREATED)

        count = await emitter.emit(event)
        assert count == 1

        subscription = emitter.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_emit_event_helper(self, emitter: EventEmitter) -> None:
        """Test emit_event convenience method."""
        sub_id = emitter.subscribe()
        event = await emitter.emit_event(
            EventType.MESSAGE_SENT,
            data={"content": "test"},
            session_id="sess-1",
        )

        assert event.type == EventType.MESSAGE_SENT.value
        assert event.data["content"] == "test"
        assert event.session_id == "sess-1"

        subscription = emitter.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.queue.qsize() == 1

    @pytest.mark.asyncio
    async def test_emit_with_filters(self, emitter: EventEmitter) -> None:
        """Test that emit respects subscription filters."""
        # Subscribe to only SESSION events
        sub_id = emitter.subscribe(
            event_types={EventType.SESSION_CREATED, EventType.SESSION_DESTROYED}
        )

        # Emit different event types
        await emitter.emit(GatewayEvent(type=EventType.SESSION_CREATED))
        await emitter.emit(GatewayEvent(type=EventType.MESSAGE_RECEIVED))
        await emitter.emit(GatewayEvent(type=EventType.SESSION_DESTROYED))

        subscription = emitter.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.queue.qsize() == 2  # Only session events

    @pytest.mark.asyncio
    async def test_listen_generator(self, emitter: EventEmitter) -> None:
        """Test listening for events as async generator."""
        sub_id = emitter.subscribe()

        # Emit events before listening
        await emitter.emit_event(EventType.SESSION_CREATED, data={"num": 1})
        await emitter.emit_event(EventType.SESSION_CREATED, data={"num": 2})

        received: list[GatewayEvent] = []
        async for event in emitter.listen(sub_id, timeout=0.1):
            received.append(event)
            if len(received) >= 2:
                emitter.unsubscribe(sub_id)
                break

        assert len(received) == 2
        assert received[0].data["num"] == 1
        assert received[1].data["num"] == 2

    @pytest.mark.asyncio
    async def test_listen_nonexistent_subscription(self, emitter: EventEmitter) -> None:
        """Test listening on non-existent subscription."""
        received = []
        async for event in emitter.listen("nonexistent"):
            received.append(event)

        assert received == []

    @pytest.mark.asyncio
    async def test_clear_all(self, emitter: EventEmitter) -> None:
        """Test clearing all subscriptions."""
        emitter.subscribe()
        emitter.subscribe()
        emitter.subscribe()

        count = await emitter.clear_all()
        assert count == 3
        assert emitter.subscription_count() == 0

    def test_get_subscription(self, emitter: EventEmitter) -> None:
        """Test getting a subscription by ID."""
        sub_id = emitter.subscribe()
        subscription = emitter.get_subscription(sub_id)
        assert subscription is not None
        assert subscription.subscriber_id == sub_id

    def test_get_subscription_not_found(self, emitter: EventEmitter) -> None:
        """Test getting non-existent subscription."""
        subscription = emitter.get_subscription("nonexistent")
        assert subscription is None

    @pytest.mark.asyncio
    async def test_multiple_subscribers(self, emitter: EventEmitter) -> None:
        """Test emitting to multiple subscribers."""
        sub1 = emitter.subscribe()
        sub2 = emitter.subscribe()
        sub3 = emitter.subscribe()

        event = GatewayEvent(type=EventType.SYSTEM_STATUS)
        count = await emitter.emit(event)

        assert count == 3
        assert emitter.get_subscription(sub1).queue.qsize() == 1  # type: ignore
        assert emitter.get_subscription(sub2).queue.qsize() == 1  # type: ignore
        assert emitter.get_subscription(sub3).queue.qsize() == 1  # type: ignore

    @pytest.mark.asyncio
    async def test_concurrent_emit_and_subscribe(self, emitter: EventEmitter) -> None:
        """Test concurrent operations are safe."""

        async def subscriber() -> str:
            return emitter.subscribe()

        async def emit_events() -> None:
            for _ in range(10):
                await emitter.emit_event(EventType.PROCESSING_PROGRESS)

        # Run concurrently
        results = await asyncio.gather(
            subscriber(),
            subscriber(),
            emit_events(),
        )

        # Both subscribers should be registered
        assert emitter.subscription_count() >= 2
