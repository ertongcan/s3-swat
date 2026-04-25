"""
main.py
S3 SWAT — FastAPI entry point.
Serves the REST API and the static dashboard.
"""

import os
from contextlib import asynccontextmanager
import sys
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from dotenv import load_dotenv

from api.routes import router as api_router
from db.database import init_db

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    await init_db()
    yield


app = FastAPI(
    title="S3 SWAT",
    description="S3 Cost Audit SaaS — Ghost Hunter, Network Scout, Efficiency Audit",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow dashboard to call API from any origin during dev) ────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── API routes ───────────────────────────────────────────────────────────────
app.include_router(api_router)

# ── Static files (dashboard) ────────────────────────────────────────────────
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.isdir(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def root():
    """Serve the dashboard."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "S3 SWAT API is running. Visit /docs for the API explorer."}


if __name__ == "__main__":
    print(sys.path)
    import uvicorn

    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host=host, port=port, reload=True)
