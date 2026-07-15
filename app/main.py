import os
from fastapi import FastAPI
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

@app.get("/")
def read_root():
    return {
        "status": "healthy",
        "system": "CardioTrack QA Manual API",
        "documentation": "/docs"
    }
