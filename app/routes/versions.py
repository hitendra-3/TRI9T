from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import DocumentVersionResponse
from app.models import DocumentVersion, Node

router = APIRouter(prefix="/api/versions", tags=["Versions"])

@router.get("/{version_id}", response_model=DocumentVersionResponse)
def get_version(version_id: int, db: Session = Depends(get_db)):
    """
    Retrieves document version details by version ID.
    """
    version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version with ID {version_id} not found."
        )
    return version

@router.get("/{version_id}/stats", response_model=dict)
def get_version_stats(version_id: int, db: Session = Depends(get_db)):
    """
    Computes statistics for a version compared to its predecessor.
    """
    version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version with ID {version_id} not found."
        )
        
    # Get all nodes in this version
    nodes = db.query(Node).filter(Node.version_id == version_id).all()
    total_nodes = len(nodes)
    
    # Get predecessor version of the same document
    prev_version = db.query(DocumentVersion)\
        .filter(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.created_at < version.created_at
        )\
        .order_by(DocumentVersion.created_at.desc())\
        .first()
        
    if not prev_version:
        # First version: all nodes are new
        return {
            "total_nodes": total_nodes,
            "new_nodes": total_nodes,
            "modified_nodes": 0,
            "unchanged_nodes": 0,
            "deleted_nodes": 0
        }
        
    # Get predecessor nodes
    prev_nodes = db.query(Node).filter(Node.version_id == prev_version.id).all()
    prev_nodes_by_logical = {n.logical_id: n for n in prev_nodes}
    
    new_count = 0
    modified_count = 0
    unchanged_count = 0
    
    for n in nodes:
        if n.logical_id not in prev_nodes_by_logical:
            new_count += 1
        elif n.content_hash != prev_nodes_by_logical[n.logical_id].content_hash:
            modified_count += 1
        else:
            unchanged_count += 1
            
    deleted_count = len(set(prev_nodes_by_logical.keys()) - {n.logical_id for n in nodes})
    
    return {
        "total_nodes": total_nodes,
        "new_nodes": new_count,
        "modified_nodes": modified_count,
        "unchanged_nodes": unchanged_count,
        "deleted_nodes": deleted_count
    }
