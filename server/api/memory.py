from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel, Field

from server.dependencies import get_memory_store
from server.memory.keys import ALLOWED_PREFERENCE_KEYS, ALIAS_KINDS
from server.memory.store import MemoryStore
from server.utils.security import verify_auth_token

router = APIRouter(tags=["memory"], dependencies=[Depends(verify_auth_token)])


class PreferenceBody(BaseModel):
    key: str = Field(min_length=1, max_length=64)
    value: str = Field(min_length=1, max_length=512)


class AliasBody(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    kind: str = Field(min_length=1, max_length=32)
    value: str = Field(min_length=1, max_length=512)


@router.get("/v1/memory")
async def memory_summary(memory: MemoryStore = Depends(get_memory_store)) -> dict[str, Any]:
    return memory.stats()


@router.get("/v1/memory/preferences")
async def list_preferences(memory: MemoryStore = Depends(get_memory_store)) -> dict[str, Any]:
    return {"keys": sorted(ALLOWED_PREFERENCE_KEYS), "preferences": memory.list_preferences()}


@router.put("/v1/memory/preferences")
async def put_preference(
    body: PreferenceBody,
    memory: MemoryStore = Depends(get_memory_store),
) -> dict[str, str]:
    try:
        return memory.set_preference(body.key, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/v1/memory/preferences/{key}")
async def delete_preference(key: str, memory: MemoryStore = Depends(get_memory_store)) -> dict[str, Any]:
    if not memory.delete_preference(key):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Preference not found.")
    return {"deleted": True, "key": key}


@router.get("/v1/memory/aliases")
async def list_aliases(
    kind: Optional[str] = Query(default=None),
    memory: MemoryStore = Depends(get_memory_store),
) -> dict[str, Any]:
    if kind and kind not in ALIAS_KINDS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="kind must be application or path")
    return {"aliases": memory.list_aliases(kind=kind)}


@router.put("/v1/memory/aliases")
async def put_alias(body: AliasBody, memory: MemoryStore = Depends(get_memory_store)) -> dict[str, str]:
    try:
        return memory.set_alias(body.name, body.kind, body.value)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.delete("/v1/memory/aliases/{name}")
async def delete_alias(name: str, memory: MemoryStore = Depends(get_memory_store)) -> dict[str, Any]:
    if not memory.delete_alias(name):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alias not found.")
    return {"deleted": True, "name": name}


@router.get("/v1/memory/history")
async def list_history(
    limit: int = Query(default=20, ge=1, le=100),
    memory: MemoryStore = Depends(get_memory_store),
) -> dict[str, Any]:
    return {"history": memory.list_history(limit=limit)}
