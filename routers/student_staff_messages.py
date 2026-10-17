from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import and_, exists, func, or_
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Course,
    Enrollment,
    Staff,
    StaffCourse,
    StudentStaffConversation,
    StudentStaffMessage,
    User,
)
from routers.auth import get_current_user
from routers.staff_portal import get_current_staff_record
from schemas.student_staff_message import (
    StudentStaffMessageCreate,
    StudentStaffReplyCreate,
)


router = APIRouter(
    prefix="/student-staff-messages",
    tags=["Student Staff Messages"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_active_student(current_user: User):
    if current_user.role != "user":
        raise HTTPException(status_code=403, detail="Student access required")
    if current_user.status != "Active":
        raise HTTPException(status_code=403, detail="Student account is inactive")


def get_course_staff(db: Session, course: Course):
    staff_rows = (
        db.query(Staff, User)
        .join(User, User.id == Staff.user_id)
        .outerjoin(StaffCourse, StaffCourse.staff_id == Staff.id)
        .filter(
            Staff.branch_id == course.branch_id,
            Staff.status == "Active",
            User.status == "Active",
            User.role == "staff",
            or_(
                StaffCourse.course_id == course.id,
                and_(
                    StaffCourse.id.is_(None),
                    Staff.course_id == course.id,
                    ~exists()
                    .where(StaffCourse.staff_id == Staff.id)
                    .correlate(Staff),
                ),
            ),
        )
        .distinct()
        .order_by(Staff.name.asc(), Staff.id.asc())
        .all()
    )
    return staff_rows


def get_student_course(db: Session, student: User, course_id: int) -> Course:
    enrollment = (
        db.query(Enrollment.id)
        .filter(
            Enrollment.user_id == student.id,
            Enrollment.course_id == course_id,
            Enrollment.course_status == "approved",
        )
        .first()
    )
    if not enrollment:
        raise HTTPException(
            status_code=403,
            detail="You are not enrolled in this approved course",
        )

    course = (
        db.query(Course)
        .filter(Course.id == course_id, Course.is_active == True)
        .first()
    )
    if not course:
        raise HTTPException(status_code=404, detail="Active course not found")
    return course


def get_conversation_messages(db: Session, conversation_id: int):
    return (
        db.query(StudentStaffMessage, User)
        .join(User, User.id == StudentStaffMessage.sender_id)
        .filter(StudentStaffMessage.conversation_id == conversation_id)
        .order_by(StudentStaffMessage.created_at.asc(), StudentStaffMessage.id.asc())
        .all()
    )


def message_response(message: StudentStaffMessage, sender: User):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": sender.name,
        "sender_role": message.sender_role,
        "message": message.message,
        "is_read": message.is_read,
        "created_at": message.created_at,
    }


def conversation_response(db: Session, conversation: StudentStaffConversation):
    student = db.query(User).filter(User.id == conversation.student_id).first()
    staff = db.query(Staff).filter(Staff.id == conversation.staff_id).first()
    course = db.query(Course).filter(Course.id == conversation.course_id).first()
    last_message = (
        db.query(StudentStaffMessage)
        .filter(StudentStaffMessage.conversation_id == conversation.id)
        .order_by(
            StudentStaffMessage.created_at.desc(),
            StudentStaffMessage.id.desc(),
        )
        .first()
    )
    return {
        "conversation_id": conversation.id,
        "student": (
            {"id": student.id, "name": student.name} if student else None
        ),
        "staff": (
            {"id": staff.id, "name": staff.name, "user_id": staff.user_id}
            if staff
            else None
        ),
        "course": (
            {"id": course.id, "title": course.title} if course else None
        ),
        "last_message": (
            {
                "message": last_message.message,
                "sender_role": last_message.sender_role,
                "created_at": last_message.created_at,
            }
            if last_message
            else None
        ),
        "unread_count": 0,
    }


@router.get("/student/available-staff")
def get_student_available_staff(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_active_student(current_user)
    courses = (
        db.query(Course)
        .join(Enrollment, Enrollment.course_id == Course.id)
        .filter(
            Enrollment.user_id == current_user.id,
            Enrollment.course_status == "approved",
            Course.is_active == True,
        )
        .distinct()
        .order_by(Course.title.asc(), Course.id.asc())
        .all()
    )

    return {
        "courses": [
            {
                "course_id": course.id,
                "course_title": course.title,
                "staff": [
                    {
                        "staff_id": staff.id,
                        "staff_name": staff.name,
                        "staff_user_id": user.id,
                    }
                    for staff, user in get_course_staff(db, course)
                ],
            }
            for course in courses
        ]
    }


@router.post("/student/send", status_code=201)
def student_send_message(
    message_data: StudentStaffMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_active_student(current_user)
    course = get_student_course(db, current_user, message_data.course_id)
    assigned_staff = {
        staff.id: (staff, user)
        for staff, user in get_course_staff(db, course)
    }
    if message_data.staff_id not in assigned_staff:
        raise HTTPException(
            status_code=403,
            detail="Selected staff member is not assigned to this course",
        )

    message_text = message_data.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    conversation = (
        db.query(StudentStaffConversation)
        .filter(
            StudentStaffConversation.student_id == current_user.id,
            StudentStaffConversation.staff_id == message_data.staff_id,
            StudentStaffConversation.course_id == course.id,
        )
        .first()
    )
    if not conversation:
        conversation = StudentStaffConversation(
            student_id=current_user.id,
            staff_id=message_data.staff_id,
            course_id=course.id,
        )
        db.add(conversation)
        db.flush()

    message = StudentStaffMessage(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        sender_role="student",
        message=message_text,
        is_read=False,
    )
    db.add(message)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    db.refresh(conversation)
    return {
        "message": "Message sent successfully",
        "conversation_id": conversation.id,
        "data": message_response(message, current_user),
    }


@router.get("/student/conversations")
def get_student_conversations(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_active_student(current_user)
    conversations = (
        db.query(StudentStaffConversation)
        .filter(StudentStaffConversation.student_id == current_user.id)
        .order_by(
            StudentStaffConversation.updated_at.desc(),
            StudentStaffConversation.id.desc(),
        )
        .all()
    )
    results = []
    total_unread = 0
    for conversation in conversations:
        unread = (
            db.query(func.count(StudentStaffMessage.id))
            .filter(
                StudentStaffMessage.conversation_id == conversation.id,
                StudentStaffMessage.sender_role == "staff",
                StudentStaffMessage.is_read == False,
            )
            .scalar()
            or 0
        )
        total_unread += unread
        summary = conversation_response(db, conversation)
        summary["unread_count"] = unread
        results.append(summary)
    return {
        "unread_count": total_unread,
        "total_conversations": len(results),
        "conversations": results,
    }


@router.get("/student/unread-count")
def get_student_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_active_student(current_user)
    unread = (
        db.query(func.count(StudentStaffMessage.id))
        .join(
            StudentStaffConversation,
            StudentStaffConversation.id == StudentStaffMessage.conversation_id,
        )
        .filter(
            StudentStaffConversation.student_id == current_user.id,
            StudentStaffMessage.sender_role == "staff",
            StudentStaffMessage.is_read == False,
        )
        .scalar()
        or 0
    )
    return {"unread_count": unread}


@router.get("/student/conversations/{conversation_id}")
def get_student_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_active_student(current_user)
    conversation = (
        db.query(StudentStaffConversation)
        .filter(
            StudentStaffConversation.id == conversation_id,
            StudentStaffConversation.student_id == current_user.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.query(StudentStaffMessage).filter(
        StudentStaffMessage.conversation_id == conversation.id,
        StudentStaffMessage.sender_role == "staff",
        StudentStaffMessage.is_read == False,
    ).update(
        {StudentStaffMessage.is_read: True},
        synchronize_session=False,
    )
    db.commit()
    return {
        **conversation_response(db, conversation),
        "messages": [
            message_response(message, sender)
            for message, sender in get_conversation_messages(db, conversation.id)
        ],
    }


@router.get("/staff/conversations")
def get_staff_conversations(
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    conversations = (
        db.query(StudentStaffConversation)
        .filter(StudentStaffConversation.staff_id == current_staff.id)
        .order_by(
            StudentStaffConversation.updated_at.desc(),
            StudentStaffConversation.id.desc(),
        )
        .all()
    )
    results = []
    total_unread = 0
    for conversation in conversations:
        unread = (
            db.query(func.count(StudentStaffMessage.id))
            .filter(
                StudentStaffMessage.conversation_id == conversation.id,
                StudentStaffMessage.sender_role == "student",
                StudentStaffMessage.is_read == False,
            )
            .scalar()
            or 0
        )
        total_unread += unread
        summary = conversation_response(db, conversation)
        summary["unread_count"] = unread
        results.append(summary)
    return {
        "unread_count": total_unread,
        "total_conversations": len(results),
        "conversations": results,
    }


@router.get("/staff/unread-count")
def get_staff_unread_count(
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    unread = (
        db.query(func.count(StudentStaffMessage.id))
        .join(
            StudentStaffConversation,
            StudentStaffConversation.id == StudentStaffMessage.conversation_id,
        )
        .filter(
            StudentStaffConversation.staff_id == current_staff.id,
            StudentStaffMessage.sender_role == "student",
            StudentStaffMessage.is_read == False,
        )
        .scalar()
        or 0
    )
    return {"unread_count": unread}


@router.get("/staff/conversations/{conversation_id}")
def get_staff_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    conversation = (
        db.query(StudentStaffConversation)
        .filter(
            StudentStaffConversation.id == conversation_id,
            StudentStaffConversation.staff_id == current_staff.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.query(StudentStaffMessage).filter(
        StudentStaffMessage.conversation_id == conversation.id,
        StudentStaffMessage.sender_role == "student",
        StudentStaffMessage.is_read == False,
    ).update(
        {StudentStaffMessage.is_read: True},
        synchronize_session=False,
    )
    db.commit()
    return {
        **conversation_response(db, conversation),
        "messages": [
            message_response(message, sender)
            for message, sender in get_conversation_messages(db, conversation.id)
        ],
    }


@router.post("/staff/conversations/{conversation_id}/reply", status_code=201)
def staff_reply_to_student(
    conversation_id: int,
    message_data: StudentStaffReplyCreate,
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    conversation = (
        db.query(StudentStaffConversation)
        .filter(
            StudentStaffConversation.id == conversation_id,
            StudentStaffConversation.staff_id == current_staff.id,
        )
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    message_text = message_data.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    message = StudentStaffMessage(
        conversation_id=conversation.id,
        sender_id=current_staff.user_id,
        sender_role="staff",
        message=message_text,
        is_read=False,
    )
    db.add(message)
    conversation.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(message)
    return {
        "message": "Reply sent successfully",
        "conversation_id": conversation.id,
        "data": message_response(
            message,
            db.query(User).filter(User.id == current_staff.user_id).first(),
        ),
    }
