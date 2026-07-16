from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Optional
from app.database import get_db, engine, Base
from app.schemas import DocumentResponse, DocumentVersionResponse, DocumentCreate
from app.models import Document, DocumentVersion, Node, Selection, GeneratedTestCases, selection_nodes
from app.services.ingest_service import ingest_document_version
from app.parser import parse_markdown, parse_pdf_to_markdown
from pydantic import BaseModel
from sqlalchemy import text
import base64

router = APIRouter(prefix="/api/documents", tags=["Documents"])

# ── Admin: Clear DB ──────────────────────────────────────────────────────────
@router.delete("/admin/clear-db", tags=["Admin"])
def clear_database(db: Session = Depends(get_db)):
    """
    Drops all data from every table and resets sequences.
    FOR TESTING ONLY.
    """
    try:
        # Delete in FK-safe order
        # Note: generated_test_cases is now stored in MongoDB; the SQLite table may not exist
        try:
            db.execute(text("DELETE FROM generated_test_cases"))
        except Exception:
            pass  # Table moved to MongoDB
        db.execute(text("DELETE FROM selection_nodes"))
        db.execute(text("DELETE FROM selections"))
        db.execute(text("DELETE FROM nodes"))
        db.execute(text("DELETE FROM document_versions"))
        db.execute(text("DELETE FROM documents"))
        # Reset SQLite auto-increment counters
        for tbl in ["selection_nodes","selections","nodes","document_versions","documents"]:
            try:
                db.execute(text(f"DELETE FROM sqlite_sequence WHERE name='{tbl}'"))
            except Exception:
                pass
        db.commit()
        
        # Clear MongoDB/local JSON collection as well
        from app.mongodb import clear_mongo_collections
        clear_mongo_collections()
        
        return {"status": "cleared", "message": "All data has been wiped. Ready for fresh testing."}
    except Exception as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=f"Clear failed: {str(e)}")



class IngestRequest(BaseModel):
    document_name: str
    version_label: str
    markdown_content: Optional[str] = None
    file_base64: Optional[str] = None
    file_type: Optional[str] = None  # "pdf", "md", "txt"
    force: bool = False
    is_new_document: bool = False
    document_id: Optional[int] = None

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
    If mismatch with previous version exceeds 70%, returns a warning unless force=True.
    """
    # 0. Decode and parse PDF/Text base64 if provided
    if payload.file_base64:
        try:
            file_bytes = base64.b64decode(payload.file_base64)
            if payload.file_type == "pdf":
                payload.markdown_content = parse_pdf_to_markdown(file_bytes)
            else:
                payload.markdown_content = file_bytes.decode("utf-8", errors="replace")
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Failed to process uploaded file: {str(e)}"
            )

    if not payload.markdown_content:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Either markdown_content or file_base64 must be provided."
        )
    # 1. Resolve document
    doc = None
    if payload.document_id:
        doc = db.query(Document).filter(Document.id == payload.document_id).first()
    else:
        doc = db.query(Document).filter(Document.name == payload.document_name).first()
        
    if not doc:
        # Document does not exist yet; treat it as a new document upload for backward compatibility
        payload.is_new_document = True
        
    # 2. Check for mismatch if a previous version exists
    if doc and not payload.is_new_document:
        prev_version = db.query(DocumentVersion)\
            .filter(DocumentVersion.document_id == doc.id)\
            .order_by(DocumentVersion.created_at.desc())\
            .first()
            
        if prev_version:
            # Parse markdown content to calculate mismatch rate
            parsed_nodes = parse_markdown(payload.markdown_content)
            if not parsed_nodes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No sections could be parsed from the provided markdown content."
                )
                
            # Fetch previous nodes from DB
            prev_nodes = db.query(Node).filter(Node.version_id == prev_version.id).all()
            prev_paths = {n.path for n in prev_nodes if n.level > 1}
            
            # Count matches
            new_paths = {n["path"] for n in parsed_nodes if n["level"] > 1}
            if not new_paths:  # Fallback if only level 1 headings exist
                new_paths = {n["path"] for n in parsed_nodes}
                prev_paths = {n.path for n in prev_nodes}
                
            match_count = sum(1 for p in new_paths if p in prev_paths)
            total_new = len(new_paths)
            
            mismatch_ratio = (total_new - match_count) / total_new if total_new > 0 else 0.0
            mismatch_percent = mismatch_ratio * 100.0
            
            if mismatch_percent > 70.0 and not payload.force:
                return {
                    "status": "warning",
                    "message": "mismatch check",
                    "mismatch_percent": round(mismatch_percent, 1),
                    "matched_nodes": match_count,
                    "total_nodes": total_new
                }

    # 3. Perform the actual ingestion
    try:
        version, stats = ingest_document_version(
            db,
            payload.document_name,
            payload.version_label,
            payload.markdown_content
        )
        return {
            "status": "success",
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
