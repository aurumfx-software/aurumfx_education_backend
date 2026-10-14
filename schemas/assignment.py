from pydantic import BaseModel, Field


class AssignmentGradeUpdate(BaseModel):
    marks_obtained: float = Field(ge=0)
    feedback: str | None = None
