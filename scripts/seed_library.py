from __future__ import annotations

from datetime import datetime, timedelta, timezone
import uuid

from sqlalchemy import insert, select, update

from campusmind.tools.actions import (
    library_books,
    library_inventory,
    library_loans,
)
from campusmind.platform.db import User
from campusmind.platform.db import get_session_factory


BOOKS = (
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000001701"),
        "book_code": "LIB-GRL-001",
        "title": "Graph Representation Learning",
        "author": "William L. Hamilton",
        "isbn": "9781681739632",
        "subject": "Graph Learning / Knowledge Graph / GNN",
        "location": "主图书馆三层 A-03",
        "total": 3,
        "available": 2,
        "reserved": 0,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000001702"),
        "book_code": "LIB-DL-001",
        "title": "Deep Learning",
        "author": "Ian Goodfellow, Yoshua Bengio, Aaron Courville",
        "isbn": "9780262035613",
        "subject": "Deep Learning / Machine Learning",
        "location": "主图书馆三层 A-07",
        "total": 5,
        "available": 4,
        "reserved": 0,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000001703"),
        "book_code": "LIB-KG-001",
        "title": "知识图谱：方法、实践与应用",
        "author": "王昊奋 等",
        "isbn": "9787121366710",
        "subject": "知识图谱 / GraphRAG / NLP",
        "location": "主图书馆四层 B-12",
        "total": 4,
        "available": 3,
        "reserved": 0,
    },
    {
        "id": uuid.UUID("00000000-0000-0000-0000-000000001704"),
        "book_code": "LIB-DDIA-001",
        "title": "Designing Data-Intensive Applications",
        "author": "Martin Kleppmann",
        "isbn": "9781449373320",
        "subject": "Distributed Systems / Data Engineering",
        "location": "主图书馆二层 C-09",
        "total": 3,
        "available": 2,
        "reserved": 0,
    },
)


def main() -> None:
    factory = get_session_factory()
    now = datetime.now(timezone.utc)
    with factory() as session:
        actor = session.scalar(select(User).where(User.username == "student001"))
        if actor is None:
            raise RuntimeError("student001 is missing; run python -m scripts.seed_core first")

        for index, book in enumerate(BOOKS, start=1):
            existing = session.execute(
                select(library_books.c.id).where(library_books.c.id == book["id"])
            ).scalar_one_or_none()
            book_values = {
                "book_code": book["book_code"],
                "title": book["title"],
                "author": book["author"],
                "isbn": book["isbn"],
                "subject": book["subject"],
                "location": book["location"],
                "updated_at": now,
            }
            if existing is None:
                session.execute(
                    insert(library_books).values(
                        id=book["id"], created_at=now, **book_values
                    )
                )
            else:
                session.execute(
                    update(library_books)
                    .where(library_books.c.id == book["id"])
                    .values(**book_values)
                )

            inv_id = uuid.UUID(f"00000000-0000-0000-0000-{1710 + index:012d}")
            inv = session.execute(
                select(library_inventory.c.id).where(library_inventory.c.book_id == book["id"])
            ).scalar_one_or_none()
            if inv is None:
                session.execute(
                    insert(library_inventory).values(
                        id=inv_id,
                        book_id=book["id"],
                        total_copies=book["total"],
                        available_copies=book["available"],
                        reserved_copies=book["reserved"],
                        updated_at=now,
                    )
                )

        loan_id = uuid.UUID("00000000-0000-0000-0000-000000001721")
        loan_exists = session.execute(
            select(library_loans.c.id).where(library_loans.c.id == loan_id)
        ).scalar_one_or_none()
        if loan_exists is None:
            session.execute(
                insert(library_loans).values(
                    id=loan_id,
                    actor_user_id=actor.id,
                    book_id=BOOKS[3]["id"],
                    status="borrowed",
                    borrowed_at=now - timedelta(days=7),
                    due_at=now + timedelta(days=23),
                    returned_at=None,
                )
            )
        session.commit()

    print("CampusMind synthetic library catalog applied successfully.")


if __name__ == "__main__":
    main()
