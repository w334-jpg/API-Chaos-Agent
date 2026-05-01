"""Enhanced TDD tests for Phase 2: gRPC/GraphQL Schema Parsers.

Covers: unit tests, functional tests, edge cases, stress tests.
"""

import os
import tempfile
import time

import pytest

from api_chaos_agent.models.schema import (
    ApiProtocol,
    FieldType,
    GraphQLOperationType,
    GrpcMethodType,
)
from api_chaos_agent.services.grpc_graphql_parser import (
    GraphQLSchemaParser,
    GrpcSchemaParser,
    detect_protocol,
)


class TestGrpcParserUnit:
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

    def test_parse_no_package(self):
        proto = '''
syntax = "proto3";
service NoPackage { rpc M (R) returns (R) {} }
'''
        spec = self.parser.parse_text(proto)
        assert spec.grpc_services[0].package == ""

    def test_parse_method_request_response_types(self):
        proto = '''
syntax = "proto3";
package test;
service OrderService {
  rpc CreateOrder (CreateOrderRequest) returns (CreateOrderResponse) {}
}
'''
        spec = self.parser.parse_text(proto)
        method = spec.grpc_services[0].methods[0]
        assert method.name == "CreateOrder"
        assert method.request_fields[0].message_type == "CreateOrderRequest"
        assert method.response_fields[0].message_type == "CreateOrderResponse"

    def test_parse_deeply_nested_braces(self):
        proto = '''
syntax = "proto3";
package nested;

service Outer {
  rpc Method1 (Req) returns (Res) {}
  rpc Method2 (Req) returns (stream Res) {}
}

message Req {
  message Inner {
    string value = 1;
  }
  Inner inner = 1;
}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert len(spec.grpc_services[0].methods) == 2

    def test_parse_service_with_many_methods(self):
        methods = "\n".join(
            f"  rpc Method{i} (Req) returns (Res) {{}}" for i in range(20)
        )
        proto = f'''
syntax = "proto3";
package many_methods;

service BigService {{
{methods}
}}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services[0].methods) == 20

    def test_parse_title_from_first_service(self):
        proto = '''
syntax = "proto3";
package test;
service MyService { rpc M (R) returns (R) {} }
'''
        spec = self.parser.parse_text(proto)
        assert spec.title == "MyService"

    def test_parse_title_default_when_no_services(self):
        proto = 'syntax = "proto3";\npackage test;'
        spec = self.parser.parse_text(proto)
        assert spec.title == "gRPC API"

    def test_parse_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse("/nonexistent/path/test.proto")

    def test_parse_file_wrong_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{}')
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unsupported file extension"):
                    self.parser.parse(f.name)
            finally:
                os.unlink(f.name)

    def test_parse_file_valid_proto(self):
        proto_content = '''
syntax = "proto3";
package file.test;
service FileService { rpc Get (Req) returns (Res) {} }
'''
        with tempfile.NamedTemporaryFile(suffix=".proto", delete=False, mode="w") as f:
            f.write(proto_content)
            f.flush()
            try:
                spec = self.parser.parse(f.name)
                assert spec.protocol == ApiProtocol.GRPC
                assert len(spec.grpc_services) == 1
                assert spec.grpc_services[0].package == "file.test"
            finally:
                os.unlink(f.name)

    def test_parse_raw_spec_contains_source(self):
        proto = 'syntax = "proto3";\nservice Svc { rpc M (R) returns (R) {} }'
        spec = self.parser.parse_text(proto)
        assert "source" in spec.raw_spec
        assert "Svc" in spec.raw_spec["source"]

    def test_parse_version_always_1_0_0(self):
        proto = 'syntax = "proto3";\nservice Svc { rpc M (R) returns (R) {} }'
        spec = self.parser.parse_text(proto)
        assert spec.version == "1.0.0"

    def test_parse_base_url_none(self):
        proto = 'syntax = "proto3";\nservice Svc { rpc M (R) returns (R) {} }'
        spec = self.parser.parse_text(proto)
        assert spec.base_url is None


class TestGrpcParserEdgeCases:
    def setup_method(self):
        self.parser = GrpcSchemaParser()

    def test_parse_whitespace_heavy(self):
        proto = '''
syntax = "proto3";

package   whitespace.test  ;


service   SpacedService   {
  rpc   Method1   (  Req  )   returns   (  Res  )   {}
}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert spec.grpc_services[0].name == "SpacedService"
        assert len(spec.grpc_services[0].methods) == 1

    def test_parse_comments_in_proto(self):
        proto = '''
syntax = "proto3";
package comments;

// This is a comment
service CommentedService {
  // Another comment
  rpc Method1 (Req) returns (Res) {}
  /* Block comment */
  rpc Method2 (Req) returns (stream Res) {}
}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert len(spec.grpc_services[0].methods) == 2

    def test_parse_empty_string(self):
        spec = self.parser.parse_text("")
        assert len(spec.grpc_services) == 0
        assert spec.protocol == ApiProtocol.GRPC

    def test_parse_only_syntax_declaration(self):
        spec = self.parser.parse_text('syntax = "proto3";')
        assert len(spec.grpc_services) == 0

    def test_parse_rpc_with_no_spaces(self):
        proto = '''
syntax = "proto3";
package compact;
service S{rpc M(Req)returns(Res){}}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert len(spec.grpc_services[0].methods) == 1

    def test_parse_multiple_packages_same_service_name(self):
        proto = '''
syntax = "proto3";
package pkg1;
service SameName { rpc M1 (R) returns (R) {} }
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 1
        assert spec.grpc_services[0].name == "SameName"

    def test_parse_rpc_with_stream_keyword_variations(self):
        proto = '''
syntax = "proto3";
package stream_test;
service StreamSvc {
  rpc Unary (Req) returns (Res) {}
  rpc ServerStream (Req) returns (stream Res) {}
  rpc ClientStream (stream Req) returns (Res) {}
  rpc BidiStream (stream Req) returns (stream Res) {}
}
'''
        spec = self.parser.parse_text(proto)
        methods = spec.grpc_services[0].methods
        assert len(methods) == 4
        assert methods[0].method_type == GrpcMethodType.UNARY
        assert methods[1].method_type == GrpcMethodType.SERVER_STREAMING
        assert methods[2].method_type == GrpcMethodType.CLIENT_STREAMING
        assert methods[3].method_type == GrpcMethodType.BIDI_STREAMING


class TestGraphQLParserUnit:
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

    def test_parse_all_operation_types_combined(self):
        sdl = '''
type Query {
  getUser(id: ID!): User
}

type Mutation {
  createUser(name: String!): User
}

type Subscription {
  onUserCreated: User
}
'''
        spec = self.parser.parse_text(sdl)
        queries = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.QUERY]
        mutations = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.MUTATION]
        subscriptions = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.SUBSCRIPTION]
        assert len(queries) >= 1
        assert len(mutations) >= 1
        assert len(subscriptions) >= 1

    def test_parse_field_with_multiple_arguments(self):
        sdl = '''
type Query {
  search(query: String!, limit: Int, offset: Int): [Result]
}
'''
        spec = self.parser.parse_text(sdl)
        search_op = next((op for op in spec.graphql_operations if op.name == "search"), None)
        assert search_op is not None
        assert len(search_op.fields[0].arguments) >= 1

    def test_parse_nullable_vs_non_nullable(self):
        sdl = '''
type Query {
  requiredField: String!
  optionalField: String
}
'''
        spec = self.parser.parse_text(sdl)
        req_op = next((op for op in spec.graphql_operations if op.name == "requiredField"), None)
        opt_op = next((op for op in spec.graphql_operations if op.name == "optionalField"), None)
        assert req_op is not None
        assert opt_op is not None
        assert req_op.fields[0].nullable is False
        assert opt_op.fields[0].nullable is True

    def test_parse_scalar_types(self):
        sdl = '''
type Query {
  intField: Int
  floatField: Float
  stringField: String
  boolField: Boolean
  idField: ID
}
'''
        spec = self.parser.parse_text(sdl)
        ops = {op.name: op for op in spec.graphql_operations}
        assert ops["intField"].fields[0].field_type == FieldType.INTEGER
        assert ops["floatField"].fields[0].field_type == FieldType.NUMBER
        assert ops["stringField"].fields[0].field_type == FieldType.STRING
        assert ops["boolField"].fields[0].field_type == FieldType.BOOLEAN
        assert ops["idField"].fields[0].field_type == FieldType.STRING

    def test_parse_object_return_type(self):
        sdl = '''
type Query {
  customType: CustomObject
}
'''
        spec = self.parser.parse_text(sdl)
        op = spec.graphql_operations[0]
        assert op.fields[0].field_type == FieldType.OBJECT

    def test_parse_title_always_graphql_api(self):
        sdl = 'type Query { hello: String }'
        spec = self.parser.parse_text(sdl)
        assert spec.title == "GraphQL API"

    def test_parse_version_always_1_0_0(self):
        sdl = 'type Query { hello: String }'
        spec = self.parser.parse_text(sdl)
        assert spec.version == "1.0.0"

    def test_parse_base_url_none(self):
        sdl = 'type Query { hello: String }'
        spec = self.parser.parse_text(sdl)
        assert spec.base_url is None

    def test_parse_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            self.parser.parse("/nonexistent/schema.graphql")

    def test_parse_file_wrong_extension(self):
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
            f.write(b'{}')
            f.flush()
            try:
                with pytest.raises(ValueError, match="Unsupported file extension"):
                    self.parser.parse(f.name)
            finally:
                os.unlink(f.name)

    def test_parse_file_valid_graphql(self):
        sdl = 'type Query { hello: String }'
        with tempfile.NamedTemporaryFile(suffix=".graphql", delete=False, mode="w") as f:
            f.write(sdl)
            f.flush()
            try:
                spec = self.parser.parse(f.name)
                assert spec.protocol == ApiProtocol.GRAPHQL
                assert len(spec.graphql_operations) >= 1
            finally:
                os.unlink(f.name)

    def test_parse_file_gql_extension(self):
        sdl = 'type Query { test: String }'
        with tempfile.NamedTemporaryFile(suffix=".gql", delete=False, mode="w") as f:
            f.write(sdl)
            f.flush()
            try:
                spec = self.parser.parse(f.name)
                assert spec.protocol == ApiProtocol.GRAPHQL
            finally:
                os.unlink(f.name)

    def test_parse_file_graphqls_extension(self):
        sdl = 'type Query { test: String }'
        with tempfile.NamedTemporaryFile(suffix=".graphqls", delete=False, mode="w") as f:
            f.write(sdl)
            f.flush()
            try:
                spec = self.parser.parse(f.name)
                assert spec.protocol == ApiProtocol.GRAPHQL
            finally:
                os.unlink(f.name)


class TestGraphQLParserEdgeCases:
    def setup_method(self):
        self.parser = GraphQLSchemaParser()

    def test_parse_no_arguments(self):
        sdl = '''
type Query {
  allUsers: [User]
}
'''
        spec = self.parser.parse_text(sdl)
        op = spec.graphql_operations[0]
        assert op.fields[0].arguments == []

    def test_parse_required_argument(self):
        sdl = '''
type Query {
  user(id: ID!): User
}
'''
        spec = self.parser.parse_text(sdl)
        op = spec.graphql_operations[0]
        req_args = [a for a in op.fields[0].arguments if a.required]
        assert len(req_args) >= 1

    def test_parse_whitespace_heavy(self):
        sdl = '''
type   Query   {
   hello  :   String
}
'''
        spec = self.parser.parse_text(sdl)
        assert len(spec.graphql_operations) >= 1

    def test_parse_only_type_definitions(self):
        sdl = '''
type User {
  id: ID!
  name: String
}
'''
        spec = self.parser.parse_text(sdl)
        assert len(spec.graphql_operations) == 0

    def test_parse_array_return_type(self):
        sdl = '''
type Query {
  users: [User]
}
'''
        spec = self.parser.parse_text(sdl)
        op = spec.graphql_operations[0]
        assert op is not None

    def test_parse_non_standard_type_names(self):
        sdl = '''
type Query {
  myCustom123Field: MyType
}
'''
        spec = self.parser.parse_text(sdl)
        op = next((o for o in spec.graphql_operations if o.name == "myCustom123Field"), None)
        assert op is not None


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

    def test_detect_case_insensitive(self):
        assert detect_protocol("API.PROTO") == ApiProtocol.GRPC
        assert detect_protocol("Schema.GraphQL") == ApiProtocol.GRAPHQL

    def test_detect_unknown_extension(self):
        assert detect_protocol("readme.md") == ApiProtocol.REST
        assert detect_protocol("data.xml") == ApiProtocol.REST

    def test_detect_no_extension(self):
        assert detect_protocol("Makefile") == ApiProtocol.REST

    def test_detect_path_with_directories(self):
        assert detect_protocol("/path/to/api.proto") == ApiProtocol.GRPC
        assert detect_protocol("/path/to/schema.graphql") == ApiProtocol.GRAPHQL


class TestGrpcParserStress:
    def setup_method(self):
        self.parser = GrpcSchemaParser()

    def test_parse_large_proto_many_services(self):
        services = []
        for i in range(50):
            services.append(f"""
service Service{i} {{
  rpc Method{i}A (Req) returns (Res) {{}}
  rpc Method{i}B (Req) returns (stream Res) {{}}
  rpc Method{i}C (stream Req) returns (Res) {{}}
  rpc Method{i}D (stream Req) returns (stream Res) {{}}
}}""")
        proto = f'syntax = "proto3";\npackage stress;\n' + "\n".join(services)
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services) == 50
        assert len(spec.grpc_services[0].methods) == 4
        total_methods = sum(len(s.methods) for s in spec.grpc_services)
        assert total_methods == 200

    def test_parse_large_proto_many_methods_per_service(self):
        methods = "\n".join(f"  rpc Method{i:04d}(Req) returns (Res) {{}}" for i in range(100))
        proto = f'''
syntax = "proto3";
package stress;
service MegaService {{
{methods}
}}
'''
        spec = self.parser.parse_text(proto)
        assert len(spec.grpc_services[0].methods) == 100

    def test_parse_performance_under_1_second(self):
        services = []
        for i in range(100):
            methods = "\n".join(f"  rpc M{j}(R) returns (R) {{}}" for j in range(10))
            services.append(f"service S{i} {{\n{methods}\n}}")
        proto = f'syntax = "proto3";\npackage perf;\n' + "\n".join(services)
        start = time.monotonic()
        spec = self.parser.parse_text(proto)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Parsing took {elapsed:.3f}s, expected < 1.0s"
        assert len(spec.grpc_services) == 100

    def test_parse_repeated_calls_consistent(self):
        proto = '''
syntax = "proto3";
package consistent;
service TestSvc {
  rpc M1 (R) returns (R) {}
  rpc M2 (R) returns (stream R) {}
}
'''
        specs = [self.parser.parse_text(proto) for _ in range(10)]
        for spec in specs:
            assert len(spec.grpc_services) == 1
            assert len(spec.grpc_services[0].methods) == 2
            assert spec.grpc_services[0].name == "TestSvc"


class TestGraphQLParserStress:
    def setup_method(self):
        self.parser = GraphQLSchemaParser()

    def test_parse_large_sdl_many_operations(self):
        queries = "\n".join(f"  query{i}(id: ID!): Result{i}" for i in range(100))
        sdl = f"type Query {{\n{queries}\n}}"
        spec = self.parser.parse_text(sdl)
        assert len(spec.graphql_operations) == 100

    def test_parse_large_sdl_all_types(self):
        queries = "\n".join(f"  q{i}: String" for i in range(50))
        mutations = "\n".join(f"  m{i}(input: String!): String" for i in range(50))
        subscriptions = "\n".join(f"  sub{i}: Message" for i in range(50))
        sdl = f"""
type Query {{
{queries}
}}

type Mutation {{
{mutations}
}}

type Subscription {{
{subscriptions}
}}
"""
        spec = self.parser.parse_text(sdl)
        assert len(spec.graphql_operations) == 150

    def test_parse_performance_under_1_second(self):
        queries = "\n".join(f"  query{i}(id: ID!, name: String!, value: Int): Result{i}" for i in range(500))
        sdl = f"type Query {{\n{queries}\n}}"
        start = time.monotonic()
        spec = self.parser.parse_text(sdl)
        elapsed = time.monotonic() - start
        assert elapsed < 1.0, f"Parsing took {elapsed:.3f}s, expected < 1.0s"
        assert len(spec.graphql_operations) == 500

    def test_parse_repeated_calls_consistent(self):
        sdl = '''
type Query {
  hello: String
  world: String
}

type Mutation {
  setHello(msg: String!): String
}
'''
        specs = [self.parser.parse_text(sdl) for _ in range(10)]
        for spec in specs:
            assert len(spec.graphql_operations) == 3


class TestGrpcParserFunctional:
    def setup_method(self):
        self.parser = GrpcSchemaParser()

    def test_full_ecommerce_proto(self):
        proto = '''
syntax = "proto3";
package ecommerce.v1;

service ProductService {
  rpc GetProduct (GetProductRequest) returns (GetProductResponse) {}
  rpc ListProducts (ListProductsRequest) returns (stream Product) {}
  rpc CreateProduct (CreateProductRequest) returns (CreateProductResponse) {}
  rpc UpdateProduct (UpdateProductRequest) returns (UpdateProductResponse) {}
  rpc DeleteProduct (DeleteProductRequest) returns (DeleteProductResponse) {}
}

service OrderService {
  rpc CreateOrder (CreateOrderRequest) returns (CreateOrderResponse) {}
  rpc GetOrder (GetOrderRequest) returns (GetOrderResponse) {}
  rpc StreamOrderUpdates (StreamOrderUpdatesRequest) returns (stream OrderUpdate) {}
  rpc CancelOrder (CancelOrderRequest) returns (CancelOrderResponse) {}
}

service PaymentService {
  rpc ProcessPayment (ProcessPaymentRequest) returns (ProcessPaymentResponse) {}
  rpc RefundPayment (RefundPaymentRequest) returns (RefundPaymentResponse) {}
}
'''
        spec = self.parser.parse_text(proto)
        assert spec.protocol == ApiProtocol.GRPC
        assert len(spec.grpc_services) == 3
        assert spec.grpc_services[0].name == "ProductService"
        assert len(spec.grpc_services[0].methods) == 5
        assert spec.grpc_services[1].name == "OrderService"
        assert len(spec.grpc_services[1].methods) == 4
        assert spec.grpc_services[2].name == "PaymentService"
        assert len(spec.grpc_services[2].methods) == 2
        stream_method = next(m for m in spec.grpc_services[1].methods if m.name == "StreamOrderUpdates")
        assert stream_method.method_type == GrpcMethodType.SERVER_STREAMING

    def test_spec_can_be_serialized(self):
        proto = '''
syntax = "proto3";
package serial;
service Svc { rpc M (Req) returns (Res) {} }
'''
        spec = self.parser.parse_text(proto)
        json_str = spec.model_dump_json()
        assert "Svc" in json_str
        assert "grpc" in json_str

    def test_spec_roundtrip(self):
        proto = '''
syntax = "proto3";
package roundtrip;
service RoundTripSvc {
  rpc Unary (Req) returns (Res) {}
  rpc Stream (Req) returns (stream Res) {}
}
'''
        spec = self.parser.parse_text(proto)
        data = spec.model_dump()
        from api_chaos_agent.models.schema import APISpec
        restored = APISpec(**data)
        assert restored.protocol == ApiProtocol.GRPC
        assert len(restored.grpc_services) == 1
        assert len(restored.grpc_services[0].methods) == 2


class TestGraphQLParserFunctional:
    def setup_method(self):
        self.parser = GraphQLSchemaParser()

    def test_full_blog_api_sdl(self):
        sdl = '''
type Query {
  post(id: ID!): Post
  posts(limit: Int, offset: Int): [Post]
  author(id: ID!): Author
  search(query: String!): [SearchResult]
}

type Mutation {
  createPost(title: String!, content: String!, authorId: ID!): Post
  updatePost(id: ID!, title: String, content: String): Post
  deletePost(id: ID!): Boolean
  createAuthor(name: String!, email: String!): Author
}

type Subscription {
  onPostCreated: Post
  onPostUpdated(postId: ID!): Post
}
'''
        spec = self.parser.parse_text(sdl)
        assert spec.protocol == ApiProtocol.GRAPHQL
        queries = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.QUERY]
        mutations = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.MUTATION]
        subscriptions = [op for op in spec.graphql_operations if op.operation_type == GraphQLOperationType.SUBSCRIPTION]
        assert len(queries) == 4
        assert len(mutations) == 4
        assert len(subscriptions) == 2

    def test_spec_can_be_serialized(self):
        sdl = 'type Query { hello: String }'
        spec = self.parser.parse_text(sdl)
        json_str = spec.model_dump_json()
        assert "graphql" in json_str

    def test_spec_roundtrip(self):
        sdl = '''
type Query {
  user(id: ID!): User
}

type Mutation {
  createUser(name: String!): User
}
'''
        spec = self.parser.parse_text(sdl)
        data = spec.model_dump()
        from api_chaos_agent.models.schema import APISpec
        restored = APISpec(**data)
        assert restored.protocol == ApiProtocol.GRAPHQL
        assert len(restored.graphql_operations) == 2
