import argparse
from pathlib import Path
import sys

from sqlalchemy import select

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.core.config import get_settings
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models.admin import Admin


def parse_args() -> argparse.Namespace:
    settings = get_settings()
    parser = argparse.ArgumentParser(description="Create or update admin user.")
    parser.add_argument("--login", default=settings.bootstrap_admin_login)
    parser.add_argument("--password", default=settings.bootstrap_admin_password)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session_factory = get_session_factory()
    with session_factory() as db:
        existing = db.scalar(select(Admin).where(Admin.login == args.login))
        if existing:
            existing.password_hash = hash_password(args.password)
            db.add(existing)
            action = "updated"
        else:
            db.add(
                Admin(
                    login=args.login,
                    password_hash=hash_password(args.password),
                    role="admin",
                )
            )
            action = "created"
        db.commit()
    print(f"Admin {args.login} {action}.")


if __name__ == "__main__":
    main()
