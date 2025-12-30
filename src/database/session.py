"""
SQLAlchemy session management.
"""
import logging
from contextlib import contextmanager
from typing import Generator

from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import NullPool, QueuePool

from .models import Base

logger = logging.getLogger("invoice_processor.database.session")


class SessionManager:
    """Manages SQLAlchemy sessions and connections."""
    
    def __init__(self, connection_string: str, echo: bool = False):
        """
        Initialize session manager.
        
        Args:
            connection_string: Database URL (postgresql://...)
            echo: If True, log all SQL statements
        """
        self.connection_string = connection_string
        self.echo = echo
        
        # Create engine
        self.engine = create_engine(
            connection_string,
            echo=echo,
            poolclass=QueuePool,
            pool_size=5,
            max_overflow=10,
            pool_pre_ping=True,  # Verify connections before using
        )
        
        # Create session factory
        self.SessionLocal = sessionmaker(
            bind=self.engine,
            autocommit=False,
            autoflush=False,
            expire_on_commit=False
        )
        
        logger.info("Initialized SQLAlchemy SessionManager")
    
    @contextmanager
    def session(self) -> Generator[Session, None, None]:
        """
        Context manager for database sessions.
        
        Usage:
            with session_manager.session() as session:
                invoice = session.query(Invoice).first()
        """
        session = self.SessionLocal()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()
    
    def create_all_tables(self):
        """Create all tables defined in models."""
        logger.info("Creating all tables")
        Base.metadata.create_all(bind=self.engine)
        logger.info("✓ Tables created")
    
    def drop_all_tables(self):
        """Drop all tables. Use with caution!"""
        logger.warning("Dropping all tables")
        Base.metadata.drop_all(bind=self.engine)
        logger.info("✓ Tables dropped")
    
    def close(self):
        """Close all connections."""
        self.engine.dispose()
        logger.info("Database connections closed")


def get_session_manager(connection_string: str, echo: bool = False) -> SessionManager:
    """
    Factory function to create a session manager.
    
    Args:
        connection_string: Database URL
        echo: If True, log SQL statements
        
    Returns:
        SessionManager instance
    """
    return SessionManager(connection_string, echo=echo)
