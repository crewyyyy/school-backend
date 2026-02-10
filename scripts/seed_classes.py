from pathlib import Path
import sys

from sqlalchemy import select

if __package__ is None or __package__ == "":
    sys.path.append(str(Path(__file__).resolve().parents[1]))

from app.db.session import get_session_factory
from app.models.class_model import SchoolClass


DEFAULT_LETTERS = ("А", "Б")


def main() -> None:
    session_factory = get_session_factory()
    inserted = 0
    with session_factory() as db:
        for grade in range(5, 12):
            for letter in DEFAULT_LETTERS:
                class_name = f"{grade}{letter}"
                existing = db.scalar(select(SchoolClass).where(SchoolClass.name == class_name))
                if existing:
                    continue
                db.add(SchoolClass(grade=grade, letter=letter, name=class_name, total_points=0))
                inserted += 1
        db.commit()
    print(f"Inserted classes: {inserted}")


if __name__ == "__main__":
    main()
