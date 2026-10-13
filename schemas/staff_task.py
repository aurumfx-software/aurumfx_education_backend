from datetime import date

from pydantic import BaseModel, Field, field_validator


class StaffTaskCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    description: str = Field(min_length=1)
    due_date: date | None = None
    student_ids: list[int] | None = Field(default=None, min_length=1)

    @field_validator("title", "description")
    @classmethod
    def trim_required_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("This field cannot be blank")
        return value
