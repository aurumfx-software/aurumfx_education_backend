from typing import Optional
from pydantic import BaseModel, ConfigDict


class SettingsSchema(BaseModel):
    address: Optional[str] = None
    phone: Optional[str] = None
    alt_phone: Optional[str] = None
    email: Optional[str] = None
    admissions_email: Optional[str] = None
    working_hours: Optional[str] = None


class SettingsResponse(SettingsSchema):
    id: int

    model_config = ConfigDict(from_attributes=True)





