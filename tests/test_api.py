import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app

client = TestClient(app)

@pytest.fixture(autouse=True)
def use_clean_db(clean_db):
    """Wrapper to make the clean_db fixture autouse for all API tests."""
    pass


# ─── Health Check ─────────────────────────────────────────────────────────────

def test_api_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

# ─── Ingest ───────────────────────────────────────────────────────────────────

def test_ingest_new_document_returns_201():
    """Ingesting a new document creates a document + version with correct node stats."""
    md = "# Device Manual\n## Section A\nContent A.\n## Section B\nContent B.\n"
    r = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "success"
    assert data["stats"]["total_nodes"] == 3   # root + A + B
    assert data["stats"]["new_nodes"] == 3
    assert data["stats"]["modified_nodes"] == 0


def test_ingest_version_update_detects_changes():
    """Ingesting v2 correctly marks modified, new, and unchanged nodes."""
    md_v1 = "# Manual\n## Intro\nOriginal intro.\n## Specs\nOriginal specs.\n"
    client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md_v1
    })

    md_v2 = (
        "# Manual\n"
        "## Intro\nUpdated intro content.\n"   # modified
        "## Specs\nOriginal specs.\n"           # unchanged
        "## Appendix\nNew section.\n"           # new
    )
    r = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v2",
        "markdown_content": md_v2
    })
    assert r.status_code == 201
    stats = r.json()["stats"]
    assert stats["new_nodes"] == 1
    assert stats["modified_nodes"] == 1


def test_ingest_mismatch_warning():
    """Ingesting a completely different v2 triggers a mismatch warning (no force)."""
    md_v1 = "# Manual\n## Section A\nContent.\n"
    client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md_v1,
        "is_new_document": True
    })

    md_v2 = "# Unrelated\n## ZZZ\nCompletely different.\n"
    r = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v2",
        "markdown_content": md_v2,
        "is_new_document": False
    })
    assert r.status_code == 201
    data = r.json()
    assert data["status"] == "warning"
    assert data["mismatch_percent"] > 0


def test_ingest_force_overrides_mismatch():
    """Forcing ingestion on a mismatched document proceeds successfully."""
    md_v1 = "# Manual\n## Section A\nContent.\n"
    client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md_v1,
        "is_new_document": True
    })

    md_v2 = "# Unrelated\n## ZZZ\nCompletely different.\n"
    r = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v2",
        "markdown_content": md_v2,
        "is_new_document": False,
        "force": True
    })
    assert r.status_code == 201
    assert r.json()["status"] == "success"

# ─── Nodes ────────────────────────────────────────────────────────────────────

def test_browse_nodes_returns_root_level():
    """Browse returns only root-level nodes (parent_id = NULL)."""
    md = "# Manual\n## Section A\nContent.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    }).json()
    ver_id = res["version"]["id"]
    doc_id = res["version"]["document_id"]

    r = client.get(f"/api/nodes/browse?document_id={doc_id}&version_id={ver_id}")
    assert r.status_code == 200
    nodes = r.json()
    assert len(nodes) == 1  # Only root has parent_id=NULL


def test_search_nodes_by_keyword():
    """Search returns the node matching the query term."""
    md = "# Manual\n## Safety Warnings\nSafety content.\n## Calibration\nCal content.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    }).json()
    doc_id = res["version"]["document_id"]

    r = client.get(f"/api/nodes/search?document_id={doc_id}&query=Safety")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert "Safety" in results[0]["title"]

# ─── Selections ───────────────────────────────────────────────────────────────

def test_create_selection_from_nodes():
    """Creating a selection with valid node IDs returns a selection object."""
    md = "# Manual\n## Section A\nContent.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    }).json()
    doc_id = res["version"]["document_id"]

    search_r = client.get(f"/api/nodes/search?document_id={doc_id}&query=Section")
    node_id = search_r.json()[0]["id"]

    r = client.post("/api/selections", json={
        "name": "My Test Selection",
        "node_ids": [node_id]
    })
    assert r.status_code == 201
    sel = r.json()
    assert sel["name"] == "My Test Selection"
    assert len(sel["nodes"]) == 1

# ─── Generation & Staleness ───────────────────────────────────────────────────

@patch("app.services.generation_service.generate_qa_test_cases")
def test_generate_test_cases_calls_llm(mock_llm):
    """Triggering generation calls the LLM and returns structured test cases."""
    mock_llm.return_value = {
        "prompt": "test prompt",
        "raw_response": '{"test_cases": []}',
        "test_cases": [
            {
                "title": "Functional Check",
                "steps": ["Power on device", "Check display"],
                "expected_result": "Device initialises correctly",
                "priority": "High"
            }
        ]
    }

    md = "# Manual\n## Section A\nContent.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    }).json()
    doc_id = res["version"]["document_id"]
    node_id = client.get(f"/api/nodes/search?document_id={doc_id}&query=Section").json()[0]["id"]

    sel_id = client.post("/api/selections", json={
        "name": "Gen Selection",
        "node_ids": [node_id]
    }).json()["id"]

    r = client.post(f"/api/selections/{sel_id}/generate")
    assert r.status_code == 200
    data = r.json()
    assert len(data["test_cases"]) == 1
    mock_llm.assert_called_once()


@patch("app.services.generation_service.generate_qa_test_cases")
def test_second_generate_uses_cache(mock_llm):
    """Calling generate a second time (without force) returns cached result."""
    mock_llm.return_value = {
        "prompt": "p",
        "raw_response": "{}",
        "test_cases": [{"title": "T", "steps": ["s"], "expected_result": "e", "priority": "Low"}]
    }

    md = "# Manual\n## Section A\nContent.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md
    }).json()
    doc_id = res["version"]["document_id"]
    node_id = client.get(f"/api/nodes/search?document_id={doc_id}&query=Section").json()[0]["id"]
    sel_id = client.post("/api/selections", json={"name": "Cache Test", "node_ids": [node_id]}).json()["id"]

    client.post(f"/api/selections/{sel_id}/generate")  # first call
    mock_llm.reset_mock()

    client.post(f"/api/selections/{sel_id}/generate")  # second call - should use cache
    mock_llm.assert_not_called()


@patch("app.services.generation_service.generate_qa_test_cases")
def test_staleness_detected_after_v2_ingest(mock_llm):
    """
    After generating test cases for v1, ingesting v2 with a modified section
    causes the test cases to be flagged as stale.
    """
    mock_llm.return_value = {
        "prompt": "p",
        "raw_response": "{}",
        "test_cases": [{"title": "T", "steps": ["s"], "expected_result": "e", "priority": "Low"}]
    }

    md_v1 = "# Manual\n## Section A\nOriginal content.\n"
    res = client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v1",
        "markdown_content": md_v1
    }).json()
    doc_id = res["version"]["document_id"]
    node_id = client.get(f"/api/nodes/search?document_id={doc_id}&query=Section").json()[0]["id"]
    sel_id = client.post("/api/selections", json={"name": "Stale Test", "node_ids": [node_id]}).json()["id"]

    client.post(f"/api/selections/{sel_id}/generate")

    # Verify not stale before v2
    r = client.get(f"/api/selections/{sel_id}/test-cases")
    assert r.json()["is_stale"] is False

    # Ingest v2 with modified content
    md_v2 = "# Manual\n## Section A\nUpdated content in v2.\n"
    client.post("/api/documents/ingest", json={
        "document_name": "Test Device",
        "version_label": "v2",
        "markdown_content": md_v2
    })

    # Now it should be stale
    r = client.get(f"/api/selections/{sel_id}/test-cases")
    data = r.json()
    assert data["is_stale"] is True
    assert "was modified in version v2" in data["staleness_reason"]
    assert len(data["impacted_nodes"]) == 1
    assert data["impacted_nodes"][0]["status"] == "modified"
    assert "diff" in data["impacted_nodes"][0]
