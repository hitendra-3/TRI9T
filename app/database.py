import os
from sqlalchemy import create_engine, event, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import declarative_base, sessionmaker

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./ct200_database.db")

# Create engine with connect_args for SQLite
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False}
)

# Enable foreign keys for SQLite
@event.listens_for(Engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    if DATABASE_URL.startswith("sqlite"):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def ensure_fts5_table():
    """
    Creates the FTS5 virtual table for full-text search across nodes.
    Also creates triggers to keep the FTS index in sync with the nodes table.

    FTS5 provides:
      - Word-boundary tokenisation (not LIKE '%query%' substring matching)
      - Ranked results via bm25() scoring
      - Phrase search: "battery life"
      - Prefix search: batter*
    """
    with engine.connect() as conn:
        # Create FTS5 virtual table (content table mirrors nodes)
        conn.execute(text("""
            CREATE VIRTUAL TABLE IF NOT EXISTS nodes_fts
            USING fts5(
                heading,
                title,
                body_text,
                content='nodes',
                content_rowid='id'
            )
        """))

        # Trigger: AFTER INSERT on nodes → insert into FTS
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS nodes_ai AFTER INSERT ON nodes BEGIN
                INSERT INTO nodes_fts(rowid, heading, title, body_text)
                VALUES (new.id, new.heading, new.title, new.body_text);
            END
        """))

        # Trigger: AFTER DELETE on nodes → remove from FTS
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS nodes_ad AFTER DELETE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, heading, title, body_text)
                VALUES ('delete', old.id, old.heading, old.title, old.body_text);
            END
        """))

        # Trigger: AFTER UPDATE on nodes → update FTS
        conn.execute(text("""
            CREATE TRIGGER IF NOT EXISTS nodes_au AFTER UPDATE ON nodes BEGIN
                INSERT INTO nodes_fts(nodes_fts, rowid, heading, title, body_text)
                VALUES ('delete', old.id, old.heading, old.title, old.body_text);
                INSERT INTO nodes_fts(rowid, heading, title, body_text)
                VALUES (new.id, new.heading, new.title, new.body_text);
            END
        """))

        conn.commit()
