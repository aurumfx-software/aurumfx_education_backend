from pydantic import BaseModel

from schemas.enrollment import AdminEnrollmentResponse


class SuperAdminBranchResponse(BaseModel):
    branch_id: int
    branch_name: str
    location: str


class SuperAdminCourseResponse(BaseModel):
    course_id: int
    course_title: str
    is_active: bool
    total_students: int


class SuperAdminCourseStudentsResponse(BaseModel):
    branch_id: int
    branch_name: str
    course_id: int
    course_title: str
    total_students: int
    students: list[AdminEnrollmentResponse]
