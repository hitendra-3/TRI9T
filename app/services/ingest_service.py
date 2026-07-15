from sqlalchemy.orm import Session
from app.models import Document, DocumentVersion, Node
from app.parser import parse_markdown
from app.versioning import match_and_version_nodes
import datetime

def ingest_document_version(
    db: Session,
    document_name: str,
    version_label: str,
    markdown_content: str
) -> tuple[DocumentVersion, dict]:
    """
    Ingests a new version of a document.
    Parses the markdown, matches nodes with the previous version,
    and persists everything.
    
    Returns:
        (DocumentVersion, stats_dict)
    """
    # 1. Create or get document
    doc = db.query(Document).filter(Document.name == document_name).first()
    if not doc:
        doc = Document(name=document_name)
        db.add(doc)
        db.commit()
        db.refresh(doc)
        
    # 2. Check for previous version (most recently created version)
    prev_version = db.query(DocumentVersion)\
        .filter(DocumentVersion.document_id == doc.id)\
        .order_by(DocumentVersion.created_at.desc())\
        .first()
    
    # 3. Handle if version_label already exists (e.g. overwrite for idempotency)
    existing_version = db.query(DocumentVersion)\
        .filter(DocumentVersion.document_id == doc.id, DocumentVersion.version_label == version_label)\
        .first()
    if existing_version:
        db.delete(existing_version)
        db.commit()
        # Re-fetch previous version just in case the deleted one was the previous version
        prev_version = db.query(DocumentVersion)\
            .filter(DocumentVersion.document_id == doc.id)\
            .order_by(DocumentVersion.created_at.desc())\
            .first()

    # Create new document version
    new_version = DocumentVersion(
        document_id=doc.id,
        version_label=version_label
    )
    db.add(new_version)
    db.commit()
    db.refresh(new_version)
    
    # 4. Parse markdown
    parsed_nodes = parse_markdown(markdown_content)
    
    # 5. Version and match nodes
    prev_version_id = prev_version.id if prev_version else None
    enriched_nodes = match_and_version_nodes(db, doc.id, parsed_nodes, prev_version_id)
    
    # 6. Save nodes in order (parents first)
    path_to_db_id = {}
    new_count = 0
    modified_count = 0
    unchanged_count = 0
    
    for en_node in enriched_nodes:
        # Check if parent is already saved to link parent_id
        parent_id = None
        if en_node["parent_path"] and en_node["parent_path"] in path_to_db_id:
            parent_id = path_to_db_id[en_node["parent_path"]]
            
        db_node = Node(
            document_id=doc.id,
            version_id=new_version.id,
            logical_id=en_node["logical_id"],
            heading=en_node["heading"],
            title=en_node["title"],
            level=en_node["level"],
            body_text=en_node["body_text"],
            content_hash=en_node["content_hash"],
            parent_id=parent_id,
            path=en_node["path"]
        )
        db.add(db_node)
        db.commit()
        db.refresh(db_node)
        
        # Track path to db id mapping for child lookups
        path_to_db_id[en_node["path"]] = db_node.id
        
        # Statistics
        if en_node["is_new"]:
            new_count += 1
        elif en_node["is_modified"]:
            modified_count += 1
        else:
            unchanged_count += 1
            
    # Calculate deleted nodes statistics
    deleted_count = 0
    if prev_version_id:
        prev_nodes = db.query(Node).filter(Node.version_id == prev_version_id).all()
        prev_logical_ids = {n.logical_id for n in prev_nodes}
        current_logical_ids = {n["logical_id"] for n in enriched_nodes}
        deleted_count = len(prev_logical_ids - current_logical_ids)
        
    stats = {
        "total_nodes": len(enriched_nodes),
        "new_nodes": new_count,
        "modified_nodes": modified_count,
        "unchanged_nodes": unchanged_count,
        "deleted_nodes": deleted_count
    }
    
    return new_version, stats
