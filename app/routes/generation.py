from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import TestCasesResponse
from app.services.generation_service import (
    generate_test_cases_for_selection,
    get_generation_with_staleness,
    get_generations_for_node
)
from typing import List

router = APIRouter(tags=["Generation"])

@router.post("/api/selections/{selection_id}/generate", status_code=status.HTTP_200_OK)
def generate_test_cases(
    selection_id: int,
    force: bool = Query(False, description="Force LLM regeneration, bypassing cache"),
    model_name: str = Query("gemini-2.5-flash", description="Gemini model name to use"),
    db: Session = Depends(get_db)
):
    """
    Given a selection, reconstructs the text, calls Gemini to generate test cases, and stores the results.
    """
    gen = generate_test_cases_for_selection(db, selection_id, force=force, model_name=model_name)
    return {
        "message": "Test cases generated successfully",
        "generation_id": gen.id,
        "selection_id": gen.selection_id,
        "test_cases": gen.test_cases
    }

@router.get("/api/selections/{selection_id}/test-cases", response_model=TestCasesResponse)
def get_selection_test_cases(selection_id: int, db: Session = Depends(get_db)):
    """
    Fetches generated test cases for a selection and returns them along with their current staleness status.
    """
    return get_generation_with_staleness(db, selection_id)

@router.get("/api/nodes/{node_id}/test-cases", response_model=List[TestCasesResponse])
def get_node_test_cases(node_id: int, db: Session = Depends(get_db)):
    """
    Fetches previously generated test cases related to a specific node ID (matched logically across versions).
    """
    return get_generations_for_node(db, node_id)
