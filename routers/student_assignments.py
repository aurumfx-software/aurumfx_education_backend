from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Course, CourseTask, StudentTaskAssignment, User
from routers.auth import get_current_user


router = APIRouter(
    prefix="/student/assignments",
    tags=["Student Assignments"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("")
def get_my_assignments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")

    assignment_rows = (
        db.query(StudentTaskAssignment, CourseTask, Course)
        .join(CourseTask, CourseTask.id == StudentTaskAssignment.task_id)
        .join(Course, Course.id == CourseTask.course_id)
        .filter(StudentTaskAssignment.student_id == current_user.id)
        .order_by(
            StudentTaskAssignment.assigned_at.desc(),
            StudentTaskAssignment.id.desc(),
        )
        .all()
    )
    return {
        "total_assignments": len(assignment_rows),
        "assignments": [
            {
                "assignment_id": assignment.id,
                "task_id": task.id,
                "title": task.title,
                "description": task.description,
                "due_date": task.due_date,
                "assigned_at": assignment.assigned_at,
                "course": {
                    "course_id": course.id,
                    "course_title": course.title,
                    "branch_id": course.branch_id,
                },
            }
            for assignment, task, course in assignment_rows
        ],
    }
