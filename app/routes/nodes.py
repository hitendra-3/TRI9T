from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db
from app.schemas import NodeResponse, NodeDetailResponse, DiffSummary
from app.models import Node, DocumentVersion, Document
from app.diff import generate_diff

router = APIRouter(prefix="/api/nodes", tags=["Nodes"])

@router.get("/browse", response_model=List[NodeResponse])
def browse_top_level_nodes(
    document_id: int,
    version_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Lists all top-level sections (where parent_id is NULL) for a given document version.
    Defaults to the latest version if version_id is not specified.
    """
    # 1. Resolve version
    if version_id is None:
        latest = db.query(DocumentVersion)\
            .filter(DocumentVersion.document_id == document_id)\
            .order_by(DocumentVersion.created_at.desc())\
            .first()
        if not latest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No versions found for document ID {document_id}."
            )
        version_id = latest.id
    else:
        ver = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
        if not ver:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Version with ID {version_id} not found."
            )

    # 2. Query top-level nodes
    nodes = db.query(Node).filter(
        Node.version_id == version_id,
        Node.parent_id.is_(None)
    ).all()
    
    return nodes

@router.get("/search", response_model=List[NodeResponse])
def search_nodes(
    document_id: int,
    query: str = Query(..., min_length=1),
    version_id: Optional[int] = None,
    db: Session = Depends(get_db)
):
    """
    Searches/filters sections across headings or body text using a simple SQLite LIKE search.
    """
    if version_id is None:
        latest = db.query(DocumentVersion)\
            .filter(DocumentVersion.document_id == document_id)\
            .order_by(DocumentVersion.created_at.desc())\
            .first()
        if not latest:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"No versions found for document ID {document_id}."
            )
        version_id = latest.id
        
    search_pattern = f"%{query}%"
    nodes = db.query(Node).filter(
        Node.version_id == version_id,
        (Node.heading.like(search_pattern) | Node.body_text.like(search_pattern))
    ).all()
    
    return nodes

@router.get("/{node_id}", response_model=NodeDetailResponse)
def get_node_by_id(node_id: int, db: Session = Depends(get_db)):
    """
    Fetches a specific node by ID, including its full text, content hash, and children.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID {node_id} not found."
        )
        
    # Fetch children in the same version
    children = db.query(Node).filter(
        Node.version_id == node.version_id,
        Node.parent_id == node.id
    ).all()
    
    # Map to schema
    detail = NodeDetailResponse(
        id=node.id,
        document_id=node.document_id,
        version_id=node.version_id,
        logical_id=node.logical_id,
        heading=node.heading,
        title=node.title,
        level=node.level,
        body_text=node.body_text,
        content_hash=node.content_hash,
        parent_id=node.parent_id,
        path=node.path,
        children=[NodeResponse.model_validate(c) for c in children]
    )
    
    return detail

@router.get("/{node_id}/diff", response_model=DiffSummary)
def get_node_diff(node_id: int, db: Session = Depends(get_db)):
    """
    Given a node ID, checks if it has changed compared to its counterpart in the latest document version.
    Returns whether it changed, and if so, a unified diff summary.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID {node_id} not found."
        )
        
    # Find latest version of the document
    latest_version = db.query(DocumentVersion)\
        .filter(DocumentVersion.document_id == node.document_id)\
        .order_by(DocumentVersion.created_at.desc())\
        .first()
        
    if not latest_version:
        return DiffSummary(has_changed=False, diff_type="unchanged")
        
    # Find counterpart node in the latest version by logical_id
    latest_node = db.query(Node).filter(
        Node.version_id == latest_version.id,
        Node.logical_id == node.logical_id
    ).first()
    
    node_version_label = node.version.version_label
    latest_version_label = latest_version.version_label
    
    if not latest_node:
        # Node was deleted in the latest version
        return DiffSummary(
            has_changed=True,
            diff_type="deleted",
            old_version=node_version_label,
            new_version=latest_version_label,
            old_content=node.body_text,
            new_content=None,
            diff_text=f"--- {node_version_label}\n+++ {latest_version_label} (deleted)\n@@ -1,{len(node.body_text.splitlines())} +0,0 @@\n" + "\n".join(f"- {line}" for line in node.body_text.splitlines())
        )
        
    if node.content_hash == latest_node.content_hash:
        # No change
        return DiffSummary(
            has_changed=False,
            diff_type="unchanged",
            old_version=node_version_label,
            new_version=latest_version_label,
            old_content=node.body_text,
            new_content=latest_node.body_text,
            diff_text=""
        )
        
    # Content has changed
    diff_text = generate_diff(
        node.body_text,
        latest_node.body_text,
        node_version_label,
        latest_version_label
    )
    
    return DiffSummary(
        has_changed=True,
        diff_type="modified",
        old_version=node_version_label,
        new_version=latest_version_label,
        old_content=node.body_text,
        new_content=latest_node.body_text,
        diff_text=diff_text
    )
