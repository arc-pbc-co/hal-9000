"""Database persistence for gateway sessions.

This module provides session persistence functionality, allowing
sessions to survive gateway restarts.
"""

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.orm import Session as DBSession

from hal9000.db.models import GatewaySession, init_db
from hal9000.gateway.session import ResearchContext, Session, SessionManager, ensure_utc

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Get current UTC time as timezone-aware datetime."""
    return datetime.now(timezone.utc)


class PersistentSessionManager(SessionManager):
    """Session manager with database persistence.

    Extends SessionManager to save and load sessions from the database,
    enabling session continuity across gateway restarts.
    """

    def __init__(
        self,
        database_url: str = "sqlite:///./hal9000.db",
        session_timeout_minutes: int = 60,
        auto_save: bool = True,
    ) -> None:
        """Initialize the persistent session manager.

        Args:
            database_url: SQLAlchemy database URL.
            session_timeout_minutes: Minutes after which inactive sessions expire.
            auto_save: Whether to auto-save on session changes.
        """
        super().__init__()
        self.database_url = database_url
        self.session_timeout_minutes = session_timeout_minutes
        self.auto_save = auto_save

        # Initialize database
        self._engine, self._session_factory = init_db(database_url)

    def _get_db_session(self) -> DBSession:
        """Get a new database session."""
        return self._session_factory()  # type: ignore[no-any-return]

    def load_sessions(self) -> int:
        """Load existing sessions from the database.

        Returns:
            Number of sessions loaded.
        """
        db = self._get_db_session()
        try:
            # Calculate timeout cutoff
            cutoff = utc_now() - timedelta(minutes=self.session_timeout_minutes)

            # Load active sessions (not expired)
            db_sessions = db.query(GatewaySession).filter(
                GatewaySession.last_active >= cutoff
            ).all()

            loaded = 0
            for db_session in db_sessions:
                session = self._db_to_session(db_session)
                self._sessions[session.id] = session
                loaded += 1

            logger.info(f"Loaded {loaded} sessions from database")
            return loaded

        finally:
            db.close()

    def _db_to_session(self, db_session: GatewaySession) -> Session:
        """Convert a database session to a Session object.

        Args:
            db_session: The database session record.

        Returns:
            A Session object.
        """
        # Parse JSON fields
        context_data = json.loads(db_session.context) if db_session.context else {}
        history = json.loads(db_session.conversation_history) if db_session.conversation_history else []
        tools = json.loads(db_session.active_tools) if db_session.active_tools else []

        return Session(
            id=db_session.id,
            channel=db_session.channel,
            created_at=ensure_utc(db_session.created_at),
            user_id=db_session.user_id,
            context=ResearchContext.from_dict(context_data),
            conversation_history=history,
            active_tools=tools,
        )

    def _session_to_db(self, session: Session) -> GatewaySession:
        """Convert a Session object to database record format.

        Args:
            session: The session to convert.

        Returns:
            A GatewaySession database record.
        """
        return GatewaySession(
            id=session.id,
            channel=session.channel,
            user_id=session.user_id,
            context=json.dumps(session.context.to_dict()),
            conversation_history=json.dumps(session.conversation_history),
            active_tools=json.dumps(session.active_tools),
            created_at=session.created_at,
            last_active=utc_now(),
        )

    def save_session(self, session_id: str) -> bool:
        """Save a session to the database.

        Args:
            session_id: The session ID to save.

        Returns:
            True if saved successfully, False otherwise.
        """
        session = self._sessions.get(session_id)
        if session is None:
            return False

        db = self._get_db_session()
        try:
            # Check if session exists in DB
            db_session = db.query(GatewaySession).filter_by(id=session_id).first()

            if db_session is None:
                # Create new record
                db_session = self._session_to_db(session)
                db.add(db_session)
            else:
                # Update existing record
                db_session.channel = session.channel
                db_session.user_id = session.user_id
                db_session.context = json.dumps(session.context.to_dict())
                db_session.conversation_history = json.dumps(session.conversation_history)
                db_session.active_tools = json.dumps(session.active_tools)
                db_session.last_active = utc_now()

            db.commit()
            return True

        except Exception as e:
            logger.error(f"Failed to save session {session_id}: {e}")
            db.rollback()
            return False

        finally:
            db.close()

    def save_all_sessions(self) -> int:
        """Save all active sessions to the database.

        Returns:
            Number of sessions saved.
        """
        saved = 0
        for session_id in list(self._sessions.keys()):
            if self.save_session(session_id):
                saved += 1
        return saved

    def create_session(
        self,
        channel: str = "websocket",
        user_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> Session:
        """Create a new session and optionally persist it.

        Args:
            channel: The communication channel.
            user_id: Optional user identifier.
            session_id: Optional specific session ID.

        Returns:
            The newly created Session.
        """
        session = super().create_session(channel, user_id, session_id)

        if self.auto_save:
            self.save_session(session.id)

        return session

    def remove_session(self, session_id: str) -> bool:
        """Remove a session from memory and database.

        Args:
            session_id: The session ID to remove.

        Returns:
            True if removed, False if not found.
        """
        # Remove from memory
        removed = super().remove_session(session_id)

        if removed:
            # Remove from database
            db = self._get_db_session()
            try:
                db.query(GatewaySession).filter_by(id=session_id).delete()
                db.commit()
            except Exception as e:
                logger.error(f"Failed to remove session {session_id} from DB: {e}")
                db.rollback()
            finally:
                db.close()

        return removed

    def cleanup_expired_sessions(self) -> int:
        """Remove sessions older than the timeout.

        Returns:
            Number of sessions removed.
        """
        cutoff = utc_now() - timedelta(minutes=self.session_timeout_minutes)
        removed = 0

        # Remove from memory
        expired_ids = [
            sid for sid, session in self._sessions.items()
            if session.created_at < cutoff
        ]

        for session_id in expired_ids:
            del self._sessions[session_id]
            removed += 1

        # Remove from database
        db = self._get_db_session()
        try:
            db_removed = db.query(GatewaySession).filter(
                GatewaySession.last_active < cutoff
            ).delete()
            db.commit()
            logger.info(f"Cleaned up {removed} expired sessions from memory, {db_removed} from DB")
        except Exception as e:
            logger.error(f"Failed to cleanup expired sessions from DB: {e}")
            db.rollback()
        finally:
            db.close()

        return removed

    def update_session_activity(self, session_id: str) -> bool:
        """Update the last_active timestamp for a session.

        Args:
            session_id: The session ID to update.

        Returns:
            True if updated, False if not found.
        """
        if session_id not in self._sessions:
            return False

        if self.auto_save:
            db = self._get_db_session()
            try:
                db_session = db.query(GatewaySession).filter_by(id=session_id).first()
                if db_session:
                    db_session.last_active = utc_now()
                    db.commit()
                    return True
            except Exception as e:
                logger.error(f"Failed to update session activity: {e}")
                db.rollback()
            finally:
                db.close()

        return False
