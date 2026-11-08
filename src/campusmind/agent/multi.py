from __future__ import annotations

from enum import Enum
from typing import Literal
from pydantic import BaseModel, Field
import re
from typing import Iterable
from sqlalchemy.orm import Session
from campusmind.agent.runtime import AgentRuntimeService
from campusmind.tools.student import StudentSqlToolService
from campusmind.tools.course import CourseToolService
from campusmind.tools.actions import LibraryActionService
from campusmind.tools.research import ResearchToolService
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import uuid
from campusmind.platform.db import AgentRun, AgentStep
from campusmind.platform.db import get_session_factory
import inspect
import time
from campusmind.platform.security import AuthorizationService

"""CampusMind multi domain."""

# ---- app/multi_agent/types.py ----
class AgentDomain(str, Enum):
    ACADEMIC = "academic"
    RESEARCH = "research"
    LIBRARY = "library"
    CAMPUS_SERVICE = "campus_service"
    GENERAL_KNOWLEDGE = "general_knowledge"


ChildStatus = Literal[
    "completed",
    "completed_with_warning",
    "deferred",
    "awaiting_approval",
    "cancelled",
    "failed",
]

SupervisorStatus = Literal[
    "completed",
    "completed_with_warning",
    "deferred",
    "awaiting_approval",
    "failed",
]

EvidenceKind = Literal["sql", "tool", "rag", "graph", "hybrid", "action", "unknown"]


class AgentEvidence(BaseModel):
    evidence_id: str = Field(min_length=1, max_length=80)
    task_id: str = Field(min_length=1, max_length=40)
    domain: AgentDomain
    source_kind: EvidenceKind
    source: str = Field(min_length=1, max_length=120)
    summary: str = Field(min_length=1, max_length=500)
    payload: dict = Field(default_factory=dict)


class MultiAgentTask(BaseModel):
    task_id: str = Field(min_length=1, max_length=40)
    domain: AgentDomain
    query: str = Field(min_length=1, max_length=2000)
    reason: str = Field(min_length=1, max_length=300)
    requires_actor: bool = False
    write_intent: bool = False
    depends_on: list[str] = Field(default_factory=list, max_length=8)
    context_keys: list[str] = Field(default_factory=list, max_length=20)


class MultiAgentPlan(BaseModel):
    tasks: list[MultiAgentTask] = Field(default_factory=list, min_length=1, max_length=8)
    parallelizable: bool = True
    supervisor_reason: str = Field(min_length=1, max_length=500)


class ChildAgentResult(BaseModel):
    task_id: str
    domain: AgentDomain
    query: str
    status: ChildStatus
    answer: str
    source: str
    pending_approval: bool = False
    approval_id: str | None = None
    trace_id: str | None = None
    structured_data: dict | None = None
    consumed_context: dict = Field(default_factory=dict)
    evidence: list[AgentEvidence] = Field(default_factory=list)
    error: str | None = None


class MultiAgentResult(BaseModel):
    trace_id: str
    actor_user_id: str | None = None
    query: str
    plan: MultiAgentPlan
    child_results: list[ChildAgentResult]
    status: SupervisorStatus
    pending_approval: bool
    answer: str
    elapsed_ms: float
    execution_order: list[str] = Field(default_factory=list)
    shared_context: dict = Field(default_factory=dict)
    evidence: list[AgentEvidence] = Field(default_factory=list)
    evidence_merge_passed: bool = False
    trace_persisted: bool = False
    trace_persist_error: str | None = None

# ---- app/multi_agent/agents.py ----
def _approval_id(structured: dict | None) -> str | None:
    if not structured:
        return None
    value = structured.get("approval_id")
    return str(value) if value is not None else None


def _runtime_child(
    session: Session,
    task: MultiAgentTask,
    *,
    actor_user_id=None,
    persist_trace: bool = False,
) -> ChildAgentResult:
    runtime = AgentRuntimeService(session)
    try:
        result = runtime.answer(
            task.query,
            actor_user_id=actor_user_id,
            max_retries=1,
            max_answer_rewrites=1,
            persist_trace=persist_trace,
        )
    finally:
        runtime.close()
    structured = result.retrieval_result.structured_data
    return ChildAgentResult(
        task_id=task.task_id,
        domain=task.domain,
        query=task.query,
        status=result.status,
        answer=result.final_answer,
        source=f"agent_runtime:{result.planned_decision.route.value}",
        pending_approval=result.pending_approval,
        approval_id=_approval_id(structured),
        trace_id=result.trace_id,
        structured_data=structured,
    )


class AcademicAgent:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.sql = StudentSqlToolService(session)
        self.course = CourseToolService(session)

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        q = "".join(task.query.lower().split())
        if any(token in q for token in ("学业概况", "学业情况", "综合学业")):
            if actor_user_id is None:
                return ChildAgentResult(
                    task_id=task.task_id,
                    domain=task.domain,
                    query=task.query,
                    status="deferred",
                    answer="Academic Agent 需要 actor_user_id 才能读取学生个人学业数据。",
                    source="student_sql",
                    structured_data={"self_only": True, "reason": "missing_actor_user_id"},
                )
            profile = self.sql.get_student_profile(actor_user_id)
            courses = self.sql.get_student_courses(actor_user_id)
            graduation = self.sql.get_graduation_progress(actor_user_id)
            course_rows = courses.data.get("courses", [])
            g = graduation.data
            answer = (
                f"Academic Agent 学业上下文：{profile.data['major_name']}专业，"
                f"已获 {g['earned_credits']:g}/{g['graduation_credits']:g} 学分，"
                f"还差 {g['remaining_credits']:g} 学分；"
                f"当前结构化已修课程记录 {len(course_rows)} 条。"
                "这里只核验现有结构化学业记录和学分总量，不把它扩展为完整毕业资格结论。"
            )
            return ChildAgentResult(
                task_id=task.task_id,
                domain=task.domain,
                query=task.query,
                status="completed",
                answer=answer,
                source="student_sql",
                structured_data={
                    "capability": "academic_context",
                    "self_only": True,
                    "data": {
                        "profile": profile.data,
                        "courses": course_rows,
                        "graduation": graduation.data,
                    },
                },
            )

        if any(token in q for token in ("毕业", "学分", "成绩", "我的课程", "我修")):
            if actor_user_id is None:
                return ChildAgentResult(
                    task_id=task.task_id,
                    domain=task.domain,
                    query=task.query,
                    status="deferred",
                    answer="Academic Agent 需要 actor_user_id 才能读取学生个人学业数据。",
                    source="student_sql",
                    structured_data={"self_only": True, "reason": "missing_actor_user_id"},
                )
            if "毕业" in q:
                result = self.sql.get_graduation_progress(actor_user_id)
            elif "成绩" in q:
                result = self.sql.get_student_grades(actor_user_id)
            else:
                result = self.sql.get_student_credits(actor_user_id)
            return ChildAgentResult(
                task_id=task.task_id,
                domain=task.domain,
                query=task.query,
                status="completed",
                answer=result.answer,
                source="student_sql",
                structured_data={
                    "capability": result.capability.value,
                    "self_only": result.self_only,
                    "data": result.data,
                },
            )

        if self.course.can_answer(task.query):
            result = self.course.answer(task.query)
            return ChildAgentResult(
                task_id=task.task_id,
                domain=task.domain,
                query=task.query,
                status="completed",
                answer=result.answer,
                source="course_tool",
                structured_data={
                    "capability": result.capability.value,
                    "read_only": result.read_only,
                    "data": result.data,
                },
            )
        return _runtime_child(self.session, task, actor_user_id=actor_user_id)


class ResearchAgent:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tool = ResearchToolService(session)

    @staticmethod
    def _dedupe(items: Iterable[dict]) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for item in items:
            key = str(item.get("teacher_id") or item.get("display_name"))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    @staticmethod
    def _requested_count(query: str, default: int = 2) -> int:
        q = query or ""
        mapping = {"一个": 1, "一位": 1, "两个": 2, "两位": 2, "三个": 3, "三位": 3}
        for token, value in mapping.items():
            if token in q:
                return value
        match = re.search(r"(\d+)\s*(?:个|位)?(?:老师|教师|导师)", q)
        return max(1, min(int(match.group(1)), 5)) if match else default

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        context = dict(shared_context or {})
        q = "".join(task.query.lower().split())
        if any(token in q for token in ("教授哪些课程", "同时教授", "哪些老师研究")):
            return _runtime_child(self.session, task, actor_user_id=actor_user_id)

        if any(token in q for token in ("老师", "教师", "导师", "ai方向")):
            if any(token in q for token in ("ai", "人工智能")):
                candidates = self._dedupe([
                    *self.tool.search_teacher("知识图谱"),
                    *self.tool.search_teacher("大语言模型"),
                    *self.tool.search_teacher("检索增强生成"),
                ])
            elif "知识图谱" in q:
                candidates = self.tool.search_teacher("知识图谱")
            elif any(token in q for token in ("大语言模型", "大模型")):
                candidates = self.tool.search_teacher("大语言模型")
            else:
                candidates = self.tool.search_teacher("")
            limit = self._requested_count(task.query)
            values = candidates[:limit]
            major = context.get("academic.major_name")
            prefix = f"结合上游 Academic Agent 提供的{major}专业上下文，" if major else ""
            answer = (
                prefix
                + "Research Agent 推荐："
                + "；".join(
                    f"{item['display_name']}（{'、'.join(area['name'] for area in item.get('research_areas', []))}）"
                    for item in values
                )
                + "。"
                if values
                else "Research Agent 没有找到匹配的科研教师。"
            )
            return ChildAgentResult(
                task_id=task.task_id,
                domain=task.domain,
                query=task.query,
                status="completed",
                answer=answer,
                source="research_tool",
                structured_data={
                    "capability": "research_teacher_search",
                    "teachers": values,
                    "count": len(values),
                    "context_used": context,
                },
            )

        if self.tool.supports(task.query):
            result = self.tool.answer(task.query)
            return ChildAgentResult(
                task_id=task.task_id,
                domain=task.domain,
                query=task.query,
                status="completed",
                answer=result.answer,
                source="research_tool",
                structured_data={
                    "capability": result.capability.value,
                    "data": result.data,
                    "context_used": context,
                },
            )
        return _runtime_child(self.session, task, actor_user_id=actor_user_id)


class LibraryAgent:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.tool = LibraryActionService(session)

    @staticmethod
    def _dedupe(items: Iterable[dict]) -> list[dict]:
        result: list[dict] = []
        seen: set[str] = set()
        for item in items:
            key = str(item.get("book_id") or item.get("book_code") or item.get("title"))
            if key in seen:
                continue
            seen.add(key)
            result.append(item)
        return result

    def _books_from_context(self, context: dict) -> list[dict]:
        areas = [str(item) for item in (context.get("research.research_areas") or [])]
        values: list[dict] = []
        if any("知识图谱" in area or "检索增强" in area for area in areas):
            values.extend(self.tool.search_book("知识图谱", limit=3))
            values.extend(self.tool.search_book("Graph", limit=3))
        if any("大语言模型" in area or "强化学习" in area for area in areas):
            values.extend(self.tool.search_book("Learning", limit=3))
        return self._dedupe(values)[:3]

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        context = dict(shared_context or {})
        q = "".join(task.query.lower().split())
        write_intent = task.write_intent or any(token in q for token in ("预约", "预订", "借书", "借阅"))
        if write_intent:
            return _runtime_child(
                self.session,
                task,
                actor_user_id=actor_user_id,
                persist_trace=True,
            )

        contextual_values = self._books_from_context(context) if context else []
        if contextual_values:
            values = contextual_values
        elif any(token in q for token in ("ai", "人工智能", "大模型", "相关图书")):
            values = self._dedupe([
                *self.tool.search_book("知识图谱", limit=3),
                *self.tool.search_book("Learning", limit=3),
            ])[:3]
        elif "知识图谱" in q or "graphrag" in q:
            values = self._dedupe([
                *self.tool.search_book("知识图谱", limit=3),
                *self.tool.search_book("Graph", limit=3),
            ])[:3]
        else:
            values = self.tool.recommend_books("", limit=3)

        context_prefix = "根据上游 Research Agent 提供的研究方向，" if contextual_values else ""
        answer = (
            context_prefix
            + "Library Agent 推荐："
            + "；".join(f"《{item['title']}》 / {item['author']}" for item in values)
            + "。"
            if values
            else "Library Agent 暂时没有找到匹配图书。"
        )
        return ChildAgentResult(
            task_id=task.task_id,
            domain=task.domain,
            query=task.query,
            status="completed",
            answer=answer,
            source="library_tool",
            structured_data={
                "capability": "library_recommend",
                "books": values,
                "count": len(values),
                "read_only": True,
                "context_used": context,
            },
        )


class CampusServiceAgent:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        return _runtime_child(
            self.session,
            task,
            actor_user_id=actor_user_id,
            persist_trace=task.write_intent,
        )


class GeneralKnowledgeAgent:
    def __init__(self, session: Session) -> None:
        self.session = session

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        return _runtime_child(self.session, task, actor_user_id=actor_user_id)


class SpecialistRegistry:
    def __init__(self, session: Session) -> None:
        self.agents = {
            AgentDomain.ACADEMIC: AcademicAgent(session),
            AgentDomain.RESEARCH: ResearchAgent(session),
            AgentDomain.LIBRARY: LibraryAgent(session),
            AgentDomain.CAMPUS_SERVICE: CampusServiceAgent(session),
            AgentDomain.GENERAL_KNOWLEDGE: GeneralKnowledgeAgent(session),
        }

    def run(self, task: MultiAgentTask, *, actor_user_id=None, shared_context=None) -> ChildAgentResult:
        return self.agents[task.domain].run(
            task,
            actor_user_id=actor_user_id,
            shared_context=shared_context,
        )

# ---- app/multi_agent/context.py ----
class SharedAgentContext:
    """Bounded cross-agent context for cross-agent context.

    The context only carries structured outputs produced by already completed
    specialist tasks. It never exposes raw private rows from another actor and
    it never authorizes a write action.
    """

    def __init__(self) -> None:
        self.facts: dict[str, object] = {}
        self.evidence: list[AgentEvidence] = []
        self.task_outputs: dict[str, dict] = {}

    @staticmethod
    def _source_kind(source: str) -> str:
        value = (source or "").lower()
        if value == "student_sql" or value.endswith(":sql"):
            return "sql"
        if value in {"course_tool", "research_tool", "library_tool"}:
            return "tool"
        if value.endswith(":graph"):
            return "graph"
        if value.endswith(":hybrid"):
            return "hybrid"
        if value.endswith(":rag"):
            return "rag"
        if value.endswith(":tool"):
            return "action"
        return "unknown"

    @staticmethod
    def _summary(child: ChildAgentResult) -> str:
        text = " ".join((child.answer or "").split())
        return text[:480] or f"{child.domain.value} specialist result"

    @staticmethod
    def _unique(values) -> list:
        result = []
        seen = set()
        for value in values:
            key = str(value)
            if key in seen:
                continue
            seen.add(key)
            result.append(value)
        return result

    def _extract_facts(self, child: ChildAgentResult) -> None:
        structured = child.structured_data or {}
        capability = structured.get("capability")
        data = structured.get("data") or {}

        if child.domain.value == "academic":
            if capability == "academic_context":
                profile = data.get("profile") or {}
                graduation = data.get("graduation") or {}
                courses = data.get("courses") or []
                self.facts["academic.major_name"] = profile.get("major_name") or graduation.get("major_name")
                self.facts["academic.college_name"] = profile.get("college_name")
                self.facts["academic.grade_level"] = profile.get("grade_level")
                self.facts["academic.earned_credits"] = graduation.get("earned_credits")
                self.facts["academic.graduation_credits"] = graduation.get("graduation_credits")
                self.facts["academic.remaining_credits"] = graduation.get("remaining_credits")
                self.facts["academic.completed_courses"] = [
                    item.get("course_name") for item in courses if item.get("course_name")
                ]
                self.facts["academic.credit_scope_only"] = True
            elif capability == "graduation_progress":
                self.facts["academic.major_name"] = data.get("major_name")
                self.facts["academic.earned_credits"] = data.get("earned_credits")
                self.facts["academic.graduation_credits"] = data.get("graduation_credits")
                self.facts["academic.remaining_credits"] = data.get("remaining_credits")
                self.facts["academic.credit_scope_only"] = True

        if child.domain.value == "research":
            teachers = structured.get("teachers") or data.get("teachers") or []
            if teachers:
                self.facts["research.teacher_names"] = self._unique(
                    item.get("display_name") for item in teachers if item.get("display_name")
                )
                areas: list[str] = []
                for item in teachers:
                    for area in item.get("research_areas", []):
                        name = area.get("name") if isinstance(area, dict) else str(area)
                        if name:
                            areas.append(name)
                self.facts["research.research_areas"] = self._unique(areas)

        if child.domain.value == "library":
            books = structured.get("books") or data.get("books") or []
            if books:
                self.facts["library.book_titles"] = self._unique(
                    item.get("title") for item in books if item.get("title")
                )

    def context_for(self, task: MultiAgentTask) -> dict:
        if not task.depends_on and not task.context_keys:
            return {}
        if task.context_keys:
            return {
                key: deepcopy(self.facts.get(key))
                for key in task.context_keys
                if key in self.facts and self.facts.get(key) is not None
            }
        # Fallback for future tasks that specify dependencies but no explicit keys.
        return deepcopy(self.facts)

    def absorb(self, child: ChildAgentResult) -> ChildAgentResult:
        self.task_outputs[child.task_id] = {
            "domain": child.domain.value,
            "status": child.status,
            "source": child.source,
            "structured_data": deepcopy(child.structured_data),
        }
        self._extract_facts(child)
        evidence = AgentEvidence(
            evidence_id=f"ev-{child.task_id}-{len(self.evidence) + 1}",
            task_id=child.task_id,
            domain=child.domain,
            source_kind=self._source_kind(child.source),
            source=child.source,
            summary=self._summary(child),
            payload=deepcopy(child.structured_data or {}),
        )
        self.evidence.append(evidence)
        return child.model_copy(update={"evidence": [evidence]})

    def snapshot(self) -> dict:
        return deepcopy(self.facts)

# ---- app/multi_agent/planner.py ----
class SupervisorPlanner:
    """Transparent supervisor planner with optional cross-agent context dependencies."""

    _ACADEMIC = ("毕业", "学分", "培养方案", "选课", "课程表", "先修", "成绩", "学习路径", "学业")
    _RESEARCH = ("老师", "教师", "导师", "科研", "研究方向", "论文", "实验室", "项目", "ai", "人工智能", "大模型", "知识图谱", "rag")
    _LIBRARY = ("图书", "书籍", "书", "馆藏", "借阅", "借书")
    _CAMPUS = ("教室", "自习室", "场地", "活动", "办事", "流程", "通知")
    _WRITE = ("预约", "预订", "报名", "提交", "删除", "修改", "借")
    _CONTEXTUAL = (
        "结合我的",
        "根据我的",
        "基于我的",
        "针对我的",
        "再根据",
        "根据这些",
        "结合这些",
        "基于这些",
        "结合上一步",
        "根据上一步",
    )

    @staticmethod
    def _compact(query: str) -> str:
        return "".join((query or "").lower().split())

    @staticmethod
    def _task(
        task_id: int,
        domain: AgentDomain,
        query: str,
        reason: str,
        *,
        requires_actor=False,
        write_intent=False,
        depends_on=None,
        context_keys=None,
    ) -> MultiAgentTask:
        return MultiAgentTask(
            task_id=f"task-{task_id}",
            domain=domain,
            query=query,
            reason=reason,
            requires_actor=requires_actor,
            write_intent=write_intent,
            depends_on=list(depends_on or []),
            context_keys=list(context_keys or []),
        )

    @classmethod
    def _academic_query(cls, query: str) -> str:
        q = cls._compact(query)
        if any(token in q for token in ("学业情况", "学业概况", "结合我的", "根据我的", "基于我的")):
            return "查询我的综合学业概况"
        if "毕业" in q:
            return "我还差多少学分毕业？"
        if "成绩" in q:
            return "查询我的成绩"
        if "学分" in q:
            return "我有多少学分？"
        return query

    @classmethod
    def _research_query(cls, query: str) -> str:
        q = cls._compact(query)
        if any(token in q for token in ("老师", "教师", "导师", "ai", "人工智能")):
            return "推荐AI方向科研教师"
        if "论文" in q:
            return "搜索论文 RAG"
        if "实验室" in q:
            return "搜索实验室 RAG"
        if "项目" in q:
            return "搜索科研项目 Agentic"
        return query

    @classmethod
    def _library_query(cls, query: str) -> str:
        q = cls._compact(query)
        if any(token in q for token in ("预约", "预订", "借书", "借阅")):
            return query
        if any(token in q for token in ("根据这些", "再根据", "结合这些", "研究方向")):
            return "根据上游研究方向推荐相关图书"
        if any(token in q for token in ("ai", "人工智能", "大模型", "知识图谱", "rag")):
            return "推荐AI相关图书"
        return "推荐相关图书"

    def plan(self, query: str) -> MultiAgentPlan:
        raw = (query or "").strip()
        q = self._compact(raw)
        if not raw:
            raise ValueError("query must not be empty")

        tasks: list[MultiAgentTask] = []
        next_id = 1

        if any(token in q for token in self._ACADEMIC):
            requires_actor = any(token in q for token in ("我", "我的", "毕业", "学分", "成绩", "学业"))
            tasks.append(self._task(
                next_id,
                AgentDomain.ACADEMIC,
                self._academic_query(raw),
                "学业/毕业/学分问题交给 Academic Agent",
                requires_actor=requires_actor,
            ))
            next_id += 1

        if any(token in q for token in self._RESEARCH):
            tasks.append(self._task(
                next_id,
                AgentDomain.RESEARCH,
                self._research_query(raw),
                "教师/科研方向/论文/实验室/项目交给 Research Agent",
            ))
            next_id += 1

        if any(token in q for token in self._LIBRARY):
            write_intent = any(token in q for token in ("预约", "预订", "借书", "借阅"))
            tasks.append(self._task(
                next_id,
                AgentDomain.LIBRARY,
                self._library_query(raw),
                "图书/馆藏/推荐/借阅交给 Library Agent",
                requires_actor=write_intent,
                write_intent=write_intent,
            ))
            next_id += 1

        if any(token in q for token in self._CAMPUS):
            write_intent = any(token in q for token in self._WRITE)
            tasks.append(self._task(
                next_id,
                AgentDomain.CAMPUS_SERVICE,
                raw,
                "教室/场地/办事/通知交给 Campus Service Agent",
                requires_actor=write_intent,
                write_intent=write_intent,
            ))
            next_id += 1

        if not tasks:
            tasks.append(self._task(
                1,
                AgentDomain.GENERAL_KNOWLEDGE,
                raw,
                "未命中专用校园业务域，交给 General Knowledge Agent",
            ))

        unique: list[MultiAgentTask] = []
        seen: set[AgentDomain] = set()
        for item in tasks:
            if item.domain in seen:
                continue
            seen.add(item.domain)
            unique.append(item.model_copy(update={"task_id": f"task-{len(unique) + 1}"}))

        contextual = any(token in q for token in self._CONTEXTUAL)
        by_domain = {item.domain: item for item in unique}

        if contextual and AgentDomain.ACADEMIC in by_domain and AgentDomain.RESEARCH in by_domain:
            academic = by_domain[AgentDomain.ACADEMIC]
            research = by_domain[AgentDomain.RESEARCH]
            research.depends_on = [academic.task_id]
            research.context_keys = [
                "academic.major_name",
                "academic.remaining_credits",
                "academic.completed_courses",
            ]

        if contextual and AgentDomain.RESEARCH in by_domain and AgentDomain.LIBRARY in by_domain:
            research = by_domain[AgentDomain.RESEARCH]
            library = by_domain[AgentDomain.LIBRARY]
            dependencies = [research.task_id]
            context_keys = ["research.teacher_names", "research.research_areas"]
            if AgentDomain.ACADEMIC in by_domain:
                academic = by_domain[AgentDomain.ACADEMIC]
                dependencies.insert(0, academic.task_id)
                context_keys.insert(0, "academic.major_name")
            library.depends_on = dependencies
            library.context_keys = context_keys

        has_dependencies = any(item.depends_on for item in unique)
        parallelizable = not any(item.write_intent for item in unique) and not has_dependencies
        mode = "带跨 Agent 上下文依赖的任务 DAG" if has_dependencies else "可独立执行的领域任务"
        return MultiAgentPlan(
            tasks=unique,
            parallelizable=parallelizable,
            supervisor_reason=(
                f"Supervisor 将请求拆分为 {len(unique)} 个{mode}；"
                "每个子 Agent 只调用其已有、已验证的 CampusMind 能力。"
            ),
        )

# ---- app/multi_agent/trace_repository.py ----
class SqlMultiAgentTraceRepository:
    """Persist supervisor, context handoffs, evidence merge and specialist steps."""

    def __init__(self, session_factory=None) -> None:
        self.session_factory = session_factory or get_session_factory()

    def persist(self, result: MultiAgentResult) -> None:
        run_id = uuid.UUID(result.trace_id)
        finished = datetime.now(timezone.utc)
        started = finished - timedelta(milliseconds=result.elapsed_ms)
        score = 1.0 if result.status == "completed" else 0.8
        risk = "medium" if result.pending_approval else "low"

        with self.session_factory() as session:
            session.add(
                AgentRun(
                    id=run_id,
                    user_id=(uuid.UUID(result.actor_user_id) if result.actor_user_id else None),
                    conversation_id=None,
                    query=result.query,
                    intent="hierarchical_multi_agent",
                    complexity="mixed" if len(result.plan.tasks) > 1 else "simple",
                    risk_level=risk,
                    retrieval_strategy="hierarchical_multi_agent",
                    status=result.status,
                    validation_score=Decimal(str(score)),
                    final_answer=result.answer,
                    started_at=started,
                    finished_at=finished,
                    latency_ms=int(round(result.elapsed_ms)),
                )
            )
            session.flush()

            sequence = 1
            session.add(
                AgentStep(
                    agent_run_id=run_id,
                    sequence_no=sequence,
                    step_name="supervisor_plan",
                    step_type="supervisor",
                    status="completed",
                    input_json={"query": result.query},
                    output_json={
                        "parallelizable": result.plan.parallelizable,
                        "tasks": [item.model_dump(mode="json") for item in result.plan.tasks],
                        "execution_order": result.execution_order,
                    },
                    latency_ms=0,
                )
            )
            sequence += 1

            task_lookup = {item.task_id: item for item in result.plan.tasks}
            for child in result.child_results:
                task = task_lookup.get(child.task_id)
                if child.consumed_context:
                    session.add(
                        AgentStep(
                            agent_run_id=run_id,
                            sequence_no=sequence,
                            step_name=f"context_handoff_{child.domain.value}",
                            step_type="context_handoff",
                            status="completed",
                            input_json={
                                "task_id": child.task_id,
                                "depends_on": list(task.depends_on) if task else [],
                                "context_keys": list(task.context_keys) if task else [],
                            },
                            output_json={"consumed_context": child.consumed_context},
                            latency_ms=0,
                        )
                    )
                    sequence += 1

                session.add(
                    AgentStep(
                        agent_run_id=run_id,
                        sequence_no=sequence,
                        step_name=f"handoff_{child.domain.value}",
                        step_type="specialist_agent",
                        status=child.status,
                        input_json={
                            "task_id": child.task_id,
                            "query": child.query,
                            "consumed_context": child.consumed_context,
                        },
                        output_json={
                            "answer": child.answer,
                            "source": child.source,
                            "pending_approval": child.pending_approval,
                            "approval_id": child.approval_id,
                            "child_trace_id": child.trace_id,
                            "structured_data": child.structured_data,
                            "evidence": [item.model_dump(mode="json") for item in child.evidence],
                            "error": child.error,
                        },
                        latency_ms=0,
                    )
                )
                sequence += 1

            session.add(
                AgentStep(
                    agent_run_id=run_id,
                    sequence_no=sequence,
                    step_name="evidence_merge",
                    step_type="supervisor_context",
                    status="completed" if result.evidence_merge_passed else "completed_with_warning",
                    input_json={"child_count": len(result.child_results)},
                    output_json={
                        "evidence_merge_passed": result.evidence_merge_passed,
                        "evidence_count": len(result.evidence),
                        "evidence": [item.model_dump(mode="json") for item in result.evidence],
                        "shared_context": result.shared_context,
                    },
                    latency_ms=0,
                )
            )
            sequence += 1

            session.add(
                AgentStep(
                    agent_run_id=run_id,
                    sequence_no=sequence,
                    step_name="supervisor_synthesis",
                    step_type="supervisor",
                    status=result.status,
                    input_json={
                        "child_count": len(result.child_results),
                        "evidence_count": len(result.evidence),
                    },
                    output_json={
                        "answer": result.answer,
                        "pending_approval": result.pending_approval,
                        "evidence_merge_passed": result.evidence_merge_passed,
                    },
                    latency_ms=0,
                )
            )
            session.commit()

# ---- app/multi_agent/coordinator.py ----
class ContextAwareExecutionCoordinator:
    """Execute a bounded task DAG and carry structured context between agents."""

    def __init__(self, registry, *, authorization=None) -> None:
        self.registry = registry
        self.authorization = authorization

    @staticmethod
    def _supports_context(callable_obj) -> bool:
        try:
            parameters = inspect.signature(callable_obj).parameters.values()
        except (TypeError, ValueError):
            return False
        return any(
            parameter.name == "shared_context"
            or parameter.kind is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

    def _run(self, task, *, actor_user_id, shared_context):
        if self._supports_context(self.registry.run):
            return self.registry.run(
                task,
                actor_user_id=actor_user_id,
                shared_context=shared_context,
            )
        # multi-agent runtime-compatible custom registries used in tests/integrations.
        return self.registry.run(task, actor_user_id=actor_user_id)

    def execute(self, plan: MultiAgentPlan, *, actor_user_id=None):
        tasks = {task.task_id: task for task in plan.tasks}
        for task in plan.tasks:
            unknown = [dep for dep in task.depends_on if dep not in tasks]
            if unknown:
                raise ValueError(f"task {task.task_id} has unknown dependencies: {unknown}")

        context = SharedAgentContext()
        children: list[ChildAgentResult] = []
        execution_order: list[str] = []
        finished: set[str] = set()
        pending = list(plan.tasks)

        while pending:
            ready = [task for task in pending if all(dep in finished for dep in task.depends_on)]
            if not ready:
                raise ValueError("multi-agent dependency graph contains a cycle")

            # This first version executes ready tasks deterministically. The plan
            # still exposes parallelizable=True when no cross-task dependency is
            # required, so a future async executor can parallelize safely.
            for task in ready:
                consumed = context.context_for(task)
                auth_decision = None
                if self.authorization is not None:
                    auth_decision = self.authorization.authorize_task(task, actor_user_id)

                if auth_decision is not None and not auth_decision.allowed:
                    child = ChildAgentResult(
                        task_id=task.task_id,
                        domain=task.domain,
                        query=task.query,
                        status="deferred",
                        answer=(
                            "Authorization 已在 Specialist handoff 之前拒绝该任务；"
                            "未执行 SQL、Retriever 或写操作。"
                        ),
                        source="authorization",
                        structured_data={
                            "authorization": auth_decision.model_dump(mode="json"),
                            "side_effects": 0,
                        },
                    )
                else:
                    try:
                        child = self._run(
                            task,
                            actor_user_id=actor_user_id,
                            shared_context=consumed,
                        )
                    except Exception as exc:
                        child = ChildAgentResult(
                            task_id=task.task_id,
                            domain=task.domain,
                            query=task.query,
                            status="failed",
                            answer=f"{task.domain.value} 子 Agent 执行失败，Supervisor 已隔离该分支。",
                            source="supervisor_fail_soft",
                            error=f"{type(exc).__name__}: {exc}",
                        )
                    if auth_decision is not None:
                        structured = dict(child.structured_data or {})
                        structured["authorization"] = auth_decision.model_dump(mode="json")
                        child = child.model_copy(update={"structured_data": structured})

                child = child.model_copy(update={"consumed_context": consumed})
                child = context.absorb(child)
                children.append(child)
                execution_order.append(task.task_id)
                finished.add(task.task_id)
                pending.remove(task)

        return children, execution_order, context

# ---- app/multi_agent/service.py ----
class HierarchicalMultiAgentService:
    """Campus Supervisor + specialist agents + cross-agent context shared context."""

    def __init__(
        self,
        session: Session,
        *,
        planner=None,
        registry=None,
        trace_repository=None,
        coordinator=None,
        authorization=None,
    ) -> None:
        self.session = session
        self.planner = planner or SupervisorPlanner()
        self.registry = registry or SpecialistRegistry(session)
        self.trace_repository = trace_repository or SqlMultiAgentTraceRepository()
        self.authorization = authorization or AuthorizationService(session)
        self.coordinator = coordinator or ContextAwareExecutionCoordinator(
            self.registry, authorization=self.authorization
        )

    def plan(self, query: str) -> MultiAgentPlan:
        return self.planner.plan(query)

    @staticmethod
    def _status(children: list[ChildAgentResult]):
        if any(item.pending_approval or item.status == "awaiting_approval" for item in children):
            return "awaiting_approval", True
        if children and all(item.status == "deferred" for item in children):
            return "deferred", False
        if any(item.status == "failed" for item in children):
            return "completed_with_warning", False
        if any(item.status in {"deferred", "completed_with_warning"} for item in children):
            return "completed_with_warning", False
        return "completed", False

    @staticmethod
    def _synthesize(
        children: list[ChildAgentResult],
        *,
        pending_approval: bool,
        context_note: str | None = None,
    ) -> str:
        sections: list[str] = []
        labels = {
            "academic": "学业",
            "research": "科研",
            "library": "图书馆",
            "campus_service": "校园服务",
            "general_knowledge": "综合知识",
        }
        for child in children:
            label = labels.get(child.domain.value, child.domain.value)
            sections.append(f"【{label}】{child.answer}")
        if context_note:
            sections.append(f"【协同上下文】{context_note}")
        if pending_approval:
            sections.append("存在需要人工确认的写操作；Supervisor 已暂停执行，请使用返回的 approval_id 通过既有 /api/v1/agent/resume 确认或拒绝。")
        return "\n\n".join(sections)

    @staticmethod
    def _context_note(plan: MultiAgentPlan, children: list[ChildAgentResult], evidence_count: int) -> str | None:
        dependent = [item for item in plan.tasks if item.depends_on]
        if not dependent:
            return None
        handoffs = sum(1 for item in children if item.consumed_context)
        return (
            f"已完成 {handoffs} 次跨 Agent 结构化上下文传递，并合并 {evidence_count} 条来源证据；"
            "下游 Agent 只能读取计划声明的 context_keys，不能借此扩大权限或绕过 HITL。"
        )

    def answer(
        self,
        query: str,
        *,
        actor_user_id=None,
        persist_trace: bool = True,
    ) -> MultiAgentResult:
        started = time.perf_counter()
        trace_id = str(uuid.uuid4())
        plan = self.plan(query)

        try:
            children, execution_order, context = self.coordinator.execute(
                plan,
                actor_user_id=actor_user_id,
            )
        except Exception as exc:
            # A coordinator-level failure is different from an isolated child
            # branch failure: the dependency graph itself could not execute.
            elapsed = round((time.perf_counter() - started) * 1000, 3)
            result = MultiAgentResult(
                trace_id=trace_id,
                actor_user_id=(str(actor_user_id) if actor_user_id is not None else None),
                query=query,
                plan=plan,
                child_results=[],
                status="failed",
                pending_approval=False,
                answer="Supervisor 无法完成跨 Agent 依赖执行；没有执行任何后续写操作。",
                elapsed_ms=elapsed,
                execution_order=[],
                shared_context={},
                evidence=[],
                evidence_merge_passed=False,
                trace_persist_error=f"{type(exc).__name__}: {exc}",
            )
            return result

        status, pending = self._status(children)
        evidence = list(context.evidence)
        shared_context = context.snapshot()
        evidence_merge_passed = len(evidence) == len(children) and all(item.source for item in evidence)
        answer = self._synthesize(
            children,
            pending_approval=pending,
            context_note=self._context_note(plan, children, len(evidence)),
        )
        result = MultiAgentResult(
            trace_id=trace_id,
            actor_user_id=(str(actor_user_id) if actor_user_id is not None else None),
            query=query,
            plan=plan,
            child_results=children,
            status=status,
            pending_approval=pending,
            answer=answer,
            elapsed_ms=round((time.perf_counter() - started) * 1000, 3),
            execution_order=execution_order,
            shared_context=shared_context,
            evidence=evidence,
            evidence_merge_passed=evidence_merge_passed,
        )

        if persist_trace:
            try:
                self.trace_repository.persist(result)
                result.trace_persisted = True
            except Exception as exc:
                result.trace_persist_error = f"{type(exc).__name__}: {exc}"
        return result
