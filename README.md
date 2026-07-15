# CardioTrack QA Manual System Backend

This repository contains a backend REST API designed to ingest the CardioTrack CT-200 manual, parse it into a versioned hierarchical tree, manage user-defined selections, generate QA test cases using Gemini 2.5 Flash, and track staleness of those test cases when the document is updated.

---

## Technical Stack
- **Python 3.12+**
- **FastAPI** (REST API)
- **SQLAlchemy 2.0** (ORM)
- **SQLite** (Single-file database and JSON store)
- **Pytest & HTTPX** (Testing)
- **Google AI Python SDK** (Gemini 2.5 Flash Integration)

---

## Project Structure
```
tri9t-ai/
├── app/
│   ├── database.py         # SQLAlchemy & SQLite DB setup
│   ├── models.py           # SQLAlchemy database tables
│   ├── schemas.py          # Pydantic v2 schemas
│   ├── parser.py           # Custom markdown hierarchical parser
│   ├── versioning.py       # Path-based version matching engine
│   ├── hashing.py          # SHA-256 content hashing
│   ├── diff.py             # Text diff utility (difflib)
│   ├── llm.py              # Gemini LLM generation service
│   ├── routes/             # FastAPI Router files
│   │   ├── documents.py    # Ingestion and document list routes
│   │   ├── versions.py     # Version query routes
│   │   ├── nodes.py        # Browse, search, and node diff routes
│   │   ├── selections.py   # Pinned selections routes
│   │   └── generation.py   # Test case generation & staleness retrieval
│   └── services/           # Business logic service layers
│       ├── ingest_service.py
│       ├── selection_service.py
│       └── generation_service.py
├── data/
│   ├── ct200_manual.md     # Baseline manual (V1)
│   └── ct200_manual_v2.md  # Updated manual (V2)
├── tests/                  # Unit and integration test suite
│   ├── test_api.py
│   ├── test_parser.py
│   └── test_versioning.py
├── .gitignore
├── Approach.md             # Design decision log
├── README.md               # Quickstart guide
└── requirements.txt        # Package dependencies
```

---

## Installation & Setup

1. **Clone or navigate to the project directory**:
   ```bash
   cd d:/AI-Engineer
   ```

2. **Create and activate a virtual environment**:
   - **Windows**:
     ```powershell
     python -m venv .venv
     .venv\Scripts\activate
     ```
   - **macOS/Linux**:
     ```bash
     python -m venv .venv
     source .venv/bin/activate
     ```

3. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

4. **Environment Variables**:
   Create a `.env` file in the root of the project:
   ```env
   GEMINI_API_KEY=your_actual_google_gemini_api_key
   DATABASE_URL=sqlite:///./ct200_database.db
   ```

---

## Running the Application

Start the FastAPI development server:
```bash
uvicorn app.main:app --reload
```
Once started:
- Interactive Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- API Root: [http://127.0.0.1:8000/](http://127.0.0.1:8000/)

---

## Running Tests

Execute the automated test suite verifying parser rules, version matching, and API workflows:
```bash
python -m pytest
```

---

## Step-by-Step Flow: V1 → V2 Re-Ingestion & Staleness

Below is a walkthrough of the entire lifecycle using `curl` commands.

### Step 1: Ingest Version 1 (V1)
Send the content of `data/ct200_manual.md` as version `v1`:
```bash
curl -X POST "http://127.0.0.1:8000/api/documents/ingest" \
     -H "Content-Type: application/json" \
     -d "{
       \"document_name\": \"CardioTrack CT-200\",
       \"version_label\": \"v1\",
       \"markdown_content\": \"$(cat data/ct200_manual.md | sed 's/\"/\\\"/g' | awk '{printf \"%s\\n\", $0}')\"
     }"
```
*Note for Windows PowerShell: If `cat` is not available, you can copy the contents of `data/ct200_manual.md` directly into the JSON body inside the Swagger UI.*

### Step 2: Browse and Search Nodes
Query the node IDs for Section 4 (Alarms and Safety Behavior) to see what got created:
```bash
curl -X GET "http://127.0.0.1:8000/api/nodes/search?document_id=1&query=Alarms"
```
Assume the search returns the node ID for `4.2 Error Codes` (e.g. `node_id = 26`).

### Step 3: Create a Selection
Create a version-pinned selection named "Safety Alarms" containing `node_id = 26`:
```bash
curl -X POST "http://127.0.0.1:8000/api/selections" \
     -H "Content-Type: application/json" \
     -d "{
       \"name\": \"Safety Alarms\",
       \"node_ids\": [26]
     }"
```
This returns the created `selection_id` (e.g. `selection_id = 1`).

### Step 4: Generate QA Test Cases
Generate test cases using Gemini 2.5 Flash (requires a valid `GEMINI_API_KEY`):
```bash
curl -X POST "http://127.0.0.1:8000/api/selections/1/generate"
```
This stores the output in the database linked to selection 1.

### Step 5: Check Staleness on V1 (Fresh)
Query the generated test cases and check the staleness status:
```bash
curl -X GET "http://127.0.0.1:8000/api/selections/1/test-cases"
```
Response:
- `is_stale: false`
- `staleness_reason: null`

### Step 6: Ingest Version 2 (V2)
Now, ingest the modified document `data/ct200_manual_v2.md` as version `v2`:
```bash
curl -X POST "http://127.0.0.1:8000/api/documents/ingest" \
     -H "Content-Type: application/json" \
     -d "{
       \"document_name\": \"CardioTrack CT-200\",
       \"version_label\": \"v2\",
       \"markdown_content\": \"$(cat data/ct200_manual_v2.md | sed 's/\"/\\\"/g' | awk '{printf \"%s\\n\", $0}')\"
     }"
```

### Step 7: Retrieve Test Cases (Staleness & Diff Triggered)
Check the test cases status again:
```bash
curl -X GET "http://127.0.0.1:8000/api/selections/1/test-cases"
```
Since V2 changed the table values for `E3` in Section `4.2 Error Codes`, the API detects the hash mismatch and returns:
- `is_stale: true`
- `staleness_reason: "Section '/CardioTrack.../4. Alarms and Safety Behavior/4.2 Error Codes' was modified in version v2."`
- `impacted_nodes`: A list detailing the node changes and containing a **unified line-by-line diff** showing exactly what lines added/removed in V2.
