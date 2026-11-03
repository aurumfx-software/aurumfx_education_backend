from datetime import date

from pydantic import BaseModel, Field


class BranchHolidayCreate(BaseModel):
    date: date
    reason: str = Field(min_length=1, max_length=255)
