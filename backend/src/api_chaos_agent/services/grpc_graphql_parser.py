"""Schema parsers for gRPC (Protobuf) and GraphQL specifications.

Extends the core SchemaParser to support non-REST API protocols.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from api_chaos_agent.models.schema import (
    ApiProtocol,
    APISpec,
    FieldType,
    GraphQLOperation,
    GraphQLOperationType,
    GraphQLField,
    GrpcField,
    GrpcMethod,
    GrpcMethodType,
    GrpcService,
    FieldConstraint,
)


_PROTO_TYPE_MAP: dict[str, FieldType] = {
    "string": FieldType.STRING,
    "int32": FieldType.INTEGER,
    "int64": FieldType.INTEGER,
    "uint32": FieldType.INTEGER,
    "uint64": FieldType.INTEGER,
    "sint32": FieldType.INTEGER,
    "sint64": FieldType.INTEGER,
    "fixed32": FieldType.INTEGER,
    "fixed64": FieldType.INTEGER,
    "sfixed32": FieldType.INTEGER,
    "sfixed64": FieldType.INTEGER,
    "float": FieldType.NUMBER,
    "double": FieldType.NUMBER,
    "bool": FieldType.BOOLEAN,
    "bytes": FieldType.BYTES,
    "string": FieldType.STRING,
}

_GRAPHQL_TYPE_MAP: dict[str, FieldType] = {
    "String": FieldType.STRING,
    "Int": FieldType.INTEGER,
    "Float": FieldType.NUMBER,
    "Boolean": FieldType.BOOLEAN,
    "ID": FieldType.STRING,
}


class GrpcSchemaParser:
    """Parse Protobuf/gRPC service definitions into structured APISpec objects."""

    def parse(self, file_path: str) -> APISpec:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"Proto file not found: {file_path}")
        if path.suffix.lower() not in (".proto",):
            raise ValueError(f"Unsupported file extension '{path.suffix}'. Only .proto is supported.")
        raw_text = path.read_text(encoding="utf-8")
        return self.parse_text(raw_text)

    def parse_text(self, text: str) -> APISpec:
        services = self._extract_services(text)
        package = self._extract_package(text)
        title = services[0].name if services else "gRPC API"
        return APISpec(
            title=title,
            version="1.0.0",
            protocol=ApiProtocol.GRPC,
            grpc_services=services,
            base_url=None,
            raw_spec={"package": package, "source": text},
        )

    def _extract_package(self, text: str) -> str:
        match = re.search(r'^\s*package\s+([\w.]+)\s*;', text, re.MULTILINE)
        return match.group(1) if match else ""

    def _extract_services(self, text: str) -> list[GrpcService]:
        services: list[GrpcService] = []
        service_pattern = re.compile(r'service\s+(\w+)\s*\{', re.DOTALL)
        for match in service_pattern.finditer(text):
            name = match.group(1)
            start = match.end()
            depth = 1
            pos = start
            while pos < len(text) and depth > 0:
                if text[pos] == '{':
                    depth += 1
                elif text[pos] == '}':
                    depth -= 1
                pos += 1
            body = text[start:pos - 1]
            methods = self._extract_methods(body)
            services.append(GrpcService(name=name, package=self._extract_package(text), methods=methods))
        return services

    def _extract_methods(self, service_body: str) -> list[GrpcMethod]:
        methods: list[GrpcMethod] = []
        method_pattern = re.compile(r'rpc\s+(\w+)\s*\(\s*(stream\s+)?(\w+)\s*\)\s*returns\s*\(\s*(stream\s+)?(\w+)\s*\)')
        for match in method_pattern.finditer(service_body):
            name = match.group(1)
            client_streaming = bool(match.group(2))
            request_type = match.group(3)
            server_streaming = bool(match.group(4))
            response_type = match.group(5)
            method_type = GrpcMethodType.UNARY
            if server_streaming and client_streaming:
                method_type = GrpcMethodType.BIDI_STREAMING
            elif server_streaming:
                method_type = GrpcMethodType.SERVER_STREAMING
            elif client_streaming:
                method_type = GrpcMethodType.CLIENT_STREAMING
            methods.append(GrpcMethod(
                name=name,
                method_type=method_type,
                request_fields=[GrpcField(name="body", field_type=FieldType.OBJECT, message_type=request_type)],
                response_fields=[GrpcField(name="body", field_type=FieldType.OBJECT, message_type=response_type)],
            ))
        return methods


class GraphQLSchemaParser:
    """Parse GraphQL schema (SDL) into structured APISpec objects."""

    def parse(self, file_path: str) -> APISpec:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"GraphQL schema file not found: {file_path}")
        if path.suffix.lower() not in (".graphql", ".gql", ".graphqls"):
            raise ValueError(f"Unsupported file extension '{path.suffix}'. Only .graphql/.gql/.graphqls supported.")
        raw_text = path.read_text(encoding="utf-8")
        return self.parse_text(raw_text)

    def parse_text(self, text: str) -> APISpec:
        operations = self._extract_operations(text)
        return APISpec(
            title="GraphQL API",
            version="1.0.0",
            protocol=ApiProtocol.GRAPHQL,
            graphql_operations=operations,
            base_url=None,
            raw_spec={"source": text},
        )

    def _extract_operations(self, text: str) -> list[GraphQLOperation]:
        operations: list[GraphQLOperation] = []
        for op_type_def in [("type Query", GraphQLOperationType.QUERY), ("type Mutation", GraphQLOperationType.MUTATION), ("type Subscription", GraphQLOperationType.SUBSCRIPTION)]:
            keyword, op_type = op_type_def
            pattern = re.compile(rf'{re.escape(keyword)}\s*(?:\w+\s*)?\{{([^}}]*)\}}', re.DOTALL)
            for match in pattern.finditer(text):
                body = match.group(1)
                fields = self._extract_fields(body)
                for field in fields:
                    operations.append(GraphQLOperation(
                        name=field.name,
                        operation_type=op_type,
                        fields=[field],
                    ))
        return operations

    def _extract_fields(self, body: str) -> list[GraphQLField]:
        fields: list[GraphQLField] = []
        field_pattern = re.compile(r'(\w+)\s*(?:\(([^)]*)\))?\s*:\s*(\[?\w+!?]?)')
        for match in field_pattern.finditer(body):
            name = match.group(1)
            args_str = match.group(2) or ""
            return_type = match.group(3) or "String"
            nullable = "!" not in return_type
            clean_type = return_type.replace("!", "").replace("[", "").replace("]", "")
            field_type = _GRAPHQL_TYPE_MAP.get(clean_type, FieldType.OBJECT)
            arguments = self._parse_arguments(args_str)
            fields.append(GraphQLField(
                name=name,
                field_type=field_type,
                nullable=nullable,
                arguments=arguments,
            ))
        return fields

    def _parse_arguments(self, args_str: str) -> list[FieldConstraint]:
        if not args_str.strip():
            return []
        constraints: list[FieldConstraint] = []
        for arg in args_str.split(","):
            arg = arg.strip()
            if not arg:
                continue
            parts = arg.split(":")
            if len(parts) >= 2:
                name = parts[0].strip().lstrip("$")
                type_str = parts[1].strip().replace("!", "")
                field_type = _GRAPHQL_TYPE_MAP.get(type_str, FieldType.OBJECT)
                constraints.append(FieldConstraint(field_name=name, field_type=field_type, required="!" in parts[1]))
        return constraints


def detect_protocol(file_path: str) -> ApiProtocol:
    """Auto-detect API protocol from file extension."""
    suffix = Path(file_path).suffix.lower()
    if suffix in (".proto",):
        return ApiProtocol.GRPC
    if suffix in (".graphql", ".gql", ".graphqls"):
        return ApiProtocol.GRAPHQL
    return ApiProtocol.REST
