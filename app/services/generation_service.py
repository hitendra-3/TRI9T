from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Selection, GeneratedTestCases, Node, DocumentVersion, Document
from app.llm import generate_qa_test_cases
from app.diff import generate_diff
import json

def generate_test_cases_for_selection(
    db: Session,
    selection_id: int,
    force: bool = False,
    model_name: str = "gemini-2.5-flash"
) -> GeneratedTestCases:
    """
    Generates QA test cases for a selection.
    If force is False, returns cached generation if it exists.
    Otherwise makes a call to Gemini.
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection with ID {selection_id} not found."
        )
        
    # Check cache
    existing_gen = db.query(GeneratedTestCases).filter(GeneratedTestCases.selection_id == selection_id).first()
    if existing_gen and not force:
        return existing_gen
        
    # Reconstruct text content of selected nodes sorted by ID (maintaining document order)
    nodes = sorted(selection.nodes, key=lambda n: n.id)
    if not nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selection has no nodes linked to it."
        )
        
    context_parts = []
    for node in nodes:
        context_parts.append(f"Heading: {node.heading}\nPath: {node.path}\nLevel: {node.level}\nContent:\n{node.body_text}")
    context_text = "\n\n---\n\n".join(context_parts)
    
    doc_name = selection.version.document.name
    
    # Call LLM
    try:
        result = generate_qa_test_cases(doc_name, context_text, model_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM Generation failed: {str(e)}"
        )
        
    # Save/Update in DB
    if existing_gen:
        existing_gen.prompt = result["prompt"]
        existing_gen.raw_response = result["raw_response"]
        existing_gen.test_cases = result["test_cases"]
        db.commit()
        db.refresh(existing_gen)
        return existing_gen
    else:
        new_gen = GeneratedTestCases(
            selection_id=selection_id,
            prompt=result["prompt"],
            raw_response=result["raw_response"],
            test_cases=result["test_cases"]
        )
        db.add(new_gen)
        db.commit()
        db.refresh(new_gen)
        return new_gen

def get_generation_with_staleness(
    db: Session,
    selection_id: int
) -> dict:
    """
    Retrieves the generated test cases for a selection and detects staleness
    against the latest version of the document.
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection with ID {selection_id} not found."
        )
        
    gen = db.query(GeneratedTestCases).filter(GeneratedTestCases.selection_id == selection_id).first()
    if not gen:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No test cases have been generated for selection {selection_id} yet."
        )
        
    # Detect staleness
    # 1. Get latest version of the document
    doc_id = selection.version.document_id
    latest_version = db.query(DocumentVersion)\
        .filter(DocumentVersion.document_id == doc_id)\
        .order_by(DocumentVersion.created_at.desc())\
        .first()
        
    is_stale = False
    staleness_reasons = []
    impacted_nodes = []
    
    # 2. Compare pinned selection nodes to latest version nodes
    pinned_version_label = selection.version.version_label
    latest_version_label = latest_version.version_label if latest_version else "Unknown"
    
    # If the selection version is indeed the latest version, then it's not stale
    if latest_version and selection.version_id != latest_version.id:
        # Fetch latest nodes indexed by logical_id for fast lookup
        latest_nodes = db.query(Node).filter(Node.version_id == latest_version.id).all()
        latest_nodes_by_logical = {n.logical_id: n for n in latest_nodes}
        
        for p_node in selection.nodes:
            # Find counterpart in latest version by logical ID
            l_node = latest_nodes_by_logical.get(p_node.logical_id)
            
            node_status = "unchanged"
            diff_text = None
            
            if not l_node:
                # Node deleted
                is_stale = True
                node_status = "deleted"
                reason = f"Section '{p_node.path}' was deleted in version {latest_version_label}."
                staleness_reasons.append(reason)
                impacted_nodes.append({
                    "node_id": p_node.id,
                    "logical_id": p_node.logical_id,
                    "path": p_node.path,
                    "status": "deleted",
                    "diff": f"--- {pinned_version_label}\n+++ {latest_version_label}\n@@ -1 +0,0 @@\n- {p_node.body_text[:100]}..."
                })
            elif p_node.content_hash != l_node.content_hash:
                # Node modified
                is_stale = True
                node_status = "modified"
                diff_text = generate_diff(
                    p_node.body_text,
                    l_node.body_text,
                    pinned_version_label,
                    latest_version_label
                )
                reason = f"Section '{p_node.path}' was modified in version {latest_version_label}."
                staleness_reasons.append(reason)
                impacted_nodes.append({
                    "node_id": p_node.id,
                    "logical_id": p_node.logical_id,
                    "path": p_node.path,
                    "status": "modified",
                    "diff": diff_text
                })
                
    staleness_reason_str = "; ".join(staleness_reasons) if staleness_reasons else None
    
    return {
        "id": gen.id,
        "selection_id": gen.selection_id,
        "test_cases": gen.test_cases,
        "created_at": gen.created_at,
        "is_stale": is_stale,
        "staleness_reason": staleness_reason_str,
        "impacted_nodes": impacted_nodes
    }

def get_generations_for_node(
    db: Session,
    node_id: int
) -> list:
    """
    Fetches all generated test cases that include a specific node ID (logical matching).
    Returns list of dicts with test cases, selection metadata, and staleness details.
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID {node_id} not found."
        )
        
    # To find generations linked to this logical node, we find all selections
    # that contain any Node sharing node.logical_id.
    selections = db.query(Selection)\
        .join(Selection.nodes)\
        .filter(Node.logical_id == node.logical_id)\
        .all()
        
    results = []
    for sel in selections:
        # Check if there is an associated test case generation
        gen = db.query(GeneratedTestCases).filter(GeneratedTestCases.selection_id == sel.id).first()
        if gen:
            staleness_details = get_generation_with_staleness(db, sel.id)
            results.append(staleness_details)
            
    return results
