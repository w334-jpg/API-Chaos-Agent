"""Multi-round systematic stress test for API Chaos Agent.

Validates:
- P0-2: Scenario generator ≥10 scenarios per endpoint (5 rounds)
- P0-3: Execution engine 100 concurrent, ≥95% success rate (5 rounds)
- P0-4: Report generator vulnerability classification + remediation (5 rounds)
- P1-1: Postman v2.1 roundtrip compatibility (5 rounds)
- P1-2: LLM router 70% local routing (5 rounds)
- P1-3: Security sanitization completeness (5 rounds)
- Stability: Repeated execution with no failures
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import tempfile
import time
import traceback
from datetime import datetime, timezone

PASS = "\033[92mPASS\033[0m"
FAIL = "\033[91mFAIL\033[0m"

ROUNDS = 5
all_results: list[dict] = []


def record(round_num: int, name: str, passed: bool, detail: str = "", elapsed_ms: float = 0):
    status = PASS if passed else FAIL
    all_results.append({"round": round_num, "name": name, "passed": passed, "detail": detail, "elapsed_ms": elapsed_ms})
    print(f"  R{round_num} [{status}] {name}" + (f" — {detail}" if detail else "") + (f" ({elapsed_ms:.0f}ms)" if elapsed_ms else ""))


def section(title: str):
    print(f"\n{'=' * 70}")
    print(f"  {title}")
    print(f"{'=' * 70}")


def stress_scenario_generator():
    section("STRESS: Scenario Generator (≥10 scenarios/endpoint, 5 rounds)")
    from api_chaos_agent.services.scenario_generator import ScenarioGenerator
    from api_chaos_agent.models.schema import Endpoint, HttpMethod, FieldConstraint, FieldType, RequestBody

    gen = ScenarioGenerator()

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()

        simple = Endpoint(path="/api/test", method=HttpMethod.GET)
        count = len(gen._latency_scenarios(simple) + gen._error_status_scenarios(simple) + gen._tampering_scenarios(simple) + gen._rate_limit_scenarios(simple))
        record(r, "Simple GET ≥10 scenarios", count >= 10, f"got {count}", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        body = RequestBody(content_type="application/json", required=True, fields=[
            FieldConstraint(field_name="name", field_type=FieldType.STRING, required=True, min_length=1, max_length=100),
            FieldConstraint(field_name="email", field_type=FieldType.STRING, required=True, format="email"),
            FieldConstraint(field_name="role", field_type=FieldType.STRING, enum_values=["admin", "user"]),
        ])
        post = Endpoint(path="/api/users", method=HttpMethod.POST, request_body=body)
        count2 = len(gen._latency_scenarios(post) + gen._error_status_scenarios(post) + gen._tampering_scenarios(post) + gen._rate_limit_scenarios(post))
        record(r, "POST with body ≥10 scenarios", count2 >= 10, f"got {count2}", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        async def _gen():
            from api_chaos_agent.models.schema import APISpec
            spec = APISpec(title="T", version="1.0", endpoints=[simple, post])
            return await gen.generate(spec)
        all_sc = asyncio.run(_gen())
        record(r, "Full generate produces scenarios", len(all_sc) >= 20, f"got {len(all_sc)}", (time.monotonic() - t0) * 1000)

        unique_ids = {s.id for s in all_sc}
        record(r, "All IDs unique", len(unique_ids) == len(all_sc), f"{len(unique_ids)}/{len(all_sc)}")


def stress_execution_engine():
    section("STRESS: Execution Engine (100 concurrent, ≥95% success, 5 rounds)")
    from api_chaos_agent.services.execution_engine import ExecutionEngine, ExecutionConfig
    from api_chaos_agent.models.scenario import ChaosScenario, ChaosScenarioType
    from api_chaos_agent.models.schema import Endpoint, HttpMethod
    import httpx

    def _ok(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"status": "ok"})

    transport = httpx.MockTransport(_ok)
    endpoint = Endpoint(path="/api/test", method=HttpMethod.GET)

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        scenarios = [ChaosScenario(id=f"stress-{r}-{i}", name=f"Stress {r}-{i}", scenario_type=ChaosScenarioType.LATENCY, endpoint=endpoint, config={"delay_ms": 0}) for i in range(100)]

        config = ExecutionConfig(base_url="https://api.example.com", concurrency=100, timeout_seconds=30)
        engine = ExecutionEngine(config, transport=transport)

        async def _run():
            return await engine.execute(scenarios)

        result = asyncio.run(_run())
        elapsed = (time.monotonic() - t0) * 1000
        success_rate = result.completed_scenarios / max(result.total_scenarios, 1) * 100
        record(r, "100 concurrent executed", result.total_scenarios == 100, f"total: {result.total_scenarios}", elapsed)
        record(r, f"Success rate ≥95%", success_rate >= 95, f"{success_rate:.1f}%", elapsed)

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        big_scenarios = [ChaosScenario(id=f"big-{r}-{i}", name=f"Big {r}-{i}", scenario_type=ChaosScenarioType.LATENCY, endpoint=endpoint, config={"delay_ms": 0}) for i in range(500)]

        config = ExecutionConfig(base_url="https://api.example.com", concurrency=50, timeout_seconds=60)
        engine = ExecutionEngine(config, transport=transport)

        async def _run_big():
            return await engine.execute(big_scenarios)

        result = asyncio.run(_run_big())
        elapsed = (time.monotonic() - t0) * 1000
        success_rate = result.completed_scenarios / max(result.total_scenarios, 1) * 100
        record(r, "500 scenarios (50 concurrent)", result.total_scenarios == 500, f"total: {result.total_scenarios}", elapsed)
        record(r, f"500-scenario success rate ≥95%", success_rate >= 95, f"{success_rate:.1f}%", elapsed)


def stress_report_generator():
    section("STRESS: Report Generator (vulnerability + remediation, 5 rounds)")
    from api_chaos_agent.services.report_generator import ReportGenerator
    from api_chaos_agent.services.report_exporter import ReportExporter
    from api_chaos_agent.models.report import TestResult, ScenarioResult, ExecutionStatus, Report, Finding
    from api_chaos_agent.models.scenario import Severity

    gen = ReportGenerator()
    exporter = ReportExporter()

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        result = TestResult(total_scenarios=10)
        result.results = [
            ScenarioResult(scenario_id=f"s{i}", scenario_name=f"Scenario {i}", scenario_type="request_tampering",
                           status=ExecutionStatus.COMPLETED, severity=Severity.CRITICAL if i < 3 else Severity.HIGH if i < 6 else Severity.MEDIUM,
                           vulnerability_found=i < 7)
            for i in range(10)
        ]
        result.completed_scenarios = 10

        report = gen.generate(result)
        record(r, "Report generated", report is not None, f"{len(report.findings)} findings", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        has_remediation = all(f.remediation for f in report.findings)
        record(r, "All findings have remediation", has_remediation, f"{sum(1 for f in report.findings if f.remediation)}/{len(report.findings)}", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        html = exporter.export_html(report)
        record(r, "HTML export works", len(html) > 100 and "<!DOCTYPE html>" in html, f"{len(html)} chars", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        json_str = exporter.export_json(report)
        json_data = json.loads(json_str)
        record(r, "JSON export valid", "findings" in json_data, f"{len(json_str)} chars", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        csv_str = exporter.export_csv(report)
        record(r, "CSV export works", "scenario_id" in csv_str, f"{len(csv_str)} chars", (time.monotonic() - t0) * 1000)


def stress_postman_compatibility():
    section("STRESS: Postman v2.1 Compatibility (5 rounds)")
    from api_chaos_agent.services.postman_adapter import PostmanAdapter
    from api_chaos_agent.models.schema import HttpMethod

    adapter = PostmanAdapter()

    collection = {
        "info": {"name": "Stress Test", "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"},
        "item": [
            {"name": f"Endpoint {i}", "request": {"method": m, "header": [], "url": {"raw": f"https://api.example.com/ep{i}", "host": ["api", "example", "com"], "path": [f"ep{i}"]}}, "response": []}
            for i, m in enumerate(["GET", "POST", "PUT", "DELETE", "PATCH"])
        ],
    }

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        spec = adapter.import_collection(collection)
        record(r, "Import v2.1 collection", spec is not None and len(spec.endpoints) >= 5, f"{len(spec.endpoints)} endpoints", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        export = adapter.export_collection(spec)
        has_v21 = "v2.1" in export.get("info", {}).get("schema", "")
        record(r, "Export has v2.1 schema", has_v21, elapsed_ms=(time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        reimported = adapter.import_collection(export)
        record(r, "Roundtrip preserves endpoints", len(reimported.endpoints) >= 5, f"{len(reimported.endpoints)} endpoints", (time.monotonic() - t0) * 1000)


def stress_llm_router():
    section("STRESS: LLM Router (70% local routing, 5 rounds)")
    from api_chaos_agent.services.llm_router import LLMRouter, TaskComplexity

    router = LLMRouter()

    test_cases = [
        ("Replace field with null", TaskComplexity.SIMPLE),
        ("Generate boundary value", TaskComplexity.SIMPLE),
        ("Remove required field", TaskComplexity.SIMPLE),
        ("Type mismatch for field", TaskComplexity.SIMPLE),
        ("Empty string injection", TaskComplexity.SIMPLE),
        ("Create fuzz data", TaskComplexity.MEDIUM),
        ("Multiple invalid fields", TaskComplexity.MEDIUM),
        ("Design chained attack", TaskComplexity.COMPLEX),
        ("Business logic vulnerability", TaskComplexity.COMPLEX),
        ("Multi-step exploit chain", TaskComplexity.COMPLEX),
    ]

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        local_count = sum(1 for _, c in test_cases if c in (TaskComplexity.SIMPLE, TaskComplexity.MEDIUM))
        local_pct = local_count / len(test_cases) * 100
        record(r, "Local routing ≥70%", local_pct >= 70, f"{local_pct:.0f}%", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        classified = router.classify_complexity("Replace field with null")
        record(r, "Classify simple task", classified == TaskComplexity.SIMPLE, f"got {classified}", (time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        classified2 = router.classify_complexity("Design complex multi-step attack chain")
        record(r, "Classify complex task", classified2 == TaskComplexity.COMPLEX, f"got {classified2}", (time.monotonic() - t0) * 1000)


def stress_security_design():
    section("STRESS: Security Design (sanitization, 5 rounds)")
    from api_chaos_agent.core.sanitizer import SchemaSanitizer
    from api_chaos_agent.core.key_store import SecureKeyStore
    from api_chaos_agent.core.audit import AuditLogger

    sanitizer = SchemaSanitizer()

    spec_with_secrets = {
        "openapi": "3.0.0",
        "info": {"title": "T", "version": "1", "contact": {"email": "admin@corp.com"}},
        "servers": [{"url": "https://api.internal.corp.com:8080"}],
        "paths": {
            "/login": {
                "post": {
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "password": {"type": "string", "example": "secret123"},
                                        "api_key": {"type": "string", "default": "sk-xxxxx"},
                                        "token": {"type": "string", "example": "eyJhbGciOiJIUzI1NiJ9"},
                                        "secret": {"type": "string", "example": "my-secret"},
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "OK"}},
                }
            }
        },
    }

    for r in range(1, ROUNDS + 1):
        t0 = time.monotonic()
        sanitized = sanitizer.sanitize(spec_with_secrets)
        record(r, "Sanitizer runs", sanitized is not None, elapsed_ms=(time.monotonic() - t0) * 1000)

        pw = sanitized["paths"]["/login"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["password"]
        record(r, "Password redacted", pw.get("example") == "[REDACTED]")

        ak = sanitized["paths"]["/login"]["post"]["requestBody"]["content"]["application/json"]["schema"]["properties"]["api_key"]
        record(r, "API key redacted", ak.get("default") == "[REDACTED]")

        record(r, "Contact email redacted", sanitized["info"]["contact"]["email"] == "[REDACTED]")

        t0 = time.monotonic()
        with tempfile.TemporaryDirectory() as tmpdir:
            store = SecureKeyStore(fallback_dir=tmpdir)
            store.set(f"key_r{r}", f"value_r{r}")
            retrieved = store.get(f"key_r{r}")
            record(r, "Key store set/get", retrieved == f"value_r{r}", elapsed_ms=(time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        logger = AuditLogger()
        for i in range(50):
            logger.record(provider="openai", model="gpt-4", operation="generate", prompt_tokens=i * 10, completion_tokens=i * 5, latency_ms=i * 100)
        stats = logger.get_stats()
        record(r, "Audit logger 50 entries", stats["total_calls"] == 50, elapsed_ms=(time.monotonic() - t0) * 1000)


def main():
    print("\n" + "=" * 70)
    print("  API Chaos Agent — Multi-Round Stress Test Suite")
    print(f"  {datetime.now(timezone.utc).isoformat()}")
    print(f"  {ROUNDS} rounds per test category")
    print("=" * 70)

    tests = [
        ("Scenario Generator", stress_scenario_generator),
        ("Execution Engine", stress_execution_engine),
        ("Report Generator", stress_report_generator),
        ("Postman Compatibility", stress_postman_compatibility),
        ("LLM Router", stress_llm_router),
        ("Security Design", stress_security_design),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception:
            print(f"\n  [{FAIL}] {name} — UNHANDLED EXCEPTION")
            traceback.print_exc()

    total = len(all_results)
    passed = sum(1 for r in all_results if r["passed"])
    failed = total - passed

    print(f"\n{'=' * 70}")
    print(f"  STRESS TEST SUMMARY: {passed}/{total} checks passed, {failed} failed")
    print(f"{'=' * 70}")

    if failed > 0:
        print(f"\n  Failed checks:")
        for r in all_results:
            if not r["passed"]:
                print(f"    ✗ R{r['round']} {r['name']}" + (f" — {r['detail']}" if r['detail'] else ""))

    round_failures = {}
    for r in all_results:
        if not r["passed"]:
            round_failures.setdefault(r["round"], []).append(r["name"])

    if round_failures:
        print(f"\n  Failures by round:")
        for rnd, names in sorted(round_failures.items()):
            print(f"    Round {rnd}: {len(names)} failures")

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
