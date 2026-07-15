import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import RedirectResponse
from dotenv import load_dotenv
from app.database import engine, Base
from app.routes import documents, versions, nodes, selections, generation

# Load environment variables
load_dotenv()

# Initialize DB tables on startup
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="CardioTrack QA Manual System",
    description="Backend API to parse technical manuals, manage selections, generate QA test cases, and track version staleness.",
    version="1.0.0"
)

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
    Returns API health status.
    """
    return {"status": "healthy"}

