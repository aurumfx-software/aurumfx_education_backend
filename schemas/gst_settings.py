from pydantic import BaseModel, ConfigDict, Field


class GSTSettingsUpdate(BaseModel):
    cgst_percent: float = Field(ge=0, le=100)
    sgst_percent: float = Field(ge=0, le=100)


class GSTSettingsResponse(BaseModel):
    cgst_percent: float
    sgst_percent: float
    total_gst_percent: float

    model_config = ConfigDict(from_attributes=True)
