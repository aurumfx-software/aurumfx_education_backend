from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import Course, CourseTask, StudentTaskAssignment, User
from routers.auth import get_current_user
from utils.assignment_files import (
    assignment_pdf_url,
    delete_assignment_pdf,
    upload_assignment_pdf,
)


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
                "status": (
                    "verified"
                    if assignment.marks_obtained is not None
                    else "submitted"
                    if assignment.submitted_at is not None
                    else "pending_submission"
                ),
                "submission_url": assignment_pdf_url(assignment.submission_key),
                "submission_filename": assignment.submission_filename,
                "submitted_at": assignment.submitted_at,
                "marks_obtained": assignment.marks_obtained,
                "max_marks": task.max_marks,
                "feedback": assignment.feedback,
                "marked_at": assignment.marked_at,
                "course": {
                    "course_id": course.id,
                    "course_title": course.title,
                    "branch_id": course.branch_id,
                },
            }
            for assignment, task, course in assignment_rows
        ],
    }


@router.post("/{assignment_id}/submit")
async def submit_assignment(
    assignment_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")

    assignment = (
        db.query(StudentTaskAssignment)
        .filter(
            StudentTaskAssignment.id == assignment_id,
            StudentTaskAssignment.student_id == current_user.id,
        )
        .first()
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Assigned task not found")
    if assignment.marks_obtained is not None:
        raise HTTPException(
            status_code=409,
            detail="A verified assignment cannot be resubmitted",
        )

    new_key, filename = await upload_assignment_pdf(
        current_user.id,
        assignment.id,
        file,
    )
    old_key = assignment.submission_key
    assignment.submission_key = new_key
    assignment.submission_filename = filename
    assignment.submitted_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(assignment)
    except Exception:
        db.rollback()
        delete_assignment_pdf(new_key)
        raise

    if old_key:
        delete_assignment_pdf(old_key)

    return {
        "message": "Assignment submitted successfully",
        "assignment_id": assignment.id,
        "status": "submitted",
        "submission_filename": assignment.submission_filename,
        "submitted_at": assignment.submitted_at,
    }
