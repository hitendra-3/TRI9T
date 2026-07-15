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
