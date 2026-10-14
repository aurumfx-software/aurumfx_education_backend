import secrets

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database_models import Staff


def generate_staff_code(db: Session) -> str:
    for _ in range(900):
        code = f"STF{secrets.randbelow(900) + 100}"
        if not db.query(Staff.id).filter(Staff.staff_code == code).first():
            return code

    raise HTTPException(
        status_code=409,
        detail="No unused three-digit staff codes are available",
    )
