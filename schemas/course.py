from datetime import date

from pydantic import BaseModel, ConfigDict, Field


class CurriculumSection(BaseModel):
    title: str
    topics: list[str]


class CourseCreate(BaseModel):
    title: str
    description: str
    price: float
    duration: str
    category: str | None = None
    level: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    curriculum: list[CurriculumSection] | None = None


class CourseResponse(BaseModel):
    id: int
    title: str
    description: str
    price: float
    duration: str

    image: str | None = None
    category: str | None = None
    level: str | None = None

    start_date: date | None = None
    end_date: date | None = None

    curriculum: list[CurriculumSection] | None = None

    installment_schedule: str | None = None
    installment_count: int | None = None

    is_active: bool

    model_config = ConfigDict(
        from_attributes=True
    )


class CourseInstallmentTermResponse(BaseModel):
    term_number: int
    amount: float
    due_date: date


class BranchAdminCourseResponse(CourseResponse):
    installment_terms: list[CourseInstallmentTermResponse] | None = Field(
        default=None
    )