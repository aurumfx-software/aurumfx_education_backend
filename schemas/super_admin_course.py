from pydantic import BaseModel

from schemas.course import BranchAdminCourseResponse


class SuperAdminCourseCreateResult(BaseModel):
    branch_id: int
    branch_name: str
    course: BranchAdminCourseResponse
