from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List
from app.database import get_db
from app.schemas import DocumentResponse, DocumentVersionResponse, DocumentCreate
from app.models import Document, DocumentVersion
from app.services.ingest_service import ingest_document_version
from pydantic import BaseModel

router = APIRouter(prefix="/api/documents", tags=["Documents"])

class IngestRequest(BaseModel):
    document_name: str
    version_label: str
    markdown_content: str

@router.get("/presets/{filename}", response_model=dict)
def get_preset_file(filename: str):
    """
    Retrieves the content of a preset manual from the data/ folder.
    """
    import os
    if filename not in ["ct200_manual.md", "ct200_manual_v2.md"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid preset filename. Only ct200_manual.md and ct200_manual_v2.md are supported."
        )
    
    preset_path = os.path.join("data", filename)
    if not os.path.exists(preset_path):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Preset file {filename} not found."
        )
    
    try:
        with open(preset_path, "r", encoding="utf-8") as f:
            content = f.read()
        return {"filename": filename, "content": content}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to read preset: {str(e)}"
        )

@router.post("/ingest", response_model=dict, status_code=status.HTTP_201_CREATED)
def ingest_document(payload: IngestRequest, db: Session = Depends(get_db)):

    """
    Ingests a new version of a document. Parses, matches structure, and persists it.
    """
    try:
        version, stats = ingest_document_version(
            db,
            payload.document_name,
            payload.version_label,
            payload.markdown_content
        )
        return {
            "message": "Document version ingested successfully",
            "version": {
                "id": version.id,
                "document_id": version.document_id,
                "version_label": version.version_label,
                "created_at": version.created_at
            },
            "stats": stats
        }
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Ingestion failed: {str(e)}"
        )

@router.get("", response_model=List[DocumentResponse])
def list_documents(db: Session = Depends(get_db)):
    """
    Lists all documents.
    """
    return db.query(Document).all()

@router.get("/{document_id}/versions", response_model=List[DocumentVersionResponse])
def list_document_versions(document_id: int, db: Session = Depends(get_db)):
    """
    Lists all versions for a given document.
    """
    doc = db.query(Document).filter(Document.id == document_id).first()
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Document with ID {document_id} not found."
        )
    return db.query(DocumentVersion).filter(DocumentVersion.document_id == document_id).all()
