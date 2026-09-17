from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import SystemSettings, User

from schemas.settings import (
    SettingsSchema,
    SettingsResponse
)

from routers.auth import get_current_super_admin


router = APIRouter(
    prefix="/settings"
)


# ==========================================
# DATABASE DEPENDENCY
# ==========================================

def get_db():
    db = SessionLocal()

    try:
        yield db
    finally:
        db.close()


# ==========================================
# GET OR CREATE SETTINGS
# ==========================================

# def get_or_create_settings(
#     db: Session
# ) -> SystemSettings:

#     settings = (
#         db.query(SystemSettings)
#         .first()
#     )

#     if not settings:

#         settings = SystemSettings(
#             id=1,
#             address="Calicut Cyberpark Road, Mavoor Road Junction, Calicut, Kerala 673004, India",
#             phone="+91 98765 43210",
#             alt_phone="+91 98765 43211",
#             email="info@exampleinstitute.com",
#             admissions_email="admissions@exampleinstitute.com",
#             working_hours="Monday – Saturday: 8:30 AM – 6:30 PM"
#         )

#         db.add(settings)

#         db.commit()

#         db.refresh(settings)

#     return settings


# ==========================================
# GET PUBLIC SETTINGS
# ==========================================

# @router.get(
#     "/",
#     response_model=SettingsResponse,
#     tags=["Super Admin"]
# )
# def get_settings(
#     db: Session = Depends(get_db)
# ):
#     """
#     Get current institute contact settings.
#     """

#     return get_or_create_settings(db)


# # ==========================================
# # UPDATE SUPER ADMIN SETTINGS
# # ==========================================

# @router.put(
#     "/",
#     response_model=SettingsResponse,
#     tags=["Super Admin"]
# )
# def update_settings(
#     settings_data: SettingsSchema,
#     db: Session = Depends(get_db),
#     current_admin: User = Depends(get_current_super_admin)
# ):
#     """
#     Update institute contact settings.
#     Super admin only.
#     """

#     settings = get_or_create_settings(db)


#     # ==========================================
#     # UPDATE ADDRESS
#     # ==========================================

#     if settings_data.address is not None:
#         settings.address = settings_data.address


#     # ==========================================
#     # UPDATE PHONE
#     # ==========================================

#     if settings_data.phone is not None:
#         settings.phone = settings_data.phone


#     # ==========================================
#     # UPDATE ALTERNATE PHONE
#     # ==========================================

#     if settings_data.alt_phone is not None:
#         settings.alt_phone = settings_data.alt_phone


#     # ==========================================
#     # UPDATE EMAIL
#     # ==========================================

#     if settings_data.email is not None:
#         settings.email = settings_data.email


#     # ==========================================
#     # UPDATE ADMISSIONS EMAIL
#     # ==========================================

#     if settings_data.admissions_email is not None:
#         settings.admissions_email = (
#             settings_data.admissions_email
#         )


#     # ==========================================
#     # UPDATE WORKING HOURS
#     # ==========================================

#     if settings_data.working_hours is not None:
#         settings.working_hours = (
#             settings_data.working_hours
#         )


#     # ==========================================
#     # SAVE CHANGES
#     # ==========================================

#     db.commit()

#     db.refresh(settings)

#     return settings