# API Documentation

Base URL: `http://localhost:8000`

Interactive API documentation is available at `/docs` (Swagger UI) and `/redoc` (ReDoc) when the server is running.

## Authentication

Most endpoints require a JWT token when authentication is enabled.

```bash
# Get a token
curl -X POST http://localhost:8000/auth/token \
  -d "username=admin&password=admin"
```

Include the token in subsequent requests:

```bash
curl -H "Authorization: Bearer <token>" http://localhost:8000/api/schemas
```

## Schema Management

### Upload & Parse OpenAPI Schema

```bash
# Upload a schema file
curl -X POST http://localhost:8000/api/schemas \
  -H "Content-Type: multipart/form-data" \
  -F "file=@petstore.yaml"

# Response
{
  "id": "uuid-here",
  "title": "Petstore API",
  "version": "1.0.0",
  "endpoints": [
    {
      "path": "/pets",
      "method": "GET",
      "summary": "List all pets",
      "parameters": [...],
      "request_body": null,
      "responses": {...}
    }
  ]
}
```

### List Schemas

```bash
curl http://localhost:8000/api/schemas
```

### Get Schema Details

```bash
curl http://localhost:8000/api/schemas/{schema_id}
```

## Scenario Generation

### Generate Chaos Scenarios

```bash
curl -X POST http://localhost:8000/api/scenarios/generate \
  -H "Content-Type: application/json" \
  -d '{
    "schema_id": "uuid-here",
    "scenario_types": ["latency", "error_status", "tampering", "rate_burst"]
  }'
```

### List Scenarios

```bash
curl http://localhost:8000/api/scenarios
```

### Scenario Types

| Type | Description |
|------|-------------|
| `latency` | Latency injection scenarios |
| `error_status` | Error status code scenarios (4xx/5xx) |
| `tampering` | Request body tampering scenarios |
| `rate_burst` | Rate limit burst scenarios |

## Test Execution

### Run Chaos Tests

```bash
curl -X POST http://localhost:8000/api/execution/run \
  -H "Content-Type: application/json" \
  -d '{
    "scenario_ids": ["scenario-uuid-1", "scenario-uuid-2"],
    "base_url": "https://api.example.com",
    "concurrency": 10,
    "timeout_seconds": 30
  }'
```

### Execution Configuration

| Parameter | Default | Description |
|-----------|---------|-------------|
| `concurrency` | 10 | Number of concurrent requests |
| `timeout_seconds` | 30 | Request timeout in seconds |
| `max_retries` | 2 | Maximum retry attempts |
| `retry_delay` | 1.0 | Delay between retries (seconds) |

### WebSocket: Real-time Progress

Connect to `ws://localhost:8000/ws/executions/{execution_id}` for real-time execution progress.

```javascript
const ws = new WebSocket('ws://localhost:8000/ws/executions/your-execution-id');
ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log(`Progress: ${data.completed}/${data.total}`);
};
```

## Report Management

### Generate Report

```bash
curl -X POST http://localhost:8000/api/reports/generate \
  -H "Content-Type: application/json" \
  -d '{
    "execution_id": "execution-uuid"
  }'
```

### Export Report

```bash
# HTML format (default)
curl http://localhost:8000/api/reports/{report_id}/export?format=html -o report.html

# JSON format
curl http://localhost:8000/api/reports/{report_id}/export?format=json -o report.json

# CSV format
curl http://localhost:8000/api/reports/{report_id}/export?format=csv -o report.csv
```

### Severity Levels

| Level | Description |
|-------|-------------|
| `critical` | System crash, data loss, or security breach |
| `high` | Significant functionality degradation |
| `medium` | Partial functionality impact |
| `low` | Minor issues or cosmetic problems |
| `info` | Informational findings |

## Postman Compatibility

### Import Postman Collection

```bash
curl -X POST http://localhost:8000/api/postman/import \
  -H "Content-Type: multipart/form-data" \
  -F "file=@collection.json"
```

### Export as Postman Collection

```bash
curl -X POST http://localhost:8000/api/postman/export \
  -H "Content-Type: application/json" \
  -d '{"schema_id": "uuid-here"}' \
  -o collection.json
```

## Health Check

```bash
# Liveness
curl http://localhost:8000/health/live

# Readiness
curl http://localhost:8000/health/ready

# Full health with dependency status
curl http://localhost:8000/health
```

## Error Responses

All errors follow RFC 7807 Problem Details format:

```json
{
  "detail": "Error message describing what went wrong"
}
```

Common HTTP status codes:

| Code | Meaning |
|------|---------|
| 400 | Bad Request - Invalid input parameters |
| 401 | Unauthorized - Missing or invalid JWT token |
| 404 | Not Found - Resource does not exist |
| 413 | Payload Too Large - Request body exceeds limit |
| 429 | Too Many Requests - Rate limit exceeded |
| 500 | Internal Server Error - Unexpected server error |
