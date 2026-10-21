from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Course,
    CourseAnnouncement,
    CourseTask,
    Staff,
    StaffCourse,
    StudentTaskAssignment,
    User,
)
from routers.auth import get_current_super_admin, get_current_user
from routers.staff_portal import (
    build_staff_profile,
    build_staff_verification_reviewers,
)


router = APIRouter(
    prefix="/staff-monitoring",
    tags=["Staff Monitoring"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def get_staff_monitoring_data(
    db: Session,
    branch_id: int,
    offset: int,
    limit: int,
):
    total_staff = (
        db.query(func.count(Staff.id))
        .filter(Staff.branch_id == branch_id)
        .scalar()
        or 0
    )
    staff_members = (
        db.query(Staff)
        .filter(Staff.branch_id == branch_id)
        .order_by(Staff.name.asc(), Staff.id.asc())
        .offset(offset)
        .limit(limit)
        .all()
    )
    staff_ids = [staff.id for staff in staff_members]

    courses_by_staff = {staff_id: [] for staff_id in staff_ids}
    if staff_ids:
        course_rows = (
            db.query(StaffCourse.staff_id, Course)
            .join(Course, Course.id == StaffCourse.course_id)
            .filter(
                StaffCourse.staff_id.in_(staff_ids),
                Course.branch_id == branch_id,
            )
            .order_by(Course.title.asc(), Course.id.asc())
            .all()
        )
        for staff_id, course in course_rows:
            courses_by_staff[staff_id].append(course)

        fallback_course_ids = [
            staff.course_id
            for staff in staff_members
            if not courses_by_staff[staff.id]
        ]
        fallback_courses = (
            db.query(Course)
            .filter(
                Course.id.in_(fallback_course_ids),
                Course.branch_id == branch_id,
            )
            .all()
            if fallback_course_ids
            else []
        )
        fallback_by_id = {course.id: course for course in fallback_courses}
        for staff in staff_members:
            if not courses_by_staff[staff.id]:
                fallback_course = fallback_by_id.get(staff.course_id)
                if fallback_course:
                    courses_by_staff[staff.id].append(fallback_course)

    tasks_by_staff = {staff_id: [] for staff_id in staff_ids}
    if staff_ids:
        task_rows = (
            db.query(CourseTask, Course.title, func.count(StudentTaskAssignment.id))
            .join(Course, Course.id == CourseTask.course_id)
            .outerjoin(
                StudentTaskAssignment,
                StudentTaskAssignment.task_id == CourseTask.id,
            )
            .filter(
                CourseTask.staff_id.in_(staff_ids),
                Course.branch_id == branch_id,
            )
            .group_by(CourseTask.id, Course.title)
            .order_by(CourseTask.created_at.desc(), CourseTask.id.desc())
            .all()
        )
        for task, course_title, assigned_student_count in task_rows:
            tasks_by_staff[task.staff_id].append(
                {
                    "id": task.id,
                    "course_id": task.course_id,
                    "course_title": course_title,
                    "title": task.title,
                    "description": task.description,
                    "due_date": task.due_date,
                    "max_marks": task.max_marks,
                    "created_at": task.created_at,
                    "assigned_student_count": assigned_student_count,
                }
            )

    announcements_by_staff = {staff_id: [] for staff_id in staff_ids}
    if staff_ids:
        announcement_rows = (
            db.query(CourseAnnouncement, Course.title)
            .join(Course, Course.id == CourseAnnouncement.course_id)
            .filter(
                CourseAnnouncement.staff_id.in_(staff_ids),
                Course.branch_id == branch_id,
            )
            .order_by(
                CourseAnnouncement.created_at.desc(),
                CourseAnnouncement.id.desc(),
            )
            .all()
        )
        for announcement, course_title in announcement_rows:
            announcements_by_staff[announcement.staff_id].append(
                {
                    "id": announcement.id,
                    "course_id": announcement.course_id,
                    "course_title": course_title,
                    "title": announcement.title,
                    "message": announcement.message,
                    "event_at": announcement.event_at,
                    "created_at": announcement.created_at,
                }
            )

    monitored_staff = []
    for staff in staff_members:
        profile = build_staff_profile(db, staff)
        profile.update(build_staff_verification_reviewers(db, staff))
        profile.update(
            {
                "id": staff.id,
                "status": staff.status,
                "courses": [
                    {"id": course.id, "title": course.title}
                    for course in courses_by_staff[staff.id]
                ],
                "assignments": tasks_by_staff[staff.id],
                "assignment_count": len(tasks_by_staff[staff.id]),
                "announcements": announcements_by_staff[staff.id],
                "announcement_count": len(announcements_by_staff[staff.id]),
            }
        )
        monitored_staff.append(profile)

    return {
        "total_staff": total_staff,
        "offset": offset,
        "limit": limit,
        "staff": monitored_staff,
    }


@router.get("/branch-admin")
def get_branch_admin_staff_monitoring(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "branch_admin":
        raise HTTPException(status_code=403, detail="Branch admin access required")
    if current_user.status != "Active":
        raise HTTPException(
            status_code=403,
            detail="Branch admin account is inactive",
        )
    if not current_user.branch_id:
        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch",
        )

    branch = db.query(Branch).filter(Branch.id == current_user.branch_id).first()
    if not branch:
        raise HTTPException(status_code=404, detail="Branch not found")

    return {
        "branch": {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
        },
        **get_staff_monitoring_data(db, branch.id, offset, limit),
    }


@router.get("/super-admin/branches")
def get_monitoring_branches(
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    branches = (
        db.query(Branch)
        .filter(Branch.status == "Active")
        .order_by(Branch.name.asc(), Branch.id.asc())
        .all()
    )
    return [
        {
            "id": branch.id,
            "name": branch.name,
            "location": branch.location,
        }
        for branch in branches
    ]


@router.get("/super-admin")
def get_super_admin_staff_monitoring(
    branch_id: int | None = Query(default=None, gt=0),
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_admin: User = Depends(get_current_super_admin),
):
    if branch_id is None:
        branches = (
            db.query(Branch)
            .order_by(Branch.name.asc(), Branch.id.asc())
            .all()
        )
    else:
        branch = db.query(Branch).filter(Branch.id == branch_id).first()
        if not branch:
            raise HTTPException(status_code=404, detail="Branch not found")
        branches = [branch]

    monitoring = []
    total_staff = 0
    for branch in branches:
        branch_data = get_staff_monitoring_data(db, branch.id, offset, limit)
        total_staff += branch_data["total_staff"]
        monitoring.append(
            {
                "branch": {
                    "id": branch.id,
                    "name": branch.name,
                    "location": branch.location,
                },
                **branch_data,
            }
        )

    return {
        "branch_id": branch_id,
        "total_staff": total_staff,
        "branches": monitoring,
    }
