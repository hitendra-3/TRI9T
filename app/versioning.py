from typing import Optional
import uuid
from typing import List, Dict, Any, Tuple
from sqlalchemy.orm import Session
from app.models import Node, DocumentVersion
from app.hashing import compute_content_hash
from app.diff import generate_diff

def match_and_version_nodes(
    db: Session,
    document_id: int,
    parsed_nodes: List[Dict[str, Any]],
    v1_version_id: Optional[int]
) -> List[Dict[str, Any]]:
    """
    Matches parsed nodes for a new version against an existing version (v1_version_id).
    If matched by path:
        - Reuses the logical_id.
        - Compares content_hash.
    If new:
        - Generates a new logical_id.
        
    Returns the list of node dicts enriched with:
        - logical_id
        - content_hash
        - is_new (bool)
        - is_modified (bool)
        - old_node_id (optional db ID of matched node in V1)
    """
    # 1. Fetch all nodes of the previous version if it exists
    v1_nodes_by_path: Dict[str, Node] = {}
    if v1_version_id:
        v1_nodes = db.query(Node).filter(Node.version_id == v1_version_id).all()
        v1_nodes_by_path = {n.path: n for n in v1_nodes}
        
    enriched_nodes = []
    for parsed in parsed_nodes:
        path = parsed["path"]
        heading = parsed["heading"]
        title = parsed["title"]
        level = parsed["level"]
        body_text = parsed["body_text"]
        
        # Compute current content hash
        current_hash = compute_content_hash(heading, level, body_text)
        
        is_new = True
        is_modified = False
        logical_id = str(uuid.uuid4())
        old_node_id = None
        
        # Try matching by path
        if path in v1_nodes_by_path:
            v1_node = v1_nodes_by_path[path]
            logical_id = v1_node.logical_id
            old_node_id = v1_node.id
            is_new = False
            # Check if content has modified
            if v1_node.content_hash != current_hash:
                is_modified = True
                
        enriched_nodes.append({
            **parsed,
            "logical_id": logical_id,
            "content_hash": current_hash,
            "is_new": is_new,
            "is_modified": is_modified,
            "old_node_id": old_node_id
        })
        
    return enriched_nodes
