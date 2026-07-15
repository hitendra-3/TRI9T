from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import SelectionCreate, SelectionResponse
from app.services.selection_service import create_selection, get_selection
from app.models import Selection
from typing import List

router = APIRouter(prefix="/api/selections", tags=["Selections"])

@router.post("", response_model=SelectionResponse, status_code=status.HTTP_201_CREATED)
def post_selection(payload: SelectionCreate, db: Session = Depends(get_db)):
    """
    Submits a set of node IDs as a named "selection" and pins them to their version.
    """
    return create_selection(db, payload.name, payload.node_ids)

@router.get("", response_model=List[SelectionResponse])
def list_selections(db: Session = Depends(get_db)):
    """
    Lists all selections.
    """
    return db.query(Selection).all()

@router.get("/{selection_id}", response_model=SelectionResponse)
def read_selection(selection_id: int, db: Session = Depends(get_db)):
    """
    Retrieves selection details including all selected nodes.
    """
    return get_selection(db, selection_id)

