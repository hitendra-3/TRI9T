"""
Generation service — stores QA test cases in MongoDB Atlas.

Storage design:
  - SQLite: selections, nodes, versions (relational, joins needed)
  - MongoDB: generated_test_cases (document-oriented, schema-flexible, no joins needed)

Each MongoDB document has the following shape:
{
  "selection_id":  int,               # FK to SQLite selections.id (unique index)
  "document_name": str,               # denormalised for fast reads
  "version_label": str,               # which version was selected when generated
  "prompt":        str,               # full prompt sent to LLM
  "raw_response":  str,               # raw LLM text output
  "test_cases": [                     # Pydantic-validated, structured array
    {
      "title":           str,
      "steps":           [str],
      "expected_result": str,
      "priority":        str
    }
  ],
  "source_node_snapshots": {          # content_hash per logical_id at generation time
    "<logical_id>": "<content_hash>"  # enables precise staleness detection
  },
  "created_at": datetime
}
"""

from datetime import datetime, timezone
from sqlalchemy.orm import Session
from fastapi import HTTPException, status
from app.models import Selection, Node, DocumentVersion
from app.llm import generate_qa_test_cases
from app.diff import generate_diff
from app.mongodb import get_test_cases_collection
from bson import ObjectId
import json


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _to_serialisable(doc: dict) -> dict:
    """Convert MongoDB document to JSON-serialisable dict."""
    if doc is None:
        return None
    doc = dict(doc)
    if "_id" in doc:
        doc["_id"] = str(doc["_id"])
    if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
        doc["created_at"] = doc["created_at"].isoformat()
    return doc


# ─── Core Generation ──────────────────────────────────────────────────────────

def generate_test_cases_for_selection(
    db: Session,
    selection_id: int,
    force: bool = False,
    model_name: str = "gemini-3.1-flash-lite"
) -> dict:
    """
    Generates QA test cases for a selection and stores them in MongoDB.

    Duplicate policy:
      - force=False (default): return the cached MongoDB document if it exists.
      - force=True:            call the LLM again and REPLACE the existing document.

    This design means old test cases are overwritten (not versioned) on force.
    Rationale: regeneration is an explicit user choice; keeping old versions
    alongside new ones would require a separate history collection and adds
    complexity without clear benefit for a QA workflow.
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection with ID {selection_id} not found."
        )

    col = get_test_cases_collection()

    # ── Cache check ──────────────────────────────────────────────────────────
    existing = col.find_one({"selection_id": selection_id})
    if existing and not force:
        return _to_serialisable(existing)

    # ── Build context from selected nodes ────────────────────────────────────
    nodes = sorted(selection.nodes, key=lambda n: n.id)
    if not nodes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The selection has no nodes linked to it."
        )

    context_parts = []
    source_snapshots = {}
    for node in nodes:
        context_parts.append(
            f"Heading: {node.heading}\nPath: {node.path}\n"
            f"Level: {node.level}\nContent:\n{node.body_text}"
        )
        source_snapshots[node.logical_id] = node.content_hash

    context_text = "\n\n---\n\n".join(context_parts)
    doc_name = selection.version.document.name
    version_label = selection.version.version_label

    # ── Call LLM ─────────────────────────────────────────────────────────────
    try:
        result = generate_qa_test_cases(doc_name, context_text, model_name)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"LLM Generation failed: {str(e)}"
        )

    # ── Persist to MongoDB ────────────────────────────────────────────────────
    mongo_doc = {
        "selection_id": selection_id,
        "document_name": doc_name,
        "version_label": version_label,
        "prompt": result["prompt"],
        "raw_response": result["raw_response"],
        "test_cases": result["test_cases"],
        "source_node_snapshots": source_snapshots,
        "created_at": datetime.now(timezone.utc)
    }

    if existing:
        col.replace_one({"selection_id": selection_id}, mongo_doc)
        mongo_doc = col.find_one({"selection_id": selection_id})
    else:
        insert_result = col.insert_one(mongo_doc)
        mongo_doc["_id"] = insert_result.inserted_id

    return _to_serialisable(mongo_doc)


# ─── Staleness Detection ──────────────────────────────────────────────────────

def get_generation_with_staleness(db: Session, selection_id: int) -> dict:
    """
    Retrieves the generated test cases from MongoDB and computes staleness
    by comparing source_node_snapshots against the current latest version.

    Staleness logic:
      - We stored the content_hash of each node AT GENERATION TIME.
      - We look up each node's current hash in the latest document version.
      - If any hash differs, the test case is stale (even for a single word change).

    Honest limitation: a one-word prose change is treated identically to a
    changed numeric threshold (e.g. 299 mmHg → 250 mmHg). Both are flagged
    as stale. A future improvement would parse diffs for numeric changes and
    assign them higher priority ("critical-stale" vs "prose-stale").
    """
    selection = db.query(Selection).filter(Selection.id == selection_id).first()
    if not selection:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Selection with ID {selection_id} not found."
        )

    col = get_test_cases_collection()
    mongo_doc = col.find_one({"selection_id": selection_id})
    if not mongo_doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No test cases have been generated for selection {selection_id} yet."
        )

    # ── Latest version lookup ─────────────────────────────────────────────────
    doc_id = selection.version.document_id
    latest_version = (
        db.query(DocumentVersion)
        .filter(DocumentVersion.document_id == doc_id)
        .order_by(DocumentVersion.created_at.desc())
        .first()
    )

    is_stale = False
    staleness_reasons = []
    impacted_nodes = []

    pinned_label = selection.version.version_label
    latest_label = latest_version.version_label if latest_version else "Unknown"

    if latest_version and selection.version_id != latest_version.id:
        # Build lookup: logical_id → (current_hash, node)
        latest_nodes = db.query(Node).filter(Node.version_id == latest_version.id).all()
        latest_by_logical = {n.logical_id: n for n in latest_nodes}

        # source_node_snapshots may be missing in old docs (pre-MongoDB migration)
        snapshots = mongo_doc.get("source_node_snapshots") or {
            n.logical_id: n.content_hash for n in selection.nodes
        }

        for logical_id, old_hash in snapshots.items():
            l_node = latest_by_logical.get(logical_id)

            if not l_node:
                is_stale = True
                staleness_reasons.append(
                    f"Node '{logical_id}' was deleted in version {latest_label}."
                )
                impacted_nodes.append({
                    "logical_id": logical_id,
                    "status": "deleted",
                    "diff": f"Section deleted in {latest_label}."
                })
            elif l_node.content_hash != old_hash:
                is_stale = True
                # Fetch old body text from pinned selection node
                pinned_node = next(
                    (n for n in selection.nodes if n.logical_id == logical_id), None
                )
                old_body = pinned_node.body_text if pinned_node else ""
                diff_text = generate_diff(old_body, l_node.body_text, pinned_label, latest_label)
                staleness_reasons.append(
                    f"Section '{l_node.path}' was modified in version {latest_label}."
                )
                impacted_nodes.append({
                    "logical_id": logical_id,
                    "heading": l_node.title,
                    "path": l_node.path,
                    "status": "modified",
                    "diff": diff_text
                })

    doc_out = _to_serialisable(mongo_doc)
    doc_out.update({
        "selection_id": selection_id,
        "version_id": selection.version_id,
        "is_stale": is_stale,
        "staleness_reason": "; ".join(staleness_reasons) if staleness_reasons else None,
        "impacted_nodes": impacted_nodes
    })
    return doc_out


# ─── Retrieval by Node ────────────────────────────────────────────────────────

def get_generations_for_node(db: Session, node_id: int) -> list:
    """
    Fetches all MongoDB generation documents that included a given node
    (matched by logical_id across all versions).
    """
    node = db.query(Node).filter(Node.id == node_id).first()
    if not node:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Node with ID {node_id} not found."
        )

    # Find all selections that contain this logical_id
    selections = (
        db.query(Selection)
        .join(Selection.nodes)
        .filter(Node.logical_id == node.logical_id)
        .all()
    )

    results = []
    for sel in selections:
        col = get_test_cases_collection()
        if col.find_one({"selection_id": sel.id}):
            results.append(get_generation_with_staleness(db, sel.id))

    return results
