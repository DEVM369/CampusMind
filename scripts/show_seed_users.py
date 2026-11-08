from __future__ import annotations

from sqlalchemy import select

from campusmind.platform.db import User, get_session_factory

USERNAMES = ("student001", "teacher001", "teacher002", "admin")


def main() -> None:
    factory = get_session_factory()
    with factory() as session:
        rows = session.execute(
            select(User.username, User.id, User.full_name)
            .where(User.username.in_(USERNAMES))
            .order_by(User.username)
        ).all()

    if not rows:
        print("No CampusMind seed users found. Run: python -m scripts.seed_core")
        return

    print("CampusMind seed users (operator diagnostics only; sign in with username and password):")
    for username, user_id, full_name in rows:
        print(f"{username:12}  {user_id}  {full_name or ''}")


if __name__ == "__main__":
    main()
