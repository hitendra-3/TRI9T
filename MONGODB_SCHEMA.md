# MongoDB Schema Reference — CardioTrack QA System

This document explains the MongoDB collection structure used for storing LLM-generated QA test cases.

---

## Why MongoDB for Test Case Storage?

| Consideration | SQLite (relational) | MongoDB (document) |
|---|---|---|
| Data shape | Flat rows | Nested JSON (arrays of steps) |
| Query pattern | `JOIN` across tables | `find_one({"selection_id": X})` |
| Schema evolution | Requires `ALTER TABLE` migration | Add new fields with no migration |
| Offline capability | Built-in | Automatic fallback to local JSON |

---

## Collection: `generated_test_cases`

**Database**: `ct200_qa` (configured via `MONGODB_DB_NAME` env variable)

### Document Schema

```json
{
  "_id": "ObjectId (auto-generated)",

  "selection_id": 1,
  // Integer FK — links back to the SQLite selections table
  // UNIQUE INDEX — one document per selection

  "document_name": "CardioTrack CT-200",
  // Denormalised from SQLite for fast reads without a JOIN

  "version_label": "v1",
  // The version this generation was created against

  "prompt": "You are a QA engineer for medical devices...",
  // Full prompt text sent to the Gemini API

  "raw_response": "{\"test_cases\": [...]}",
  // Raw LLM response text before Pydantic validation

  "test_cases": [
    {
      "title": "Overpressure Auto-Deflation Test",
      "steps": [
        "Set up a pressure simulation test rig connected to the CT-200 cuff port",
        "Gradually increase simulated cuff pressure past 299 mmHg",
        "Monitor the emergency deflation valve trigger"
      ],
      "expected_result": "Device triggers emergency valve, deflates within 2 seconds, displays error code E3",
      "priority": "High"
    },
    {
      "title": "E3 Error Code Display Verification",
      "steps": [
        "Connect a pressure simulator to CT-200",
        "Force pressure to exceed 299 mmHg",
        "Observe the display"
      ],
      "expected_result": "Device displays E3 error code within 500ms of overpressure event",
      "priority": "High"
    }
  ],
  // Pydantic-validated array — always 3-5 items, never null

  "source_node_snapshots": {
    "97cb7042-4f9c-4ec8-98ca-2c46d187d80f": "sha256:abc123...",
    "b3e11042-7d9c-4bc8-97ba-1c34d188e90a": "sha256:def456..."
  },
  // {logical_id: content_hash} at time of generation
  // This is the foundation of staleness detection
  // If a node's hash changes in a newer version → is_stale = true

  "created_at": "2024-01-01T12:00:00.000Z"
  // UTC timestamp of generation
}
```

---

## Indexes

Automatically created on startup via `app/mongodb.py::ensure_indexes()`:

| Index | Type | Purpose |
|---|---|---|
| `selection_id` | Unique | Enforce one-generation-per-selection; fast lookup |
| `document_name` | Standard | Filter all test cases for a document |
| `logical_ids` | Standard | (reserved) Future multi-node lookups |

---

## How to Connect (MongoDB Atlas)

### Step 1 — Get your connection string
1. Log in at https://cloud.mongodb.com
2. Click your cluster → **Connect** → **Connect your application**
3. Select **Python** driver, version **3.12 or later**
4. Copy the connection string:
   ```
   mongodb+srv://<username>:<password>@<your-cluster>.mongodb.net/<dbname>?retryWrites=true&w=majority
   ```

### Step 2 — Add to `.env`
```env
MONGODB_URI=mongodb+srv://shitendra777_db_user:VHPvZYwzfs6CSrjq@<your-cluster>.mongodb.net/ct200_qa?retryWrites=true&w=majority
MONGODB_DB_NAME=ct200_qa
```

> **Important**: Replace `<your-cluster>` with your actual Atlas cluster hostname.
> It looks like: `cluster0.abc12.mongodb.net` — you get the exact string from the Atlas UI.

### Step 3 — Whitelist your IP
In Atlas: **Network Access** → **Add IP Address** → Add your current IP (or `0.0.0.0/0` for development).

### Step 4 — Verify connection
```bash
python -c "from app.mongodb import ping_mongo; print(ping_mongo())"
```
Expected output: `True`

---

## Offline Fallback

If MongoDB is unreachable (wrong URI, IP not whitelisted, no internet), the system automatically falls back to a local JSON file store at `data/local_generated_test_cases.json`.

The fallback uses the same API: `find_one`, `insert_one`, `replace_one`. All tests pass in offline mode.

---

## Viewing Data in Atlas

Once connected, you can view the stored test cases in the Atlas UI:
1. Go to **Browse Collections** in your cluster
2. Select database: `ct200_qa`
3. Select collection: `generated_test_cases`

You'll see all generated test case documents with their full prompts, responses, and node snapshots.
