import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from app.database import engine, Base, ensure_fts5_table
from app.routes import documents, versions, nodes, selections, generation

# Load environment variables
load_dotenv()

# Initialize DB tables on startup
# Trigger reload
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CardioTrack QA Manual System",
    description="Backend API to parse technical manuals, manage selections, generate QA test cases, and track version staleness.",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    """Initialize FTS5 index and MongoDB indexes on startup."""
    # 1. SQLite FTS5 full-text search table
    try:
        ensure_fts5_table()
        print("[FTS5] Full-text search table ready.")
    except Exception as e:
        print(f"[FTS5] Warning: could not create FTS5 table: {e}")

    # 2. MongoDB Atlas
    try:
        from app.mongodb import ensure_indexes, ping_mongo
        if ping_mongo():
            ensure_indexes()
            print("[MongoDB] Connected and indexes ensured.")
        else:
            print("[MongoDB] WARNING: Could not reach MongoDB. Test case generation will fail until connection is restored.")
    except Exception as e:
        print(f"[MongoDB] Startup warning: {e}")

# Include routes
app.include_router(documents.router)
app.include_router(versions.router)
app.include_router(nodes.router)
app.include_router(selections.router)
app.include_router(generation.router)

# Mount static files for frontend UI
app.mount("/static", StaticFiles(directory="app/static"), name="static")

@app.get("/")
def read_root():
    """
    Redirects the root path to the interactive Dashboard UI.
    """
    return RedirectResponse(url="/static/index.html")

@app.get("/health")
def read_health():
    """
    Returns API health status including MongoDB connectivity.
    """
    from app.mongodb import ping_mongo
    mongo_ok = ping_mongo()
    return {
        "status": "healthy",
        "mongodb": "connected" if mongo_ok else "unreachable"
    }
