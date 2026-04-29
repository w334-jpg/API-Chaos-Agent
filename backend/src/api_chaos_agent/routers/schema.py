"""Schema router — upload and manage API schema definitions."""

from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, File, HTTPException, UploadFile

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.schema import APISpec
from api_chaos_agent.services.schema_parser import SchemaParser
from api_chaos_agent.services.store import store

router = APIRouter(prefix="/api/schemas", tags=["schemas"])

_ALLOWED_CONTENT_TYPES: set[str] = {
    "application/json",
    "application/x-yaml",
    "text/yaml",
    "text/x-yaml",
    "application/yaml",
}

_MAX_SCHEMA_ID_LEN = 256


def _sanitize_filename(name: str) -> str:
    name = name.replace("..", "").replace("/", "").replace("\\", "")
    name = re.sub(r"[^\w.\-]", "_", name)
    return name or "upload"


@router.post("/upload", response_model=dict)
async def upload_schema(
    _user: CurrentUser,
    file: UploadFile = File(...),
) -> dict:
    if not file.filename:
        raise HTTPException(status_code=400, detail="No filename provided")

    if file.size is not None and file.size > settings.server.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="Empty file")

    if len(content) > settings.server.max_upload_size:
        raise HTTPException(status_code=413, detail="File too large (max 10 MB)")

    if file.content_type and file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported content type: {file.content_type}",
        )

    _sanitize_filename(file.filename)

    import tempfile, os
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=_suffix_for(file.filename))
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()

        parser = SchemaParser()
        spec: APISpec = parser.parse(tmp.name)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    schema_id = await store.save_schema(spec)
    return {"schema_id": schema_id, "title": spec.title, "endpoints": len(spec.endpoints)}


@router.get("/", response_model=dict)
async def list_schemas(_user: CurrentUser) -> dict:
    schemas = await store.list_schemas()
    return {
        "schemas": [
            {"id": sid, "title": s.title, "version": s.version, "endpoints": len(s.endpoints)}
            for sid, s in schemas.items()
        ]
    }


@router.get("/{schema_id}", response_model=APISpec)
async def get_schema(schema_id: str, _user: CurrentUser) -> APISpec:
    if len(schema_id) > _MAX_SCHEMA_ID_LEN:
        raise HTTPException(status_code=400, detail="schema_id too long")
    spec = await store.get_schema(schema_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Schema not found")
    return spec


def _suffix_for(filename: str) -> str:
    if filename.endswith(".yaml") or filename.endswith(".yml"):
        return ".yaml"
    return ".json"
