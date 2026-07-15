from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Selection, Node, DocumentVersion
from typing import List

def create_selection(
    db: Session,
    name: str,
    node_ids: List[int]
) -> Selection:
    """
    Creates a selection of nodes.
    Validates that:
      - All nodes exist
      - All nodes belong to the same version
    """
    if not node_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Selection must contain at least one node ID."
        )
        
    # Fetch nodes
    nodes = db.query(Node).filter(Node.id.in_(node_ids)).all()
    if len(nodes) != len(node_ids):
        found_ids = {n.id for n in nodes}
        missing_ids = list(set(node_ids) - found_ids)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Nodes with IDs {missing_ids} not found."
        )
        
    # Check that all nodes belong to the same version
    version_ids = {n.version_id for n in nodes}
    if len(version_ids) > 1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="All selected nodes must belong to the same document version."
        )
        
    version_id = list(version_ids)[0]
    
    # Create selection
    selection = Selection(
        name=name,
        version_id=version_id
    )
    db.add(selection)
    db.commit()
    db.refresh(selection)
    
    # Associate nodes
    selection.nodes.extend(nodes)
    db.commit()
    db.refresh(selection)
    
    return selection

def get_selection(db: Session, selection_id: int) -> Selection:
    """
    Retrieves a selection by ID.
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection with ID {selection_id} not found."
        )
    return selection
