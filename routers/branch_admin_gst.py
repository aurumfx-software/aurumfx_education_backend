from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import GSTSettings
from routers.courses import get_current_branch_admin
from schemas.gst_settings import GSTSettingsResponse


router = APIRouter(
    prefix="/branch-admin/gst-settings",
    tags=["Branch Admin GST Settings"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/", response_model=GSTSettingsResponse)
def get_branch_admin_gst_settings(
    db: Session = Depends(get_db),
    branch_admin=Depends(get_current_branch_admin),
):
    settings = (
        db.query(GSTSettings)
        .filter(GSTSettings.id == 1)
        .first()
    )
    if not settings:
        return {
            "cgst_percent": 0,
            "sgst_percent": 0,
            "total_gst_percent": 0,
        }

    return {
        "cgst_percent": settings.cgst_percent,
        "sgst_percent": settings.sgst_percent,
        "total_gst_percent": round(
            settings.cgst_percent + settings.sgst_percent,
            2,
        ),
    }
