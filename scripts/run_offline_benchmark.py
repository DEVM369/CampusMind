"""Run the fixed, network-free CampusMind functional benchmark.

The benchmark compares deterministic retrieval policies over a checked-in
synthetic corpus. It records every case input, retrieved evidence, route,
citations, refusal decision and latency so the aggregate metrics can be
recomputed without hidden state. It is functional evidence, not online LLM
quality evidence.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
from pathlib import Path
from typing import Any

from campusmind.knowledge.adaptive import RuleBasedRouteAnalyzer

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DATASET = ROOT / "datasets" / "offline_benchmark_v1.json"
DEFAULT_OUTPUT = ROOT / "reports" / "offline" / "benchmark-v1.json"
SYSTEMS = ("A_text_rag", "B_hybrid_rag", "C_graph_rag", "D_adaptive_rag", "E_agentic_rag")
REFUSAL = "当前离线评测没有足够的可验证证据，无法安全回答。"
DEFERRED = "该问题需要经过认证的结构化查询或人工审批流程。"


def load_dataset(path: Path = DEFAULT_DATASET) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if data.get("scope") != "offline_functional":
        raise ValueError("The benchmark must be marked offline_functional")
    if data.get("embedding_provider") != "deterministic" or data.get("llm_provider") != "disabled":
        raise ValueError("The benchmark must disable online models")
    return data


def _allowed(chunk: dict[str, Any], actor: str) -> bool:
    visibility = chunk.get("visibility")
    if visibility == "public":
        return True
    if visibility == "campus":
        return actor in {"campus", "owner"}
    return visibility == "private" and chunk.get("owner") == actor


def _chunk_map(dataset: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {item["id"]: item for item in dataset["corpus"]}


def _text_retrieve(case: dict[str, Any], chunks: dict[str, dict[str, Any]]) -> list[str]:
    terms = {str(item).lower() for item in case.get("query_terms", [])}
    scored: list[tuple[int, str]] = []
    for chunk in chunks.values():
        if chunk.get("status") != "active" or not _allowed(chunk, case["actor"]):
            continue
        haystack = " ".join(
            [chunk.get("title", ""), chunk.get("content", ""), *chunk.get("keywords", [])]
        ).lower()
        score = sum(1 for term in terms if term in haystack)
        if score >= 2:
            scored.append((score, chunk["id"]))
    scored.sort(key=lambda item: (-item[0], item[1]))
    return [item[1] for item in scored[:4]]


def _graph_retrieve(
    case: dict[str, Any],
    dataset: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
    *,
    retry: bool = False,
) -> list[str]:
    if case.get("graph_failure") == "transient_miss" and not retry:
        return []
    terms = {str(item).lower() for item in case.get("query_terms", [])}
    matches: list[tuple[int, str]] = []
    for edge in dataset.get("graph", []):
        if edge.get("status") != "active":
            continue
        source = chunks.get(edge.get("source"))
        if source is None or not _allowed(source, case["actor"]):
            continue
        score = len(terms.intersection(str(item).lower() for item in edge.get("query_terms", [])))
        if score >= 2:
            matches.append((score, edge["source"]))
    matches.sort(key=lambda item: (-item[0], item[1]))
    return list(dict.fromkeys(item[1] for item in matches))


def _merge(*groups: list[str]) -> list[str]:
    result: list[str] = []
    for group in groups:
        for item in group:
            if item not in result:
                result.append(item)
    return result[:4]


def _route(query: str) -> str:
    return RuleBasedRouteAnalyzer().analyze(query).route.value


def _answer(
    ids: list[str],
    chunks: dict[str, dict[str, Any]],
    *,
    refusal: bool,
    deferred: bool,
) -> str:
    if deferred:
        return DEFERRED
    if refusal or not ids:
        return REFUSAL
    return "根据合成知识库：" + " ".join(chunks[item]["content"] for item in ids)


def _case_result(
    system: str,
    case: dict[str, Any],
    dataset: dict[str, Any],
    chunks: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    started = time.perf_counter()
    initial_route = _route(case["query"])
    retry_count = 0
    fallback_reason = None
    validator_events: list[str] = []
    text_ids = _text_retrieve(case, chunks)
    graph_ids = _graph_retrieve(case, dataset, chunks)
    routed_route = {"A_text_rag": "rag", "B_hybrid_rag": "hybrid", "C_graph_rag": "graph"}.get(
        system, initial_route
    )
    executed_route = routed_route

    if system == "A_text_rag":
        retrieved = text_ids
    elif system == "B_hybrid_rag":
        retrieved = _merge(graph_ids, text_ids)
    elif system == "C_graph_rag":
        retrieved = graph_ids
    elif initial_route == "sql" or initial_route == "tool":
        retrieved = []
        executed_route = None
    elif initial_route == "graph":
        if system == "E_agentic_rag" and not graph_ids:
            retry_count = 1
            validator_events.append("graph_retry")
            graph_ids = _graph_retrieve(case, dataset, chunks, retry=True)
        if graph_ids:
            retrieved = _merge(graph_ids, text_ids) if retry_count else graph_ids
            if retry_count:
                executed_route = "hybrid"
        elif text_ids:
            retrieved = text_ids
            executed_route = "rag"
            fallback_reason = "no_source_verified_graph_path"
            validator_events.append("graph_to_text_fallback")
        else:
            retrieved = []
    elif initial_route == "hybrid":
        retrieved = _merge(graph_ids, text_ids)
    else:
        retrieved = text_ids

    invalid_candidate = case.get("bad_citation_candidate")
    candidate_citations = [invalid_candidate] if invalid_candidate and system == "E_agentic_rag" else list(retrieved)
    citation_valid = all(item in retrieved for item in candidate_citations)
    if not citation_valid:
        validator_events.append("invalid_citation_refused")

    deferred = initial_route in {"sql", "tool"}
    refusal = not retrieved or not citation_valid
    answer = _answer(retrieved, chunks, refusal=refusal, deferred=deferred)
    final_citations = [] if refusal or deferred else list(retrieved)
    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    return {
        "system": system,
        "case_id": case["case_id"],
        "query": case["query"],
        "actor": case["actor"],
        "expected_route": case["expected_route"],
        "routed_route": routed_route,
        "executed_route": executed_route,
        "retrieved_ids": retrieved,
        "qrels": list(case.get("qrels", [])),
        "forbidden_ids": list(case.get("forbidden_ids", [])),
        "answer": answer,
        "answer_terms": list(case.get("answer_terms", [])),
        "expected_refusal": bool(case.get("expected_refusal")),
        "refused": refusal,
        "deferred": deferred,
        "candidate_citations": candidate_citations,
        "citations": final_citations,
        "citation_valid": citation_valid,
        "retry_count": retry_count,
        "fallback_reason": fallback_reason,
        "validator_events": validator_events,
        "latency_ms": elapsed_ms,
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 3)


def _retrieval_metrics(rows: list[dict[str, Any]]) -> dict[str, float]:
    scored = [row for row in rows if row["qrels"]]
    if not scored:
        return {"recall_at_3": 0.0, "mrr": 0.0, "ndcg_at_3": 0.0, "retrieval_cases": 0}
    recalls: list[float] = []
    reciprocal_ranks: list[float] = []
    ndcgs: list[float] = []
    for row in scored:
        qrels = set(row["qrels"])
        retrieved = row["retrieved_ids"][:3]
        recalls.append(len(qrels.intersection(retrieved)) / len(qrels))
        first = next((index + 1 for index, item in enumerate(retrieved) if item in qrels), None)
        reciprocal_ranks.append(1.0 / first if first else 0.0)
        dcg = sum(1.0 / math.log2(index + 2) for index, item in enumerate(retrieved) if item in qrels)
        ideal = sum(1.0 / math.log2(index + 2) for index in range(min(len(qrels), 3)))
        ndcgs.append(dcg / ideal if ideal else 0.0)
    return {
        "recall_at_3": round(statistics.fmean(recalls), 4),
        "mrr": round(statistics.fmean(reciprocal_ranks), 4),
        "ndcg_at_3": round(statistics.fmean(ndcgs), 4),
        "retrieval_cases": len(scored),
    }


def recompute_metrics(rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        raise ValueError("benchmark report contains no raw cases")
    route_accuracy = statistics.fmean(row["routed_route"] == row["expected_route"] for row in rows)
    answer_correctness = statistics.fmean(
        (row["refused"] if row["expected_refusal"] else all(term in row["answer"] for term in row["answer_terms"]))
        for row in rows
    )
    citation_rows = [row for row in rows if row["citations"] or row["expected_refusal"]]
    citation_support = statistics.fmean(
        all(item in row["retrieved_ids"] for item in row["citations"]) for row in citation_rows
    ) if citation_rows else 0.0
    acl_rows = [row for row in rows if row["forbidden_ids"]]
    leaked = sum(
        bool(set(row["forbidden_ids"]).intersection(row["retrieved_ids"] + row["citations"]))
        or any(item in row["answer"] for item in row["forbidden_ids"])
        for row in acl_rows
    )
    return {
        **_retrieval_metrics(rows),
        "case_count": len(rows),
        "route_accuracy": round(route_accuracy, 4),
        "answer_correctness": round(answer_correctness, 4),
        "citation_support_rate": round(citation_support, 4),
        "unauthorized_evidence_leakage_rate": round(leaked / len(acl_rows), 4) if acl_rows else 0.0,
        "refusal_rate": round(statistics.fmean(row["refused"] for row in rows), 4),
        "retry_cases": sum(row["retry_count"] > 0 for row in rows),
        "p50_latency_ms": _percentile([row["latency_ms"] for row in rows], 0.50),
        "p95_latency_ms": _percentile([row["latency_ms"] for row in rows], 0.95),
    }


def run(dataset: dict[str, Any]) -> dict[str, Any]:
    chunks = _chunk_map(dataset)
    raw_cases = [
        _case_result(system, case, dataset, chunks)
        for system in SYSTEMS
        for case in dataset["cases"]
    ]
    summaries = {
        system: recompute_metrics([row for row in raw_cases if row["system"] == system])
        for system in SYSTEMS
    }
    return {
        "benchmark_id": dataset["benchmark_id"],
        "benchmark_version": dataset["version"],
        "scope": dataset["scope"],
        "model_quality_claim": "none; deterministic/extractive offline functional evaluation only",
        "source_dataset": str(DEFAULT_DATASET.relative_to(ROOT)).replace("\\", "/"),
        "systems": list(SYSTEMS),
        "case_count": len(dataset["cases"]),
        "raw_cases": raw_cases,
        "metrics": summaries,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args(argv)
    dataset = load_dataset(args.dataset)
    report = run(dataset)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote sanitized offline benchmark report: {args.output}")
    for system, metrics in report["metrics"].items():
        print(
            f"{system}: route={metrics['route_accuracy']:.4f} "
            f"recall@3={metrics['recall_at_3']:.4f} "
            f"answer={metrics['answer_correctness']:.4f} "
            f"acl_leak={metrics['unauthorized_evidence_leakage_rate']:.4f}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
