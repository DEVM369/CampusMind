from __future__ import annotations

import re
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from campusmind.agent.runtime import AgentRuntimeService
from campusmind.platform.db import (
    AgentRun,
    EvaluationCase,
    EvaluationDataset,
    EvaluationResult,
    get_db,
)
from campusmind.platform.security import (
    AuthorizationDenied,
    AuthorizationService,
)


router = APIRouter()


def get_authorization_service(
    db: Session = Depends(get_db),
) -> AuthorizationService:
    return AuthorizationService(db)


def _authorize(
    authorization: AuthorizationService,
    actor_user_id: uuid.UUID,
) -> None:
    for capability in (
        "admin.dashboard.read",
        "evaluation.run",
    ):
        try:
            authorization.require(
                capability,
                actor_user_id,
            )
        except AuthorizationDenied as exc:
            raise HTTPException(
                status_code=403,
                detail=str(exc),
            ) from exc


def _normalise_text(
    value: str | None,
) -> str:
    text = str(value or "").lower()

    text = re.sub(
        r"[\s\u3000]+",
        "",
        text,
    )

    text = re.sub(
        r"""[
            \u3002
            \uff0c
            \uff01
            \uff1f
            \uff1a
            \uff1b
            ,
            .
            !
            ?
            :
            ;
            "
            '
            \(
            \)
            \[
            \]
            \{
            \}
        ]""",
        "",
        text,
        flags=re.VERBOSE,
    )

    replacements = (
        "\u6559\u6388",
        "\u8001\u5e08",
        "\u8bfe\u7a0b",
        "\u5b66\u5206",
    )

    for token in replacements:
        text = text.replace(
            token,
            "",
        )

    return text


def _expected_terms(
    expected: str | None,
) -> list[str]:
    value = str(expected or "").strip()

    if not value:
        return []

    parts = re.split(
        r"[\u3001,\uff0c;\uff1b/]+",
        value,
    )

    result = []

    for part in parts:
        normalised = _normalise_text(
            part
        )

        if normalised:
            result.append(
                normalised
            )

    return result


def _score_answer(
    expected: str | None,
    actual: str | None,
    *,
    fallback_score: float,
    fallback_passed: bool,
    expected_evidence: dict[str, Any] | None = None,
    observed: dict[str, Any] | None = None,
) -> tuple[float, bool, dict[str, Any]]:
    terms = _expected_terms(
        expected
    )

    actual_normalised = _normalise_text(
        actual
    )

    requirements = dict(
        expected_evidence
        or {}
    )

    observed_values = dict(
        observed
        or {}
    )

    if terms:
        matched = [
            term
            for term in terms
            if term in actual_normalised
        ]

        term_score = (
            len(matched)
            / len(terms)
        )

        term_passed = (
            len(matched)
            == len(terms)
        )

    else:
        matched = []
        term_score = float(
            fallback_score
        )
        term_passed = bool(
            fallback_passed
        )

    requirement_scores: list[float] = []
    requirement_checks: dict[str, Any] = {}

    required_relations = [
        str(item)
        for item in (
            requirements.get(
                "required_relation_types"
            )
            or []
        )
    ]

    observed_relations = {
        str(item)
        for item in (
            observed_values.get(
                "relation_types"
            )
            or []
        )
    }

    if required_relations:
        matched_relations = [
            item
            for item in required_relations
            if item in observed_relations
        ]

        relation_score = (
            len(matched_relations)
            / len(required_relations)
        )

        requirement_scores.append(
            relation_score
        )

        requirement_checks[
            "required_relation_types"
        ] = {
            "required": required_relations,
            "observed": sorted(
                observed_relations
            ),
            "matched": matched_relations,
            "missing": [
                item
                for item in required_relations
                if item
                not in observed_relations
            ],
            "score": round(
                relation_score,
                4,
            ),
        }

    min_graph_paths = requirements.get(
        "min_graph_paths"
    )

    if min_graph_paths is not None:
        required_count = int(
            min_graph_paths
        )

        actual_count = int(
            observed_values.get(
                "graph_path_count"
            )
            or 0
        )

        graph_score = (
            1.0
            if actual_count
            >= required_count
            else (
                actual_count
                / required_count
                if required_count > 0
                else 1.0
            )
        )

        requirement_scores.append(
            graph_score
        )

        requirement_checks[
            "min_graph_paths"
        ] = {
            "required": required_count,
            "observed": actual_count,
            "score": round(
                graph_score,
                4,
            ),
        }

    min_citations = requirements.get(
        "min_citations"
    )

    if min_citations is not None:
        required_count = int(
            min_citations
        )

        actual_count = int(
            observed_values.get(
                "citation_count"
            )
            or 0
        )

        citation_score = (
            1.0
            if actual_count
            >= required_count
            else (
                actual_count
                / required_count
                if required_count > 0
                else 1.0
            )
        )

        requirement_scores.append(
            citation_score
        )

        requirement_checks[
            "min_citations"
        ] = {
            "required": required_count,
            "observed": actual_count,
            "score": round(
                citation_score,
                4,
            ),
        }

    required_route = requirements.get(
        "required_route"
    )

    if required_route:
        expected_route = str(
            required_route
        ).lower()

        executed_route = str(
            observed_values.get(
                "executed_route"
            )
            or ""
        ).lower()

        active_route = str(
            observed_values.get(
                "active_route"
            )
            or ""
        ).lower()

        route_ok = (
            executed_route
            == expected_route
            or active_route
            == expected_route
        )

        route_score = (
            1.0
            if route_ok
            else 0.0
        )

        requirement_scores.append(
            route_score
        )

        requirement_checks[
            "required_route"
        ] = {
            "required": expected_route,
            "executed": executed_route,
            "active": active_route,
            "score": route_score,
        }

    overall_score = term_score

    if requirement_scores:
        overall_score = min(
            [
                term_score,
                *requirement_scores,
            ]
        )

    requirements_passed = all(
        value >= 1.0
        for value
        in requirement_scores
    )

    passed = (
        term_passed
        and requirements_passed
    )

    return (
        round(
            overall_score,
            4,
        ),
        passed,
        {
            "scorer": (
                "deterministic_term_and_evidence_v2"
            ),
            "expected_terms": terms,
            "matched_terms": matched,
            "term_coverage": round(
                term_score,
                4,
            ),
            "evidence_requirements": (
                requirements
            ),
            "evidence_checks": (
                requirement_checks
            ),
            "evidence_requirements_passed": (
                requirements_passed
            ),
        },
    )

def _upsert_result(
    db: Session,
    *,
    dataset_id: uuid.UUID,
    case_id: uuid.UUID,
    agent_run_id: uuid.UUID | None,
    score: float,
    passed: bool,
    metrics: dict[str, Any],
) -> EvaluationResult:
    existing = db.scalar(
        select(EvaluationResult)
        .where(
            EvaluationResult.dataset_id
            == dataset_id,
            EvaluationResult.case_id
            == case_id,
        )
        .order_by(
            EvaluationResult.created_at.desc()
        )
        .limit(1)
    )

    if existing is None:
        existing = EvaluationResult(
            dataset_id=dataset_id,
            case_id=case_id,
            agent_run_id=agent_run_id,
            score=score,
            passed=passed,
            metrics_json=metrics,
        )

        db.add(existing)

    else:
        existing.agent_run_id = (
            agent_run_id
        )
        existing.score = score
        existing.passed = passed
        existing.metrics_json = metrics

    db.commit()
    db.refresh(existing)

    return existing


@router.post(
    "/evaluations/{dataset_id}/run"
)
def run_evaluation(
    dataset_id: uuid.UUID,
    actor_user_id: uuid.UUID,
    db: Session = Depends(get_db),
    authorization: AuthorizationService = Depends(
        get_authorization_service
    ),
) -> dict:
    _authorize(
        authorization,
        actor_user_id,
    )

    dataset = db.get(
        EvaluationDataset,
        dataset_id,
    )

    if dataset is None:
        raise HTTPException(
            status_code=404,
            detail="Evaluation dataset not found",
        )

    if str(dataset.status).lower() != "active":
        raise HTTPException(
            status_code=409,
            detail=(
                "Only active evaluation "
                "datasets may be run"
            ),
        )

    cases = list(
        db.scalars(
            select(EvaluationCase)
            .where(
                EvaluationCase.dataset_id
                == dataset_id
            )
            .order_by(
                EvaluationCase.category.asc(),
                EvaluationCase.id.asc(),
            )
        ).all()
    )

    if not cases:
        raise HTTPException(
            status_code=409,
            detail=(
                "Evaluation dataset "
                "contains no cases"
            ),
        )

    supported_categories = {
        "Graph",
        "Multi-hop",
        "Policy",
        "SQL",
    }

    unsupported_categories = sorted(
        {
            str(case.category)
            for case in cases
            if str(case.category)
            not in supported_categories
        }
    )

    if unsupported_categories:
        raise HTTPException(
            status_code=409,
            detail=(
                "Smoke runner currently "
                "supports read-only categories "
                "only: "
                + ", ".join(
                    sorted(
                        supported_categories
                    )
                )
            ),
        )

    for case in cases:
        override = (case.metadata_json or {}).get("evaluation_actor_user_id")
        if override:
            try:
                case_actor = uuid.UUID(str(override))
            except (ValueError, TypeError, AttributeError):
                raise HTTPException(status_code=409, detail="Invalid evaluation actor") from None
            if case_actor != actor_user_id:
                raise HTTPException(
                    status_code=403,
                    detail="Evaluation actor must match the authenticated session",
                )

    service = AgentRuntimeService(
        db
    )

    results = []

    try:
        for index, case in enumerate(
            cases,
            1,
        ):
            execution_actor_user_id = (
                actor_user_id
            )

            metadata = dict(
                case.metadata_json
                or {}
            )

            actor_override = (
                metadata.get(
                    "evaluation_actor_user_id"
                )
            )

            if actor_override:
                if (
                    metadata.get(
                        "synthetic"
                    )
                    is not True
                ):
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            "Evaluation actor override "
                            "is allowed only for "
                            "synthetic benchmark cases"
                        ),
                    )

                execution_actor_user_id = (
                    uuid.UUID(
                        str(
                            actor_override
                        )
                    )
                )

            try:
                runtime = service.answer(
                    case.question,
                    top_k=6,
                    max_paths=12,
                    max_retries=1,
                    max_answer_rewrites=1,
                    persist_trace=True,
                    actor_user_id=(
                        execution_actor_user_id
                    ),
                )

                trace_uuid = None

                if runtime.trace_persisted:
                    candidate = uuid.UUID(
                        runtime.trace_id
                    )

                    db.expire_all()

                    if db.get(
                        AgentRun,
                        candidate,
                    ) is not None:
                        trace_uuid = candidate

                relation_types = sorted(
                    {
                        (
                            item.relation_type.value
                            if hasattr(
                                item.relation_type,
                                "value",
                            )
                            else str(
                                item.relation_type
                            )
                        )
                        for item in (
                            runtime.retrieval_result
                            .graph_paths
                        )
                    }
                )

                executed_route = (
                    runtime.retrieval_result
                    .executed_route.value
                    if runtime.retrieval_result
                    .executed_route
                    else None
                )

                observed = {
                    "relation_types": (
                        relation_types
                    ),
                    "graph_path_count": len(
                        runtime.retrieval_result
                        .graph_paths
                    ),
                    "citation_count": len(
                        runtime.retrieval_result
                        .evidence_hits
                    ),
                    "executed_route": (
                        executed_route
                    ),
                    "active_route": (
                        runtime.active_decision
                        .route.value
                    ),
                }

                score, passed, scorer = (
                    _score_answer(
                        case.expected_answer,
                        runtime.final_answer,
                        fallback_score=(
                            runtime.validation.score
                        ),
                        fallback_passed=(
                            runtime.validation.passed
                        ),
                        expected_evidence=(
                            case.expected_evidence
                            or {}
                        ),
                        observed=observed,
                    )
                )

                metrics = {
                    **scorer,
                    "benchmark_type": (
                        "smoke"
                    ),
                    "case_category": (
                        case.category
                    ),
                    "question": (
                        case.question
                    ),
                    "expected_answer": (
                        case.expected_answer
                    ),
                    "actual_answer": (
                        runtime.final_answer
                    ),
                    "runtime_status": (
                        runtime.status
                    ),
                    "pending_approval": (
                        runtime.pending_approval
                    ),
                    "planned_route": (
                        runtime.planned_decision
                        .route.value
                    ),
                    "active_route": (
                        runtime.active_decision
                        .route.value
                    ),
                    "executed_route": (
                        runtime.retrieval_result
                        .executed_route.value
                        if runtime
                        .retrieval_result
                        .executed_route
                        else None
                    ),
                    "validation_passed": (
                        runtime.validation.passed
                    ),
                    "validation_score": (
                        runtime.validation.score
                    ),
                    "validation_reasons": list(
                        runtime.validation.reasons
                    ),
                    "critic_passed": (
                        runtime.critic.passed
                    ),
                    "critic_score": (
                        runtime.critic.score
                    ),
                    "critic_checks": list(
                        runtime.critic.checks
                    ),
                    "citation_count": len(
                        runtime.retrieval_result
                        .evidence_hits
                    ),
                    "graph_path_count": len(
                        runtime.retrieval_result
                        .graph_paths
                    ),
                    "elapsed_ms": (
                        runtime.elapsed_ms
                    ),
                    "trace_id": (
                        runtime.trace_id
                    ),
                    "trace_persisted": (
                        runtime.trace_persisted
                    ),
                    "trace_persist_error": (
                        runtime.trace_persist_error
                    ),
                    "evaluation_requested_by_user_id": str(
                        actor_user_id
                    ),
                    "execution_actor_user_id": str(
                        execution_actor_user_id
                    ),
                }

                row = _upsert_result(
                    db,
                    dataset_id=dataset.id,
                    case_id=case.id,
                    agent_run_id=trace_uuid,
                    score=score,
                    passed=passed,
                    metrics=metrics,
                )

                results.append(
                    {
                        "index": index,
                        "result_id": str(
                            row.id
                        ),
                        "case_id": str(
                            case.id
                        ),
                        "category": (
                            case.category
                        ),
                        "question": (
                            case.question
                        ),
                        "expected_answer": (
                            case.expected_answer
                        ),
                        "actual_answer": (
                            runtime.final_answer
                        ),
                        "score": score,
                        "passed": passed,
                        "trace_id": (
                            runtime.trace_id
                        ),
                        "runtime_status": (
                            runtime.status
                        ),
                        "elapsed_ms": (
                            runtime.elapsed_ms
                        ),
                    }
                )

            except Exception as exc:
                db.rollback()

                metrics = {
                    "scorer": (
                        "runner_exception_v1"
                    ),
                    "benchmark_type": (
                        "smoke"
                    ),
                    "case_category": (
                        case.category
                    ),
                    "question": (
                        case.question
                    ),
                    "expected_answer": (
                        case.expected_answer
                    ),
                    "runner_error": (
                        f"{type(exc).__name__}: "
                        f"{exc}"
                    ),
                    "evaluation_requested_by_user_id": str(
                        actor_user_id
                    ),
                    "execution_actor_user_id": str(
                        execution_actor_user_id
                    ),
                }

                row = _upsert_result(
                    db,
                    dataset_id=dataset.id,
                    case_id=case.id,
                    agent_run_id=None,
                    score=0.0,
                    passed=False,
                    metrics=metrics,
                )

                results.append(
                    {
                        "index": index,
                        "result_id": str(
                            row.id
                        ),
                        "case_id": str(
                            case.id
                        ),
                        "category": (
                            case.category
                        ),
                        "question": (
                            case.question
                        ),
                        "expected_answer": (
                            case.expected_answer
                        ),
                        "actual_answer": None,
                        "score": 0.0,
                        "passed": False,
                        "trace_id": None,
                        "runtime_status": (
                            "runner_error"
                        ),
                        "elapsed_ms": None,
                        "error": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    }
                )

    finally:
        service.close()

    passed_count = sum(
        1
        for item in results
        if item["passed"]
    )

    failed_count = (
        len(results)
        - passed_count
    )

    pass_rate = (
        passed_count
        / len(results)
        if results
        else 0.0
    )

    average_score = (
        sum(
            float(
                item["score"]
            )
            for item in results
        )
        / len(results)
        if results
        else 0.0
    )

    return {
        "dataset_id": str(
            dataset.id
        ),
        "dataset_name": (
            dataset.name
        ),
        "dataset_version": (
            dataset.version
        ),
        "benchmark_type": "smoke",
        "scorer": (
            "deterministic_term_and_evidence_v2"
        ),
        "case_count": len(
            results
        ),
        "passed_count": (
            passed_count
        ),
        "failed_count": (
            failed_count
        ),
        "pass_rate": round(
            pass_rate,
            4,
        ),
        "average_score": round(
            average_score,
            4,
        ),
        "results": results,
    }
