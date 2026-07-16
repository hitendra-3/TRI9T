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

@router.get("/{version_id}/diff")
def get_version_diff(version_id: int, db: Session = Depends(get_db)):
    """
    Returns a detailed node-level diff between a version and its immediate predecessor.
    Each entry includes the section heading, path, status (new/modified/deleted/unchanged),
    and a unified diff text for modified nodes.
    """
    from app.diff import generate_diff

    version = db.query(DocumentVersion).filter(DocumentVersion.id == version_id).first()
    if not version:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Version with ID {version_id} not found."
        )

    # Find the immediate predecessor version for this document
    prev_version = db.query(DocumentVersion)\
        .filter(
            DocumentVersion.document_id == version.document_id,
            DocumentVersion.created_at < version.created_at
        )\
        .order_by(DocumentVersion.created_at.desc())\
        .first()

    current_nodes = db.query(Node).filter(Node.version_id == version_id).all()

    if not prev_version:
        # First version — all nodes are new
        return {
            "version_id": version_id,
            "version_label": version.version_label,
            "prev_version_id": None,
            "prev_version_label": None,
            "is_first_version": True,
            "summary": {
                "total": len(current_nodes),
                "new": len(current_nodes),
                "modified": 0,
                "deleted": 0,
                "unchanged": 0
            },
            "changes": [
                {
                    "logical_id": n.logical_id,
                    "heading": n.title,
                    "path": n.path,
                    "level": n.level,
                    "status": "new",
                    "diff_text": None
                }
                for n in current_nodes
            ]
        }

    prev_nodes = db.query(Node).filter(Node.version_id == prev_version.id).all()
    prev_by_logical = {n.logical_id: n for n in prev_nodes}
    curr_by_logical = {n.logical_id: n for n in current_nodes}

    changes = []
    new_count = modified_count = deleted_count = unchanged_count = 0

    # Check current nodes vs previous
    for n in current_nodes:
        prev_n = prev_by_logical.get(n.logical_id)
        if prev_n is None:
            new_count += 1
            changes.append({
                "logical_id": n.logical_id,
                "heading": n.title,
                "path": n.path,
                "level": n.level,
                "status": "new",
                "diff_text": None
            })
        elif n.content_hash != prev_n.content_hash:
            modified_count += 1
            diff_text = generate_diff(
                prev_n.body_text or "",
                n.body_text or "",
                prev_version.version_label,
                version.version_label
            )
            changes.append({
                "logical_id": n.logical_id,
                "heading": n.title,
                "path": n.path,
                "level": n.level,
                "status": "modified",
                "diff_text": diff_text
            })
        else:
            unchanged_count += 1

    # Check for deleted nodes (in prev but not in current)
    for logical_id, prev_n in prev_by_logical.items():
        if logical_id not in curr_by_logical:
            deleted_count += 1
            changes.append({
                "logical_id": logical_id,
                "heading": prev_n.title,
                "path": prev_n.path,
                "level": prev_n.level,
                "status": "deleted",
                "diff_text": generate_diff(
                    prev_n.body_text or "",
                    "",
                    prev_version.version_label,
                    version.version_label
                )
            })

    # Sort: modified first, then deleted, then new, then unchanged
    STATUS_ORDER = {"modified": 0, "deleted": 1, "new": 2, "unchanged": 3}
    changes.sort(key=lambda x: (STATUS_ORDER.get(x["status"], 9), x["path"]))

    return {
        "version_id": version_id,
        "version_label": version.version_label,
        "prev_version_id": prev_version.id,
        "prev_version_label": prev_version.version_label,
        "is_first_version": False,
        "summary": {
            "total": len(current_nodes),
            "new": new_count,
            "modified": modified_count,
            "deleted": deleted_count,
            "unchanged": unchanged_count
        },
        "changes": changes
    }

