from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import GSTSettings, User
from routers.auth import get_current_super_admin
from schemas.gst_settings import GSTSettingsResponse, GSTSettingsUpdate


router = APIRouter(
    prefix="/super-admin/gst-settings",
    tags=["Super Admin GST Settings"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def serialize_gst_settings(settings: GSTSettings):
    return {
        "cgst_percent": settings.cgst_percent,
        "sgst_percent": settings.sgst_percent,
        "total_gst_percent": round(
            settings.cgst_percent + settings.sgst_percent,
            2,
        ),
    }


@router.get("/", response_model=GSTSettingsResponse)
def get_gst_settings(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    settings = db.query(GSTSettings).filter(GSTSettings.id == 1).first()
    if not settings:
        return {
            "cgst_percent": 0,
            "sgst_percent": 0,
            "total_gst_percent": 0,
        }
    return serialize_gst_settings(settings)


@router.post("/", response_model=GSTSettingsResponse)
def update_gst_settings(
    settings_data: GSTSettingsUpdate,
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    settings = db.query(GSTSettings).filter(GSTSettings.id == 1).first()
    if not settings:
        settings = GSTSettings(id=1)
        db.add(settings)

    settings.cgst_percent = settings_data.cgst_percent
    settings.sgst_percent = settings_data.sgst_percent
    db.commit()
    db.refresh(settings)
    return serialize_gst_settings(settings)
