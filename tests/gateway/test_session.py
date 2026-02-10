"""Tests for gateway session management."""

from datetime import datetime, timezone

from hal9000.gateway.session import (
    ResearchContext,
    Session,
    SessionManager,
)


class TestResearchContext:
    """Tests for ResearchContext dataclass."""

    def test_create_empty_context(self) -> None:
        """Test creating an empty research context."""
        ctx = ResearchContext()
        assert ctx.documents_analyzed == []
        assert ctx.extracted_knowledge == {}
        assert ctx.materials_of_interest == []
        assert ctx.active_hypotheses == []
        assert ctx.adam_interactions == []

    def test_create_context_with_data(self) -> None:
        """Test creating a context with data."""
        ctx = ResearchContext(
            documents_analyzed=["doc1.pdf", "doc2.pdf"],
            extracted_knowledge={"key_finding": "value"},
            materials_of_interest=["Nickel", "Cobalt"],
            active_hypotheses=[{"hypothesis": "test"}],
            adam_interactions=[{"interaction": "query"}],
        )
        assert len(ctx.documents_analyzed) == 2
        assert "key_finding" in ctx.extracted_knowledge
        assert "Nickel" in ctx.materials_of_interest

    def test_to_dict(self) -> None:
        """Test converting context to dictionary."""
        ctx = ResearchContext(
            documents_analyzed=["doc.pdf"],
            materials_of_interest=["Steel"],
        )
        data = ctx.to_dict()
        assert data["documents_analyzed"] == ["doc.pdf"]
        assert data["materials_of_interest"] == ["Steel"]
        assert "extracted_knowledge" in data
        assert "active_hypotheses" in data
        assert "adam_interactions" in data

    def test_from_dict(self) -> None:
        """Test creating context from dictionary."""
        data = {
            "documents_analyzed": ["paper.pdf"],
            "extracted_knowledge": {"finding": "important"},
            "materials_of_interest": ["Aluminum"],
            "active_hypotheses": [],
            "adam_interactions": [],
        }
        ctx = ResearchContext.from_dict(data)
        assert ctx.documents_analyzed == ["paper.pdf"]
        assert ctx.extracted_knowledge["finding"] == "important"
        assert ctx.materials_of_interest == ["Aluminum"]

    def test_from_dict_with_missing_fields(self) -> None:
        """Test from_dict handles missing fields gracefully."""
        ctx = ResearchContext.from_dict({})
        assert ctx.documents_analyzed == []
        assert ctx.extracted_knowledge == {}

    def test_roundtrip_serialization(self) -> None:
        """Test context serialization roundtrip."""
        original = ResearchContext(
            documents_analyzed=["test.pdf"],
            materials_of_interest=["Titanium"],
        )
        data = original.to_dict()
        restored = ResearchContext.from_dict(data)
        assert restored.documents_analyzed == original.documents_analyzed
        assert restored.materials_of_interest == original.materials_of_interest


class TestSession:
    """Tests for Session dataclass."""

    def test_create_session_with_defaults(self) -> None:
        """Test creating a session with default values."""
        session = Session()
        assert session.id is not None
        assert session.channel == "websocket"
        assert session.created_at is not None
        assert session.user_id is None
        assert isinstance(session.context, ResearchContext)
        assert session.conversation_history == []
        assert session.active_tools == []

    def test_create_session_with_values(self) -> None:
        """Test creating a session with specific values."""
        now = datetime.now(timezone.utc)
        session = Session(
            id="sess-123",
            channel="cli",
            created_at=now,
            user_id="user-456",
            active_tools=["search", "analyze"],
        )
        assert session.id == "sess-123"
        assert session.channel == "cli"
        assert session.created_at == now
        assert session.user_id == "user-456"
        assert len(session.active_tools) == 2

    def test_to_context_window(self) -> None:
        """Test generating context window for ADAM."""
        session = Session(
            id="sess-test",
            channel="websocket",
            user_id="user-1",
            active_tools=["tool1"],
        )
        session.context.materials_of_interest = ["Material A"]

        window = session.to_context_window()
        assert window["session_id"] == "sess-test"
        assert window["channel"] == "websocket"
        assert window["user_id"] == "user-1"
        assert window["active_tools"] == ["tool1"]
        assert "research_context" in window
        assert window["research_context"]["materials_of_interest"] == ["Material A"]

    def test_to_context_window_with_conversation(self) -> None:
        """Test context window includes conversation summary."""
        session = Session(id="sess-convo")
        session.add_message({"role": "user", "content": "Hello", "topics": ["greeting"]})
        session.add_message({"role": "assistant", "content": "Hi!", "topics": ["response"]})

        window = session.to_context_window()
        summary = window["conversation_summary"]
        assert summary["message_count"] == 2
        assert "greeting" in summary["topics"]
        assert "response" in summary["topics"]

    def test_add_message(self) -> None:
        """Test adding messages to conversation history."""
        session = Session()
        session.add_message({"role": "user", "content": "Test"})

        assert len(session.conversation_history) == 1
        assert session.conversation_history[0]["role"] == "user"
        assert "timestamp" in session.conversation_history[0]

    def test_add_message_preserves_timestamp(self) -> None:
        """Test that add_message preserves existing timestamp."""
        session = Session()
        timestamp = "2026-02-01T10:00:00"
        session.add_message({"role": "user", "content": "Test", "timestamp": timestamp})

        assert session.conversation_history[0]["timestamp"] == timestamp

    def test_to_dict(self) -> None:
        """Test converting session to dictionary."""
        session = Session(
            id="sess-dict",
            channel="api",
            user_id="user-dict",
        )
        data = session.to_dict()
        assert data["id"] == "sess-dict"
        assert data["channel"] == "api"
        assert data["user_id"] == "user-dict"
        assert "created_at" in data
        assert "context" in data

    def test_from_dict(self) -> None:
        """Test creating session from dictionary."""
        data = {
            "id": "sess-from-dict",
            "channel": "websocket",
            "created_at": "2026-02-01T10:00:00",
            "user_id": "user-test",
            "context": {"materials_of_interest": ["Iron"]},
            "conversation_history": [{"role": "user", "content": "Hi"}],
            "active_tools": ["search"],
        }
        session = Session.from_dict(data)
        assert session.id == "sess-from-dict"
        assert session.channel == "websocket"
        assert session.user_id == "user-test"
        assert session.context.materials_of_interest == ["Iron"]
        assert len(session.conversation_history) == 1
        assert session.active_tools == ["search"]

    def test_from_dict_with_minimal_data(self) -> None:
        """Test from_dict handles minimal data."""
        session = Session.from_dict({})
        assert session.id is not None
        assert session.channel == "websocket"
        assert session.created_at is not None

    def test_roundtrip_serialization(self) -> None:
        """Test session serialization roundtrip."""
        original = Session(
            id="sess-roundtrip",
            channel="test",
            user_id="user-rt",
        )
        original.add_message({"role": "user", "content": "Test"})

        data = original.to_dict()
        restored = Session.from_dict(data)

        assert restored.id == original.id
        assert restored.channel == original.channel
        assert restored.user_id == original.user_id
        assert len(restored.conversation_history) == 1


class TestSessionManager:
    """Tests for SessionManager class."""

    def test_create_session(self) -> None:
        """Test creating a session through manager."""
        manager = SessionManager()
        session = manager.create_session()

        assert session.id is not None
        assert session.channel == "websocket"
        assert manager.session_count() == 1

    def test_create_session_with_options(self) -> None:
        """Test creating a session with specific options."""
        manager = SessionManager()
        session = manager.create_session(
            channel="cli",
            user_id="user-123",
            session_id="custom-id",
        )

        assert session.id == "custom-id"
        assert session.channel == "cli"
        assert session.user_id == "user-123"

    def test_get_session(self) -> None:
        """Test retrieving a session by ID."""
        manager = SessionManager()
        created = manager.create_session(session_id="get-test")

        retrieved = manager.get_session("get-test")
        assert retrieved is not None
        assert retrieved.id == created.id

    def test_get_session_not_found(self) -> None:
        """Test retrieving a non-existent session."""
        manager = SessionManager()
        result = manager.get_session("nonexistent")
        assert result is None

    def test_remove_session(self) -> None:
        """Test removing a session."""
        manager = SessionManager()
        manager.create_session(session_id="remove-test")

        assert manager.session_count() == 1
        result = manager.remove_session("remove-test")
        assert result is True
        assert manager.session_count() == 0

    def test_remove_session_not_found(self) -> None:
        """Test removing a non-existent session."""
        manager = SessionManager()
        result = manager.remove_session("nonexistent")
        assert result is False

    def test_list_sessions(self) -> None:
        """Test listing all sessions."""
        manager = SessionManager()
        manager.create_session(session_id="sess-1")
        manager.create_session(session_id="sess-2")
        manager.create_session(session_id="sess-3")

        sessions = manager.list_sessions()
        assert len(sessions) == 3
        ids = [s.id for s in sessions]
        assert "sess-1" in ids
        assert "sess-2" in ids
        assert "sess-3" in ids

    def test_list_sessions_empty(self) -> None:
        """Test listing sessions when none exist."""
        manager = SessionManager()
        sessions = manager.list_sessions()
        assert sessions == []

    def test_session_count(self) -> None:
        """Test counting active sessions."""
        manager = SessionManager()
        assert manager.session_count() == 0

        manager.create_session()
        assert manager.session_count() == 1

        manager.create_session()
        assert manager.session_count() == 2

    def test_clear_all(self) -> None:
        """Test clearing all sessions."""
        manager = SessionManager()
        manager.create_session()
        manager.create_session()
        manager.create_session()

        count = manager.clear_all()
        assert count == 3
        assert manager.session_count() == 0

    def test_clear_all_empty(self) -> None:
        """Test clearing when no sessions exist."""
        manager = SessionManager()
        count = manager.clear_all()
        assert count == 0

    def test_multiple_managers_independent(self) -> None:
        """Test that multiple managers are independent."""
        manager1 = SessionManager()
        manager2 = SessionManager()

        manager1.create_session(session_id="m1-sess")
        manager2.create_session(session_id="m2-sess")

        assert manager1.session_count() == 1
        assert manager2.session_count() == 1
        assert manager1.get_session("m2-sess") is None
        assert manager2.get_session("m1-sess") is None
