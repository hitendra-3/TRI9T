from fastapi import APIRouter, Depends, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from app.database import get_db
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
    model_name: str = Query("gemini-3.1-flash-lite", description="Gemini model name to use"),
    db: Session = Depends(get_db)
):
    """
    Given a selection, reconstructs the text, calls Gemini to generate test cases,
    and stores the results in MongoDB.

    - force=False (default): returns cached result if generation already exists.
    - force=True: triggers a new LLM call and replaces existing MongoDB document.
    """
    doc = generate_test_cases_for_selection(db, selection_id, force=force, model_name=model_name)
    return JSONResponse(content={
        "message": "Test cases generated successfully",
        "selection_id": selection_id,
        "test_cases": doc.get("test_cases", []),
        "version_label": doc.get("version_label"),
        "created_at": doc.get("created_at")
    })


@router.get("/api/selections/{selection_id}/test-cases")
def get_selection_test_cases(selection_id: int, db: Session = Depends(get_db)):
    """
    Fetches generated test cases for a selection (from MongoDB) and returns them
    with the current staleness status computed against the latest document version.
    """
    result = get_generation_with_staleness(db, selection_id)
    return JSONResponse(content=result)


@router.get("/api/nodes/{node_id}/test-cases")
def get_node_test_cases(node_id: int, db: Session = Depends(get_db)):
    """
    Fetches previously generated test cases related to a specific node ID,
    matched logically across versions using logical_id.
    """
    results = get_generations_for_node(db, node_id)
    return JSONResponse(content=results)
