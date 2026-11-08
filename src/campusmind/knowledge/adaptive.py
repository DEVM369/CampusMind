from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field
from campusmind.knowledge.graph_rag import GraphEdge
from campusmind.knowledge.rag import RetrievalResult
from campusmind.knowledge.rag import RetrievedChunk
import json
import re
from typing import Any
import time
import uuid
from sqlalchemy.orm import Session
from campusmind.knowledge.rag import BasicRagService
from campusmind.platform.security import AuthorizationService
from campusmind.platform.security import KnowledgeAclService

"""CampusMind adaptive domain."""

# ---- app/adaptive_rag/types.py ----
class RetrievalRoute(str, Enum):
    RAG = "rag"
    GRAPH = "graph"
    HYBRID = "hybrid"
    SQL = "sql"
    TOOL = "tool"


RouteComplexity = Literal[
    "simple",
    "relational",
    "multi_hop",
    "mixed",
    "structured",
    "action",
]

RouteSource = Literal["rules", "llm", "fallback"]


class RouteDecision(BaseModel):
    route: RetrievalRoute
    intent: str = Field(min_length=1, max_length=120)
    complexity: RouteComplexity
    confidence: float = Field(ge=0.0, le=1.0)
    reasons: list[str] = Field(default_factory=list, max_length=6)
    executable: bool = True
    requires_agent: bool = False
    source: RouteSource = "rules"


@dataclass(slots=True)
class AdaptiveEvidence:
    chunk: RetrievedChunk
    sources: tuple[str, ...]
    score: float
    graph_path_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class AdaptiveRagResult:
    trace_id: str
    query: str
    answer: str
    decision: RouteDecision
    executed_route: RetrievalRoute | None
    evidence_hits: list[AdaptiveEvidence]
    graph_paths: list[GraphEdge]
    text_retrieval: RetrievalResult | None
    elapsed_ms: float
    fallback_reason: str | None = None
    deferred_capability: str | None = None
    structured_data: dict | None = None

# ---- app/adaptive_rag/analyzer.py ----
_ACTION_RE = re.compile(
    r"(?:帮我|替我|给我|请帮我|我要)"
    r".{0,12}"
    r"(?:预约|借阅|借书|报名|提交|取消|修改|删除|办理|选课|退课|申请)"
)

_SQL_RE = re.compile(
    r"(?:我(?:有|已经|还差|修了|的)|我的)"
    r".{0,12}"
    r"(?:学分|成绩|课程|课表|借阅|预约|申请|毕业进度)"
    r"|(?:库存|还有几本|剩余几本|空闲教室|当前余额|当前状态)"
)

_MULTI_HOP_PATTERNS = (
    "研究知识图谱的老师教授",
    "研究大语言模型的老师教授",
    "研究强化学习的老师教授",
    "同时研究",
    "同时教授",
    "两跳",
    "多跳",
    "上游",
    "下游",
    "路径",
    "连接起来",
    "再到",
    "然后再",
)

_GRAPH_PATTERNS = (
    "PREREQUISITE_OF",
    "哪些老师",
    "哪些教师",
    "谁研究",
    "谁教授",
    "谁讲授",
    "属于哪个学院",
    "属于哪个专业",
    "哪些课程需要",
    "什么关系",
    "有什么关系",
    "前置",
    "先修",
    "研究哪些方向",
)

_TEXT_PATTERNS = (
    "多少学分",
    "最低学分",
    "几点关门",
    "几点开放",
    "借期",
    "可以借几册",
    "主要介绍",
    "主要内容",
    "具体内容",
    "申请条件",
    "什么条件",
    "什么时候",
    "开放时间",
    "办理流程",
    "怎么申请",
    "如何申请",
    "规定",
    "政策",
    "要求是什么",
    "简介",
)

_PROFILE_HYBRID_RE = re.compile(
    r"(?:老师|教师|教授).{0,10}(?:研究什么|研究方向|科研方向|简介)"
)


def _question_count(query: str) -> int:
    return query.count("？") + query.count("?")


def _contains_any(query: str, values: tuple[str, ...]) -> bool:
    return any(value in query for value in values)


# explicit_cross_source_hybrid_v125
def _is_explicit_cross_source_query(query: str) -> bool:
    """
    True when the user explicitly asks for BOTH:
    1. graph/relationship reasoning, and
    2. document / knowledge-base evidence.
    """

    graph_signal = (
        _contains_any(query, _MULTI_HOP_PATTERNS)
        or _contains_any(query, _GRAPH_PATTERNS)
    )

    document_signal = any(
        token in query
        for token in (
            "\u77e5\u8bc6\u5e93",
            "\u77e5\u8bc6\u5e93\u8d44\u6599",
            "\u77e5\u8bc6\u5e93\u4f9d\u636e",
            "\u5b66\u4e60\u8d44\u6599",
            "\u76f8\u5173\u8d44\u6599",
            "\u8d44\u6599\u63a8\u8350",
            "\u63a8\u8350\u8d44\u6599",
            "\u8bba\u6587",
            "\u56fe\u4e66",
            "\u6587\u732e",
        )
    )

    return graph_signal and document_signal


class RuleBasedRouteAnalyzer:
    """Fast deterministic router for high-confidence campus query patterns."""

    def analyze(self, query: str) -> RouteDecision:
        text = query.strip()
        if not text:
            raise ValueError("query must not be blank")

        if _ACTION_RE.search(text):
            return RouteDecision(
                route=RetrievalRoute.TOOL,
                intent="campus_action",
                complexity="action",
                confidence=0.99,
                reasons=["query asks the system to perform a campus business action"],
                executable=False,
                requires_agent=True,
                source="rules",
            )

        if _SQL_RE.search(text):
            return RouteDecision(
                route=RetrievalRoute.SQL,
                intent="structured_personal_or_realtime_data",
                complexity="structured",
                confidence=0.97,
                reasons=["answer requires personal or real-time structured campus data"],
                executable=False,
                requires_agent=True,
                source="rules",
            )

        # cross_source_hybrid_priority_v125
        if _is_explicit_cross_source_query(text):
            return RouteDecision(
                route=RetrievalRoute.HYBRID,
                intent="graph_and_document_knowledge",
                complexity="mixed",
                confidence=0.99,
                reasons=[
                    "query explicitly requests relational graph reasoning",
                    "query explicitly requests knowledge-base/document evidence",
                ],
                executable=True,
                source="rules",
            )

        multi_hop = _contains_any(text, _MULTI_HOP_PATTERNS)
        graph_signal = multi_hop or _contains_any(text, _GRAPH_PATTERNS)
        text_signal = _contains_any(text, _TEXT_PATTERNS)
        profile_hybrid = bool(_PROFILE_HYBRID_RE.search(text))
        compound = _question_count(text) >= 2

        if profile_hybrid:
            return RouteDecision(
                route=RetrievalRoute.HYBRID,
                intent="entity_profile_with_supporting_text",
                complexity="mixed",
                confidence=0.94,
                reasons=[
                    "query asks about an entity relationship/profile",
                    "graph facts benefit from supporting document evidence",
                ],
                executable=True,
                source="rules",
            )

        if graph_signal and (text_signal or compound):
            return RouteDecision(
                route=RetrievalRoute.HYBRID,
                intent="graph_and_document_knowledge",
                complexity="mixed",
                confidence=0.96,
                reasons=[
                    "query contains relational graph intent",
                    "query also asks for descriptive/document content",
                ],
                executable=True,
                source="rules",
            )

        if multi_hop:
            return RouteDecision(
                route=RetrievalRoute.GRAPH,
                intent="multi_hop_relationship_query",
                complexity="multi_hop",
                confidence=0.97,
                reasons=["query requires traversing multiple campus relationships"],
                executable=True,
                source="rules",
            )

        if graph_signal:
            return RouteDecision(
                route=RetrievalRoute.GRAPH,
                intent="relationship_query",
                complexity="relational",
                confidence=0.93,
                reasons=["query is primarily about entities and their relationships"],
                executable=True,
                source="rules",
            )

        if text_signal:
            return RouteDecision(
                route=RetrievalRoute.RAG,
                intent="document_knowledge_query",
                complexity="simple",
                confidence=0.94,
                reasons=["query asks for policy, procedure, requirement, time, or document content"],
                executable=True,
                source="rules",
            )

        return RouteDecision(
            route=RetrievalRoute.RAG,
            intent="general_knowledge_query",
            complexity="simple",
            confidence=0.68,
            reasons=["no strong structured/action/graph signal detected"],
            executable=True,
            source="fallback",
        )


class AdaptiveRouteAnalyzer:
    """Rules first, DeepSeek only for ambiguous queries."""

    def __init__(self, llm=None, *, llm_threshold: float = 0.90) -> None:
        self.rules = RuleBasedRouteAnalyzer()
        self._llm = llm
        self.llm_threshold = llm_threshold

    @property
    def llm(self):
        if self._llm is None:
            from campusmind.config import main_llm

            self._llm = main_llm
        return self._llm

    @staticmethod
    def _extract_json(value: str) -> dict[str, Any]:
        text = value.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.I)
            text = re.sub(r"\s*```$", "", text)
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end < start:
            raise ValueError("router LLM did not return a JSON object")
        return json.loads(text[start : end + 1])

    def _llm_analyze(self, query: str) -> RouteDecision:
        prompt = f"""
You are the CampusMind retrieval router.
Choose exactly one route for the user query.

Allowed routes:
- rag: policy, notice, procedure, regulation, document facts, ordinary knowledge.
- graph: relationship or multi-hop entity questions where graph structure is primary.
- hybrid: graph relationships plus descriptive/supporting document text are both useful.
- sql: personal records or real-time structured values such as credits, grades, schedules, inventory.
- tool: the user asks CampusMind to perform an action such as booking, borrowing, submitting, modifying, or cancelling.

Important:
- Do not treat "how to apply" or "application conditions" as an action; those are rag.
- sql/tool are routing decisions only in the current phase and must not be simulated.
- Return JSON only.

Examples:
"国家奖学金什么时候申请？" -> rag
"哪些老师研究大语言模型？" -> graph
"张老师研究什么？" -> hybrid
"研究知识图谱的老师教授哪些课程？" -> graph
"研究强化学习的老师教授哪些课程？智能决策系统课程主要介绍什么？" -> hybrid
"我还差多少学分毕业？" -> sql
"帮我预约明天下午的自习室" -> tool

User query:
{query}

JSON schema:
{{
  "route": "rag|graph|hybrid|sql|tool",
  "intent": "short intent label",
  "complexity": "simple|relational|multi_hop|mixed|structured|action",
  "confidence": 0.0,
  "reasons": ["reason 1", "reason 2"]
}}
""".strip()
        response = self.llm.invoke(prompt)
        data = self._extract_json(str(response.content))
        route = RetrievalRoute(str(data["route"]).lower())
        return RouteDecision(
            route=route,
            intent=str(data.get("intent") or "adaptive_route"),
            complexity=str(data.get("complexity") or "simple"),
            confidence=float(data.get("confidence", 0.75)),
            reasons=[str(item) for item in data.get("reasons", [])][:6],
            executable=route in {
                RetrievalRoute.RAG,
                RetrievalRoute.GRAPH,
                RetrievalRoute.HYBRID,
            },
            requires_agent=route in {RetrievalRoute.SQL, RetrievalRoute.TOOL},
            source="llm",
        )

    def analyze(self, query: str) -> RouteDecision:
        rule_decision = self.rules.analyze(query)
        if rule_decision.confidence >= self.llm_threshold:
            return rule_decision

        try:
            return self._llm_analyze(query)
        except Exception:
            # Routing failure must not take ordinary knowledge QA offline.
            return rule_decision

# ---- app/adaptive_rag/router.py ----
"""Compatibility facade for the adaptive route analyzer.

The implementation lives in ``analyzer.py``. Keeping this module lets future
callers use the intuitive ``campusmind.knowledge.adaptive`` import path without
creating a second, divergent routing implementation.
"""



AdaptiveQueryRouter = AdaptiveRouteAnalyzer
AdaptiveRoute = RetrievalRoute
RoutingDecision = RouteDecision

__all__ = [
    "AdaptiveQueryRouter",
    "AdaptiveRouteAnalyzer",
    "RuleBasedRouteAnalyzer",
    "AdaptiveRoute",
    "RetrievalRoute",
    "RoutingDecision",
    "RouteDecision",
]

# ---- app/adaptive_rag/service.py ----
class AdaptiveRagService:
    """Route a query to the narrowest reliable retrieval strategy."""

    def __init__(
        self,
        session: Session,
        *,
        analyzer=None,
        rag_service=None,
        graph_service=None,
        hybrid_service=None,
        sql_service=None,
        tool_service=None,
        library_tool_service=None,
        course_tool_service=None,
        research_tool_service=None,
        authorization_service=None,
        knowledge_acl_service=None,
    ) -> None:
        self.session = session
        self.analyzer = analyzer or AdaptiveRouteAnalyzer()
        self.rag_service = rag_service or BasicRagService(session)
        self._graph_service = graph_service
        self._hybrid_service = hybrid_service
        self._sql_service = sql_service
        self._tool_service = tool_service
        self._library_tool_service = library_tool_service
        self._course_tool_service = course_tool_service
        self._research_tool_service = research_tool_service
        self.authorization = authorization_service or AuthorizationService(session)
        self.knowledge_acl = knowledge_acl_service or KnowledgeAclService(
            session, authorization=self.authorization
        )
        self._owns_graph_service = graph_service is None
        self._owns_hybrid_service = hybrid_service is None

    def _graph(self):
        if self._graph_service is None:
            from campusmind.knowledge.graph_rag import GraphRagService

            self._graph_service = GraphRagService(self.session)
        return self._graph_service

    def _hybrid(self):
        if self._hybrid_service is None:
            from campusmind.knowledge.hybrid import HybridGraphRagService

            self._hybrid_service = HybridGraphRagService(self.session)
        return self._hybrid_service

    def _sql(self):
        if self._sql_service is None:
            from campusmind.tools.student import StudentSqlToolService

            self._sql_service = StudentSqlToolService(self.session)
        return self._sql_service

    def _tool(self):
        if self._tool_service is None:
            from campusmind.tools.actions import ClassroomActionService

            self._tool_service = ClassroomActionService(self.session)
        return self._tool_service


    def _library_tool(self):
        if self._library_tool_service is None:
            from campusmind.tools.actions import LibraryActionService

            self._library_tool_service = LibraryActionService(self.session)
        return self._library_tool_service

    def _course_tool(self):
        if self._course_tool_service is None:
            from campusmind.tools.course import CourseToolService

            self._course_tool_service = CourseToolService(self.session)
        return self._course_tool_service

    def _research_tool(self):
        if self._research_tool_service is None:
            from campusmind.tools.research import ResearchToolService

            self._research_tool_service = ResearchToolService(self.session)
        return self._research_tool_service

    def _action_type(self, approval_id) -> str:
        from sqlalchemy import select
        from campusmind.tools.actions import ClassroomActionNotFound, action_requests

        approval = approval_id if isinstance(approval_id, uuid.UUID) else uuid.UUID(str(approval_id))
        action_type = self.session.scalar(
            select(action_requests.c.action_type).where(action_requests.c.id == approval)
        )
        if action_type is None:
            raise ClassroomActionNotFound(f"approval_id={approval} was not found")
        return str(action_type)

    def close(self) -> None:
        if self._graph_service is not None and self._owns_graph_service:
            self._graph_service.close()
        if self._hybrid_service is not None and self._owns_hybrid_service:
            self._hybrid_service.close()

    def route(self, query: str) -> RouteDecision:
        # explicit_approval_route_priority_v128
        # Explicit HITL approval/resume commands must beat SQL,
        # Graph, RAG and ordinary action routing.
        approval_command = re.search(
            r"\bapproval_id\s*=\s*"
            r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
            r"[0-9a-fA-F]{12}\b",
            query,
            re.IGNORECASE,
        )

        # explicit_approval_intent_split_v131
        # Keep execution semantics unchanged, but expose the
        # actual HITL control intent for UI / logs / traces.
        confirm_approval_markers = (
            "\u786e\u8ba4\u6267\u884c",
            "\u786e\u8ba4",
            "\u540c\u610f",
            "\u6279\u51c6",
        )

        cancel_approval_markers = (
            "\u53d6\u6d88\u5ba1\u6279",
            "\u53d6\u6d88",
        )

        reject_approval_markers = (
            "\u62d2\u7edd",
            "\u4e0d\u540c\u610f",
            "\u4e0d\u6279\u51c6",
            "\u9a73\u56de",
        )

        approval_intent = None
        approval_reason = None

        if approval_command:
            # Order matters: e.g. "\u4e0d\u540c\u610f"
            # contains "\u540c\u610f".
            if any(
                token in query
                for token in cancel_approval_markers
            ):
                approval_intent = "cancel_approval"
                approval_reason = (
                    "query explicitly cancels HITL approval"
                )

            elif any(
                token in query
                for token in reject_approval_markers
            ):
                approval_intent = "reject_approval"
                approval_reason = (
                    "query explicitly rejects HITL approval"
                )

            elif any(
                token in query
                for token in confirm_approval_markers
            ):
                approval_intent = "confirm_approval"
                approval_reason = (
                    "query explicitly confirms HITL action"
                )

        if approval_intent is not None:
            return RouteDecision(
                route=RetrievalRoute.TOOL,
                intent=approval_intent,
                complexity="simple",
                confidence=0.99,
                reasons=[
                    "explicit approval_id supplied",
                    approval_reason,
                ],
                executable=True,
                source="rules",
            )

        # bypass_tool_shortcut_for_cross_source_v125
        # Mixed graph + document requests must reach HYBRID.
        # A structured Course/Research Tool may still be useful
        # elsewhere, but it must not consume the whole mixed query.
        if _is_explicit_cross_source_query(query):
            return self.analyzer.analyze(query)

        # course tools: explicit structured course reads are routed to the Course Tool.
        # Keep this matcher deliberately narrow so relational questions such as
        # “研究知识图谱的老师教授哪些课程” remain on GraphRAG.
        from campusmind.tools.course import CourseToolService

        course_supported = CourseToolService.supports(query)
        if course_supported and self.session is not None:
            try:
                course_supported = self._course_tool().can_answer(query)
            except Exception:
                course_supported = False

        if course_supported:
            return RouteDecision(
                route=RetrievalRoute.TOOL,
                intent="course_lookup",
                complexity="structured",
                confidence=0.99,
                reasons=["explicit course catalog/schedule/prerequisite/teacher structured query"],
                executable=True,
                requires_agent=True,
                source="rules",
            )

        from campusmind.tools.research import ResearchToolService

        if ResearchToolService.supports(query):
            return RouteDecision(
                route=RetrievalRoute.TOOL,
                intent="research_lookup",
                complexity="structured",
                confidence=0.99,
                reasons=["explicit research teacher/paper/area/lab/project structured query"],
                executable=True,
                requires_agent=True,
                source="rules",
            )
        return self.analyzer.analyze(query)

    @staticmethod
    def _rag_result(
        query: str,
        decision: RouteDecision,
        result,
        elapsed_ms: float,
        *,
        fallback_reason=None,
    ):
        return AdaptiveRagResult(
            trace_id=result.trace_id,
            query=query,
            answer=result.answer,
            decision=decision,
            executed_route=RetrievalRoute.RAG,
            evidence_hits=[
                AdaptiveEvidence(
                    chunk=hit,
                    sources=("text",),
                    score=float(hit.final_score or 0.0),
                )
                for hit in result.evidence_hits
            ],
            graph_paths=[],
            text_retrieval=result.retrieval,
            elapsed_ms=elapsed_ms,
            fallback_reason=fallback_reason,
        )

    def _deferred(
        self,
        query: str,
        decision: RouteDecision,
        elapsed_ms: float,
    ) -> AdaptiveRagResult:
        if decision.route is RetrievalRoute.SQL:
            answer = (
                "该问题需要读取用户个人结构化校园数据。"
                "SQL Tool 已接入，但当前请求没有可信的 actor_user_id 身份上下文，"
                "因此不会查询或猜测任何学生个人数据。"
            )
            capability = "sql"
        else:
            answer = (
                "该请求属于校园业务操作。写操作必须绑定 actor_user_id 并经过 Human Approval；"
                "当前请求缺少可执行上下文或对应 Tool 尚未实现，因此不会自动执行。"
            )
            capability = "tool"

        return AdaptiveRagResult(
            trace_id=str(uuid.uuid4()),
            query=query,
            answer=answer,
            decision=decision,
            executed_route=None,
            evidence_hits=[],
            graph_paths=[],
            text_retrieval=None,
            elapsed_ms=elapsed_ms,
            deferred_capability=capability,
        )

    @staticmethod
    def _graph_has_verified_evidence(result) -> bool:
        search = getattr(result, "search", None)
        if search is None:
            return False
        return bool(getattr(search, "paths", None) and getattr(search, "evidence_hits", None))

    def _rag_fallback_after_graph_miss(
        self,
        query: str,
        decision: RouteDecision,
        *,
        top_k: int,
        started: float,
        reason: str,
    ) -> AdaptiveRagResult:
        rag = self.rag_service.answer(query, top_k=top_k)
        return self._rag_result(
            query,
            decision,
            rag,
            round((time.perf_counter() - started) * 1000, 3),
            fallback_reason=reason,
        )

    def answer_with_decision(
        self,
        query: str,
        decision: RouteDecision,
        *,
        top_k: int = 6,
        max_paths: int = 12,
        actor_user_id=None,
        trace_id=None,
    ) -> AdaptiveRagResult:
        """Execute an explicit routing decision for Agent validator retries."""
        started = time.perf_counter()

        if decision.route is RetrievalRoute.TOOL:
            # natural_language_approval_resume_v126
            # Natural-language confirmation with an explicit approval_id
            # resumes the existing HITL action instead of creating a new one.
            approval_match = re.search(
                r"\bapproval_id\s*=\s*"
                r"([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
                r"[0-9a-fA-F]{12})\b",
                query,
                re.IGNORECASE,
            )

            confirm_markers = (
                "\u786e\u8ba4\u6267\u884c",
                "\u786e\u8ba4",
                "\u540c\u610f",
                "\u6279\u51c6",
            )

            reject_markers = (
                "\u62d2\u7edd",
                "\u4e0d\u540c\u610f",
                "\u53d6\u6d88\u5ba1\u6279",
                "\u53d6\u6d88",
            )

            # typed_recent_approval_reference_v129
            inferred_approval_id = None

            recent_reference = (
                any(
                    token in query
                    for token in (
                        "\u521a\u624d",
                        "\u521a\u521a",
                        "\u4e0a\u4e00\u4e2a",
                    )
                )
                and (
                    any(
                        x in query
                        for x in confirm_markers
                    )
                    or any(
                        x in query
                        for x in reject_markers
                    )
                )
            )

            recent_library_reference = (
                recent_reference
                and any(
                    token in query
                    for token in (
                        "\u56fe\u4e66",
                        "\u56fe\u4e66\u9986",
                        "\u4e66\u7c4d",
                        "\u8fd9\u672c\u4e66",
                        "\u672c\u4e66",
                        "\u501f\u4e66",
                    )
                )
            )

            recent_classroom_reference = (
                recent_reference
                and any(
                    token in query
                    for token in (
                        "\u6559\u5ba4",
                        "\u81ea\u4e60\u5ba4",
                        "\u7814\u8ba8\u5ba4",
                        "\u573a\u5730",
                    )
                )
            )

            if (
                approval_match is None
                and recent_reference
                and not recent_library_reference
                and not recent_classroom_reference
            ):
                result = self._deferred(
                    query,
                    decision,
                    round(
                        (
                            time.perf_counter()
                            - started
                        )
                        * 1000,
                        3,
                    ),
                )
                result.answer = (
                    "\u8bf7\u660e\u786e\u8bf4\u660e"
                    "\u8981\u786e\u8ba4\u7684\u662f"
                    "\u6559\u5ba4\u9884\u7ea6\u8fd8\u662f"
                    "\u56fe\u4e66\u9884\u7ea6\uff0c"
                    "\u6216\u76f4\u63a5\u63d0\u4f9b"
                    " approval_id\u3002"
                )
                return result

            if (
                approval_match is None
                and (
                    recent_library_reference
                    or recent_classroom_reference
                )
            ):
                if actor_user_id is None:
                    result = self._deferred(
                        query,
                        decision,
                        round(
                            (
                                time.perf_counter()
                                - started
                            )
                            * 1000,
                            3,
                        ),
                    )
                    result.answer = (
                        "\u5f53\u524d\u6ca1\u6709"
                        "\u53ef\u7528\u7684\u7528\u6237"
                        "\u8eab\u4efd\uff0c\u65e0\u6cd5"
                        "\u786e\u8ba4\u9884\u7ea6\u3002"
                    )
                    return result

                if recent_library_reference:
                    pending_id = (
                        self._library_tool()
                        .repository
                        .latest_valid_pending_request_id(
                            actor_user_id
                        )
                    )
                    pending_name = (
                        "\u56fe\u4e66\u9884\u7ea6"
                    )
                else:
                    pending_id = (
                        self._tool()
                        .repository
                        .latest_valid_pending_request_id(
                            actor_user_id
                        )
                    )
                    pending_name = (
                        "\u6559\u5ba4\u9884\u7ea6"
                    )

                if pending_id is None:
                    result = self._deferred(
                        query,
                        decision,
                        round(
                            (
                                time.perf_counter()
                                - started
                            )
                            * 1000,
                            3,
                        ),
                    )
                    result.answer = (
                        "\u5f53\u524d\u6ca1\u6709"
                        "\u627e\u5230\u5c5e\u4e8e"
                        "\u4f60\u7684\u5f85\u786e\u8ba4"
                        + pending_name
                        + "\u3002"
                    )
                    return result

                inferred_approval_id = str(
                    pending_id
                )

            if (
                approval_match
                or inferred_approval_id
            ) and (
                any(x in query for x in confirm_markers)
                or any(x in query for x in reject_markers)
            ):
                if actor_user_id is None:
                    return self._deferred(
                        query,
                        decision,
                        round(
                            (time.perf_counter() - started) * 1000,
                            3,
                        ),
                    )

                approval_id = (
                    approval_match.group(1)
                    if approval_match
                    else inferred_approval_id
                )

                approved = not any(
                    x in query
                    for x in reject_markers
                )

                from campusmind.tools.actions import (
                    ClassroomActionError,
                )

                try:
                    resumed = self.resume_tool_action(
                        approval_id,
                        actor_user_id,
                        approved=approved,
                    )
                except ClassroomActionError as exc:
                    if self.session is not None:
                        self.session.rollback()

                    result = self._deferred(
                        query,
                        decision,
                        round(
                            (
                                time.perf_counter()
                                - started
                            )
                            * 1000,
                            3,
                        ),
                    )
                    result.answer = (
                        "\u672c\u6b21\u64cd\u4f5c"
                        "\u672a\u6267\u884c\uff1a"
                        + str(exc)
                    )
                    result.deferred_capability = (
                        "tool_action_conflict"
                    )
                    return result

                status = getattr(
                    resumed.status,
                    "value",
                    str(resumed.status),
                )

                return AdaptiveRagResult(
                    trace_id=(
                        str(resumed.trace_id)
                        if resumed.trace_id
                        else str(uuid.uuid4())
                    ),
                    query=query,
                    answer=resumed.answer,
                    decision=decision.model_copy(
                        update={"executable": True}
                    ),
                    executed_route=RetrievalRoute.TOOL,
                    evidence_hits=[],
                    graph_paths=[],
                    text_retrieval=None,
                    elapsed_ms=round(
                        (
                            time.perf_counter()
                            - started
                        )
                        * 1000,
                        3,
                    ),
                    structured_data={
                        "capability": resumed.capability,
                        "phase": status,
                        "approval_id": (
                            resumed.approval_id
                        ),
                        "reservation": (
                            resumed.reservation
                        ),
                        "state_changed": (
                            resumed.state_changed
                        ),
                        "idempotent": (
                            resumed.idempotent
                        ),
                        "audit": resumed.audit,
                    },
                )
            # Read-only Course Tools are safe to execute without Human Approval
            # and do not expose a student's private records.
            from campusmind.tools.course import CourseToolService

            if self._course_tool().can_answer(query):
                self.authorization.require("course.read", actor_user_id)
                course_result = self._course_tool().answer(query)
                return AdaptiveRagResult(
                    trace_id=str(uuid.uuid4()),
                    query=query,
                    answer=course_result.answer,
                    decision=decision.model_copy(update={"executable": True}),
                    executed_route=RetrievalRoute.TOOL,
                    evidence_hits=[],
                    graph_paths=[],
                    text_retrieval=None,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                    structured_data={
                        "capability": course_result.capability.value,
                        "source": course_result.source,
                        "read_only": course_result.read_only,
                        "data": course_result.data,
                    },
                )

            from campusmind.tools.research import ResearchToolService

            if ResearchToolService.supports(query):
                self.authorization.require("research.read", actor_user_id)
                research_result = self._research_tool().answer(query)
                return AdaptiveRagResult(
                    trace_id=str(uuid.uuid4()),
                    query=query,
                    answer=research_result.answer,
                    decision=decision.model_copy(update={"executable": True}),
                    executed_route=RetrievalRoute.TOOL,
                    evidence_hits=[],
                    graph_paths=[],
                    text_retrieval=None,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                    structured_data={
                        "capability": research_result.capability.value,
                        "source": research_result.source,
                        "read_only": research_result.read_only,
                        "data": research_result.data,
                    },
                )

            if actor_user_id is None:
                return self._deferred(
                    query,
                    decision,
                    round((time.perf_counter() - started) * 1000, 3),
                )

            classroom_tool = self._tool()
            library_tool = self._library_tool()
            selected_tool = None
            if classroom_tool.supports(query):
                selected_tool = classroom_tool
            elif library_tool.supports(query):
                selected_tool = library_tool

            if selected_tool is None:
                result = self._deferred(
                    query,
                    decision,
                    round((time.perf_counter() - started) * 1000, 3),
                )
                result.answer = (
                    "该请求已经进入 Campus Tool 路由，但当前只实现教室预约和图书预约。"
                    "其他写操作仍然安全 deferred，不会伪装执行。"
                )
                return result

            capability = (
                "classroom.reserve" if selected_tool is classroom_tool else "library.reserve"
            )
            self.authorization.require(capability, actor_user_id)
            prepared = selected_tool.prepare_reservation(
                query,
                actor_user_id,
                trace_id=trace_id,
            )
            return AdaptiveRagResult(
                trace_id=str(uuid.uuid4()),
                query=query,
                answer=prepared.answer,
                decision=decision.model_copy(update={"executable": True}),
                executed_route=None,
                evidence_hits=[],
                graph_paths=[],
                text_retrieval=None,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                deferred_capability="tool_approval",
                structured_data={
                    "capability": prepared.capability,
                    "phase": prepared.status.value,
                    "approval_id": prepared.approval_id,
                    "trace_id": prepared.trace_id,
                    "requested": prepared.requested.model_dump(mode="json"),
                    "candidates": [item.model_dump(mode="json") for item in prepared.candidates],
                    "expires_at": prepared.expires_at,
                    "audit": prepared.audit,
                },
            )

        if decision.route is RetrievalRoute.SQL:
            if actor_user_id is None:
                return self._deferred(
                    query,
                    decision,
                    round((time.perf_counter() - started) * 1000, 3),
                )
            self.authorization.require("student.self.read", actor_user_id)
            sql_result = self._sql().answer(query, actor_user_id)
            return AdaptiveRagResult(
                trace_id=str(uuid.uuid4()),
                query=query,
                answer=sql_result.answer,
                decision=decision.model_copy(update={"executable": True}),
                executed_route=RetrievalRoute.SQL,
                evidence_hits=[],
                graph_paths=[],
                text_retrieval=None,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                structured_data={
                    "capability": sql_result.capability.value,
                    "source": sql_result.source,
                    "self_only": sql_result.self_only,
                    "data": sql_result.data,
                },
            )

        try:
            # document security layer: bind document ACL to PostgreSQL *before* any Vector,
            # Keyword, Graph evidence or Hybrid retrieval SQL is executed.
            # session=None is retained only for isolated historical fake tests.
            if decision.route in {
                RetrievalRoute.RAG,
                RetrievalRoute.GRAPH,
                RetrievalRoute.HYBRID,
            } and self.session is not None:
                self.knowledge_acl.apply_to_session(actor_user_id)

            if decision.route is RetrievalRoute.RAG:
                result = self.rag_service.answer(query, top_k=top_k)
                return self._rag_result(
                    query,
                    decision,
                    result,
                    round((time.perf_counter() - started) * 1000, 3),
                )

            if decision.route is RetrievalRoute.GRAPH:
                result = self._graph().answer(query, max_paths=max_paths)
                if not self._graph_has_verified_evidence(result):
                    rag = self.rag_service.answer(query, top_k=top_k)
                    if getattr(rag, "evidence_hits", None):
                        return self._rag_result(
                            query,
                            decision,
                            rag,
                            round((time.perf_counter() - started) * 1000, 3),
                            fallback_reason=(
                                "GraphRAG returned no source-verified path; "
                                "document RAG supplied verified fallback evidence."
                            ),
                        )

                    raw_path_count = int(getattr(result.search, "raw_path_count", 0) or 0)
                    diagnostics = list(getattr(result.search, "diagnostics", ()) or ())
                    if actor_user_id is None and raw_path_count > 0:
                        return AdaptiveRagResult(
                            trace_id=result.trace_id,
                            query=query,
                            answer=(
                                "知识图谱已经命中关系候选，但当前会话未设置用户 ID；"
                                "匿名知识权限仅允许 public 来源，候选关系的来源证据未能在当前权限下通过验证。"
                                "请在右上角设置已授权用户 ID 后重试。"
                            ),
                            decision=decision,
                            executed_route=RetrievalRoute.GRAPH,
                            evidence_hits=[],
                            graph_paths=[],
                            text_retrieval=getattr(rag, "retrieval", None),
                            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                            fallback_reason=(
                                "graph candidates exist but source evidence is not visible "
                                "under anonymous/public ACL"
                            ),
                            structured_data={
                                "raw_graph_path_count": raw_path_count,
                                "graph_diagnostics": diagnostics,
                                "access_scope": "public",
                                "requires_actor_for_campus_evidence": True,
                            },
                        )

                    return self._rag_result(
                        query,
                        decision,
                        rag,
                        round((time.perf_counter() - started) * 1000, 3),
                        fallback_reason=(
                            "GraphRAG and document RAG returned no source-verified evidence."
                        ),
                    )
                return AdaptiveRagResult(
                    trace_id=result.trace_id,
                    query=query,
                    answer=result.answer,
                    decision=decision,
                    executed_route=RetrievalRoute.GRAPH,
                    evidence_hits=[
                        AdaptiveEvidence(
                            chunk=hit,
                            sources=("graph",),
                            score=1.0,
                        )
                        for hit in result.search.evidence_hits
                    ],
                    graph_paths=list(result.search.paths),
                    text_retrieval=None,
                    elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
                )

            result = self._hybrid().answer(
                query,
                top_k=top_k,
                max_paths=max_paths,
            )
            paths = (
                result.search.graph_search.paths
                if result.search.graph_search is not None
                else []
            )
            return AdaptiveRagResult(
                trace_id=result.trace_id,
                query=query,
                answer=result.answer,
                decision=decision,
                executed_route=RetrievalRoute.HYBRID,
                evidence_hits=[
                    AdaptiveEvidence(
                        chunk=item.chunk,
                        sources=tuple(item.sources),
                        score=float(item.fusion_score),
                        graph_path_ids=tuple(item.graph_path_ids),
                    )
                    for item in result.evidence_hits
                ],
                graph_paths=list(paths),
                text_retrieval=result.search.text_retrieval,
                elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            )
        except Exception as exc:
            if decision.route in {RetrievalRoute.GRAPH, RetrievalRoute.HYBRID}:
                rag = self.rag_service.answer(query, top_k=top_k)
                return self._rag_result(
                    query,
                    decision,
                    rag,
                    round((time.perf_counter() - started) * 1000, 3),
                    fallback_reason=f"{type(exc).__name__}: {exc}",
                )
            raise

    def answer(
        self,
        query: str,
        *,
        top_k: int = 6,
        max_paths: int = 12,
        actor_user_id=None,
        trace_id=None,
    ) -> AdaptiveRagResult:
        return self.answer_with_decision(
            query,
            self.route(query),
            top_k=top_k,
            max_paths=max_paths,
            actor_user_id=actor_user_id,
            trace_id=trace_id,
        )

    def resume_tool_action(
        self,
        approval_id,
        actor_user_id,
        *,
        approved: bool,
        room_id: str | None = None,
        book_id: str | None = None,
        resource_id: str | None = None,
    ):
        action_type = self._action_type(approval_id)
        if action_type == "reserve_classroom":
            self.authorization.require("classroom.reserve", actor_user_id)
            return self._tool().resume_reservation(
                approval_id,
                actor_user_id,
                approved=approved,
                room_id=room_id or resource_id,
            )
        if action_type == "reserve_library_book":
            self.authorization.require("library.reserve", actor_user_id)
            return self._library_tool().resume_reservation(
                approval_id,
                actor_user_id,
                approved=approved,
                book_id=book_id or resource_id,
            )
        from campusmind.tools.actions import ClassroomActionConflict

        raise ClassroomActionConflict(f"unsupported action_type={action_type}")

    def retry_tool_prepare_audit(self, approval_id, actor_user_id, *, trace_id):
        action_type = self._action_type(approval_id)
        if action_type == "reserve_classroom":
            self.authorization.require("classroom.reserve", actor_user_id)
            return self._tool().retry_prepare_audit(
                approval_id, actor_user_id, trace_id=trace_id
            )
        if action_type == "reserve_library_book":
            self.authorization.require("library.reserve", actor_user_id)
            return self._library_tool().retry_prepare_audit(
                approval_id, actor_user_id, trace_id=trace_id
            )
        from campusmind.tools.actions import ClassroomActionConflict

        raise ClassroomActionConflict(f"unsupported action_type={action_type}")
