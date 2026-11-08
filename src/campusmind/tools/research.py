from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import re
import uuid
from sqlalchemy import MetaData, Table, and_, func, or_, select
from sqlalchemy.orm import Session

"""CampusMind research domain."""

# ---- app/campus_tools/research.py ----
class ResearchToolError(RuntimeError):
    pass


class ResearchToolNotFound(ResearchToolError):
    pass


class ResearchCapability(str, Enum):
    TEACHERS = "research_teacher_search"
    PAPERS = "research_paper_search"
    AREAS = "research_area_search"
    LABS = "research_lab_search"
    PROJECTS = "research_project_search"


@dataclass(slots=True)
class ResearchIntent:
    query: str
    capability: ResearchCapability
    keyword: str


@dataclass(slots=True)
class ResearchToolResult:
    capability: ResearchCapability
    answer: str
    data: dict
    source: str = "postgresql"
    read_only: bool = True


class ResearchIntentParser:
    _CAPABILITY_MARKERS = {
        ResearchCapability.TEACHERS: (
            "搜索教师", "查询教师", "查找教师", "科研教师", "教师科研档案", "教师档案",
        ),
        ResearchCapability.PAPERS: (
            "搜索论文", "查询论文", "查论文", "论文检索", "科研论文",
        ),
        ResearchCapability.AREAS: (
            "搜索研究方向", "查询研究方向", "研究方向列表", "搜索科研方向", "查询科研方向", "科研方向列表",
        ),
        ResearchCapability.LABS: (
            "搜索实验室", "查询实验室", "查实验室", "科研实验室", "实验室列表",
        ),
        ResearchCapability.PROJECTS: (
            "搜索科研项目", "查询科研项目", "查科研项目", "科研项目列表", "搜索研究项目", "查询研究项目",
        ),
    }
    _GENERIC = (
        "帮我", "请帮我", "请", "搜索", "查询", "查找", "看看", "一下", "相关", "有哪些", "是什么",
    )

    @staticmethod
    def _compact(query: str) -> str:
        return "".join((query or "").lower().split())

    @classmethod
    def supports(cls, query: str) -> bool:
        q = cls._compact(query)
        return any(marker in q for markers in cls._CAPABILITY_MARKERS.values() for marker in markers)

    @classmethod
    def capability(cls, query: str) -> ResearchCapability:
        q = cls._compact(query)
        for capability, markers in cls._CAPABILITY_MARKERS.items():
            if any(marker in q for marker in markers):
                return capability
        raise ResearchToolError("query is not an explicit Research Tool request")

    @classmethod
    def parse(cls, query: str) -> ResearchIntent:
        raw = (query or "").strip()
        capability = cls.capability(raw)
        normalized = raw
        for markers in cls._CAPABILITY_MARKERS.values():
            for marker in markers:
                normalized = normalized.replace(marker, " ")
        for token in cls._GENERIC:
            normalized = normalized.replace(token, " ")
        normalized = re.sub(r"[《》\"“”‘’？?，,。！!、:：;；()（）]", " ", normalized)
        keyword = " ".join(item for item in normalized.split() if item).strip()
        return ResearchIntent(query=raw, capability=capability, keyword=keyword)


class ResearchRepository:
    def __init__(self, session: Session) -> None:
        self.session = session
        metadata = MetaData()
        bind = session.get_bind()
        self.profiles = Table("research_teacher_profiles", metadata, autoload_with=bind)
        self.areas = Table("research_areas", metadata, autoload_with=bind)
        self.teacher_areas = Table("teacher_research_areas", metadata, autoload_with=bind)
        self.labs = Table("research_labs", metadata, autoload_with=bind)
        self.lab_memberships = Table("research_lab_memberships", metadata, autoload_with=bind)
        self.projects = Table("research_projects", metadata, autoload_with=bind)
        self.project_members = Table("research_project_members", metadata, autoload_with=bind)
        self.papers = Table("research_papers", metadata, autoload_with=bind)
        self.paper_authors = Table("research_paper_authors", metadata, autoload_with=bind)

    @staticmethod
    def _json(row) -> dict:
        result = {}
        for key, value in dict(row).items():
            if isinstance(value, uuid.UUID):
                value = str(value)
            elif hasattr(value, "isoformat"):
                value = value.isoformat()
            result[key] = value
        return result

    def _teacher_areas(self, teacher_id) -> list[dict]:
        rows = self.session.execute(
            select(
                self.areas.c.code,
                self.areas.c.name,
                self.areas.c.description,
                self.teacher_areas.c.is_primary,
            )
            .join(self.teacher_areas, self.teacher_areas.c.research_area_id == self.areas.c.id)
            .where(self.teacher_areas.c.teacher_id == uuid.UUID(str(teacher_id)))
            .order_by(self.teacher_areas.c.is_primary.desc(), self.areas.c.name.asc())
        ).mappings().all()
        return [self._json(row) for row in rows]

    def _member_profiles(self, membership: Table, owner_col, owner_id) -> list[dict]:
        rows = self.session.execute(
            select(
                self.profiles.c.teacher_id,
                self.profiles.c.display_name,
                self.profiles.c.title,
                membership.c.role,
            )
            .join(membership, membership.c.teacher_id == self.profiles.c.teacher_id)
            .where(owner_col == uuid.UUID(str(owner_id)))
            .order_by(self.profiles.c.display_name.asc())
        ).mappings().all()
        return [self._json(row) for row in rows]

    def search_teachers(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        stmt = (
            select(
                self.profiles.c.teacher_id,
                self.profiles.c.display_name,
                self.profiles.c.title,
                self.profiles.c.bio,
                self.profiles.c.homepage_url,
            )
            .outerjoin(self.teacher_areas, self.teacher_areas.c.teacher_id == self.profiles.c.teacher_id)
            .outerjoin(self.areas, self.areas.c.id == self.teacher_areas.c.research_area_id)
        )
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(
                self.profiles.c.display_name.ilike(pattern),
                self.profiles.c.title.ilike(pattern),
                self.profiles.c.bio.ilike(pattern),
                self.areas.c.name.ilike(pattern),
                self.areas.c.description.ilike(pattern),
            ))
        rows = self.session.execute(stmt.distinct().order_by(self.profiles.c.display_name.asc()).limit(limit)).mappings().all()
        result = []
        for row in rows:
            item = self._json(row)
            item["research_areas"] = self._teacher_areas(item["teacher_id"])
            result.append(item)
        return result

    def search_papers(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        stmt = select(
            self.papers.c.id.label("paper_id"), self.papers.c.title, self.papers.c.abstract,
            self.papers.c.venue, self.papers.c.published_year, self.papers.c.doi, self.papers.c.url,
        )
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(self.papers.c.title.ilike(pattern), self.papers.c.abstract.ilike(pattern), self.papers.c.venue.ilike(pattern)))
        rows = self.session.execute(stmt.order_by(self.papers.c.published_year.desc(), self.papers.c.title.asc()).limit(limit)).mappings().all()
        result = []
        for row in rows:
            item = self._json(row)
            authors = self.session.execute(
                select(self.profiles.c.teacher_id, self.profiles.c.display_name, self.paper_authors.c.author_order)
                .join(self.paper_authors, self.paper_authors.c.teacher_id == self.profiles.c.teacher_id)
                .where(self.paper_authors.c.paper_id == uuid.UUID(item["paper_id"]))
                .order_by(self.paper_authors.c.author_order.asc())
            ).mappings().all()
            item["authors"] = [self._json(author) for author in authors]
            result.append(item)
        return result

    def search_areas(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        stmt = select(self.areas.c.id.label("research_area_id"), self.areas.c.code, self.areas.c.name, self.areas.c.description)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(self.areas.c.name.ilike(pattern), self.areas.c.description.ilike(pattern), self.areas.c.code.ilike(pattern)))
        rows = self.session.execute(stmt.order_by(self.areas.c.name.asc()).limit(limit)).mappings().all()
        result = []
        for row in rows:
            item = self._json(row)
            count = self.session.scalar(select(func.count()).select_from(self.teacher_areas).where(self.teacher_areas.c.research_area_id == uuid.UUID(item["research_area_id"])))
            item["teacher_count"] = int(count or 0)
            result.append(item)
        return result

    def search_labs(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        stmt = select(self.labs.c.id.label("lab_id"), self.labs.c.code, self.labs.c.name, self.labs.c.description, self.labs.c.website_url)
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(self.labs.c.name.ilike(pattern), self.labs.c.description.ilike(pattern), self.labs.c.code.ilike(pattern)))
        rows = self.session.execute(stmt.order_by(self.labs.c.name.asc()).limit(limit)).mappings().all()
        result = []
        for row in rows:
            item = self._json(row)
            item["members"] = self._member_profiles(self.lab_memberships, self.lab_memberships.c.lab_id, item["lab_id"])
            result.append(item)
        return result

    def search_projects(self, query: str, *, limit: int = 10) -> list[dict]:
        q = (query or "").strip()
        stmt = select(
            self.projects.c.id.label("project_id"), self.projects.c.code, self.projects.c.name,
            self.projects.c.summary, self.projects.c.status, self.projects.c.funding_source,
            self.projects.c.start_date, self.projects.c.end_date,
        )
        if q:
            pattern = f"%{q}%"
            stmt = stmt.where(or_(self.projects.c.name.ilike(pattern), self.projects.c.summary.ilike(pattern), self.projects.c.code.ilike(pattern), self.projects.c.funding_source.ilike(pattern)))
        rows = self.session.execute(stmt.order_by(self.projects.c.name.asc()).limit(limit)).mappings().all()
        result = []
        for row in rows:
            item = self._json(row)
            item["members"] = self._member_profiles(self.project_members, self.project_members.c.project_id, item["project_id"])
            result.append(item)
        return result


class ResearchToolService:
    def __init__(self, session: Session, *, repository: ResearchRepository | None = None) -> None:
        self.session = session
        self.repository = repository or ResearchRepository(session)

    @classmethod
    def supports(cls, query: str) -> bool:
        return ResearchIntentParser.supports(query)

    def search_teacher(self, query: str, *, limit: int = 10) -> list[dict]:
        return self.repository.search_teachers(query, limit=max(1, min(limit, 30)))

    def search_papers(self, query: str, *, limit: int = 10) -> list[dict]:
        return self.repository.search_papers(query, limit=max(1, min(limit, 30)))

    def search_research_area(self, query: str, *, limit: int = 10) -> list[dict]:
        return self.repository.search_areas(query, limit=max(1, min(limit, 30)))

    def search_lab(self, query: str, *, limit: int = 10) -> list[dict]:
        return self.repository.search_labs(query, limit=max(1, min(limit, 30)))

    def search_projects(self, query: str, *, limit: int = 10) -> list[dict]:
        return self.repository.search_projects(query, limit=max(1, min(limit, 30)))

    def answer(self, query: str) -> ResearchToolResult:
        intent = ResearchIntentParser.parse(query)
        keyword = intent.keyword
        if intent.capability is ResearchCapability.TEACHERS:
            values = self.search_teacher(keyword)
            names = [item["display_name"] for item in values]
            answer = f"科研教师查询结果：{'、'.join(names)}。" if names else "没有找到匹配的科研教师。"
            data = {"query": keyword, "teachers": values, "count": len(values)}
        elif intent.capability is ResearchCapability.PAPERS:
            values = self.search_papers(keyword)
            titles = [item["title"] for item in values]
            answer = f"科研论文查询结果：{'；'.join(titles)}。" if titles else "没有找到匹配的科研论文。"
            data = {"query": keyword, "papers": values, "count": len(values)}
        elif intent.capability is ResearchCapability.AREAS:
            values = self.search_research_area(keyword)
            names = [item["name"] for item in values]
            answer = f"研究方向查询结果：{'、'.join(names)}。" if names else "没有找到匹配的研究方向。"
            data = {"query": keyword, "research_areas": values, "count": len(values)}
        elif intent.capability is ResearchCapability.LABS:
            values = self.search_lab(keyword)
            names = [item["name"] for item in values]
            answer = f"科研实验室查询结果：{'、'.join(names)}。" if names else "没有找到匹配的科研实验室。"
            data = {"query": keyword, "labs": values, "count": len(values)}
        else:
            values = self.search_projects(keyword)
            names = [item["name"] for item in values]
            answer = f"科研项目查询结果：{'、'.join(names)}。" if names else "没有找到匹配的科研项目。"
            data = {"query": keyword, "projects": values, "count": len(values)}
        return ResearchToolResult(capability=intent.capability, answer=answer, data=data)
