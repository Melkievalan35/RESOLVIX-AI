"""
Resolvix-AI backend entrypoint.

Run with:
    uvicorn main:app --reload --host 0.0.0.0 --port 8000
"""
import os
import sys

PROJECT_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..")
)
print(sys.path)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))

if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import auth, complaints, dashboard, notifications, reports, users
from database.connection import Base, engine

# Creates tables if they don't exist yet. For production, use the
# migrations in database/migrations/ (e.g. Alembic) instead.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="Resolvix-AI API",
    description="AI-powered complaint resolution platform backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten this to known frontend origins in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(complaints.router)
app.include_router(dashboard.router)
app.include_router(users.router)
app.include_router(reports.router)
app.include_router(notifications.router)


@app.get("/", tags=["Health"])
def root():
    return {"status": "ok", "service": "Resolvix-AI backend"}


@app.get("/health", tags=["Health"])
def health_check():
    return {"status": "healthy"}
