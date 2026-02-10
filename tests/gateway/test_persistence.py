"""Tests for gateway session persistence."""

import json
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from hal9000.db.models import GatewaySession, init_db
from hal9000.gateway.persistence import PersistentSessionManager
from hal9000.gateway.session import Session


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db_url = f"sqlite:///{db_path}"
        yield db_url


class TestPersistentSessionManager:
    """Tests for PersistentSessionManager class."""

    def test_create_manager(self, temp_db):
        """Test creating a persistent session manager."""
        manager = PersistentSessionManager(database_url=temp_db)

        assert manager.database_url == temp_db
        assert manager.session_timeout_minutes == 60
        assert manager.auto_save is True

    def test_create_manager_custom_settings(self, temp_db):
        """Test creating manager with custom settings."""
        manager = PersistentSessionManager(
            database_url=temp_db,
            session_timeout_minutes=30,
            auto_save=False,
        )

        assert manager.session_timeout_minutes == 30
        assert manager.auto_save is False

    def test_create_session(self, temp_db):
        """Test creating a session."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = manager.create_session(channel="test")

        assert session.id in manager._sessions
        assert session.channel == "test"

    def test_create_session_persists_to_db(self, temp_db):
        """Test that creating a session persists it to the database."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = manager.create_session(channel="test", user_id="user123")

        # Verify it's in the database
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            assert db_session is not None
            assert db_session.channel == "test"
            assert db_session.user_id == "user123"
        finally:
            db.close()

    def test_create_session_no_auto_save(self, temp_db):
        """Test creating session without auto save."""
        manager = PersistentSessionManager(database_url=temp_db, auto_save=False)

        session = manager.create_session()

        # Verify it's NOT in the database
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            assert db_session is None
        finally:
            db.close()

    def test_save_session(self, temp_db):
        """Test explicitly saving a session."""
        manager = PersistentSessionManager(database_url=temp_db, auto_save=False)

        session = manager.create_session()
        session.conversation_history.append({"test": "message"})

        result = manager.save_session(session.id)

        assert result is True

        # Verify database state
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            assert db_session is not None
            history = json.loads(db_session.conversation_history)
            assert len(history) == 1
            assert history[0]["test"] == "message"
        finally:
            db.close()

    def test_save_session_not_found(self, temp_db):
        """Test saving a non-existent session."""
        manager = PersistentSessionManager(database_url=temp_db)

        result = manager.save_session("nonexistent-id")

        assert result is False

    def test_save_session_updates_existing(self, temp_db):
        """Test that save_session updates existing records."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = manager.create_session()

        # Update session
        session.conversation_history.append({"msg": 1})
        manager.save_session(session.id)

        session.conversation_history.append({"msg": 2})
        manager.save_session(session.id)

        # Verify only one record exists with updated data
        db = manager._get_db_session()
        try:
            db_sessions = db.query(GatewaySession).filter_by(id=session.id).all()
            assert len(db_sessions) == 1
            history = json.loads(db_sessions[0].conversation_history)
            assert len(history) == 2
        finally:
            db.close()

    def test_load_sessions(self, temp_db):
        """Test loading sessions from database."""
        # Create and save sessions
        manager1 = PersistentSessionManager(database_url=temp_db)
        session1 = manager1.create_session(user_id="user1")
        session2 = manager1.create_session(user_id="user2")

        # Create new manager and load
        manager2 = PersistentSessionManager(database_url=temp_db)
        loaded = manager2.load_sessions()

        assert loaded == 2
        assert session1.id in manager2._sessions
        assert session2.id in manager2._sessions
        assert manager2._sessions[session1.id].user_id == "user1"
        assert manager2._sessions[session2.id].user_id == "user2"

    def test_load_sessions_excludes_expired(self, temp_db):
        """Test that expired sessions are not loaded."""
        manager1 = PersistentSessionManager(
            database_url=temp_db, session_timeout_minutes=1
        )

        session = manager1.create_session()

        # Manually expire the session in DB
        db = manager1._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            db_session.last_active = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
        finally:
            db.close()

        # Create new manager and load
        manager2 = PersistentSessionManager(
            database_url=temp_db, session_timeout_minutes=1
        )
        loaded = manager2.load_sessions()

        assert loaded == 0
        assert session.id not in manager2._sessions

    def test_load_sessions_preserves_context(self, temp_db):
        """Test that session context is preserved when loading."""
        manager1 = PersistentSessionManager(database_url=temp_db)

        session = manager1.create_session()
        session.context.materials_of_interest.append("graphene")
        session.context.documents_analyzed.append("paper1.pdf")
        manager1.save_session(session.id)

        # Load in new manager
        manager2 = PersistentSessionManager(database_url=temp_db)
        manager2.load_sessions()

        loaded_session = manager2._sessions[session.id]
        assert "graphene" in loaded_session.context.materials_of_interest
        assert "paper1.pdf" in loaded_session.context.documents_analyzed

    def test_remove_session(self, temp_db):
        """Test removing a session from memory and database."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = manager.create_session()
        session_id = session.id

        result = manager.remove_session(session_id)

        assert result is True
        assert session_id not in manager._sessions

        # Verify removed from database
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session_id).first()
            assert db_session is None
        finally:
            db.close()

    def test_remove_session_not_found(self, temp_db):
        """Test removing a non-existent session."""
        manager = PersistentSessionManager(database_url=temp_db)

        result = manager.remove_session("nonexistent-id")

        assert result is False

    def test_cleanup_expired_sessions(self, temp_db):
        """Test cleaning up expired sessions."""
        manager = PersistentSessionManager(
            database_url=temp_db, session_timeout_minutes=1
        )

        # Create sessions
        session1 = manager.create_session()
        session2 = manager.create_session()

        # Manually expire one session
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session1.id).first()
            db_session.last_active = datetime.now(timezone.utc) - timedelta(minutes=5)
            db.commit()
        finally:
            db.close()

        # Also expire in memory
        manager._sessions[session1.id] = Session(
            id=session1.id,
            channel="test",
            created_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        )

        removed = manager.cleanup_expired_sessions()

        assert removed >= 1
        assert session1.id not in manager._sessions
        assert session2.id in manager._sessions

    def test_save_all_sessions(self, temp_db):
        """Test saving all sessions."""
        manager = PersistentSessionManager(database_url=temp_db, auto_save=False)

        manager.create_session()
        manager.create_session()
        manager.create_session()

        saved = manager.save_all_sessions()

        assert saved == 3

        # Verify in database
        db = manager._get_db_session()
        try:
            count = db.query(GatewaySession).count()
            assert count == 3
        finally:
            db.close()

    def test_update_session_activity(self, temp_db):
        """Test updating session activity timestamp."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = manager.create_session()

        # Get initial timestamp
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            initial_time = db_session.last_active
        finally:
            db.close()

        # Update activity
        import time
        time.sleep(0.1)
        manager.update_session_activity(session.id)

        # Check timestamp changed
        db = manager._get_db_session()
        try:
            db_session = db.query(GatewaySession).filter_by(id=session.id).first()
            assert db_session.last_active >= initial_time
        finally:
            db.close()

    def test_update_session_activity_not_found(self, temp_db):
        """Test updating activity for non-existent session."""
        manager = PersistentSessionManager(database_url=temp_db)

        result = manager.update_session_activity("nonexistent-id")

        assert result is False


class TestDatabaseModel:
    """Tests for GatewaySession database model."""

    def test_gateway_session_model(self, temp_db):
        """Test GatewaySession model fields."""
        engine, session_factory = init_db(temp_db)

        db = session_factory()
        try:
            session = GatewaySession(
                id="test-id",
                channel="websocket",
                user_id="user123",
                context='{"materials_of_interest": ["graphene"]}',
                conversation_history='[{"msg": "test"}]',
                active_tools='["tool1"]',
            )
            db.add(session)
            db.commit()

            loaded = db.query(GatewaySession).filter_by(id="test-id").first()
            assert loaded is not None
            assert loaded.channel == "websocket"
            assert loaded.user_id == "user123"
            assert "graphene" in loaded.context
            assert "test" in loaded.conversation_history
        finally:
            db.close()

    def test_gateway_session_repr(self, temp_db):
        """Test GatewaySession string representation."""
        session = GatewaySession(id="test-id", channel="test")

        repr_str = repr(session)

        assert "test-id" in repr_str
        assert "test" in repr_str


class TestSessionConversion:
    """Tests for session object conversion."""

    def test_db_to_session(self, temp_db):
        """Test converting DB record to Session object."""
        manager = PersistentSessionManager(database_url=temp_db)

        db_session = GatewaySession(
            id="test-id",
            channel="cli",
            user_id="user1",
            context='{"materials_of_interest": ["copper"]}',
            conversation_history='[{"role": "user", "content": "hello"}]',
            active_tools='["search"]',
            created_at=datetime.now(timezone.utc),
        )

        session = manager._db_to_session(db_session)

        assert session.id == "test-id"
        assert session.channel == "cli"
        assert session.user_id == "user1"
        assert "copper" in session.context.materials_of_interest
        assert len(session.conversation_history) == 1
        assert "search" in session.active_tools

    def test_session_to_db(self, temp_db):
        """Test converting Session object to DB record."""
        manager = PersistentSessionManager(database_url=temp_db)

        session = Session(
            id="test-id",
            channel="websocket",
            user_id="user1",
        )
        session.context.materials_of_interest.append("silicon")
        session.conversation_history.append({"test": True})
        session.active_tools.append("analyze")

        db_session = manager._session_to_db(session)

        assert db_session.id == "test-id"
        assert db_session.channel == "websocket"
        assert db_session.user_id == "user1"
        assert "silicon" in db_session.context
        assert "test" in db_session.conversation_history
        assert "analyze" in db_session.active_tools

    def test_roundtrip_conversion(self, temp_db):
        """Test Session -> DB -> Session preserves data."""
        manager = PersistentSessionManager(database_url=temp_db)

        original = Session(
            id="test-id",
            channel="websocket",
            user_id="researcher1",
        )
        original.context.materials_of_interest = ["graphene", "carbon nanotubes"]
        original.context.documents_analyzed = ["paper1.pdf", "paper2.pdf"]
        original.context.extracted_knowledge = {"key": "value"}
        original.conversation_history = [
            {"role": "user", "content": "analyze this"},
            {"role": "assistant", "content": "result"},
        ]
        original.active_tools = ["search", "analyze", "export"]

        # Convert to DB and back
        db_session = manager._session_to_db(original)
        restored = manager._db_to_session(db_session)

        assert restored.id == original.id
        assert restored.channel == original.channel
        assert restored.user_id == original.user_id
        assert restored.context.materials_of_interest == original.context.materials_of_interest
        assert restored.context.documents_analyzed == original.context.documents_analyzed
        assert restored.context.extracted_knowledge == original.context.extracted_knowledge
        assert restored.conversation_history == original.conversation_history
        assert restored.active_tools == original.active_tools
