"""
MongoDB client module for LLM-generated test case storage.

Why MongoDB instead of a separate SQLite table?
- Generated test cases are document-oriented (nested arrays of steps, expected results)
  and do not benefit from SQLite's row-based storage model.
- Queries are always by selection_id (a simple key lookup), not complex relational joins.
- MongoDB's JSON document model stores test_cases natively without serialising to a TEXT column.
- This separation also means LLM output can evolve its schema (e.g. add trace fields)
  without altering the SQLite migration, which is important for regulated data.
- MongoDB Atlas free tier provides cloud persistence, removing the risk of local DB file corruption.
"""

import os
import json
from typing import Optional
from pymongo import MongoClient
from pymongo.collection import Collection
from pymongo.database import Database
from bson import ObjectId

_client: MongoClient = None
_db: Database = None
_use_local_fallback = False

class LocalJSONCollection:
    """
    A lightweight file-backed mock MongoDB collection that implements the minimum subset 
    of pymongo collection API used by generation_service.py.
    This serves as the 'well-justified JSON store' fallback if MongoDB Atlas is offline or misconfigured.
    """
    def __init__(self, filepath: str = "data/local_generated_test_cases.json"):
        self.filepath = filepath
        self._ensure_file()

    def _ensure_file(self):
        os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
        if not os.path.exists(self.filepath):
            with open(self.filepath, "w", encoding="utf-8") as f:
                json.dump([], f)

    def _read_all(self) -> list:
        try:
            with open(self.filepath, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []

    def _write_all(self, data: list):
        with open(self.filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, default=str, indent=2)

    def find_one(self, filter_dict: dict) -> Optional[dict]:
        data = self._read_all()
        for doc in data:
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                return doc
        return None

    def insert_one(self, doc: dict):
        class InsertOneResult:
            def __init__(self, inserted_id):
                self.inserted_id = inserted_id
        
        data = self._read_all()
        if "_id" not in doc:
            doc["_id"] = str(ObjectId())
        # Convert datetime if present
        if "created_at" in doc and hasattr(doc["created_at"], "isoformat"):
            doc["created_at"] = doc["created_at"].isoformat()
        data.append(doc)
        self._write_all(data)
        return InsertOneResult(doc["_id"])

    def replace_one(self, filter_dict: dict, replacement: dict):
        data = self._read_all()
        replaced = False
        for idx, doc in enumerate(data):
            match = True
            for k, v in filter_dict.items():
                if doc.get(k) != v:
                    match = False
                    break
            if match:
                if "_id" not in replacement and "_id" in doc:
                    replacement["_id"] = doc["_id"]
                if "created_at" in replacement and hasattr(replacement["created_at"], "isoformat"):
                    replacement["created_at"] = replacement["created_at"].isoformat()
                data[idx] = replacement
                replaced = True
                break
        if not replaced:
            if "_id" not in replacement:
                replacement["_id"] = str(ObjectId())
            if "created_at" in replacement and hasattr(replacement["created_at"], "isoformat"):
                replacement["created_at"] = replacement["created_at"].isoformat()
            data.append(replacement)
        self._write_all(data)

    def create_index(self, *args, **kwargs):
        # Indexing is a no-op for the local JSON collection
        pass


def get_mongo_client() -> MongoClient:
    """Returns the shared MongoClient instance (lazy init)."""
    global _client
    if _client is None:
        uri = os.getenv("MONGODB_URI")
        if not uri:
            raise RuntimeError(
                "MONGODB_URI is not set. Add it to your .env file.\n"
                "Format: mongodb+srv://<user>:<pass>@<cluster>.mongodb.net/<dbname>"
            )
        _client = MongoClient(uri, serverSelectionTimeoutMS=5000)
    return _client

def get_mongo_db() -> Database:
    """Returns the shared MongoDB database instance."""
    global _db
    if _db is None:
        client = get_mongo_client()
        db_name = os.getenv("MONGODB_DB_NAME", "ct200_qa")
        _db = client[db_name]
    return _db

def get_test_cases_collection():
    """
    Returns the 'generated_test_cases' collection.
    Automatically falls back to LocalJSONCollection if MongoDB connection/DNS fails.
    """
    global _use_local_fallback
    if _use_local_fallback:
        return LocalJSONCollection()

    try:
        db = get_mongo_db()
        # Trigger network call to verify connection
        db.client.server_info()
        return db["generated_test_cases"]
    except Exception as e:
        print(f"[MongoDB] Connection failed: {e}. Falling back to local JSON store.")
        _use_local_fallback = True
        return LocalJSONCollection()

def ensure_indexes():
    """Creates indexes on the test_cases collection for fast lookups."""
    col = get_test_cases_collection()
    col.create_index("selection_id", unique=True)
    col.create_index("logical_ids")      # for node-based lookups
    col.create_index("document_name")

def ping_mongo() -> bool:
    """Returns True if MongoDB is reachable, False otherwise."""
    global _use_local_fallback
    if _use_local_fallback:
        return False
    try:
        client = get_mongo_client()
        client.admin.command("ping")
        return True
    except Exception as e:
        print(f"[MongoDB] Ping failed: {e}")
        return False

def clear_mongo_collections():
    """Wipes all documents from the test cases collection (for clean testing/admin reset)."""
    col = get_test_cases_collection()
    if isinstance(col, LocalJSONCollection):
        col._write_all([])
    else:
        col.delete_many({})
