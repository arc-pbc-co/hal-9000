"""Session management for the HAL-9000 Gateway.

This module provides session tracking and management for WebSocket clients,
including research context and conversation history.
"""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional


@dataclass
class ResearchContext:
    """Research context accumulated during a session.

    Tracks the research state and knowledge gathered during
    interactions with HAL-9000.
    """

    documents_analyzed: list[str] = field(default_factory=list)
    extracted_knowledge: dict[str, Any] = field(default_factory=dict)
    materials_of_interest: list[str] = field(default_factory=list)
    active_hypotheses: list[dict[str, Any]] = field(default_factory=list)
    adam_interactions: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert context to dictionary."""
        return {
            "documents_analyzed": self.documents_analyzed,
            "extracted_knowledge": self.extracted_knowledge,
            "materials_of_interest": self.materials_of_interest,
            "active_hypotheses": self.active_hypotheses,
            "adam_interactions": self.adam_interactions,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ResearchContext":
        """Create context from dictionary."""
        return cls(
            documents_analyzed=data.get("documents_analyzed", []),
            extracted_knowledge=data.get("extracted_knowledge", {}),
            materials_of_interest=data.get("materials_of_interest", []),
            active_hypotheses=data.get("active_hypotheses", []),
            adam_interactions=data.get("adam_interactions", []),
        )


@dataclass
class Session:
    """A client session in the HAL-9000 gateway.

    Tracks connection state, research context, and conversation history
    for a connected client.
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    channel: str = "websocket"
    created_at: datetime = field(default_factory=datetime.utcnow)
    user_id: Optional[str] = None
    context: ResearchContext = field(default_factory=ResearchContext)
    conversation_history: list[dict[str, Any]] = field(default_factory=list)
    active_tools: list[str] = field(default_factory=list)

    def to_context_window(self) -> dict[str, Any]:
        """Generate context window for ADAM integration.

        Returns a dictionary containing session state suitable for
        passing to ADAM as context.
        """
        return {
            "session_id": self.id,
            "channel": self.channel,
            "user_id": self.user_id,
            "research_context": self.context.to_dict(),
            "conversation_summary": self._summarize_conversation(),
            "active_tools": self.active_tools,
        }

    def _summarize_conversation(self) -> dict[str, Any]:
        """Create a summary of the conversation history."""
        if not self.conversation_history:
            return {"message_count": 0, "topics": [], "last_interaction": None}

        topics: list[str] = []
        for msg in self.conversation_history:
            if "topics" in msg:
                topics.extend(msg["topics"])

        # Deduplicate topics while preserving order
        seen: set[str] = set()
        unique_topics: list[str] = []
        for topic in topics:
            if topic not in seen:
                seen.add(topic)
                unique_topics.append(topic)

        last_msg = self.conversation_history[-1]
        return {
            "message_count": len(self.conversation_history),
            "topics": unique_topics[:10],  # Limit to top 10 topics
            "last_interaction": last_msg.get("timestamp"),
        }

    def add_message(self, message: dict[str, Any]) -> None:
        """Add a message to conversation history."""
        if "timestamp" not in message:
            message["timestamp"] = datetime.utcnow().isoformat()
        self.conversation_history.append(message)

    def to_dict(self) -> dict[str, Any]:
        """Convert session to dictionary for serialization."""
        return {
            "id": self.id,
            "channel": self.channel,
            "created_at": self.created_at.isoformat(),
            "user_id": self.user_id,
            "context": self.context.to_dict(),
            "conversation_history": self.conversation_history,
            "active_tools": self.active_tools,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Session":
        """Create session from dictionary."""
        created_at = data.get("created_at")
        if isinstance(created_at, str):
            created_at = datetime.fromisoformat(created_at)
        elif created_at is None:
            created_at = datetime.utcnow()

        context_data = data.get("context", {})
        context = (
            ResearchContext.from_dict(context_data)
            if isinstance(context_data, dict)
            else ResearchContext()
        )

        return cls(
            id=data.get("id", str(uuid.uuid4())),
            channel=data.get("channel", "websocket"),
            created_at=created_at,
            user_id=data.get("user_id"),
            context=context,
            conversation_history=data.get("conversation_history", []),
            active_tools=data.get("active_tools", []),
        )


class SessionManager:
    """Manages active sessions in the gateway.

    Provides methods for creating, retrieving, and removing sessions.
    """

    def __init__(self) -> None:
        """Initialize the session manager."""
        self._sessions: dict[str, Session] = {}

    def create_session(
        self,
        channel: str = "websocket",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Create a new session.

        Args:
            channel: The communication channel (e.g., "websocket", "cli").
            user_id: Optional user identifier.
            session_id: Optional specific session ID to use.

        Returns:
            The newly created Session.
        """
        session = Session(
            id=session_id or str(uuid.uuid4()),
            channel=channel,
            user_id=user_id,
        )
        self._sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[Session]:
        """Get a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            The Session if found, None otherwise.
        """
        return self._sessions.get(session_id)

    def remove_session(self, session_id: str) -> bool:
        """Remove a session by ID.

        Args:
            session_id: The session identifier.

        Returns:
            True if the session was removed, False if not found.
        """
        if session_id in self._sessions:
            del self._sessions[session_id]
            return True
        return False

    def list_sessions(self) -> list[Session]:
        """List all active sessions.

        Returns:
            A list of all active Session objects.
        """
        return list(self._sessions.values())

    def session_count(self) -> int:
        """Get the number of active sessions.

        Returns:
            The count of active sessions.
        """
        return len(self._sessions)

    def clear_all(self) -> int:
        """Remove all sessions.

        Returns:
            The number of sessions that were removed.
        """
        count = len(self._sessions)
        self._sessions.clear()
        return count
