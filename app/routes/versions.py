from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from app.database import get_db
from app.schemas import DocumentVersionResponse
from app.models import DocumentVersion

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
