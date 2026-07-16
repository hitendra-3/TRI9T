import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch
from app.main import app
from app.database import Base, engine, SessionLocal
from app.models import Node, DocumentVersion, Selection, GeneratedTestCases

# Setup a clean test database for each test run
@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)

client = TestClient(app)

def test_api_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

@patch("app.services.generation_service.generate_qa_test_cases")
def test_full_workflow_integration(mock_generate_llm):
    # Setup mock return value for LLM generation
    mock_generate_llm.return_value = {
        "prompt": "mock prompt",
        "raw_response": '{"test_cases": []}',
        "test_cases": [
            {
                "title": "Cuff Pressure Check",
                "steps": ["Step 1: Spike cuff pressure to 300 mmHg"],
                "expected_result": "Emergency deflation valve opens",
                "priority": "High"
            }
        ]
    }

    # 1. Ingest V1
    v1_markdown = """# CardioTrack CT-200
## 1. Overview
Body text for overview version 1.
## 2. Safety Alarms
Body text for safety alarms version 1.
"""
    response = client.post(
        "/api/documents/ingest",
        json={
            "document_name": "CardioTrack CT-200",
            "version_label": "v1",
            "markdown_content": v1_markdown
        }
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["stats"]["total_nodes"] == 3
    version_v1_id = res_data["version"]["id"]
    
    # 2. Browse nodes
    response = client.get(f"/api/nodes/browse?document_id=1&version_id={version_v1_id}")
    assert response.status_code == 200
    nodes = response.json()
    assert len(nodes) == 1 # Only Root node has parent_id as NULL
    
    # Search nodes to get specific node IDs
    response = client.get("/api/nodes/search?document_id=1&query=Safety")
    assert response.status_code == 200
    search_results = response.json()
    assert len(search_results) == 1
    safety_node_v1 = search_results[0]
    safety_node_v1_id = safety_node_v1["id"]
    
    # 3. Create a selection with the Safety Alarms node
    response = client.post(
        "/api/selections",
        json={
            "name": "Safety Systems Selection",
            "node_ids": [safety_node_v1_id]
        }
    )
    assert response.status_code == 201
    selection = response.json()
    selection_id = selection["id"]
    
    # 4. Generate test cases (triggers LLM)
    response = client.post(f"/api/selections/{selection_id}/generate")
    assert response.status_code == 200
    gen_data = response.json()
    assert len(gen_data["test_cases"]) == 1
    assert gen_data["test_cases"][0]["title"] == "Cuff Pressure Check"
    
    # Ensure LLM service was called
    mock_generate_llm.assert_called_once()
    mock_generate_llm.reset_mock()
    
    # Generate again WITHOUT force -> should return cached result, not calling LLM
    response = client.post(f"/api/selections/{selection_id}/generate")
    assert response.status_code == 200
    mock_generate_llm.assert_not_called()
    
    # 5. Check staleness (currently it should NOT be stale because V1 is still the latest version)
    response = client.get(f"/api/selections/{selection_id}/test-cases")
    assert response.status_code == 200
    test_cases_status = response.json()
    assert test_cases_status["is_stale"] is False
    assert test_cases_status["staleness_reason"] is None
    
    # 6. Ingest V2 (where Safety Alarms node content is modified)
    v2_markdown = """# CardioTrack CT-200
## 1. Overview
Body text for overview version 1.
## 2. Safety Alarms
Body text for safety alarms version 2. Content modified!
"""
    response = client.post(
        "/api/documents/ingest",
        json={
            "document_name": "CardioTrack CT-200",
            "version_label": "v2",
            "markdown_content": v2_markdown
        }
    )
    assert response.status_code == 201
    
    # 7. Check staleness again (now it should be STALE since a node in the selection was modified)
    response = client.get(f"/api/selections/{selection_id}/test-cases")
    assert response.status_code == 200
    stale_status = response.json()
    assert stale_status["is_stale"] is True
    assert "was modified in version v2" in stale_status["staleness_reason"]
    assert len(stale_status["impacted_nodes"]) == 1
    assert stale_status["impacted_nodes"][0]["status"] == "modified"
    assert "diff" in stale_status["impacted_nodes"][0]
    
    # 8. Check test cases by node ID
    response = client.get(f"/api/nodes/{safety_node_v1_id}/test-cases")
    assert response.status_code == 200
    node_test_cases = response.json()
    assert len(node_test_cases) == 1
    assert node_test_cases[0]["is_stale"] is True

def test_mismatch_warning_and_force_ingest():
    # 1. Ingest V1
    v1_markdown = "# CardioTrack CT-200\n## 1. Overview\nOverview text."
    response = client.post(
        "/api/documents/ingest",
        json={
            "document_name": "CardioTrack CT-200",
            "version_label": "v1",
            "markdown_content": v1_markdown,
            "is_new_document": True
        }
    )
    assert response.status_code == 201
    
    # 2. Ingest completely different V2 (mismatch exceeds 70%)
    different_v2_markdown = "# CardioTrack CT-200\n## 9. Totally Unrelated Heading\nUnrelated text."
    response = client.post(
        "/api/documents/ingest",
        json={
            "document_name": "CardioTrack CT-200",
            "version_label": "v2",
            "markdown_content": different_v2_markdown,
            "is_new_document": False
        }
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] == "warning"
    assert res_data["mismatch_percent"] == 100.0
    
    # 3. Force Ingest V2 (should succeed)
    response = client.post(
        "/api/documents/ingest",
        json={
            "document_name": "CardioTrack CT-200",
            "version_label": "v2",
            "markdown_content": different_v2_markdown,
            "is_new_document": False,
            "force": True
        }
    )
    assert response.status_code == 201
    res_data = response.json()
    assert res_data["status"] == "success"
    assert res_data["stats"]["total_nodes"] == 2
