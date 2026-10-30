import math

from fastapi import HTTPException
from sqlalchemy.orm import Session

from database_models import GSTSettings


def get_gst_percentages(db: Session) -> tuple[float, float]:
    settings = db.query(GSTSettings).filter(GSTSettings.id == 1).first()
    if not settings:
        raise HTTPException(
            status_code=400,
            detail=(
                "GST settings are not configured. "
                "Please ask the superadmin to configure CGST and SGST "
                "before adding or updating courses."
            ),
        )
    return settings.cgst_percent, settings.sgst_percent


def calculate_course_amounts(
    base_price: float,
    cgst_percent: float,
    sgst_percent: float,
) -> dict[str, float]:
    """Treat the entered course price as the final GST-inclusive price."""
    if not math.isfinite(base_price) or base_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Course price must be greater than 0",
        )

    base_price = round(base_price, 2)

    return {
        "base_price": base_price,
        "cgst_percent": 0,
        "sgst_percent": 0,
        "cgst_amount": 0,
        "sgst_amount": 0,
        "price": base_price,
    }


def get_course_amounts(db: Session, base_price: float) -> dict[str, float]:
    return calculate_course_amounts(base_price, 0, 0)
