from __future__ import annotations

import uuid

from campusmind.tools.student import StudentSqlQueryAnalyzer
from campusmind.tools.student import StudentSqlToolService
from campusmind.tools.student import StudentSqlCapability


class FakeRepository:
    def get_profile(self, actor_user_id):
        return {
            "user_id": str(actor_user_id),
            "student_id": "student-1",
            "student_no": "20240001",
            "full_name": "Student",
            "major_code": "SE",
            "major_name": "软件工程",
            "department_name": "计算机科学与技术系",
            "college_name": "计算机学院",
            "enrollment_year": 2024,
            "grade_level": 3,
            "expected_graduation_date": "2028-06-30",
        }

    def get_credit_summary(self, actor_user_id):
        return {
            "student_id": "student-1",
            "major_name": "软件工程",
            "earned_credits": 86.0,
            "graduation_credits": 160.0,
            "remaining_credits": 74.0,
            "completion_rate": 53.75,
            "credit_requirement_met": False,
        }

    def get_courses(self, actor_user_id):
        return [
            {
                "course_code": "CS201",
                "course_name": "数据结构",
                "course_type": "required",
                "semester": "2025-Spring",
                "status": "completed",
                "score": 87.0,
                "credits_earned": 4.0,
            }
        ]

    def get_grades(self, actor_user_id):
        return self.get_courses(actor_user_id)


def _service():
    return StudentSqlToolService(
        session=None,
        repository=FakeRepository(),
        analyzer=StudentSqlQueryAnalyzer(),
    )


def test_sql_query_analyzer_is_allowlist_only():
    analyzer = StudentSqlQueryAnalyzer()
    assert analyzer.analyze("我还差多少学分毕业？") is StudentSqlCapability.GRADUATION_PROGRESS
    assert analyzer.analyze("我修过哪些课程？") is StudentSqlCapability.COURSES
    assert analyzer.analyze("我的成绩怎么样？") is StudentSqlCapability.GRADES
    assert analyzer.analyze("我的专业是什么？") is StudentSqlCapability.PROFILE


def test_graduation_progress_uses_structured_credit_summary():
    actor = uuid.uuid4()
    result = _service().get_graduation_progress(actor)
    assert result.self_only is True
    assert result.capability is StudentSqlCapability.GRADUATION_PROGRESS
    assert result.data["remaining_credits"] == 74.0
    assert "74" in result.answer
    assert "其他毕业条件" in result.answer


def test_courses_and_grades_are_identity_bound_results():
    actor = uuid.uuid4()
    courses = _service().get_student_courses(actor)
    grades = _service().get_student_grades(actor)
    assert courses.actor_user_id == str(actor)
    assert courses.data["courses"][0]["course_name"] == "数据结构"
    assert grades.data["grades"][0]["score"] == 87.0
