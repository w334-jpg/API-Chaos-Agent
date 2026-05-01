"""API schema models for OpenAPI / gRPC / GraphQL specifications.

Defines the data structures that represent parsed API specifications,
including endpoints, parameters, request/response bodies, and protocol-
specific models.
"""

from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


class ApiProtocol(StrEnum):
    """Supported API protocols."""

    REST = "rest"
    GRPC = "grpc"
    GRAPHQL = "graphql"


class HttpMethod(StrEnum):
    """HTTP methods for REST endpoints."""

    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    PATCH = "PATCH"
    DELETE = "DELETE"
    HEAD = "HEAD"
    OPTIONS = "OPTIONS"


class GrpcMethodType(StrEnum):
    """gRPC method types."""

    UNARY = "unary"
    SERVER_STREAMING = "server_streaming"
    CLIENT_STREAMING = "client_streaming"
    BIDI_STREAMING = "bidi_streaming"


class FieldType(StrEnum):
    """Data types for API fields."""

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
    """Constraints applied to a single API field."""

    field_name: str = Field(description="Name of the field")
    field_type: FieldType = Field(description="Data type of the field")
    required: bool = Field(default=False, description="Whether the field is required")
    min_length: int | None = Field(default=None, description="Minimum string length")
    max_length: int | None = Field(default=None, description="Maximum string length")
    minimum: float | None = Field(default=None, description="Minimum numeric value")
    maximum: float | None = Field(default=None, description="Maximum numeric value")
    pattern: str | None = Field(default=None, description="Regex pattern for validation")
    format: str | None = Field(default=None, description="Expected format (e.g. date-time, email)")
    enum_values: list[str] | None = Field(default=None, description="Allowed enum values")
    default: Any = Field(default=None, description="Default value if not provided")


class Parameter(BaseModel):
    """An API parameter (query, header, path, or cookie)."""

    name: str = Field(description="Parameter name")
    location: str = Field(description="Parameter location: query, header, path, cookie")
    param_type: FieldType = Field(description="Data type of the parameter")
    required: bool = Field(default=False, description="Whether the parameter is required")
    description: str = Field(default="", description="Human-readable description")
    constraints: list[FieldConstraint] = Field(
        default_factory=list, description="Validation constraints"
    )


class RequestBody(BaseModel):
    """HTTP request body specification."""

    content_type: str = Field(default="application/json", description="MIME content type")
    required: bool = Field(default=False, description="Whether the request body is required")
    fields: list[FieldConstraint] = Field(
        default_factory=list, description="Body field constraints"
    )
    raw_schema: dict[str, Any] = Field(default_factory=dict, description="Original JSON Schema")


class ResponseSpec(BaseModel):
    """HTTP response specification for a status code."""

    status_code: str = Field(description="HTTP status code or range (e.g. '200', '2XX')")
    description: str = Field(default="", description="Response description")
    content_type: str | None = Field(default=None, description="Response content type")
    schema_ref: str | None = Field(default=None, description="Reference to schema component")


class GrpcField(BaseModel):
    """A field within a gRPC message."""

    name: str = Field(description="Field name")
    field_type: FieldType = Field(description="Data type of the field")
    repeated: bool = Field(default=False, description="Whether the field is repeated (list)")
    optional: bool = Field(default=False, description="Whether the field is optional")
    message_type: str | None = Field(default=None, description="Referenced message type name")
    enum_values: list[str] | None = Field(default=None, description="Allowed enum values")
    map_key_type: FieldType | None = Field(
        default=None, description="Map key type if field is a map"
    )
    map_value_type: FieldType | None = Field(
        default=None, description="Map value type if field is a map"
    )
    oneof_group: str | None = Field(default=None, description="Oneof group name if applicable")
    constraints: list[FieldConstraint] = Field(
        default_factory=list, description="Validation constraints"
    )


class GrpcMethod(BaseModel):
    """A method within a gRPC service."""

    name: str = Field(description="Method name")
    method_type: GrpcMethodType = Field(
        default=GrpcMethodType.UNARY, description="gRPC method type"
    )
    request_fields: list[GrpcField] = Field(
        default_factory=list, description="Request message fields"
    )
    response_fields: list[GrpcField] = Field(
        default_factory=list, description="Response message fields"
    )
    description: str = Field(default="", description="Method description")
    deprecated: bool = Field(default=False, description="Whether the method is deprecated")


class GrpcService(BaseModel):
    """A gRPC service definition."""

    name: str = Field(description="Service name")
    package: str = Field(default="", description="Protobuf package name")
    methods: list[GrpcMethod] = Field(default_factory=list, description="Service methods")
    description: str = Field(default="", description="Service description")


class GraphQLOperationType(StrEnum):
    """GraphQL operation types."""

    QUERY = "query"
    MUTATION = "mutation"
    SUBSCRIPTION = "subscription"


class GraphQLField(BaseModel):
    """A field within a GraphQL operation."""

    name: str = Field(description="Field name")
    field_type: FieldType = Field(description="Data type of the field")
    description: str = Field(default="", description="Field description")
    arguments: list[FieldConstraint] = Field(default_factory=list, description="Field arguments")
    nullable: bool = Field(default=True, description="Whether the field can be null")
    deprecation_reason: str | None = Field(default=None, description="Reason if deprecated")


class GraphQLOperation(BaseModel):
    """A GraphQL operation (query, mutation, or subscription)."""

    name: str = Field(description="Operation name")
    operation_type: GraphQLOperationType = Field(description="Type of GraphQL operation")
    fields: list[GraphQLField] = Field(default_factory=list, description="Operation fields")
    description: str = Field(default="", description="Operation description")
    deprecated: bool = Field(default=False, description="Whether the operation is deprecated")


class Endpoint(BaseModel):
    """An API endpoint (REST route, gRPC method, or GraphQL operation)."""

    path: str = Field(description="Endpoint path (e.g. /api/v1/users)")
    method: HttpMethod = Field(description="HTTP method")
    summary: str = Field(default="", description="Short summary of the endpoint")
    description: str = Field(default="", description="Detailed description")
    parameters: list[Parameter] = Field(default_factory=list, description="Endpoint parameters")
    request_body: RequestBody | None = Field(default=None, description="Request body specification")
    responses: list[ResponseSpec] = Field(
        default_factory=list, description="Response specifications"
    )
    tags: list[str] = Field(default_factory=list, description="Grouping tags")
    operation_id: str | None = Field(default=None, description="Unique operation identifier")


class APISpec(BaseModel):
    """Complete API specification with all endpoints and metadata."""

    title: str = Field(default="", description="API title")
    version: str = Field(default="", description="API version")
    description: str = Field(default="", description="API description")
    protocol: ApiProtocol = Field(default=ApiProtocol.REST, description="Primary API protocol")
    endpoints: list[Endpoint] = Field(default_factory=list, description="REST endpoints")
    grpc_services: list[GrpcService] = Field(
        default_factory=list, description="gRPC service definitions"
    )
    graphql_operations: list[GraphQLOperation] = Field(
        default_factory=list, description="GraphQL operations"
    )
    base_url: str | None = Field(default=None, description="API base URL")
    raw_spec: dict[str, Any] = Field(default_factory=dict, description="Original raw specification")
