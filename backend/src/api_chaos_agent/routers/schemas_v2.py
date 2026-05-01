"""API routes for gRPC/GraphQL schema parsing (Phase 2)."""

from __future__ import annotations

from fastapi import APIRouter, File, UploadFile

from api_chaos_agent.core.deps import StoreDep
from api_chaos_agent.core.exceptions import SchemaError, SchemaParseError
from api_chaos_agent.core.security import CurrentUser
from api_chaos_agent.models.schema import APISpec, ApiProtocol
from api_chaos_agent.services.grpc_graphql_parser import (
    GraphQLSchemaParser,
    GrpcSchemaParser,
    detect_protocol,
)

router = APIRouter(prefix="/api/v2/schemas", tags=["schemas-v2"])


@router.post("/parse", response_model=APISpec)
async def parse_schema_v2(_user: CurrentUser, file: UploadFile = File(...)):
    filename = file.filename or ""
    protocol = detect_protocol(filename)
    content = await file.read()
    text = content.decode("utf-8")

    if protocol == ApiProtocol.GRPC:
        parser = GrpcSchemaParser()
        try:
            return parser.parse_text(text)
        except Exception as e:
            raise SchemaParseError(detail=f"gRPC parse error: {e}")
    elif protocol == ApiProtocol.GRAPHQL:
        parser = GraphQLSchemaParser()
        try:
            return parser.parse_text(text)
        except Exception as e:
            raise SchemaParseError(detail=f"GraphQL parse error: {e}")
    else:
        raise SchemaError(
            detail=f"Use /api/v1/schemas/parse for REST/OpenAPI specs. "
                   f"Detected protocol: {protocol.value}",
        )


@router.post("/parse/grpc", response_model=APISpec)
async def parse_grpc_schema(_user: CurrentUser, file: UploadFile = File(...)):
    content = await file.read()
    if not content or not content.strip():
        raise SchemaError(detail="Empty proto file")
    text = content.decode("utf-8")
    parser = GrpcSchemaParser()
    try:
        result = parser.parse_text(text)
    except Exception as e:
        raise SchemaParseError(detail=str(e))
    if not result.grpc_services:
        raise SchemaError(detail="No valid gRPC service definitions found in proto file")
    return result


@router.post("/parse/graphql", response_model=APISpec)
async def parse_graphql_schema(_user: CurrentUser, file: UploadFile = File(...)):
    content = await file.read()
    if not content or not content.strip():
        raise SchemaError(detail="Empty GraphQL schema file")
    text = content.decode("utf-8")
    parser = GraphQLSchemaParser()
    try:
        result = parser.parse_text(text)
    except Exception as e:
        raise SchemaParseError(detail=str(e))
    if not result.graphql_operations:
        raise SchemaError(detail="No valid GraphQL operations found in schema file")
    return result
