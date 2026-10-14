from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Course,
    CourseAnnouncement,
    Enrollment,
    Staff,
    User,
)
from routers.auth import get_current_user
from routers.staff_portal import get_current_staff_record, get_staff_courses
from schemas.course_announcement import (
    CourseAnnouncementCreate,
    CourseAnnouncementResponse,
    CourseAnnouncementUpdate,
)


router = APIRouter(tags=["Course Announcements"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def build_announcement_response(
    announcement: CourseAnnouncement,
    course: Course,
    staff: Staff,
):
    return {
        "id": announcement.id,
        "course_id": course.id,
        "course_title": course.title,
        "staff_id": staff.id,
        "staff_name": staff.name,
        "title": announcement.title,
        "message": announcement.message,
        "event_at": announcement.event_at,
        "created_at": announcement.created_at,
    }


def get_student_course(
    db: Session,
    current_user: User,
    course_id: int,
) -> Course:
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")
    if current_user.status != "Active":
        raise HTTPException(status_code=403, detail="Student account is inactive")

    enrollment = (
        db.query(Enrollment.id)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_id == course_id,
            Enrollment.course_status == "approved",
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this course",
        )

    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.is_active == True)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Active course not found")
    return course


def get_staff_announcement(
    db: Session,
    staff: Staff,
    announcement_id: int,
) -> tuple[CourseAnnouncement, Course]:
    row = (
        db.query(CourseAnnouncement, Course)
        .join(Course, Course.id == CourseAnnouncement.course_id)
        .filter(
            CourseAnnouncement.id == announcement_id,
            CourseAnnouncement.staff_id == staff.id,
        )
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Announcement not found")
    return row


def validate_announcement_content(
    title: str,
    message: str,
) -> tuple[str, str]:
    title = title.strip()
    message = message.strip()
    if not title or not message:
        raise HTTPException(
            status_code=400,
            detail="Announcement title and message cannot be blank",
        )
    return title, message


@router.post(
    "/staff/courses/{course_id}/announcements",
    response_model=CourseAnnouncementResponse,
    status_code=201,
)
def create_course_announcement(
    course_id: int,
    announcement_data: CourseAnnouncementCreate,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    title, message = validate_announcement_content(
        announcement_data.title,
        announcement_data.message,
    )

    announcement = CourseAnnouncement(
        course_id=course.id,
        staff_id=staff.id,
        title=title,
        message=message,
        event_at=announcement_data.event_at,
    )
    db.add(announcement)
    db.commit()
    db.refresh(announcement)
    return build_announcement_response(announcement, course, staff)


@router.get(
    "/staff/announcements",
    response_model=list[CourseAnnouncementResponse],
)
def get_my_staff_announcements(
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    rows = (
        db.query(CourseAnnouncement, Course)
        .join(Course, Course.id == CourseAnnouncement.course_id)
        .filter(CourseAnnouncement.staff_id == staff.id)
        .order_by(
            CourseAnnouncement.event_at.asc().nullslast(),
            CourseAnnouncement.created_at.desc(),
            CourseAnnouncement.id.desc(),
        )
        .all()
    )
    return [
        build_announcement_response(announcement, course, staff)
        for announcement, course in rows
    ]


@router.get(
    "/staff/courses/{course_id}/announcements",
    response_model=list[CourseAnnouncementResponse],
)
def get_my_staff_course_announcements(
    course_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    course = next(
        (course for course in get_staff_courses(db, staff) if course.id == course_id),
        None,
    )
    if not course:
        raise HTTPException(
            status_code=404,
            detail="Course is not assigned to this staff member",
        )

    announcements = (
        db.query(CourseAnnouncement)
        .filter(
            CourseAnnouncement.staff_id == staff.id,
            CourseAnnouncement.course_id == course.id,
        )
        .order_by(
            CourseAnnouncement.event_at.asc().nullslast(),
            CourseAnnouncement.created_at.desc(),
            CourseAnnouncement.id.desc(),
        )
        .all()
    )
    return [
        build_announcement_response(announcement, course, staff)
        for announcement in announcements
    ]


@router.put(
    "/staff/announcements/{announcement_id}",
    response_model=CourseAnnouncementResponse,
)
def update_staff_announcement(
    announcement_id: int,
    announcement_data: CourseAnnouncementUpdate,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    announcement, course = get_staff_announcement(db, staff, announcement_id)
    title, message = validate_announcement_content(
        announcement_data.title,
        announcement_data.message,
    )
    announcement.title = title
    announcement.message = message
    announcement.event_at = announcement_data.event_at
    db.commit()
    db.refresh(announcement)
    return build_announcement_response(announcement, course, staff)


@router.delete("/staff/announcements/{announcement_id}")
def delete_staff_announcement(
    announcement_id: int,
    db: Session = Depends(get_db),
    staff: Staff = Depends(get_current_staff_record),
):
    announcement, _ = get_staff_announcement(db, staff, announcement_id)
    db.delete(announcement)
    db.commit()
    return {
        "message": "Announcement deleted successfully",
        "announcement_id": announcement_id,
    }


@router.get(
    "/student/announcements",
    response_model=list[CourseAnnouncementResponse],
)
def get_my_course_announcements(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")
    if current_user.status != "Active":
        raise HTTPException(status_code=403, detail="Student account is inactive")

    enrolled_course_ids = (
        db.query(Enrollment.course_id)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_status == "approved",
        )
        .distinct()
        .subquery()
    )
    rows = (
        db.query(CourseAnnouncement, Course, Staff)
        .join(Course, Course.id == CourseAnnouncement.course_id)
        .join(Staff, Staff.id == CourseAnnouncement.staff_id)
        .filter(
            CourseAnnouncement.course_id.in_(enrolled_course_ids),
            Course.is_active == True,
            Staff.status == "Active",
        )
        .order_by(
            CourseAnnouncement.event_at.asc().nullslast(),
            CourseAnnouncement.created_at.desc(),
            CourseAnnouncement.id.desc(),
        )
        .all()
    )
    return [
        build_announcement_response(announcement, course, staff)
        for announcement, course, staff in rows
    ]


@router.get(
    "/student/courses/{course_id}/announcements",
    response_model=list[CourseAnnouncementResponse],
)
def get_course_announcements(
    course_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    course = get_student_course(db, current_user, course_id)
    rows = (
        db.query(CourseAnnouncement, Staff)
        .join(Staff, Staff.id == CourseAnnouncement.staff_id)
        .filter(
            CourseAnnouncement.course_id == course.id,
            Staff.status == "Active",
        )
        .order_by(
            CourseAnnouncement.event_at.asc().nullslast(),
            CourseAnnouncement.created_at.desc(),
            CourseAnnouncement.id.desc(),
        )
        .all()
    )
    return [
        build_announcement_response(announcement, course, staff)
        for announcement, staff in rows
    ]
