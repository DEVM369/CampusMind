from __future__ import annotations

from types import SimpleNamespace
from uuid import uuid4

from campusmind.platform.observability import extract_result_snapshot, sanitize_payload


def test_sanitize_redacts_credentials_without_inventing_values():
    payload = sanitize_payload(
        {
            "api_key": "secret-value",
            "Authorization": "Bearer xyz",
            "normal": 7,
        }
    )
    assert payload["api_key"] == "<redacted>"
    assert payload["Authorization"] == "<redacted>"
    assert payload["normal"] == 7


def test_result_snapshot_extracts_nested_evidence_graph_and_steps():
    chunk_id = uuid4()
    chunk = SimpleNamespace(chunk_id=chunk_id, content="李明教授研究知识图谱。")
    evidence = SimpleNamespace(chunk=chunk)
    edge = SimpleNamespace(
        relation_type="RESEARCHES",
        source_name="李明",
        target_name="知识图谱",
        path_text="李明 -[RESEARCHES]-> 知识图谱",
    )
    step = SimpleNamespace(
        step_name="retrieval_coordinator",
        duration_ms=12.5,
        status="completed",
        output_json={"evidence_hits": [evidence], "graph_paths": [edge]},
    )
    result = SimpleNamespace(
        answer="李明教授研究知识图谱。[1]",
        status="completed",
        executed_route="graph",
        elapsed_ms=55.0,
        retry_count=0,
        evidence_hits=[],
        graph_paths=[],
        steps=[step],
    )

    snapshot = extract_result_snapshot(result)
    assert snapshot.answer.startswith("李明")
    assert snapshot.route == "graph"
    assert str(chunk_id) in snapshot.evidence_ids
    assert "RESEARCHES" in snapshot.graph_path_tokens
    assert "知识图谱" in snapshot.graph_path_tokens
    assert [item.name for item in snapshot.steps] == ["retrieval_coordinator"]
    assert snapshot.steps[0].duration_ms == 12.5


def test_missing_tokens_and_step_latency_stay_none():
    result = SimpleNamespace(
        answer="answer",
        status="completed",
        executed_route="rag",
        steps=[SimpleNamespace(step_name="writer", status="completed")],
    )
    snapshot = extract_result_snapshot(result)
    assert snapshot.token_total is None
    assert snapshot.token_cost is None
    assert snapshot.steps[0].duration_ms is None


def test_component_mapping_covers_agent_pipeline():
    result = SimpleNamespace(
        answer="answer",
        status="completed",
        steps=[
            SimpleNamespace(step_name="intent_and_complexity"),
            SimpleNamespace(step_name="planner"),
            SimpleNamespace(step_name="query_decomposer"),
            SimpleNamespace(step_name="retrieval_coordinator"),
            SimpleNamespace(step_name="validator"),
            SimpleNamespace(step_name="writer"),
            SimpleNamespace(step_name="critic"),
            SimpleNamespace(step_name="finalize"),
        ],
    )
    snapshot = extract_result_snapshot(result)
    components = [item.component for item in snapshot.steps]
    assert components == [
        "router",
        "planner",
        "planner",
        "retrieval",
        "validation",
        "writer",
        "validation",
        "finalize",
    ]



def test_result_snapshot_promotes_nested_finalize_answer():
    result = SimpleNamespace(
        answer="",
        status="completed",
        executed_route="graph",
        steps=[
            SimpleNamespace(
                step_name="finalize",
                status="completed",
                output_json={
                    "final_answer": "李明研究知识图谱[1]",
                },
            )
        ],
    )

    snapshot = extract_result_snapshot(result)

    assert snapshot.answer == "李明研究知识图谱[1]"
    assert snapshot.route == "graph"



def test_result_snapshot_extracts_dict_shaped_agent_evidence_and_graph():
    chunk_id = str(uuid4())

    result = SimpleNamespace(
        answer="李明研究知识图谱[1]",
        status="completed",
        executed_route="graph",
        steps=[
            {
                "step_name": "retrieval_coordinator",
                "status": "completed",
                "output_json": {
                    "evidence_hits": [
                        {
                            "chunk": {
                                "chunk_id": chunk_id,
                                "content": "李明教授研究知识图谱。",
                            }
                        }
                    ],
                    "graph_paths": [
                        {
                            "relation_type": "RESEARCHES",
                            "source_name": "李明",
                            "target_name": "知识图谱",
                            "path_text": (
                                "李明 -[RESEARCHES]-> 知识图谱"
                            ),
                        }
                    ],
                },
            }
        ],
    )

    snapshot = extract_result_snapshot(result)

    assert chunk_id in snapshot.evidence_ids
    assert "李明教授研究知识图谱。" in snapshot.evidence_texts
    assert "RESEARCHES" in snapshot.graph_path_tokens
    assert "李明" in snapshot.graph_path_tokens
    assert "知识图谱" in snapshot.graph_path_tokens



def test_result_snapshot_traverses_agent_retrieval_result():
    chunk_id = str(uuid4())

    retrieval_result = SimpleNamespace(
        answer="李明研究知识图谱[1]",
        evidence_hits=[
            SimpleNamespace(
                chunk=SimpleNamespace(
                    chunk_id=chunk_id,
                    content="李明教授研究知识图谱。",
                ),
                score=0.95,
                sources=("graph",),
                graph_path_ids=("path-1",),
            )
        ],
        graph_paths=[
            SimpleNamespace(
                relation_type="RESEARCHES",
                source_name="李明",
                target_name="知识图谱",
                path_text="李明 -[RESEARCHES]-> 知识图谱",
            )
        ],
    )

    result = SimpleNamespace(
        final_answer="李明研究知识图谱[1]",
        status="completed",
        active_decision=SimpleNamespace(
            route="graph",
        ),
        retrieval_result=retrieval_result,
        steps=[],
        retry_count=0,
    )

    snapshot = extract_result_snapshot(result)

    assert snapshot.answer == "李明研究知识图谱[1]"
    assert chunk_id in snapshot.evidence_ids
    assert "李明教授研究知识图谱。" in snapshot.evidence_texts

    assert "RESEARCHES" in snapshot.graph_path_tokens
    assert "李明" in snapshot.graph_path_tokens
    assert "知识图谱" in snapshot.graph_path_tokens
