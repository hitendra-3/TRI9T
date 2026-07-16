import datetime
# pyrefly: ignore [missing-import]
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Table, Text, JSON
# pyrefly: ignore [missing-import]
from sqlalchemy.orm import relationship
from app.database import Base

def utc_now():
    return datetime.datetime.now(datetime.timezone.utc)

# Association table for Selections and Nodes
selection_nodes = Table(
    "selection_nodes",
    Base.metadata,
    Column("selection_id", Integer, ForeignKey("selections.id", ondelete="CASCADE"), primary_key=True),
    Column("node_id", Integer, ForeignKey("nodes.id", ondelete="CASCADE"), primary_key=True),
)

class Document(Base):
    __tablename__ = "documents"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    versions = relationship("DocumentVersion", back_populates="document", cascade="all, delete-orphan")
    nodes = relationship("Node", back_populates="document", cascade="all, delete-orphan")

class DocumentVersion(Base):
    __tablename__ = "document_versions"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_label = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=utc_now)

    document = relationship("Document", back_populates="versions")
    nodes = relationship("Node", back_populates="version", cascade="all, delete-orphan")
    selections = relationship("Selection", back_populates="version", cascade="all, delete-orphan")

class Node(Base):
    __tablename__ = "nodes"

    id = Column(Integer, primary_key=True, index=True)
    document_id = Column(Integer, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False)
    version_id = Column(Integer, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    logical_id = Column(String, index=True, nullable=False)  # Stable ID across versions
    heading = Column(String, nullable=False)                 # Raw heading (e.g. "### 1.1 Intended Use")
    title = Column(String, nullable=False)                   # Processed title (e.g. "1.1 Intended Use")
    level = Column(Integer, nullable=False)                  # Heading level (1, 2, 3, etc.)
    body_text = Column(Text, nullable=False)                 # Plain text under heading
    content_hash = Column(String, nullable=False)            # SHA-256 hash of title + level + body_text
    parent_id = Column(Integer, ForeignKey("nodes.id", ondelete="SET NULL"), nullable=True)
    path = Column(String, nullable=False)                    # Hierarchical title path, e.g. "/Device Overview/Intended Use"

    document = relationship("Document", back_populates="nodes")
    version = relationship("DocumentVersion", back_populates="nodes")
    
    # Self-referential relationship for parent/children
    parent = relationship("Node", remote_side=[id], back_populates="children")
    children = relationship("Node", back_populates="parent", cascade="all, delete-orphan")

    # Many-to-many relationship with selections
    selections = relationship("Selection", secondary=selection_nodes, back_populates="nodes")

class Selection(Base):
    __tablename__ = "selections"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    version_id = Column(Integer, ForeignKey("document_versions.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=utc_now)

    version = relationship("DocumentVersion", back_populates="selections")
    nodes = relationship("Node", secondary=selection_nodes, back_populates="selections")
    test_cases = relationship("GeneratedTestCases", back_populates="selection", cascade="all, delete-orphan")

class GeneratedTestCases(Base):
    __tablename__ = "generated_test_cases"

    id = Column(Integer, primary_key=True, index=True)
    selection_id = Column(Integer, ForeignKey("selections.id", ondelete="CASCADE"), nullable=False)
    prompt = Column(Text, nullable=False)
    raw_response = Column(Text, nullable=False)
    test_cases = Column(JSON, nullable=False)  # List of test case objects
    created_at = Column(DateTime, default=utc_now)

    selection = relationship("Selection", back_populates="test_cases")
