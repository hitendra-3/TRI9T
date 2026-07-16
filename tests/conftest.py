"""
Shared pytest fixtures available to all test modules.
Isolates tests to an independent test database file to prevent lock conflicts with the running server.
"""

import os
# Force testing to use an isolated SQLite database file to avoid locking issues
os.environ["DATABASE_URL"] = "sqlite:///./ct200_test_database.db"

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.mongodb import clear_mongo_collections


@pytest.fixture
def clean_db():
    """
    Resets the SQLite test database and MongoDB collection.
    Scoped to individual tests that request it (or test files that set autouse=True).
    """
    clear_mongo_collections()
    Base.metadata.drop_all(bind=_get_engine())
    Base.metadata.create_all(bind=_get_engine())
    yield
    clear_mongo_collections()
    Base.metadata.drop_all(bind=_get_engine())


def _get_engine():
    from app.database import engine
    return engine


@pytest.fixture
def in_memory_db():
    """
    Returns a fully isolated in-memory SQLite session.
    Used for unit-level service tests that don't need the full app context.
    Each call creates a fresh engine — zero shared state with the app or other tests.
    """
    test_engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(bind=test_engine)
    TestSession = sessionmaker(bind=test_engine)
    session = TestSession()
    try:
        yield session
    finally:
        session.close()
        Base.metadata.drop_all(bind=test_engine)
