from __future__ import annotations

from dataclasses import dataclass
from datetime import time
from decimal import Decimal
from enum import Enum
import re
import uuid
from sqlalchemy import MetaData, Table, and_, literal, or_, select
from sqlalchemy.orm import Session

"""CampusMind course domain."""

# ---- app/campus_tools/course.py ----
class CourseToolError(RuntimeError):
    pass


class CourseToolNotFound(CourseToolError):
    pass


class CourseToolSchemaError(CourseToolError):
    pass


class CourseCapability(str, Enum):
    SEARCH = "course_search"
    SCHEDULE = "course_schedule"
    PREREQUISITES = "course_prerequisites"
    TEACHERS = "course_teachers"


@dataclass(slots=True)
class CourseIntent:
    query: str
    capability: CourseCapability
    course_hint: str | None = None
    keywords: tuple[str, ...] = ()


@dataclass(slots=True)
class CourseToolResult:
    capability: CourseCapability
    answer: str
    data: dict
    source: str = "postgresql"
    read_only: bool = True


class CourseIntentParser:
    _TITLE_RE = re.compile(r"《([^》]{1,200})》")
    _QUOTE_RE = re.compile(r'["“「『]([^"”」』]{1,200})["”」』]')
    _STOPWORDS = (
        "帮我",
        "请帮我",
        "请",
        "查询",
        "查一下",
        "查找",
        "搜索",
        "看看",
        "课程表",
        "课程安排",
        "上课时间",
        "上课地点",
        "几点上课",
        "在哪里上课",
        "在哪上课",
        "先修课程",
        "先修课",
        "先修要求",
        "前置课程",
        "前置要求",
        "先学什么",
        "任课老师",
        "授课老师",
        "任课教师",
        "授课教师",
        "谁教",
        "谁来教",
        "有哪些课程",
        "课程列表",
        "课程查询",
        "有什么课程",
        "课程",
        "一下",
        "是什么",
        "是哪些",
        "有哪些",
    )

    @staticmethod
    def _compact(query: str) -> str:
        return "".join((query or "").lower().split())

    @classmethod
    def supports(cls, query: str) -> bool:
        q = cls._compact(query)

        non_course_tool_context = (
            "知识图谱",
            "graph",
            "一跳",
            "两跳",
            "多跳",
            "上游",
            "下游",
            "路径",
            "关系表",
            "关系类型",
            "relation_type",
            "字段",
            "已修",
            "张同学",
            "教学班",
            "共同先修",
            "共享先修",
            "两门目标",
        )

        if any(
            marker in q
            for marker in non_course_tool_context
        ):
            return False
        # Intentionally narrow. Questions such as “研究知识图谱的老师教授哪些课程”
        # must remain GraphRAG rather than being hijacked by the SQL Course Tool.
        explicit_markers = (
            "课程表",
            "课程安排",
            "上课时间",
            "上课地点",
            "几点上课",
            "在哪里上课",
            "在哪上课",
            "先修课程",
            "先修课",
            "先修要求",
            "前置课程",
            "前置要求",
            "先学什么",
            "prerequisite",
            "任课老师",
            "授课老师",
            "任课教师",
            "授课教师",
            "谁教",
            "谁来教",
            "搜索课程",
            "查询课程",
            "查找课程",
            "课程列表",
        )
        return any(marker in q for marker in explicit_markers)

    @classmethod
    def _capability(cls, query: str) -> CourseCapability:
        q = cls._compact(query)
        if any(token in q for token in ("课程表", "课程安排", "上课时间", "上课地点", "几点上课", "在哪里上课", "在哪上课")):
            return CourseCapability.SCHEDULE
        if any(token in q for token in ("先修课程", "先修课", "先修要求", "前置课程", "前置要求", "先学什么", "prerequisite")):
            return CourseCapability.PREREQUISITES
        if any(token in q for token in ("任课老师", "授课老师", "任课教师", "授课教师", "谁教", "谁来教")):
            return CourseCapability.TEACHERS
        return CourseCapability.SEARCH

    @classmethod
    def parse(cls, query: str) -> CourseIntent:
        raw = (query or "").strip()
        capability = cls._capability(raw)
        title_match = cls._TITLE_RE.search(raw) or cls._QUOTE_RE.search(raw)
        explicit_hint = title_match.group(1).strip() if title_match else None

        normalized = raw
        if explicit_hint:
            for decorated in (
                f"《{explicit_hint}》",
                f'"{explicit_hint}"',
                f"“{explicit_hint}”",
                f"「{explicit_hint}」",
                f"『{explicit_hint}』",
            ):
                normalized = normalized.replace(decorated, " ")
        for token in cls._STOPWORDS:
            normalized = normalized.replace(token, " ")
        normalized = re.sub(r"[？?，,。！!、:：;；()（）]", " ", normalized)
        parts = [item.strip() for item in normalized.split() if item.strip()]
        course_hint = explicit_hint or (parts[0] if parts else None)
        keywords = tuple(dict.fromkeys(([course_hint] if course_hint else []) + parts))[:8]
        return CourseIntent(
            query=raw,
            capability=capability,
            course_hint=course_hint,
            keywords=keywords,
        )


class CourseRepository:
    """Read-only course repository over the existing academic schema.

    The baseline schema provides courses/course_prerequisites/teachers/
    teaching_assignments. Reflection keeps the tool compatible with that verified
    schema instead of duplicating ORM models merely for a Tool boundary.
    """

    def __init__(self, session: Session) -> None:
        self.session = session
        bind = session.get_bind()
        metadata = MetaData()
        self.courses = Table("courses", metadata, autoload_with=bind)
        self.prerequisites = Table("course_prerequisites", metadata, autoload_with=bind)
        self.teachers = Table("teachers", metadata, autoload_with=bind)
        self.assignments = Table("teaching_assignments", metadata, autoload_with=bind)
        self.users = Table("users", metadata, autoload_with=bind)
        self.schedules = Table("course_schedules", metadata, autoload_with=bind)

    @staticmethod
    def _required(table: Table, *names: str):
        for name in names:
            if name in table.c:
                return table.c[name]
        raise CourseToolSchemaError(
            f"{table.name} is missing expected column; tried {', '.join(names)}"
        )

    @staticmethod
    def _optional(table: Table, *names: str):
        for name in names:
            if name in table.c:
                return table.c[name]
        return None

    @staticmethod
    def _json_value(value):
        if isinstance(value, uuid.UUID):
            return str(value)
        if isinstance(value, Decimal):
            return float(value)
        if isinstance(value, time):
            return value.strftime("%H:%M")
        if hasattr(value, "isoformat"):
            return value.isoformat()
        return value

    @classmethod
    def _row_json(cls, row) -> dict:
        return {key: cls._json_value(value) for key, value in dict(row).items()}

    def _course_columns(self, table: Table | None = None, *, prefix: str = ""):
        if table is None:
            table = self.courses
        ident = self._required(table, "id")
        code = self._required(table, "code", "course_code")
        name = self._required(table, "name", "course_name")
        credits = self._optional(table, "credits", "credit")
        course_type = self._optional(table, "course_type", "type")
        description = self._optional(table, "description", "summary")
        return [
            ident.label(f"{prefix}course_id"),
            code.label(f"{prefix}course_code"),
            name.label(f"{prefix}course_name"),
            (credits if credits is not None else literal(None)).label(f"{prefix}credits"),
            (course_type if course_type is not None else literal(None)).label(f"{prefix}course_type"),
            (description if description is not None else literal(None)).label(f"{prefix}description"),
        ]

    def search_courses(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        code = self._required(self.courses, "code", "course_code")
        name = self._required(self.courses, "name", "course_name")
        description = self._optional(self.courses, "description", "summary")
        clauses = [code.ilike(f"%{q}%"), name.ilike(f"%{q}%")]
        if description is not None:
            clauses.append(description.ilike(f"%{q}%"))
        stmt = select(*self._course_columns()).where(or_(*clauses)).order_by(code.asc()).limit(limit)
        return [self._row_json(row) for row in self.session.execute(stmt).mappings().all()]

    @staticmethod
    def _compact_entity_text(value) -> str:
        return "".join(
            str(value or "").lower().split()
        )

    def find_courses_mentioned_in_text(
        self,
        text: str,
        *,
        limit: int = 8,
    ) -> list[dict]:
        """Find real DB course codes/names mentioned in text."""

        compact = self._compact_entity_text(text)

        if not compact:
            return []

        code = self._required(
            self.courses,
            "code",
            "course_code",
        )

        stmt = (
            select(*self._course_columns())
            .order_by(code.asc())
        )

        rows = [
            self._row_json(row)
            for row in self.session.execute(
                stmt
            ).mappings().all()
        ]

        matched = []

        for row in rows:
            course_code = self._compact_entity_text(
                row.get("course_code")
            )
            course_name = self._compact_entity_text(
                row.get("course_name")
            )

            code_hit = (
                len(course_code) >= 3
                and course_code in compact
            )

            name_hit = (
                len(course_name) >= 2
                and course_name in compact
            )

            if not (code_hit or name_hit):
                continue

            specificity = max(
                len(course_code) if code_hit else 0,
                len(course_name) if name_hit else 0,
            )

            matched.append(
                (specificity, row)
            )

        matched.sort(
            key=lambda item: (
                -item[0],
                str(
                    item[1].get("course_code")
                    or ""
                ),
            )
        )

        return [
            row
            for _, row in matched[
                :max(1, limit)
            ]
        ]

    def get_course(self, course_ref) -> dict:
        ident = self._required(self.courses, "id")
        code = self._required(self.courses, "code", "course_code")
        name = self._required(self.courses, "name", "course_name")
        stmt = select(*self._course_columns())
        try:
            course_uuid = course_ref if isinstance(course_ref, uuid.UUID) else uuid.UUID(str(course_ref))
        except (TypeError, ValueError, AttributeError):
            text_ref = str(course_ref).strip()
            exact = stmt.where(or_(code.ilike(text_ref), name.ilike(text_ref))).limit(1)
            row = self.session.execute(exact).mappings().one_or_none()
            if row is None:
                row = self.session.execute(
                    stmt.where(or_(code.ilike(f"%{text_ref}%"), name.ilike(f"%{text_ref}%"))).order_by(code.asc()).limit(1)
                ).mappings().one_or_none()
        else:
            row = self.session.execute(stmt.where(ident == course_uuid).limit(1)).mappings().one_or_none()
        if row is None:
            raise CourseToolNotFound(f"course={course_ref!s} was not found")
        return self._row_json(row)

    def get_schedule(
        self,
        course_id,
        *,
        academic_year: str | None = None,
        semester: str | None = None,
    ) -> list[dict]:
        course_col = self._required(self.schedules, "course_id")
        stmt = select(
            self._required(self.schedules, "id").label("schedule_id"),
            course_col.label("course_id"),
            self._required(self.schedules, "academic_year").label("academic_year"),
            self._required(self.schedules, "semester").label("semester"),
            self._required(self.schedules, "weekday").label("weekday"),
            self._required(self.schedules, "start_time").label("start_time"),
            self._required(self.schedules, "end_time").label("end_time"),
            self._required(self.schedules, "classroom").label("classroom"),
            self._optional(self.schedules, "campus").label("campus")
            if self._optional(self.schedules, "campus") is not None
            else literal(None).label("campus"),
        ).where(course_col == uuid.UUID(str(course_id)))
        if academic_year:
            stmt = stmt.where(self._required(self.schedules, "academic_year") == academic_year)
        if semester:
            stmt = stmt.where(self._required(self.schedules, "semester") == semester)
        stmt = stmt.order_by(
            self._required(self.schedules, "weekday").asc(),
            self._required(self.schedules, "start_time").asc(),
        )
        return [self._row_json(row) for row in self.session.execute(stmt).mappings().all()]

    def get_prerequisites(self, course_id) -> list[dict]:
        cp_course = self._required(self.prerequisites, "course_id")
        cp_prereq = self._required(
            self.prerequisites,
            "prerequisite_course_id",
            "prerequisite_id",
        )
        prereq_course = self.courses.alias("prereq_course")
        stmt = (
            select(*self._course_columns(prereq_course, prefix="prerequisite_"))
            .select_from(self.prerequisites.join(prereq_course, cp_prereq == self._required(prereq_course, "id")))
            .where(cp_course == uuid.UUID(str(course_id)))
            .order_by(self._required(prereq_course, "code", "course_code").asc())
        )
        return [self._row_json(row) for row in self.session.execute(stmt).mappings().all()]

    def get_teachers(self, course_id) -> list[dict]:
        assignment_course = self._required(self.assignments, "course_id")
        assignment_teacher = self._required(self.assignments, "teacher_id")
        teacher_id = self._required(self.teachers, "id")
        teacher_user = self._optional(self.teachers, "user_id")
        direct_name = self._optional(self.teachers, "name", "full_name")
        employee_no = self._optional(self.teachers, "employee_no", "teacher_no")
        title = self._optional(self.teachers, "title", "professional_title")
        academic_year = self._optional(self.assignments, "academic_year", "school_year")
        semester = self._optional(self.assignments, "semester", "term")

        if teacher_user is not None:
            user_id = self._required(self.users, "id")
            user_name = self._optional(self.users, "full_name", "name", "username")
            from_clause = self.assignments.join(self.teachers, assignment_teacher == teacher_id).outerjoin(
                self.users, teacher_user == user_id
            )
            display_name = user_name if user_name is not None else direct_name
        else:
            from_clause = self.assignments.join(self.teachers, assignment_teacher == teacher_id)
            display_name = direct_name

        stmt = (
            select(
                teacher_id.label("teacher_id"),
                (display_name if display_name is not None else literal(None)).label("teacher_name"),
                (employee_no if employee_no is not None else literal(None)).label("employee_no"),
                (title if title is not None else literal(None)).label("title"),
                (academic_year if academic_year is not None else literal(None)).label("academic_year"),
                (semester if semester is not None else literal(None)).label("semester"),
            )
            .select_from(from_clause)
            .where(assignment_course == uuid.UUID(str(course_id)))
        )
        return [self._row_json(row) for row in self.session.execute(stmt).mappings().all()]


class CourseToolService:
    WEEKDAY_NAMES = {
        1: "周一",
        2: "周二",
        3: "周三",
        4: "周四",
        5: "周五",
        6: "周六",
        7: "周日",
    }

    def __init__(self, session: Session, *, parser: CourseIntentParser | None = None) -> None:
        self.session = session
        self.parser = parser or CourseIntentParser()
        self.repository = CourseRepository(session)

    @staticmethod
    def supports(query: str) -> bool:
        return CourseIntentParser.supports(query)

    def search_courses(self, query: str, *, limit: int = 10) -> list[dict]:
        intent = self.parser.parse(query)
        search_text = intent.course_hint or " ".join(intent.keywords) or query
        return self.repository.search_courses(search_text, limit=max(1, min(limit, 30)))

    def _resolve_course(self, course_ref) -> dict:
        return self.repository.get_course(course_ref)

    def _resolve_intent_course(
        self,
        intent: CourseIntent,
    ) -> dict:
        """Resolve only a real course entity from original query."""

        mentioned = (
            self.repository
            .find_courses_mentioned_in_text(
                intent.query
            )
        )

        if len(mentioned) == 1:
            return mentioned[0]

        if len(mentioned) > 1:
            labels = ", ".join(
                (
                    f"{item.get('course_code')} "
                    f"{item.get('course_name')}"
                ).strip()
                for item in mentioned[:5]
            )

            raise CourseToolError(
                "问题中识别到多门课程，无法唯一确定 CourseTool 目标："
                f"{labels}"
            )

        raise CourseToolError(
            "无法从问题中识别数据库中真实存在的具体课程；应回退到 RAG/GraphRAG 路径"
        )

    def can_answer(
        self,
        query: str,
    ) -> bool:
        """Check whether CourseTool can safely handle query."""

        if not self.supports(query):
            return False

        intent = self.parser.parse(query)

        if intent.capability is CourseCapability.SEARCH:
            return True

        mentioned = (
            self.repository
            .find_courses_mentioned_in_text(query)
        )

        return len(mentioned) == 1

    def get_course_schedule(
        self,
        course_ref,
        *,
        academic_year: str | None = None,
        semester: str | None = None,
    ) -> dict:
        course = self._resolve_course(course_ref)
        rows = self.repository.get_schedule(
            course["course_id"], academic_year=academic_year, semester=semester
        )
        for row in rows:
            row["weekday_name"] = self.WEEKDAY_NAMES.get(int(row["weekday"]), str(row["weekday"]))
        return {"course": course, "schedules": rows, "count": len(rows)}

    def get_course_prerequisites(self, course_ref) -> dict:
        course = self._resolve_course(course_ref)
        rows = self.repository.get_prerequisites(course["course_id"])
        return {"course": course, "prerequisites": rows, "count": len(rows)}

    def get_course_teacher(self, course_ref) -> dict:
        course = self._resolve_course(course_ref)
        rows = self.repository.get_teachers(course["course_id"])
        return {"course": course, "teachers": rows, "count": len(rows)}

    def answer(self, query: str) -> CourseToolResult:
        intent = self.parser.parse(query)
        if intent.capability is CourseCapability.SEARCH:
            courses = self.search_courses(query)
            if courses:
                summary = "；".join(f"{item['course_code']} {item['course_name']}" for item in courses[:6])
                answer = f"结构化课程目录中找到 {len(courses)} 门匹配课程：{summary}。"
            else:
                answer = "结构化课程目录中没有找到匹配课程。"
            return CourseToolResult(
                capability=intent.capability,
                answer=answer,
                data={"courses": courses, "count": len(courses)},
            )

        course = self._resolve_intent_course(
            intent
        )
        course_ref = course["course_id"]

        if intent.capability is CourseCapability.SCHEDULE:
            data = self.get_course_schedule(course_ref)
            course = data["course"]
            if data["schedules"]:
                summary = "；".join(
                    f"{item['weekday_name']} {item['start_time']}-{item['end_time']} {item['classroom']}"
                    for item in data["schedules"]
                )
                answer = f"{course['course_name']}的结构化课程安排为：{summary}。"
            else:
                answer = f"当前结构化数据中没有{course['course_name']}的课程安排。"
            return CourseToolResult(capability=intent.capability, answer=answer, data=data)

        if intent.capability is CourseCapability.PREREQUISITES:
            data = self.get_course_prerequisites(course_ref)
            course = data["course"]
            values = data["prerequisites"]
            if values:
                summary = "、".join(item["prerequisite_course_name"] for item in values)
                answer = f"{course['course_name']}的结构化先修课程为：{summary}。"
            else:
                answer = f"当前结构化数据中没有记录{course['course_name']}的先修课程。"
            return CourseToolResult(capability=intent.capability, answer=answer, data=data)

        data = self.get_course_teacher(course_ref)
        course = data["course"]
        values = data["teachers"]
        if values:
            summary = "、".join(
                str(item.get("teacher_name") or item.get("employee_no") or item["teacher_id"])
                for item in values
            )
            answer = f"{course['course_name']}当前结构化任课教师记录为：{summary}。"
        else:
            answer = f"当前结构化数据中没有记录{course['course_name']}的任课教师。"
        return CourseToolResult(capability=intent.capability, answer=answer, data=data)
