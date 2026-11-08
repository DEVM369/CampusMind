from __future__ import annotations

import json

from scripts.run_offline_benchmark import (
    DEFAULT_DATASET,
    load_dataset,
    recompute_metrics,
    run,
)


def test_offline_benchmark_is_fixed_and_recomputable():
    dataset = load_dataset(DEFAULT_DATASET)
    first = run(dataset)
    second = run(dataset)
    assert first["benchmark_id"] == "campusmind-offline-functional-v1"
    normalize = lambda rows: [
        {key: value for key, value in row.items() if key != "latency_ms"} for row in rows
    ]
    assert normalize(first["raw_cases"]) == normalize(second["raw_cases"])
    assert first["metrics"].keys() == second["metrics"].keys()
    for system in first["systems"]:
        rows = [row for row in first["raw_cases"] if row["system"] == system]
        assert first["metrics"][system] == recompute_metrics(rows)


def test_offline_benchmark_covers_acl_stale_graph_retry_and_refusal():
    report = run(load_dataset(DEFAULT_DATASET))
    rows = report["raw_cases"]
    acl = next(row for row in rows if row["system"] == "D_adaptive_rag" and row["case_id"] == "acl-01")
    stale = next(row for row in rows if row["system"] == "D_adaptive_rag" and row["case_id"] == "stale-01")
    retry = next(row for row in rows if row["system"] == "E_agentic_rag" and row["case_id"] == "retry-01")
    bad_citation = next(
        row for row in rows if row["system"] == "E_agentic_rag" and row["case_id"] == "citation-01"
    )
    assert acl["refused"] is True and "private-scholarship" not in acl["retrieved_ids"]
    assert stale["retrieved_ids"] == ["research-profile"]
    assert retry["retry_count"] == 1 and "graph_retry" in retry["validator_events"]
    assert bad_citation["refused"] is True and bad_citation["citation_valid"] is False


def test_report_contains_no_credentials_or_environment_files():
    report = run(load_dataset(DEFAULT_DATASET))
    text = json.dumps(report, ensure_ascii=False)
    assert "password" not in text.lower()
    assert "test.env" not in text.lower()
    assert "cookie" not in text.lower()
