from __future__ import annotations

from datetime import datetime, time, timezone
import uuid

from sqlalchemy import MetaData, Table, insert, select, update

from campusmind.platform.db import Course
from campusmind.platform.db import get_session_factory


SCHEDULES = (
    ("机器学习", "2026-2027", "2026-Fall", 2, time(8, 30), time(10, 5), "AI-A203", "主校区"),
    ("机器学习", "2026-2027", "2026-Fall", 4, time(14, 0), time(15, 35), "AI-A203", "主校区"),
    ("深度学习", "2026-2027", "2026-Fall", 3, time(10, 20), time(11, 55), "AI-B305", "主校区"),
    ("数据结构", "2026-2027", "2026-Fall", 1, time(8, 30), time(10, 5), "CS-A201", "主校区"),
    ("知识图谱", "2026-2027", "2026-Fall", 5, time(14, 0), time(15, 35), "AI-C401", "主校区"),
    ("大语言模型导论", "2026-2027", "2026-Fall", 5, time(15, 50), time(17, 25), "AI-C402", "主校区"),
)


def _schedule_id(course_id, academic_year: str, semester: str, weekday: int, start_time: time) -> uuid.UUID:
    return uuid.uuid5(
        uuid.UUID("00000000-0000-0000-0000-000000001800"),
        f"{course_id}:{academic_year}:{semester}:{weekday}:{start_time.isoformat()}",
    )


def main() -> None:
    factory = get_session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        metadata = MetaData()
        schedules = Table("course_schedules", metadata, autoload_with=session.get_bind())
        seeded = 0
        skipped = []
        for course_name, academic_year, semester, weekday, start_at, end_at, classroom, campus in SCHEDULES:
            course = session.scalar(select(Course).where(Course.name == course_name))
            if course is None:
                skipped.append(course_name)
                continue
            existing = session.execute(
                select(schedules.c.id).where(
                    schedules.c.course_id == course.id,
                    schedules.c.academic_year == academic_year,
                    schedules.c.semester == semester,
                    schedules.c.weekday == weekday,
                    schedules.c.start_time == start_at,
                )
            ).scalar_one_or_none()
            values = {
                "end_time": end_at,
                "classroom": classroom,
                "campus": campus,
                "updated_at": now,
            }
            if existing is None:
                session.execute(
                    insert(schedules).values(
                        id=_schedule_id(course.id, academic_year, semester, weekday, start_at),
                        course_id=course.id,
                        academic_year=academic_year,
                        semester=semester,
                        weekday=weekday,
                        start_time=start_at,
                        created_at=now,
                        **values,
                    )
                )
            else:
                session.execute(update(schedules).where(schedules.c.id == existing).values(**values))
            seeded += 1
        session.commit()
    print(f"CampusMind course schedules applied successfully. seeded={seeded}, skipped={sorted(set(skipped))}")


if __name__ == "__main__":
    main()
