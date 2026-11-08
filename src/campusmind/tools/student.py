from __future__ import annotations

import uuid
from sqlalchemy import select
from sqlalchemy.orm import Session
from campusmind.platform.db import College, Course, Department, Major, Student, StudentCourse, User
from enum import Enum
from pydantic import BaseModel, Field

"""CampusMind student domain."""

# ---- app/campus_sql/repository.py ----
class StudentContextNotFound(LookupError):
    pass


class StudentSqlRepository:
    """Read-only, identity-bound SQL repository.

    Every query starts from Student.user_id == actor_user_id. There is no
    target_student_id parameter, so the service cannot use this repository to
    read another student's private records.
    """

    def __init__(self, session: Session) -> None:
        self.session = session

    def _profile_row(self, actor_user_id: uuid.UUID):
        stmt = (
            select(Student, User, Major, Department, College)
            .join(User, User.id == Student.user_id)
            .join(Major, Major.id == Student.major_id)
            .join(College, College.id == Major.college_id)
            .outerjoin(Department, Department.id == Major.department_id)
            .where(Student.user_id == actor_user_id)
        )
        row = self.session.execute(stmt).one_or_none()
        if row is None:
            raise StudentContextNotFound(
                f"No student profile is bound to actor_user_id={actor_user_id}"
            )
        return row

    def get_profile(self, actor_user_id: uuid.UUID) -> dict:
        student, user, major, department, college = self._profile_row(actor_user_id)
        return {
            "user_id": str(user.id),
            "student_id": str(student.id),
            "student_no": student.student_no,
            "full_name": user.full_name,
            "major_code": major.code,
            "major_name": major.name,
            "department_name": department.name if department else None,
            "college_name": college.name,
            "enrollment_year": student.enrollment_year,
            "grade_level": student.grade_level,
            "expected_graduation_date": (
                student.expected_graduation_date.isoformat()
                if student.expected_graduation_date
                else None
            ),
        }

    def get_credit_summary(self, actor_user_id: uuid.UUID) -> dict:
        student, _user, major, _department, _college = self._profile_row(actor_user_id)
        earned = float(student.total_credits or 0)
        required = float(major.graduation_credits or 0)
        remaining = max(required - earned, 0.0)
        completion_rate = (earned / required * 100.0) if required > 0 else 0.0
        return {
            "student_id": str(student.id),
            "major_name": major.name,
            "earned_credits": earned,
            "graduation_credits": required,
            "remaining_credits": remaining,
            "completion_rate": round(completion_rate, 2),
            "credit_requirement_met": remaining <= 0.0,
        }

    def get_courses(self, actor_user_id: uuid.UUID) -> list[dict]:
        student, *_ = self._profile_row(actor_user_id)
        stmt = (
            select(StudentCourse, Course)
            .join(Course, Course.id == StudentCourse.course_id)
            .where(StudentCourse.student_id == student.id)
            .order_by(StudentCourse.semester.asc(), Course.code.asc())
        )
        rows = self.session.execute(stmt).all()
        return [
            {
                "course_code": course.code,
                "course_name": course.name,
                "course_type": course.course_type,
                "semester": record.semester,
                "status": record.status,
                "score": float(record.score) if record.score is not None else None,
                "credits_earned": float(record.credits_earned or 0),
            }
            for record, course in rows
        ]

    def get_grades(self, actor_user_id: uuid.UUID) -> list[dict]:
        return [
            item
            for item in self.get_courses(actor_user_id)
            if item["score"] is not None
        ]

# ---- app/campus_sql/types.py ----
class StudentSqlCapability(str, Enum):
    PROFILE = "student_profile"
    COURSES = "student_courses"
    CREDITS = "student_credits"
    GRADES = "student_grades"
    GRADUATION_PROGRESS = "graduation_progress"


class StudentSqlToolResult(BaseModel):
    capability: StudentSqlCapability
    actor_user_id: str
    answer: str
    data: dict = Field(default_factory=dict)
    source: str = "postgresql"
    self_only: bool = True

# ---- app/campus_sql/analyzer.py ----
class StudentSqlQueryAnalyzer:
    """Map a personal structured query to an allow-listed student SQL capability.

    This analyzer deliberately does not generate SQL. It only selects one of a
    small number of parameterized repository methods.
    """

    def analyze(self, query: str) -> StudentSqlCapability:
        q = "".join((query or "").lower().split())

        if any(token in q for token in ("还差多少学分", "毕业进度", "距离毕业", "毕业还差", "毕业学分")):
            return StudentSqlCapability.GRADUATION_PROGRESS

        if any(token in q for token in ("成绩", "分数", "绩点")):
            return StudentSqlCapability.GRADES

        if any(token in q for token in ("修过哪些课程", "已修课程", "修了哪些课", "课程记录", "我的课程")):
            return StudentSqlCapability.COURSES

        if any(token in q for token in ("我的专业", "我的学号", "几年级", "个人信息", "学生信息", "学籍")):
            return StudentSqlCapability.PROFILE

        if any(token in q for token in ("多少学分", "总学分", "已修学分", "获得学分", "学分是多少")):
            return StudentSqlCapability.CREDITS

        # SQL routing already determined that the request is a structured
        # student-data question. Credits are the safest narrow default.
        return StudentSqlCapability.CREDITS

# ---- app/campus_sql/service.py ----
class StudentSqlToolService:
    """Allow-listed, read-only SQL tools for a student's own structured data."""

    def __init__(
        self,
        session: Session,
        *,
        repository: StudentSqlRepository | None = None,
        analyzer: StudentSqlQueryAnalyzer | None = None,
    ) -> None:
        self.session = session
        self.repository = repository or StudentSqlRepository(session)
        self.analyzer = analyzer or StudentSqlQueryAnalyzer()

    @staticmethod
    def _actor(value: uuid.UUID | str) -> uuid.UUID:
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))

    def get_student_profile(self, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        actor = self._actor(actor_user_id)
        data = self.repository.get_profile(actor)
        answer = (
            f"你的学号是 {data['student_no']}，当前就读于{data['college_name']}"
            f"{data['major_name']}专业，年级为{data['grade_level']}年级。"
        )
        return StudentSqlToolResult(
            capability=StudentSqlCapability.PROFILE,
            actor_user_id=str(actor),
            answer=answer,
            data=data,
        )

    def get_student_courses(self, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        actor = self._actor(actor_user_id)
        courses = self.repository.get_courses(actor)
        if courses:
            summary = "；".join(
                f"{item['course_name']}({item['semester']}, {item['credits_earned']:g}学分)"
                for item in courses
            )
            answer = f"当前结构化课程记录中共有 {len(courses)} 条：{summary}。"
        else:
            answer = "当前结构化课程记录中没有查询到你的课程记录。"
        return StudentSqlToolResult(
            capability=StudentSqlCapability.COURSES,
            actor_user_id=str(actor),
            answer=answer,
            data={"courses": courses, "count": len(courses)},
        )

    def get_student_credits(self, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        actor = self._actor(actor_user_id)
        data = self.repository.get_credit_summary(actor)
        answer = (
            f"当前教务汇总记录显示你已获得 {data['earned_credits']:g} 学分；"
            f"{data['major_name']}专业的毕业学分要求为 {data['graduation_credits']:g} 学分。"
        )
        return StudentSqlToolResult(
            capability=StudentSqlCapability.CREDITS,
            actor_user_id=str(actor),
            answer=answer,
            data=data,
        )

    def get_student_grades(self, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        actor = self._actor(actor_user_id)
        grades = self.repository.get_grades(actor)
        if grades:
            summary = "；".join(
                f"{item['course_name']} {item['score']:g}分"
                for item in grades
            )
            answer = f"当前结构化成绩记录为：{summary}。"
        else:
            answer = "当前结构化成绩记录中没有可显示的成绩。"
        return StudentSqlToolResult(
            capability=StudentSqlCapability.GRADES,
            actor_user_id=str(actor),
            answer=answer,
            data={"grades": grades, "count": len(grades)},
        )

    def get_graduation_progress(self, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        actor = self._actor(actor_user_id)
        data = self.repository.get_credit_summary(actor)
        if data["credit_requirement_met"]:
            progress = (
                f"按学分总量要求，你已达到 {data['graduation_credits']:g} 学分的毕业学分门槛。"
            )
        else:
            progress = (
                f"按学分总量要求，你还差 {data['remaining_credits']:g} 学分毕业"
                f"（已获 {data['earned_credits']:g}/{data['graduation_credits']:g} 学分，"
                f"完成约 {data['completion_rate']:g}%）。"
            )
        answer = (
            progress
            + "这里只核验学分总量；课程类别、必修课、实习、论文等其他毕业条件尚未在本工具中核验。"
        )
        return StudentSqlToolResult(
            capability=StudentSqlCapability.GRADUATION_PROGRESS,
            actor_user_id=str(actor),
            answer=answer,
            data=data,
        )

    def answer(self, query: str, actor_user_id: uuid.UUID | str) -> StudentSqlToolResult:
        capability = self.analyzer.analyze(query)
        if capability is StudentSqlCapability.PROFILE:
            return self.get_student_profile(actor_user_id)
        if capability is StudentSqlCapability.COURSES:
            return self.get_student_courses(actor_user_id)
        if capability is StudentSqlCapability.GRADES:
            return self.get_student_grades(actor_user_id)
        if capability is StudentSqlCapability.GRADUATION_PROGRESS:
            return self.get_graduation_progress(actor_user_id)
        return self.get_student_credits(actor_user_id)
