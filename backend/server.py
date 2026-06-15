"""
KampungKonekt API Server
FastAPI server exposing user CRUD and welfare pipeline endpoints.

Run with:
    uvicorn server:app --reload --port 8000
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from memory.storage import MemoryStorage
from config.settings import settings

app = FastAPI(title="KampungKonekt API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_storage = MemoryStorage(db_path=settings.DB_PATH)


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class UserCreate(BaseModel):
    name: str
    contact_name: str
    contact_number: str


class UserUpdate(BaseModel):
    name: str
    contact_name: str
    contact_number: str


# ---------------------------------------------------------------------------
# User routes
# ---------------------------------------------------------------------------

@app.post("/users", status_code=201)
def create_user(body: UserCreate):
    try:
        user = _storage.create_user(body.name.strip(), body.contact_name.strip(), body.contact_number.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return user


@app.get("/users/{name}")
def get_user(name: str):
    user = _storage.get_user(name)
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.put("/users/{name}")
def update_user(name: str, body: UserUpdate):
    try:
        user = _storage.update_user(name, body.name.strip(), body.contact_name.strip(), body.contact_number.strip())
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))
    if not user:
        raise HTTPException(status_code=404, detail="User not found.")
    return user


@app.delete("/users/{name}", status_code=204)
def delete_user(name: str):
    deleted = _storage.delete_user(name)
    if not deleted:
        raise HTTPException(status_code=404, detail="User not found.")
