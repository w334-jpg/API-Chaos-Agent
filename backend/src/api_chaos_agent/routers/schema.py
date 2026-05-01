"""Schema router — upload and manage API schema definitions."""

from __future__ import annotations

import re

from fastapi import APIRouter, File, UploadFile

from api_chaos_agent.core.config import settings
from api_chaos_agent.core.deps import StoreDep
from api_chaos_agent.core.exceptions import (
    NotFoundError,
    RequestError,
    SchemaError,
    SchemaParseError,
)
from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.schema import APISpec
from api_chaos_agent.services.schema_parser import SchemaParser

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
    store: StoreDep,
    file: UploadFile = File(...),
) -> dict:
    if not file.filename:
        raise SchemaError(detail="No filename provided")

    if file.size is not None and file.size > settings.server.max_upload_size:
        raise SchemaError(detail="File too large (max 10 MB)")

    content = await file.read()
    if len(content) == 0:
        raise SchemaError(detail="Empty file")

    if len(content) > settings.server.max_upload_size:
        raise SchemaError(detail="File too large (max 10 MB)")

    if file.content_type and file.content_type not in _ALLOWED_CONTENT_TYPES:
        raise SchemaError(detail=f"Unsupported content type: {file.content_type}")

    safe_name = _sanitize_filename(file.filename)

    import os
    import tempfile

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=_suffix_for(safe_name))
    try:
        tmp.write(content)
        tmp.flush()
        tmp.close()

        parser = SchemaParser()
        spec: APISpec = parser.parse(tmp.name)
    except (FileNotFoundError, ValueError) as exc:
        raise SchemaParseError(detail=str(exc))
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass

    schema_id = await store.save_schema(spec)
    return {"schema_id": schema_id, "title": spec.title, "endpoints": len(spec.endpoints)}


@router.get("/", response_model=dict)
async def list_schemas(_user: CurrentUser, store: StoreDep) -> dict:
    schemas = await store.list_schemas()
    return {
        "schemas": [
            {"id": sid, "title": s.title, "version": s.version, "endpoints": len(s.endpoints)}
            for sid, s in schemas.items()
        ]
    }


@router.get("/{schema_id}", response_model=APISpec)
async def get_schema(schema_id: str, _user: CurrentUser, store: StoreDep) -> APISpec:
    if len(schema_id) > _MAX_SCHEMA_ID_LEN:
        raise RequestError(detail="schema_id too long")
    spec = await store.get_schema(schema_id)
    if spec is None:
        raise NotFoundError(detail="Schema not found")
    return spec


def _suffix_for(filename: str) -> str:
    if filename.endswith(".yaml") or filename.endswith(".yml"):
        return ".yaml"
    return ".json"
