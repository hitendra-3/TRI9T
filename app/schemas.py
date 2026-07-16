from datetime import datetime, timezone
from typing import List, Optional, Any, Annotated
from pydantic import BaseModel, Field, ConfigDict, PlainSerializer

def serialize_dt(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.isoformat().replace("+00:00", "Z")

UTCDateTime = Annotated[datetime, PlainSerializer(serialize_dt, return_type=str)]


# Document Schemas
class DocumentCreate(BaseModel):
    name: str = Field(..., description="Name of the document")

class DocumentResponse(BaseModel):
    id: int
    name: str
    created_at: UTCDateTime

    model_config = ConfigDict(from_attributes=True)

# Document Version Schemas
class DocumentVersionResponse(BaseModel):
    id: int
    document_id: int
    version_label: str
    created_at: UTCDateTime

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
    created_at: UTCDateTime
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
    version_id: Optional[int] = None   # version the selection was pinned to
    raw_response: Optional[str] = None  # Raw text from the LLM
    test_cases: List[TestCase]
    created_at: UTCDateTime
    is_stale: bool
    staleness_reason: Optional[str] = None
    impacted_nodes: List[dict] = []  # Details on which nodes changed

    model_config = ConfigDict(from_attributes=True)

