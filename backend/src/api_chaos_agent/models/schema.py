from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class ApiProtocol(str, Enum):
    REST = "rest"
    GRPC = "grpc"
    GRAPHQL = "graphql"


class HttpMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class GrpcMethodType(str, Enum):
    UNARY = "unary"
    SERVER_STREAMING = "server_streaming"
    CLIENT_STREAMING = "client_streaming"
    BIDI_STREAMING = "bidi_streaming"


class FieldType(str, Enum):
    STRING = "string"
    INTEGER = "integer"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    NULL = "null"
    BYTES = "bytes"
    ENUM = "enum"
    MAP = "map"
    ONEOF = "oneof"


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


class GrpcField(BaseModel):
    name: str
    field_type: FieldType
    repeated: bool = False
    optional: bool = False
    message_type: str | None = None
    enum_values: list[str] | None = None
    map_key_type: FieldType | None = None
    map_value_type: FieldType | None = None
    oneof_group: str | None = None
    constraints: list[FieldConstraint] = Field(default_factory=list)


class GrpcMethod(BaseModel):
    name: str
    method_type: GrpcMethodType = GrpcMethodType.UNARY
    request_fields: list[GrpcField] = Field(default_factory=list)
    response_fields: list[GrpcField] = Field(default_factory=list)
    description: str = ""
    deprecated: bool = False


class GrpcService(BaseModel):
    name: str
    package: str = ""
    methods: list[GrpcMethod] = Field(default_factory=list)
    description: str = ""


class GraphQLOperationType(str, Enum):
    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


class GraphQLField(BaseModel):
    name: str
    field_type: FieldType
    description: str = ""
    arguments: list[FieldConstraint] = Field(default_factory=list)
    nullable: bool = True
    deprecation_reason: str | None = None


class GraphQLOperation(BaseModel):
    name: str
    operation_type: GraphQLOperationType
    fields: list[GraphQLField] = Field(default_factory=list)
    description: str = ""
    deprecated: bool = False


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
    protocol: ApiProtocol = ApiProtocol.REST
    endpoints: list[Endpoint] = Field(default_factory=list)
    grpc_services: list[GrpcService] = Field(default_factory=list)
    graphql_operations: list[GraphQLOperation] = Field(default_factory=list)
    base_url: str | None = None
    raw_spec: dict[str, Any] = Field(default_factory=dict)
