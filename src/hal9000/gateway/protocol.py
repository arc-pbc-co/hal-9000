"""Protocol definitions for the HAL-9000 Gateway.

This module defines the message types and Pydantic models used for
WebSocket communication between clients and the HAL-9000 gateway.
"""

import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class MessageType(str, Enum):
    """Types of messages in the gateway protocol."""

    # Client -> Gateway
    COMMAND = "command"
    QUERY = "query"
    TOOL_CALL = "tool_call"
    FEEDBACK = "feedback"

    # Gateway -> Client
    RESPONSE = "response"
    STREAM_CHUNK = "stream_chunk"
    STREAM_END = "stream_end"
    TOOL_RESULT = "tool_result"
    ERROR = "error"

    # ADAM-specific
    ADAM_PROMPT = "adam_prompt"
    ADAM_CONTEXT = "adam_context"
    ADAM_FEEDBACK = "adam_feedback"


class ADAMPromptPayload(BaseModel):
    """Payload for ADAM-specific prompt messages.

    This model captures the structured context needed for ADAM
    to understand and respond to research-related queries.
    """

    topic_focus: str = Field(..., description="The primary research topic or question")
    literature_context: Optional[dict[str, Any]] = Field(
        default=None, description="Summarized literature findings"
    )
    materials_of_interest: list[str] = Field(
        default_factory=list, description="Materials being investigated"
    )
    experiment_context: Optional[dict[str, Any]] = Field(
        default=None, description="Current experiment parameters and state"
    )
    constraints: list[str] = Field(
        default_factory=list, description="Experimental or research constraints"
    )
    objectives: list[str] = Field(
        default_factory=list, description="Research objectives or goals"
    )


class GatewayMessage(BaseModel):
    """A message in the HAL-9000 gateway protocol.

    All communication through the gateway uses this message format.
    The payload field contains type-specific data.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique message identifier",
    )
    type: MessageType = Field(..., description="The type of message")
    session_id: str = Field(..., description="Session this message belongs to")
    timestamp: datetime = Field(
        default_factory=utc_now,
        description="When the message was created",
    )
    payload: dict[str, Any] = Field(
        default_factory=dict, description="Message-type specific payload"
    )
    metadata: dict[str, Any] = Field(
        default_factory=dict, description="Additional metadata (tracing, etc.)"
    )

    model_config = ConfigDict(use_enum_values=True)

    def to_json(self) -> str:
        """Serialize message to JSON string."""
        return self.model_dump_json()

    @classmethod
    def from_json(cls, data: str) -> "GatewayMessage":
        """Deserialize message from JSON string."""
        return cls.model_validate_json(data)

    @classmethod
    def create_response(
        cls,
        session_id: str,
        payload: dict[str, Any],
        metadata: Optional[dict[str, Any]] = None,
    ) -> "GatewayMessage":
        """Create a response message."""
        return cls(
            type=MessageType.RESPONSE,
            session_id=session_id,
            payload=payload,
            metadata=metadata or {},
        )

    @classmethod
    def create_error(
        cls,
        session_id: str,
        error: str,
        code: Optional[str] = None,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "GatewayMessage":
        """Create an error message."""
        return cls(
            type=MessageType.ERROR,
            session_id=session_id,
            payload={"error": error, "code": code},
            metadata=metadata or {},
        )

    @classmethod
    def create_stream_chunk(
        cls,
        session_id: str,
        chunk: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "GatewayMessage":
        """Create a streaming chunk message."""
        return cls(
            type=MessageType.STREAM_CHUNK,
            session_id=session_id,
            payload={"chunk": chunk},
            metadata=metadata or {},
        )

    @classmethod
    def create_stream_end(
        cls,
        session_id: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> "GatewayMessage":
        """Create a stream end message."""
        return cls(
            type=MessageType.STREAM_END,
            session_id=session_id,
            payload={},
            metadata=metadata or {},
        )
