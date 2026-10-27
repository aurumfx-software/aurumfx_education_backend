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
    if not math.isfinite(base_price) or base_price <= 0:
        raise HTTPException(
            status_code=400,
            detail="Course price must be greater than 0",
        )

    base_price = round(base_price, 2)
    cgst_amount = round(base_price * cgst_percent / 100, 2)
    sgst_amount = round(base_price * sgst_percent / 100, 2)
    total_amount = round(base_price + cgst_amount + sgst_amount, 2)

    return {
        "base_price": base_price,
        "cgst_percent": cgst_percent,
        "sgst_percent": sgst_percent,
        "cgst_amount": cgst_amount,
        "sgst_amount": sgst_amount,
        "price": total_amount,
    }


def get_course_amounts(db: Session, base_price: float) -> dict[str, float]:
    cgst_percent, sgst_percent = get_gst_percentages(db)
    return calculate_course_amounts(base_price, cgst_percent, sgst_percent)
