from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from database import SessionLocal
from database_models import (
    Branch,
    Staff,
    StaffSuperAdminConversation,
    StaffSuperAdminMessage,
    User,
)
from routers.auth import get_current_user
from routers.staff_portal import get_current_staff_record
from schemas.staff_super_admin_message import StaffSuperAdminMessageCreate


router = APIRouter(
    prefix="/staff-super-admin-messages",
    tags=["Staff Super Admin Messages"],
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def require_super_admin(current_user: User):
    if current_user.role != "super_admin":
        raise HTTPException(status_code=403, detail="Super admin access required")


def unread_staff_message_count(db: Session) -> int:
    return (
        db.query(func.count(StaffSuperAdminMessage.id))
        .filter(
            StaffSuperAdminMessage.sender_role == "staff",
            StaffSuperAdminMessage.is_read == False,
        )
        .scalar()
        or 0
    )


def conversation_details(db: Session, conversation: StaffSuperAdminConversation):
    staff = db.query(Staff).filter(Staff.id == conversation.staff_id).first()
    branch = db.query(Branch).filter(Branch.id == conversation.branch_id).first()
    last_message = (
        db.query(StaffSuperAdminMessage)
        .filter(StaffSuperAdminMessage.conversation_id == conversation.id)
        .order_by(
            StaffSuperAdminMessage.created_at.desc(),
            StaffSuperAdminMessage.id.desc(),
        )
        .first()
    )
    unread_count = (
        db.query(func.count(StaffSuperAdminMessage.id))
        .filter(
            StaffSuperAdminMessage.conversation_id == conversation.id,
            StaffSuperAdminMessage.sender_role == "staff",
            StaffSuperAdminMessage.is_read == False,
        )
        .scalar()
        or 0
    )
    return {
        "conversation_id": conversation.id,
        "staff": (
            {
                "id": staff.id,
                "user_id": staff.user_id,
                "name": staff.name,
            }
            if staff
            else None
        ),
        "branch": (
            {"id": branch.id, "name": branch.name}
            if branch
            else None
        ),
        "unread_count": unread_count,
        "last_message": (
            {
                "message": last_message.message,
                "sender_role": last_message.sender_role,
                "created_at": last_message.created_at,
            }
            if last_message
            else None
        ),
        "updated_at": conversation.updated_at,
    }


def serialize_message(message: StaffSuperAdminMessage, sender: User):
    return {
        "id": message.id,
        "sender_id": message.sender_id,
        "sender_name": sender.name,
        "sender_role": message.sender_role,
        "message": message.message,
        "is_read": message.is_read,
        "created_at": message.created_at,
    }


@router.post("/staff/send", status_code=201)
def staff_send_message(
    message_data: StaffSuperAdminMessageCreate,
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    message_text = message_data.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    conversation = (
        db.query(StaffSuperAdminConversation)
        .filter(StaffSuperAdminConversation.staff_id == current_staff.id)
        .first()
    )
    if not conversation:
        conversation = StaffSuperAdminConversation(
            staff_id=current_staff.id,
            branch_id=current_staff.branch_id,
        )
        db.add(conversation)
        db.flush()
    else:
        conversation.branch_id = current_staff.branch_id

    db.query(StaffSuperAdminMessage).filter(
        StaffSuperAdminMessage.conversation_id == conversation.id,
        StaffSuperAdminMessage.sender_role == "super_admin",
        StaffSuperAdminMessage.is_read == False,
    ).update(
        {StaffSuperAdminMessage.is_read: True},
        synchronize_session=False,
    )

    new_message = StaffSuperAdminMessage(
        conversation_id=conversation.id,
        sender_id=current_staff.user_id,
        sender_role="staff",
        message=message_text,
        is_read=False,
    )
    conversation.updated_at = func.now()
    db.add(new_message)
    db.commit()
    db.refresh(new_message)
    branch = db.query(Branch).filter(Branch.id == current_staff.branch_id).first()
    conversation_unread_count = (
        db.query(func.count(StaffSuperAdminMessage.id))
        .filter(
            StaffSuperAdminMessage.conversation_id == conversation.id,
            StaffSuperAdminMessage.sender_role == "staff",
            StaffSuperAdminMessage.is_read == False,
        )
        .scalar()
        or 0
    )

    return {
        "message": "Message sent successfully",
        "conversation_id": conversation.id,
        "staff_name": current_staff.name,
        "branch_id": conversation.branch_id,
        "branch_name": branch.name if branch else None,
        "unread_count": conversation_unread_count,
        "data": {
            "id": new_message.id,
            "sender_id": new_message.sender_id,
            "sender_name": current_staff.name,
            "sender_role": new_message.sender_role,
            "message": new_message.message,
            "is_read": new_message.is_read,
            "created_at": new_message.created_at,
        },
    }


@router.get("/staff/my")
def get_staff_messages(
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    conversation = (
        db.query(StaffSuperAdminConversation)
        .filter(StaffSuperAdminConversation.staff_id == current_staff.id)
        .first()
    )
    if not conversation:
        branch = db.query(Branch).filter(Branch.id == current_staff.branch_id).first()
        return {
            "conversation_id": None,
            "staff_name": current_staff.name,
            "branch_id": current_staff.branch_id,
            "branch_name": branch.name if branch else None,
            "messages": [],
            "unread_count": 0,
        }

    db.query(StaffSuperAdminMessage).filter(
        StaffSuperAdminMessage.conversation_id == conversation.id,
        StaffSuperAdminMessage.sender_role == "super_admin",
        StaffSuperAdminMessage.is_read == False,
    ).update(
        {StaffSuperAdminMessage.is_read: True},
        synchronize_session=False,
    )
    db.commit()

    messages = (
        db.query(StaffSuperAdminMessage, User)
        .join(User, User.id == StaffSuperAdminMessage.sender_id)
        .filter(StaffSuperAdminMessage.conversation_id == conversation.id)
        .order_by(
            StaffSuperAdminMessage.created_at.asc(),
            StaffSuperAdminMessage.id.asc(),
        )
        .all()
    )
    branch = db.query(Branch).filter(Branch.id == conversation.branch_id).first()
    return {
        "conversation_id": conversation.id,
        "staff_name": current_staff.name,
        "branch_id": conversation.branch_id,
        "branch_name": branch.name if branch else None,
        "messages": [
            serialize_message(message, sender)
            for message, sender in messages
        ],
        "unread_count": 0,
    }


@router.get("/staff/unread-count")
def get_staff_unread_count(
    db: Session = Depends(get_db),
    current_staff: Staff = Depends(get_current_staff_record),
):
    unread = (
        db.query(func.count(StaffSuperAdminMessage.id))
        .join(
            StaffSuperAdminConversation,
            StaffSuperAdminConversation.id
            == StaffSuperAdminMessage.conversation_id,
        )
        .filter(
            StaffSuperAdminConversation.staff_id == current_staff.id,
            StaffSuperAdminMessage.sender_role == "super_admin",
            StaffSuperAdminMessage.is_read == False,
        )
        .scalar()
        or 0
    )
    return {"unread_count": unread}


@router.get("/super-admin/inbox")
def get_super_admin_inbox(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_super_admin(current_user)
    conversations = (
        db.query(StaffSuperAdminConversation)
        .order_by(
            StaffSuperAdminConversation.updated_at.desc(),
            StaffSuperAdminConversation.id.desc(),
        )
        .all()
    )
    results = [conversation_details(db, conversation) for conversation in conversations]
    return {
        "unread_count": unread_staff_message_count(db),
        "total_conversations": len(results),
        "conversations": results,
    }


@router.get("/super-admin/unread-count")
def get_super_admin_unread_count(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_super_admin(current_user)
    return {"unread_count": unread_staff_message_count(db)}


@router.get("/super-admin/{conversation_id}")
def get_super_admin_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_super_admin(current_user)
    conversation = (
        db.query(StaffSuperAdminConversation)
        .filter(StaffSuperAdminConversation.id == conversation_id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.query(StaffSuperAdminMessage).filter(
        StaffSuperAdminMessage.conversation_id == conversation.id,
        StaffSuperAdminMessage.sender_role == "staff",
        StaffSuperAdminMessage.is_read == False,
    ).update(
        {StaffSuperAdminMessage.is_read: True},
        synchronize_session=False,
    )
    db.commit()

    messages = (
        db.query(StaffSuperAdminMessage, User)
        .join(User, User.id == StaffSuperAdminMessage.sender_id)
        .filter(StaffSuperAdminMessage.conversation_id == conversation.id)
        .order_by(
            StaffSuperAdminMessage.created_at.asc(),
            StaffSuperAdminMessage.id.asc(),
        )
        .all()
    )
    return {
        **conversation_details(db, conversation),
        "total_unread_count": unread_staff_message_count(db),
        "messages": [
            serialize_message(message, sender)
            for message, sender in messages
        ],
    }


@router.post("/super-admin/{conversation_id}/reply", status_code=201)
def super_admin_reply(
    conversation_id: int,
    message_data: StaffSuperAdminMessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_super_admin(current_user)
    message_text = message_data.message.strip()
    if not message_text:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    conversation = (
        db.query(StaffSuperAdminConversation)
        .filter(StaffSuperAdminConversation.id == conversation_id)
        .first()
    )
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")

    db.query(StaffSuperAdminMessage).filter(
        StaffSuperAdminMessage.conversation_id == conversation.id,
        StaffSuperAdminMessage.sender_role == "staff",
        StaffSuperAdminMessage.is_read == False,
    ).update(
        {StaffSuperAdminMessage.is_read: True},
        synchronize_session=False,
    )
    new_message = StaffSuperAdminMessage(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        sender_role="super_admin",
        message=message_text,
        is_read=False,
    )
    conversation.updated_at = func.now()
    db.add(new_message)
    db.commit()
    db.refresh(new_message)

    return {
        "message": "Reply sent successfully",
        "conversation_id": conversation.id,
        "data": {
            "id": new_message.id,
            "sender_id": new_message.sender_id,
            "sender_name": current_user.name,
            "sender_role": new_message.sender_role,
            "message": new_message.message,
            "is_read": new_message.is_read,
            "created_at": new_message.created_at,
        },
    }
