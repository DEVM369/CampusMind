from __future__ import annotations

from datetime import date, datetime, timezone
import uuid

from sqlalchemy import MetaData, Table, insert, select, update

from campusmind.platform.db import get_session_factory


NS = uuid.UUID("00000000-0000-0000-0000-000000001900")

AREAS = (
    ("RA-KG", "知识图谱", "知识表示、图谱构建、实体消歧、图推理与 GraphRAG。"),
    ("RA-LLM", "大语言模型", "大语言模型、提示学习、模型评测与校园智能应用。"),
    ("RA-RAG", "检索增强生成", "RAG、Hybrid RAG、GraphRAG、检索评测与可信生成。"),
    ("RA-RL", "强化学习", "强化学习、马尔可夫决策过程与智能体决策。"),
)

LABS = (
    ("LAB-KGE", "智能知识工程实验室", "研究知识图谱、GraphRAG、RAG 与可信知识服务。"),
    ("LAB-LAI", "大模型与智能体实验室", "研究大语言模型、Agentic RAG、多智能体与工具调用。"),
)

PROJECTS = (
    ("PRJ-CM-GRAPH", "CampusMind GraphRAG 校园知识服务", "面向高校知识服务的 GraphRAG、多跳推理与来源追踪。", "active", "校级人工智能专项", date(2026, 1, 1), date(2027, 12, 31)),
    ("PRJ-CM-AGENT", "Agentic Campus 业务协同研究", "研究 Agentic RAG、Human-in-the-loop 与校园业务工具协同。", "active", "智慧校园联合项目", date(2026, 3, 1), date(2028, 2, 29)),
)

PAPERS = (
    ("GraphRAG for Campus Knowledge Services", "A provenance-aware GraphRAG framework for multi-hop campus knowledge services.", "Campus AI Research Workshop", 2026, "10.0000/campusmind.graphrag"),
    ("Reliable Agentic Retrieval for Academic Services", "A human-in-the-loop Agentic RAG architecture for academic and campus service workflows.", "Journal of Intelligent Campus Systems", 2026, "10.0000/campusmind.agentic"),
    ("Knowledge Graph Enhanced Course Recommendation", "Knowledge graph reasoning for prerequisite-aware course recommendation.", "Education Knowledge Engineering Conference", 2025, "10.0000/campusmind.coursekg"),
)


def uid(kind: str, key: str) -> uuid.UUID:
    return uuid.uuid5(NS, f"{kind}:{key}")


def _display_name(session, teachers: Table, users: Table | None, row: dict, index: int) -> str:
    for key in ("display_name", "full_name", "name"):
        value = row.get(key)
        if value:
            return str(value)
    if users is not None and "user_id" in teachers.c and row.get("user_id") is not None:
        user = session.execute(select(users).where(users.c.id == row["user_id"])).mappings().one_or_none()
        if user:
            for key in ("display_name", "full_name", "name", "username"):
                value = user.get(key)
                if value:
                    return str(value)
    if row.get("employee_no"):
        return str(row["employee_no"])
    return f"科研教师{index + 1}"


def _upsert(session, table: Table, where_clause, values: dict, create_values: dict | None = None) -> None:
    existing = session.execute(select(table.c[list(table.primary_key.columns)[0].name]).where(where_clause).limit(1)).first()
    if existing is None:
        session.execute(insert(table).values(**(create_values or values)))
    else:
        session.execute(update(table).where(where_clause).values(**values))


def _ensure_link(session, table: Table, conditions, values: dict) -> None:
    if session.execute(select(1).select_from(table).where(*conditions).limit(1)).first() is None:
        session.execute(insert(table).values(**values))


def main() -> None:
    factory = get_session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        md = MetaData()
        bind = session.get_bind()
        teachers = Table("teachers", md, autoload_with=bind)
        users = Table("users", md, autoload_with=bind)
        profiles = Table("research_teacher_profiles", md, autoload_with=bind)
        areas = Table("research_areas", md, autoload_with=bind)
        teacher_areas = Table("teacher_research_areas", md, autoload_with=bind)
        labs = Table("research_labs", md, autoload_with=bind)
        lab_memberships = Table("research_lab_memberships", md, autoload_with=bind)
        projects = Table("research_projects", md, autoload_with=bind)
        project_members = Table("research_project_members", md, autoload_with=bind)
        papers = Table("research_papers", md, autoload_with=bind)
        paper_authors = Table("research_paper_authors", md, autoload_with=bind)

        teacher_rows = session.execute(select(teachers).order_by(teachers.c.id.asc()).limit(3)).mappings().all()
        if not teacher_rows:
            raise RuntimeError("baseline teacher seed is missing; cannot attach research data")
        teacher_ids = [row["id"] for row in teacher_rows]

        titles = ("教授", "副教授", "讲师")
        for index, row in enumerate(teacher_rows):
            teacher_id = row["id"]
            name = _display_name(session, teachers, users, dict(row), index)
            values = {
                "display_name": name,
                "title": str(row.get("title") or titles[index % len(titles)]),
                "bio": "CampusMind 合成科研档案，用于 Research Tool 与后续 Research Agent 验证。",
                "homepage_url": f"https://campusmind.example.edu/research/teachers/{teacher_id}",
                "updated_at": now,
            }
            _upsert(
                session,
                profiles,
                profiles.c.teacher_id == teacher_id,
                values,
                {"teacher_id": teacher_id, "created_at": now, **values},
            )

        area_ids = {}
        for code, name, description in AREAS:
            area_id = uid("area", code)
            area_ids[code] = area_id
            values = {"name": name, "description": description, "updated_at": now}
            _upsert(session, areas, areas.c.id == area_id, values, {"id": area_id, "code": code, "created_at": now, **values})

        area_plan = (
            (0, "RA-KG", True), (0, "RA-RAG", False),
            (min(1, len(teacher_ids)-1), "RA-LLM", True), (min(1, len(teacher_ids)-1), "RA-RAG", False),
            (min(2, len(teacher_ids)-1), "RA-RL", True),
        )
        for index, area_code, primary in area_plan:
            teacher_id = teacher_ids[index]
            area_id = area_ids[area_code]
            _ensure_link(session, teacher_areas,
                         (teacher_areas.c.teacher_id == teacher_id, teacher_areas.c.research_area_id == area_id),
                         {"teacher_id": teacher_id, "research_area_id": area_id, "is_primary": primary, "created_at": now})

        lab_ids = {}
        for code, name, description in LABS:
            lab_id = uid("lab", code); lab_ids[code] = lab_id
            values = {"name": name, "description": description, "website_url": f"https://campusmind.example.edu/research/labs/{code.lower()}", "updated_at": now}
            _upsert(session, labs, labs.c.id == lab_id, values, {"id": lab_id, "code": code, "created_at": now, **values})
        for lab_code, teacher_index, role in (("LAB-KGE", 0, "负责人"), ("LAB-KGE", min(1, len(teacher_ids)-1), "成员"), ("LAB-LAI", min(1, len(teacher_ids)-1), "负责人")):
            lab_id, teacher_id = lab_ids[lab_code], teacher_ids[teacher_index]
            _ensure_link(session, lab_memberships,
                         (lab_memberships.c.lab_id == lab_id, lab_memberships.c.teacher_id == teacher_id),
                         {"lab_id": lab_id, "teacher_id": teacher_id, "role": role, "created_at": now})

        project_ids = {}
        for code, name, summary, status, funding_source, start_date, end_date in PROJECTS:
            project_id = uid("project", code); project_ids[code] = project_id
            values = {"name": name, "summary": summary, "status": status, "funding_source": funding_source, "start_date": start_date, "end_date": end_date, "updated_at": now}
            _upsert(session, projects, projects.c.id == project_id, values, {"id": project_id, "code": code, "created_at": now, **values})
        for project_code, teacher_index, role in (("PRJ-CM-GRAPH", 0, "负责人"), ("PRJ-CM-GRAPH", min(1, len(teacher_ids)-1), "骨干"), ("PRJ-CM-AGENT", min(1, len(teacher_ids)-1), "负责人")):
            project_id, teacher_id = project_ids[project_code], teacher_ids[teacher_index]
            _ensure_link(session, project_members,
                         (project_members.c.project_id == project_id, project_members.c.teacher_id == teacher_id),
                         {"project_id": project_id, "teacher_id": teacher_id, "role": role, "created_at": now})

        paper_ids = []
        for title, abstract, venue, year, doi in PAPERS:
            paper_id = uid("paper", title); paper_ids.append(paper_id)
            values = {"abstract": abstract, "venue": venue, "published_year": year, "doi": doi, "url": f"https://campusmind.example.edu/research/papers/{paper_id}", "updated_at": now}
            _upsert(session, papers, papers.c.id == paper_id, values, {"id": paper_id, "title": title, "created_at": now, **values})
        author_plan = ((0, 0, 1), (0, min(1, len(teacher_ids)-1), 2), (1, min(1, len(teacher_ids)-1), 1), (2, 0, 1))
        for paper_index, teacher_index, order in author_plan:
            paper_id, teacher_id = paper_ids[paper_index], teacher_ids[teacher_index]
            _ensure_link(session, paper_authors,
                         (paper_authors.c.paper_id == paper_id, paper_authors.c.teacher_id == teacher_id),
                         {"paper_id": paper_id, "teacher_id": teacher_id, "author_order": order, "created_at": now})

        session.commit()

    print(f"CampusMind synthetic research domain applied successfully. teachers={len(teacher_ids)}, areas={len(AREAS)}, labs={len(LABS)}, projects={len(PROJECTS)}, papers={len(PAPERS)}")


if __name__ == "__main__":
    main()
