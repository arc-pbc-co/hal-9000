"""Tests for gateway protocol definitions."""

import json
from datetime import datetime

import pytest

from hal9000.gateway.protocol import (
    ADAMPromptPayload,
    GatewayMessage,
    MessageType,
)


class TestMessageType:
    """Tests for MessageType enum."""

    def test_all_message_types_defined(self) -> None:
        """Verify all required message types are defined."""
        expected_types = {
            "command",
            "query",
            "tool_call",
            "feedback",
            "response",
            "stream_chunk",
            "stream_end",
            "tool_result",
            "error",
            "adam_prompt",
            "adam_context",
            "adam_feedback",
        }
        actual_types = {mt.value for mt in MessageType}
        assert actual_types == expected_types

    def test_message_type_is_string_enum(self) -> None:
        """Verify MessageType values are strings."""
        for mt in MessageType:
            assert isinstance(mt.value, str)


class TestADAMPromptPayload:
    """Tests for ADAMPromptPayload model."""

    def test_create_minimal_payload(self) -> None:
        """Test creating payload with only required fields."""
        payload = ADAMPromptPayload(topic_focus="HEA synthesis methods")
        assert payload.topic_focus == "HEA synthesis methods"
        assert payload.materials_of_interest == []
        assert payload.constraints == []
        assert payload.objectives == []
        assert payload.literature_context is None
        assert payload.experiment_context is None

    def test_create_full_payload(self) -> None:
        """Test creating payload with all fields."""
        payload = ADAMPromptPayload(
            topic_focus="Nickel superalloy creep resistance",
            literature_context={
                "key_findings": ["Finding 1", "Finding 2"],
                "gaps": ["Gap 1"],
            },
            materials_of_interest=["Mar-M 247", "CM 247 LC"],
            experiment_context={
                "temperature": 982,
                "stress": 152,
                "unit": "MPa",
            },
            constraints=["Budget limit", "Time constraint"],
            objectives=["Improve creep life", "Reduce cost"],
        )
        assert payload.topic_focus == "Nickel superalloy creep resistance"
        assert len(payload.materials_of_interest) == 2
        assert len(payload.constraints) == 2
        assert len(payload.objectives) == 2
        assert payload.literature_context is not None
        assert payload.experiment_context is not None

    def test_payload_serialization(self) -> None:
        """Test payload JSON serialization."""
        payload = ADAMPromptPayload(
            topic_focus="Test topic",
            materials_of_interest=["Material A"],
        )
        json_str = payload.model_dump_json()
        data = json.loads(json_str)
        assert data["topic_focus"] == "Test topic"
        assert data["materials_of_interest"] == ["Material A"]


class TestGatewayMessage:
    """Tests for GatewayMessage model."""

    def test_create_message_with_required_fields(self) -> None:
        """Test creating a message with required fields."""
        msg = GatewayMessage(
            type=MessageType.QUERY,
            session_id="sess-123",
        )
        assert msg.type == MessageType.QUERY.value
        assert msg.session_id == "sess-123"
        assert msg.id is not None
        assert msg.timestamp is not None
        assert msg.payload == {}
        assert msg.metadata == {}

    def test_create_message_with_all_fields(self) -> None:
        """Test creating a message with all fields."""
        timestamp = datetime(2026, 2, 1, 10, 0, 0)
        msg = GatewayMessage(
            id="msg-456",
            type=MessageType.COMMAND,
            session_id="sess-789",
            timestamp=timestamp,
            payload={"action": "search", "query": "HEA synthesis"},
            metadata={"trace_id": "trace-001"},
        )
        assert msg.id == "msg-456"
        assert msg.type == MessageType.COMMAND.value
        assert msg.session_id == "sess-789"
        assert msg.timestamp == timestamp
        assert msg.payload["action"] == "search"
        assert msg.metadata["trace_id"] == "trace-001"

    def test_message_auto_generates_id(self) -> None:
        """Test that message IDs are auto-generated."""
        msg1 = GatewayMessage(type=MessageType.QUERY, session_id="sess-1")
        msg2 = GatewayMessage(type=MessageType.QUERY, session_id="sess-1")
        assert msg1.id != msg2.id

    def test_message_auto_generates_timestamp(self) -> None:
        """Test that timestamps are auto-generated."""
        msg = GatewayMessage(type=MessageType.QUERY, session_id="sess-1")
        assert isinstance(msg.timestamp, datetime)

    def test_to_json(self) -> None:
        """Test message JSON serialization."""
        msg = GatewayMessage(
            id="msg-test",
            type=MessageType.RESPONSE,
            session_id="sess-test",
            payload={"result": "success"},
        )
        json_str = msg.to_json()
        data = json.loads(json_str)
        assert data["id"] == "msg-test"
        assert data["type"] == "response"
        assert data["session_id"] == "sess-test"
        assert data["payload"]["result"] == "success"

    def test_from_json(self) -> None:
        """Test message JSON deserialization."""
        json_str = json.dumps({
            "id": "msg-from-json",
            "type": "query",
            "session_id": "sess-from-json",
            "timestamp": "2026-02-01T10:00:00",
            "payload": {"query": "test"},
            "metadata": {},
        })
        msg = GatewayMessage.from_json(json_str)
        assert msg.id == "msg-from-json"
        assert msg.type == "query"
        assert msg.session_id == "sess-from-json"
        assert msg.payload["query"] == "test"

    def test_roundtrip_serialization(self) -> None:
        """Test message serialization roundtrip."""
        original = GatewayMessage(
            type=MessageType.TOOL_CALL,
            session_id="sess-roundtrip",
            payload={"tool": "search", "args": {"query": "test"}},
            metadata={"version": "1.0"},
        )
        json_str = original.to_json()
        restored = GatewayMessage.from_json(json_str)
        assert restored.id == original.id
        assert restored.type == original.type
        assert restored.session_id == original.session_id
        assert restored.payload == original.payload
        assert restored.metadata == original.metadata

    def test_create_response_helper(self) -> None:
        """Test create_response factory method."""
        msg = GatewayMessage.create_response(
            session_id="sess-resp",
            payload={"data": "result"},
            metadata={"trace": "123"},
        )
        assert msg.type == "response"
        assert msg.session_id == "sess-resp"
        assert msg.payload["data"] == "result"
        assert msg.metadata["trace"] == "123"

    def test_create_error_helper(self) -> None:
        """Test create_error factory method."""
        msg = GatewayMessage.create_error(
            session_id="sess-err",
            error="Something went wrong",
            code="ERR_001",
        )
        assert msg.type == "error"
        assert msg.session_id == "sess-err"
        assert msg.payload["error"] == "Something went wrong"
        assert msg.payload["code"] == "ERR_001"

    def test_create_stream_chunk_helper(self) -> None:
        """Test create_stream_chunk factory method."""
        msg = GatewayMessage.create_stream_chunk(
            session_id="sess-stream",
            chunk="Hello, ",
        )
        assert msg.type == "stream_chunk"
        assert msg.session_id == "sess-stream"
        assert msg.payload["chunk"] == "Hello, "

    def test_create_stream_end_helper(self) -> None:
        """Test create_stream_end factory method."""
        msg = GatewayMessage.create_stream_end(session_id="sess-stream")
        assert msg.type == "stream_end"
        assert msg.session_id == "sess-stream"
        assert msg.payload == {}


class TestMessageTypeValidation:
    """Tests for message type validation."""

    def test_invalid_message_type_raises_error(self) -> None:
        """Test that invalid message types raise validation error."""
        with pytest.raises(ValueError):
            GatewayMessage(
                type="invalid_type",  # type: ignore
                session_id="sess-1",
            )

    def test_all_message_types_valid_in_message(self) -> None:
        """Test that all MessageType values work in GatewayMessage."""
        for mt in MessageType:
            msg = GatewayMessage(type=mt, session_id="sess-test")
            assert msg.type == mt.value
