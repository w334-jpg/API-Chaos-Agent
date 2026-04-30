"""Unit tests for Phase 2: gRPC/GraphQL Schema Parsers."""

import pytest

from api_chaos_agent.models.schema import ApiProtocol, GrpcMethodType
from api_chaos_agent.services.grpc_graphql_parser import (
    GraphQLSchemaParser,
    GrpcSchemaParser,
    detect_protocol,
)


class TestGrpcSchemaParser:
    def setup_method(self):
        self.parser = GrpcSchemaParser()

    def test_parse_simple_service(self):
        proto = '''
syntax = "proto3";
package example.v1;

service Greeter {
  rpc SayHello (HelloRequest) returns (HelloReply) {}
  rpc StreamGreetings (HelloRequest) returns (stream HelloReply) {}
}
'''
        spec = self.parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        assert len(spec.grpc_services) == 1
        assert spec.grpc_services[0].name == "Greeter"
        assert spec.grpc_services[0].package == "example.v1"
        assert len(spec.grpc_services[0].methods) == 2

    def test_parse_method_types(self):
        proto = '''
syntax = "proto3";
package test;

service Chat {
  rpc SendMessage (Msg) returns (Msg) {}
  rpc StreamMessages (Msg) returns (stream Msg) {}
  rpc UploadStream (stream Msg) returns (Msg) {}
  rpc BidiChat (stream Msg) returns (stream Msg) {}
}
'''
        spec = self.parser.parse_text(proto)
        methods = spec.grpc_services[0].methods
        assert methods[0].method_type == GrpcMethodType.UNARY
        assert methods[1].method_type == GrpcMethodType.SERVER_STREAMING
        assert methods[2].method_type == GrpcMethodType.CLIENT_STREAMING
        assert methods[3].method_type == GrpcMethodType.BIDI_STREAMING

    def test_parse_multiple_services(self):
        proto = '''
syntax = "proto3";
package multi;

service ServiceA {
  rpc MethodA (Req) returns (Res) {}
}

service ServiceB {
  rpc MethodB (Req) returns (Res) {}
}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 2

    def test_parse_empty_proto(self):
        proto = 'syntax = "proto3";\npackage empty;'
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 0

    def test_parse_extracts_package(self):
        proto = '''
syntax = "proto3";
package com.example.api.v2;
service Svc { rpc M (R) returns (R) {} }
'''
        spec = self.parser.parse_text(proto)
        assert spec.grpc_services[0].package == "com.example.api.v2"


class TestGraphQLSchemaParser:
    def setup_method(self):
        self.parser = GraphQLSchemaParser()

    def test_parse_query_type(self):
        sdl = '''
type Query {
  user(id: ID!): User
  users: [User]
}
'''
        spec = self.parser.parse_text(sdl)
        assert spec.protocol == ApiProtocol.GRAPHQL
        assert len(spec.graphql_operations) >= 1
        user_op = next((op for op in spec.graphql_operations if op.name == "user"), None)
        assert user_op is not None
        assert user_op.operation_type.value == "query"

    def test_parse_mutation_type(self):
        sdl = '''
type Mutation {
  createUser(name: String!): User
  deleteUser(id: ID!): Boolean
}
'''
        spec = self.parser.parse_text(sdl)
        create_op = next((op for op in spec.graphql_operations if op.name == "createUser"), None)
        assert create_op is not None
        assert create_op.operation_type.value == "mutation"

    def test_parse_subscription_type(self):
        sdl = '''
type Subscription {
  onMessage(roomId: ID!): Message
}
'''
        spec = self.parser.parse_text(sdl)
        sub_op = next((op for op in spec.graphql_operations if op.name == "onMessage"), None)
        assert sub_op is not None
        assert sub_op.operation_type.value == "subscription"

    def test_parse_empty_sdl(self):
        spec = self.parser.parse_text("")
        assert len(spec.graphql_operations) == 0


class TestDetectProtocol:
    def test_detect_grpc(self):
        assert detect_protocol("api.proto") == ApiProtocol.GRPC

    def test_detect_graphql(self):
        assert detect_protocol("schema.graphql") == ApiProtocol.GRAPHQL
        assert detect_protocol("api.gql") == ApiProtocol.GRAPHQL
        assert detect_protocol("schema.graphqls") == ApiProtocol.GRAPHQL

    def test_detect_rest(self):
        assert detect_protocol("openapi.yaml") == ApiProtocol.REST
        assert detect_protocol("api.json") == ApiProtocol.REST
