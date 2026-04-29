from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"


class FieldConstraint(BaseModel):
    field_name: str
    field_type: FieldType
    required: bool = False
    min_length: int | None = None
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    pattern: str | None = None
    format: str | None = None
    enum_values: list[str] | None = None
    default: Any = None


class Parameter(BaseModel):
    name: str
    location: str = Field(description="query, header, path, cookie")
    param_type: FieldType
    required: bool = False
    description: str = ""
    constraints: list[FieldConstraint] = Field(default_factory=list)


class RequestBody(BaseModel):
    content_type: str = "application/json"
    required: bool = False
    fields: list[FieldConstraint] = Field(default_factory=list)
    raw_schema: dict[str, Any] = Field(default_factory=dict)


class ResponseSpec(BaseModel):
    status_code: str
    description: str = ""
    content_type: str | None = None
    schema_ref: str | None = None


class Endpoint(BaseModel):
    path: str
    method: HttpMethod
    summary: str = ""
    description: str = ""
    parameters: list[Parameter] = Field(default_factory=list)
    request_body: RequestBody | None = None
    responses: list[ResponseSpec] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    operation_id: str | None = None


class APISpec(BaseModel):
    title: str = ""
    version: str = ""
    description: str = ""
    endpoints: list[Endpoint] = Field(default_factory=list)
    base_url: str | None = None
    raw_spec: dict[str, Any] = Field(default_factory=dict)
