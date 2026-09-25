from pydantic import BaseModel, ConfigDict


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
    curriculum: list[CurriculumSection] | None = None
    payment_plan: dict | None = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)