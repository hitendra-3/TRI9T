from datetime import datetime
from typing import List, Optional, Any
from pydantic import BaseModel, Field, ConfigDict

# Document Schemas
class DocumentCreate(BaseModel):
    name: str = Field(..., description="Name of the document")

class DocumentResponse(BaseModel):
    id: int
    name: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Document Version Schemas
class DocumentVersionResponse(BaseModel):
    id: int
    document_id: int
    version_label: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Node Schemas
class NodeResponse(BaseModel):
    id: int
    document_id: int
    version_id: int
    logical_id: str
    heading: str
    title: str
    level: int
    body_text: str
    content_hash: str
    parent_id: Optional[int]
    path: str

    model_config = ConfigDict(from_attributes=True)

class NodeDetailResponse(NodeResponse):
    children: List["NodeResponse"] = []

    model_config = ConfigDict(from_attributes=True)

# Diff Schemas
class DiffSummary(BaseModel):
    has_changed: bool
    diff_type: str  # "unchanged", "modified", "deleted", "new"
    old_version: Optional[str] = None
    new_version: Optional[str] = None
    old_content: Optional[str] = None
    new_content: Optional[str] = None
    diff_text: Optional[str] = None  # Diff summary / patch

# Selection Schemas
class SelectionCreate(BaseModel):
    name: str
    node_ids: List[int]

class SelectionResponse(BaseModel):
    id: int
    name: str
    version_id: int
    created_at: datetime
    nodes: List[NodeResponse]

    model_config = ConfigDict(from_attributes=True)

# Test Case Schema (LLM generated)
class TestCase(BaseModel):
    title: str = Field(..., description="Short, descriptive test case title")
    steps: List[str] = Field(..., description="Repeatable, concrete steps to execute the check")
    expected_result: str = Field(..., description="Detailed expected behavior")
    priority: str = Field("Medium", description="Severity or priority (High, Medium, Low)")

class GeneratedTestCasesList(BaseModel):
    test_cases: List[TestCase] = Field(..., description="List of 3 to 5 generated QA test cases")

# Generated Test Cases response
class TestCasesResponse(BaseModel):
    id: int
    selection_id: int
    test_cases: List[TestCase]
    created_at: datetime
    is_stale: bool
    staleness_reason: Optional[str] = None
    impacted_nodes: List[dict] = []  # Details on which nodes changed

    model_config = ConfigDict(from_attributes=True)
