import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.database import Base
from app.models import Document, DocumentVersion, Node
from app.services.ingest_service import ingest_document_version

# Create in-memory SQLite database for testing
@pytest.fixture
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()

def test_document_versioning_and_matching(db_session):
    # Ingest v1
    v1_markdown = """# CardioTrack
## 1. Overview
This is version 1 of overview text.
## 2. Hardware
This is version 1 of hardware text.
"""
    v1, stats_v1 = ingest_document_version(db_session, "CardioTrack", "v1", v1_markdown)
    
    assert stats_v1["total_nodes"] == 3
    assert stats_v1["new_nodes"] == 3
    assert stats_v1["modified_nodes"] == 0
    assert stats_v1["deleted_nodes"] == 0
    
    # Query v1 nodes
    v1_nodes = db_session.query(Node).filter(Node.version_id == v1.id).all()
    overview_v1 = next(n for n in v1_nodes if "Overview" in n.title)
    hardware_v1 = next(n for n in v1_nodes if "Hardware" in n.title)
    
    # Ingest v2 with:
    # - 1. Overview modified
    # - 2. Hardware unchanged
    # - 3. Interface added
    v2_markdown = """# CardioTrack
## 1. Overview
This is version 2 of overview text. Modified!
## 2. Hardware
This is version 1 of hardware text.
## 3. Interface
This is a brand new section.
"""
    v2, stats_v2 = ingest_document_version(db_session, "CardioTrack", "v2", v2_markdown)
    
    assert stats_v2["total_nodes"] == 4
    assert stats_v2["new_nodes"] == 1       # 3. Interface is new
    assert stats_v2["modified_nodes"] == 1  # 1. Overview is modified
    assert stats_v2["unchanged_nodes"] == 2 # Root and 2. Hardware are unchanged
    assert stats_v2["deleted_nodes"] == 0
    
    # Query v2 nodes
    v2_nodes = db_session.query(Node).filter(Node.version_id == v2.id).all()
    overview_v2 = next(n for n in v2_nodes if "Overview" in n.title)
    hardware_v2 = next(n for n in v2_nodes if "Hardware" in n.title)
    interface_v2 = next(n for n in v2_nodes if "Interface" in n.title)
    
    # Assert logical_id tracking
    assert overview_v2.logical_id == overview_v1.logical_id
    assert hardware_v2.logical_id == hardware_v1.logical_id
    
    # Assert content hashes
    assert overview_v2.content_hash != overview_v1.content_hash  # Content changed
    assert hardware_v2.content_hash == hardware_v1.content_hash  # Content identical
    
    # Assert interface is a new logical node
    assert interface_v2.logical_id != overview_v1.logical_id
    assert interface_v2.logical_id != hardware_v1.logical_id

def test_document_versioning_with_deletion(db_session):
    # Ingest v1
    v1_markdown = """# CardioTrack
## 1. Overview
Body text.
## 2. Hardware
Body text.
"""
    v1, _ = ingest_document_version(db_session, "CardioTrack", "v1", v1_markdown)
    
    # Ingest v2 where Hardware is deleted
    v2_markdown = """# CardioTrack
## 1. Overview
Body text.
"""
    v2, stats_v2 = ingest_document_version(db_session, "CardioTrack", "v2", v2_markdown)
    
    assert stats_v2["deleted_nodes"] == 1
    
    # Fetch all nodes in V2 and ensure none of them represents Hardware
    v2_nodes = db_session.query(Node).filter(Node.version_id == v2.id).all()
    assert not any("Hardware" in n.title for n in v2_nodes)
