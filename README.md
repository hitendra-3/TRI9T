# Technical Manual QA Test Case Generator & Version Tracker

A professional REST API and web dashboard that ingests technical product manuals, parses them into hierarchical section trees, manages user-defined document selections, generates QA test cases using Gemini, and tracks version-to-version staleness as manuals evolve.

---

## Technical Stack
- **Backend**: Python 3.12+ (FastAPI, SQLAlchemy 2.0, SQLite)
- **NoSQL Store**: MongoDB Atlas (pymongo) — for LLM-generated test case storage
- **Search**: SQLite FTS5 full-text search with BM25 ranking
- **PDF Parsing**: Gemini Vision API (primary) + pypdf (fallback)
- **LLM Engine**: Google Gemini 2.5 Flash — structured JSON generation
- **Testing**: Pytest + HTTPX (22 tests, all mocked, no API calls required)

---

## Project Structure
```
D:/AI-Engineer/
├── app/
│   ├── database.py         # SQLAlchemy + SQLite + FTS5 init
│   ├── mongodb.py          # MongoDB Atlas client (with local JSON fallback)
│   ├── models.py           # Database schema definitions
│   ├── schemas.py          # Pydantic validation schemas
│   ├── parser.py           # Hybrid PDF/Markdown hierarchical parser
│   ├── versioning.py       # Logical path-based node tracking
│   ├── hashing.py          # SHA-256 content hashing
│   ├── diff.py             # Unified diff generator
│   ├── llm.py              # Gemini LLM structured-output service
│   ├── main.py             # FastAPI entrypoint
│   ├── routes/
│   │   ├── documents.py    # Ingestion (PDF + Markdown)
│   │   ├── versions.py     # Version details and stats
│   │   ├── nodes.py        # FTS5 search + tree browse + diff
│   │   ├── selections.py   # Selection management
│   │   └── generation.py   # Test case generation (MongoDB)
│   └── static/             # SPA frontend
│       ├── index.html
│       ├── app.css
│       └── app.js
├── data/
│   ├── ct200_manual.md                  # CT-200 Manual v1
│   ├── ct200_manual_v2.md               # CT-200 Manual v2 (modified)
│   └── local_generated_test_cases.json  # Offline fallback store
├── tests/
│   ├── test_api.py         # 11 API integration tests
│   ├── test_parser.py      # 9 parser unit tests
│   └── test_versioning.py  # 2 versioning unit tests
├── demo.py                 # End-to-end CLI demo (v1→v2→staleness)
├── Approach.md             # Design decisions + Decision Log
├── .env                    # Environment config
├── README.md
└── requirements.txt
```

---

## Quickstart & Local Setup

### 1. Configure the Environment
Create a `.env` file in the project root:
```env
GEMINI_API_KEY=your_google_gemini_api_key
DATABASE_URL=sqlite:///./ct200_database.db

# MongoDB Atlas (optional — falls back to local JSON store if not set)
MONGODB_URI=mongodb+srv://<username>:<password>@<cluster>.mongodb.net/ct200_qa?retryWrites=true&w=majority
MONGODB_DB_NAME=ct200_qa
```

To get your `MONGODB_URI`:
1. Log in to [MongoDB Atlas](https://cloud.mongodb.com)
2. Go to your cluster → **Connect** → **Connect your application**
3. Copy the connection string and replace `<username>` / `<password>`

### 2. Install Dependencies
```bash
pip install -r requirements.txt
```

### 3. Run the Backend Server
```bash
uvicorn app.main:app --reload
```
- **Web UI Dashboard**: http://127.0.0.1:8000/
- **Interactive API Docs**: http://127.0.0.1:8000/docs
- **Health Check**: http://127.0.0.1:8000/health

---

## Running Automated Tests

All 22 tests pass without a live MongoDB or Gemini API:

```bash
python -m pytest
```

Expected output:
```
22 passed in ~7s
```

---

## End-to-End Demo (v1 → v2 → Staleness)

Run the full demo with the sample manual files:

```bash
python demo.py
```

This script demonstrates the complete workflow:
1. Resets the database
2. Ingests `data/ct200_manual.md` as v1
3. Searches for the "Overpressure" section using FTS5
4. Creates a named selection pinned to v1
5. Generates QA test cases via Gemini (cached in MongoDB)
6. Checks staleness — shows `is_stale: false`
7. Ingests `data/ct200_manual_v2.md` as v2
8. Rechecks staleness — shows `is_stale: true` with unified diff

---

## Manual API Walkthrough (curl)

### Step 1 — Ingest v1
```bash
curl -X POST http://127.0.0.1:8000/api/documents/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "CardioTrack CT-200",
    "version_label": "v1",
    "markdown_content": "# CardioTrack CT-200\n## 4.1 Overpressure Protection\nIf cuff pressure exceeds 299 mmHg, the device auto-deflates within 2 seconds."
  }'
```

### Step 2 — Search for sections
```bash
curl "http://127.0.0.1:8000/api/nodes/search?document_id=1&query=Overpressure"
```

### Step 3 — Create a selection
```bash
curl -X POST http://127.0.0.1:8000/api/selections \
  -H "Content-Type: application/json" \
  -d '{"name": "Safety Tests", "node_ids": [2]}'
```

### Step 4 — Generate QA test cases
```bash
curl -X POST http://127.0.0.1:8000/api/selections/1/generate
```

### Step 5 — Check staleness (before v2)
```bash
curl http://127.0.0.1:8000/api/selections/1/test-cases
# Response: {"is_stale": false, "test_cases": [...]}
```

### Step 6 — Ingest v2 (with modified pressure threshold)
```bash
curl -X POST http://127.0.0.1:8000/api/documents/ingest \
  -H "Content-Type: application/json" \
  -d '{
    "document_name": "CardioTrack CT-200",
    "version_label": "v2",
    "markdown_content": "# CardioTrack CT-200\n## 4.1 Overpressure Protection\nIf cuff pressure exceeds 250 mmHg, the device auto-deflates within 1 second.",
    "is_new_document": false,
    "document_id": 1
  }'
```

### Step 7 — Recheck staleness (after v2)
```bash
curl http://127.0.0.1:8000/api/selections/1/test-cases
# Response: {"is_stale": true, "staleness_reason": "Section was modified in v2", "impacted_nodes": [...]}
```

---

## Key App Workflows

### 1. Document Ingestion
Accepts PDF or Markdown via the dashboard or `/api/documents/ingest`:
- PDF: sent to Gemini Vision API for OCR → structured Markdown (falls back to pypdf)
- Markdown: parsed by stack-based hierarchical parser
- Each version is independent; v1 data is never overwritten

### 2. Full-Text Search (FTS5)
`GET /api/nodes/search?document_id=1&query=battery` uses SQLite FTS5:
- BM25-ranked results
- Phrase search: `query="battery life"`
- Prefix search: `query=battery*`

### 3. Selections & Version Pinning
Select sections in the tree → name the selection → pin to the current version. The selection holds references to exact node versions, so content is never ambiguous.

### 4. QA Test Case Generation
POST `/api/selections/{id}/generate` calls Gemini with the selected section text:
- Validates output with Pydantic schema (3-attempt retry with error-correction)
- Stores result in MongoDB Atlas (falls back to local JSON if offline)
- Returns cached result by default; pass `?force=true` to regenerate

### 5. Staleness Tracking
When a newer version is ingested, all existing selections are automatically compared using `source_node_snapshots` from MongoDB. Any hash change or deletion triggers `is_stale: true` with a unified diff per affected section.

### 6. Admin Reset
`DELETE /api/documents/admin/clear-db` wipes SQLite and MongoDB collections simultaneously. Also accessible via the **Clear DB** button in the dashboard sidebar.
