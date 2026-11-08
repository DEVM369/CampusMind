from __future__ import annotations

import json
import os
from datetime import date, datetime, timezone
from pathlib import Path

from sqlalchemy import select

from campusmind.platform.auth import hash_password
from campusmind.platform.db import (
    College, Course, CoursePrerequisite, Department, Document, DocumentChunk, DocumentVersion,
    EvaluationCase, EvaluationDataset, KnowledgeBase, Major, Permission, Role, RolePermission,
    Student, StudentCourse, Teacher, TeachingAssignment, User, UserRole,
)
from campusmind.platform.db import get_session_factory

ROOT = Path(__file__).resolve().parents[1]
DATA = json.loads((ROOT / "datasets" / "core_seed.json").read_text(encoding="utf-8"))


def one(session, model, **where):
    return session.scalar(select(model).filter_by(**where))


def seed() -> None:
    demo_password = os.environ.get("CAMPUSMIND_DEMO_PASSWORD", "")
    admin_password = os.environ.get("CAMPUSMIND_ADMIN_PASSWORD", "")
    if len(demo_password) < 12 or len(admin_password) < 12 or demo_password == admin_password:
        raise RuntimeError(
            "Set distinct CAMPUSMIND_DEMO_PASSWORD and CAMPUSMIND_ADMIN_PASSWORD "
            "(at least 12 characters each) before seeding"
        )

    def ensure_password(user: User, password: str) -> None:
        if not user.password_hash:
            user.password_hash = hash_password(password)

    with get_session_factory().begin() as session:
        # RBAC foundation
        role_specs = {
            "admin": ("管理员", "系统与知识库管理员"),
            "student": ("学生", "普通学生用户"),
            "teacher": ("教师", "教师用户"),
        }
        roles = {}
        for code, (name, desc) in role_specs.items():
            obj = one(session, Role, code=code) or Role(code=code, name=name, description=desc)
            session.add(obj); session.flush(); roles[code] = obj

        permission_specs = {
            "knowledge.read": "读取授权知识",
            "knowledge.manage": "管理知识库",
            "student.self.read": "读取本人学业数据",
            "course.read": "读取课程信息",
            "graph.read": "读取知识图谱",
            "tool.reserve": "执行需要确认的预约类工具",
            "audit.read": "查看审计日志",
            "admin.manage": "系统管理",
        }
        permissions = {}
        for code, name in permission_specs.items():
            obj = one(session, Permission, code=code) or Permission(code=code, name=name, description=name)
            session.add(obj); session.flush(); permissions[code] = obj
        role_perms = {
            "student": ["knowledge.read", "student.self.read", "course.read", "graph.read", "tool.reserve"],
            "teacher": ["knowledge.read", "course.read", "graph.read", "tool.reserve"],
            "admin": list(permission_specs),
        }
        for role_code, perm_codes in role_perms.items():
            for perm_code in perm_codes:
                if not session.get(RolePermission, {"role_id": roles[role_code].id, "permission_id": permissions[perm_code].id}):
                    session.add(RolePermission(role_id=roles[role_code].id, permission_id=permissions[perm_code].id))

        # Campus organization
        college_spec = DATA["campus"]["college"]
        college = one(session, College, code=college_spec["code"]) or College(**college_spec)
        session.add(college); session.flush()
        departments = {}
        for spec in DATA["campus"]["departments"]:
            obj = one(session, Department, code=spec["code"]) or Department(college_id=college.id, **spec)
            session.add(obj); session.flush(); departments[spec["code"]] = obj
        majors = {}
        for spec in DATA["campus"]["majors"]:
            obj = one(session, Major, code=spec["code"])
            if obj is None:
                obj = Major(
                    college_id=college.id, department_id=departments[spec["department"]].id,
                    code=spec["code"], name=spec["name"], graduation_credits=spec["graduation_credits"],
                )
            session.add(obj); session.flush(); majors[spec["code"]] = obj

        # Courses and prerequisite graph source data
        courses = {}
        for spec in DATA["courses"]:
            obj = one(session, Course, code=spec["code"])
            if obj is None:
                obj = Course(
                    department_id=departments[spec["department"]].id, code=spec["code"], name=spec["name"],
                    credits=spec["credits"], course_type=spec["type"], description=f"CampusMind synthetic course: {spec['name']}",
                )
            session.add(obj); session.flush(); courses[spec["code"]] = obj
        for course_code, prerequisite_code in DATA["prerequisites"]:
            key = {"course_id": courses[course_code].id, "prerequisite_course_id": courses[prerequisite_code].id}
            if not session.get(CoursePrerequisite, key):
                session.add(CoursePrerequisite(**key))

        # Users / student / teachers
        admin = one(session, User, username="admin") or User(
            username="admin", email="admin@campusmind.local", full_name="CampusMind 管理员", is_superuser=True
        )
        ensure_password(admin, admin_password)
        session.add(admin); session.flush()
        if not session.get(UserRole, {"user_id": admin.id, "role_id": roles["admin"].id}):
            session.add(UserRole(user_id=admin.id, role_id=roles["admin"].id))

        s = DATA["people"]["student"]
        student_user = one(session, User, username=s["username"]) or User(
            username=s["username"], email=s["email"], full_name=s["full_name"]
        )
        ensure_password(student_user, demo_password)
        session.add(student_user); session.flush()
        if not session.get(UserRole, {"user_id": student_user.id, "role_id": roles["student"].id}):
            session.add(UserRole(user_id=student_user.id, role_id=roles["student"].id))
        student = one(session, Student, student_no=s["student_no"]) or Student(
            user_id=student_user.id, student_no=s["student_no"], major_id=majors[s["major"]].id,
            enrollment_year=s["enrollment_year"], grade_level=s["grade_level"], total_credits=s["total_credits"],
            expected_graduation_date=date(2028, 6, 30),
        )
        session.add(student); session.flush()

        completed = [
            ("MATH101", "2024-Fall", 88, 5), ("MATH201", "2025-Spring", 84, 3),
            ("CS101", "2024-Fall", 92, 3), ("CS201", "2025-Spring", 87, 4),
        ]
        for code, semester, score, credits in completed:
            existing = one(session, StudentCourse, student_id=student.id, course_id=courses[code].id, semester=semester)
            if existing is None:
                session.add(StudentCourse(
                    student_id=student.id, course_id=courses[code].id, semester=semester,
                    status="completed", score=score, credits_earned=credits,
                ))

        teacher_objs = {}
        for t in DATA["people"]["teachers"]:
            user = one(session, User, username=t["username"]) or User(username=t["username"], email=t["email"], full_name=t["full_name"])
            ensure_password(user, demo_password)
            session.add(user); session.flush()
            if not session.get(UserRole, {"user_id": user.id, "role_id": roles["teacher"].id}):
                session.add(UserRole(user_id=user.id, role_id=roles["teacher"].id))
            teacher = one(session, Teacher, employee_no=t["employee_no"]) or Teacher(
                user_id=user.id, employee_no=t["employee_no"], department_id=departments[t["department"]].id,
                title=t["title"], bio=t["bio"],
            )
            session.add(teacher); session.flush(); teacher_objs[t["employee_no"]] = teacher
        assignments = [("T1001", "AI302"), ("T1001", "AI402"), ("T1002", "AI301"), ("T1002", "AI401")]
        for employee_no, course_code in assignments:
            if one(session, TeachingAssignment, teacher_id=teacher_objs[employee_no].id, course_id=courses[course_code].id, semester="2026-Fall") is None:
                session.add(TeachingAssignment(teacher_id=teacher_objs[employee_no].id, course_id=courses[course_code].id, semester="2026-Fall"))

        # Four first-phase knowledge bases from the implementation guide.
        kbs = {}
        for spec in DATA["knowledge_bases"]:
            obj = one(session, KnowledgeBase, code=spec["code"]) or KnowledgeBase(
                code=spec["code"], name=spec["name"], domain=spec["domain"],
                description=f"CampusMind synthetic {spec['name']}", visibility="campus", status="active",
            )
            session.add(obj); session.flush(); kbs[spec["code"]] = obj

        # Seed text evidence only; embeddings are intentionally NULL until the RAG embedding pass.
        doc = one(session, Document, object_key="seed/academic/2026-software-engineering-training-program.md")
        if doc is None:
            doc = Document(
                knowledge_base_id=kbs["academic"].id, title="2026软件工程培养方案（合成测试）",
                object_key="seed/academic/2026-software-engineering-training-program.md",
                mime_type="text/markdown", document_type="training_program", status="parsed",
            )
            session.add(doc); session.flush()
        version = one(session, DocumentVersion, document_id=doc.id, version="2026")
        if version is None:
            version = DocumentVersion(
                document_id=doc.id, version="2026", object_key=doc.object_key, status="active",
                effective_from=date(2026, 9, 1), published_at=datetime(2026, 7, 1, tzinfo=timezone.utc),
                department="计算机学院", metadata_json={"major": "软件工程", "synthetic": True},
            )
            session.add(version); session.flush()
        chunks = [
            (0, "毕业要求", "软件工程专业本科毕业最低需要修满160学分。", 16),
            (1, "人工智能方向", "学习深度学习前建议完成机器学习与线性代数；机器学习需要线性代数与Python程序设计基础。", 22),
        ]
        for idx, section, content, page in chunks:
            if one(session, DocumentChunk, document_version_id=version.id, chunk_index=idx) is None:
                session.add(DocumentChunk(
                    document_id=doc.id, document_version_id=version.id, knowledge_base_id=kbs["academic"].id,
                    chunk_index=idx, content=content, token_count=None, page=page, chapter="培养方案",
                    section=section, department="计算机学院", document_type="training_program",
                    effective_date=date(2026, 9, 1), permission_level="campus",
                    metadata_json={"major": "软件工程", "synthetic": True}, embedding=None,
                ))

        research_doc = one(session, Document, object_key="seed/research/teacher-profiles.md")
        if research_doc is None:
            research_doc = Document(
                knowledge_base_id=kbs["research"].id, title="人工智能系教师科研简介（合成测试）",
                object_key="seed/research/teacher-profiles.md", mime_type="text/markdown",
                document_type="teacher_profile", status="parsed",
            )
            session.add(research_doc); session.flush()
        research_version = one(session, DocumentVersion, document_id=research_doc.id, version="2026")
        if research_version is None:
            research_version = DocumentVersion(
                document_id=research_doc.id, version="2026", object_key=research_doc.object_key, status="active",
                effective_from=date(2026, 9, 1), published_at=datetime(2026, 8, 20, tzinfo=timezone.utc),
                department="人工智能系", metadata_json={"synthetic": True},
            )
            session.add(research_version); session.flush()
        if one(session, DocumentChunk, document_version_id=research_version.id, chunk_index=0) is None:
            session.add(DocumentChunk(
                document_id=research_doc.id, document_version_id=research_version.id, knowledge_base_id=kbs["research"].id,
                chunk_index=0, content="李明教授研究知识图谱、GraphRAG、检索增强生成与大语言模型，并教授知识图谱和大语言模型导论。",
                page=1, chapter="教师简介", section="李明教授", department="人工智能系",
                document_type="teacher_profile", effective_date=date(2026, 9, 1), permission_level="campus",
                metadata_json={"employee_no": "T1001", "synthetic": True}, embedding=None,
            ))

        benchmark = one(session, EvaluationDataset, name="CampusRAG Smoke Benchmark", version="0.1")
        if benchmark is None:
            benchmark = EvaluationDataset(
                name="CampusRAG Smoke Benchmark", version="0.1",
                description="Small synthetic smoke dataset; expanded to 300-500 questions during the evaluation stage.", status="active",
            )
            session.add(benchmark); session.flush()
        cases = [
            ("Policy", "软件工程专业毕业至少需要多少学分？", "160学分"),
            ("Graph", "学习深度学习之前应该先学习哪些课程？", "机器学习、线性代数"),
            ("SQL", "学号20240001的学生当前记录了多少总学分？", "86学分"),
            ("Multi-hop", "谁研究知识图谱并教授大语言模型相关课程？", "李明教授"),
        ]
        for category, question, expected in cases:
            if one(session, EvaluationCase, dataset_id=benchmark.id, question=question) is None:
                session.add(EvaluationCase(
                    dataset_id=benchmark.id, category=category, question=question, expected_answer=expected,
                    expected_evidence={}, metadata_json={"synthetic": True},
                ))

    print("CampusMind baseline seed data applied successfully.")


if __name__ == "__main__":
    seed()
