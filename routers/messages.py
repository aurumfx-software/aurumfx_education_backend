









# from fastapi import (
#     APIRouter,
#     Depends,
#     HTTPException,
#     WebSocket,
#     WebSocketDisconnect
# )

# from sqlalchemy.orm import Session

# from database import SessionLocal

# from database_models import (
#     User,
#     MessageConversation,
#     Message
# )

# from routers.auth import get_current_user

# from schemas.message import MessageCreate

# from utils.websocket_manager import manager

# from utils.jwt import decode_access_token


# router = APIRouter(
#     prefix="/messages"
# )


# # =========================================================
# # DATABASE
# # =========================================================

# def get_db():

#     db = SessionLocal()

#     try:
#         yield db

#     finally:
#         db.close()


# # =========================================================
# # BRANCH ADMIN - SEND MESSAGE
# # =========================================================

# @router.post(
#     "/send",
#     tags=["Branch Admin - Messages"]
# )
# async def send_message(
#     message_data: MessageCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):

#     # -----------------------------------------------------
#     # Check Branch Admin
#     # -----------------------------------------------------

#     if current_user.role != "branch_admin":

#         raise HTTPException(
#             status_code=403,
#             detail="Branch admin access required"
#         )

#     # -----------------------------------------------------
#     # Check branch
#     # -----------------------------------------------------

#     if not current_user.branch_id:

#         raise HTTPException(
#             status_code=400,
#             detail="Branch admin is not assigned to a branch"
#         )

#     # -----------------------------------------------------
#     # Validate message
#     # -----------------------------------------------------

#     message_text = message_data.message.strip()

#     if not message_text:

#         raise HTTPException(
#             status_code=400,
#             detail="Message cannot be empty"
#         )

#     # -----------------------------------------------------
#     # Find existing conversation
#     # -----------------------------------------------------

#     conversation = (
#         db.query(MessageConversation)
#         .filter(
#             MessageConversation.branch_admin_id
#             == current_user.id
#         )
#         .first()
#     )

#     # -----------------------------------------------------
#     # Create conversation if it doesn't exist
#     # -----------------------------------------------------

#     if not conversation:

#         conversation = MessageConversation(
#             branch_admin_id=current_user.id,
#             branch_id=current_user.branch_id
#         )

#         db.add(conversation)
#         db.flush()

#     # -----------------------------------------------------
#     # Create message
#     # -----------------------------------------------------

#     new_message = Message(
#         conversation_id=conversation.id,
#         sender_id=current_user.id,
#         sender_role=current_user.role,
#         message=message_text,
#         is_read=False
#     )

#     db.add(new_message)

#     db.commit()
#     db.refresh(new_message)

#     # -----------------------------------------------------
#     # Find active Super Admin
#     # -----------------------------------------------------

#     super_admin = (
#         db.query(User)
#         .filter(
#             User.role == "super_admin",
#             User.status == "Active"
#         )
#         .first()
#     )

#     # -----------------------------------------------------
#     # Send real-time message to Super Admin
#     # -----------------------------------------------------

#     if super_admin:

#         await manager.send_to_user(
#             super_admin.id,
#             {
#                 "type": "new_message",

#                 "conversation_id": conversation.id,

#                 "message": {
#                     "id": new_message.id,
#                     "sender_id": new_message.sender_id,
#                     "sender_role": new_message.sender_role,
#                     "message": new_message.message,
#                     "is_read": new_message.is_read,
#                     "created_at": (
#                         new_message.created_at.isoformat()
#                         if new_message.created_at
#                         else None
#                     )
#                 }
#             }
#         )

#     # -----------------------------------------------------
#     # Response
#     # -----------------------------------------------------

#     return {
#         "message": "Message sent successfully",

#         "conversation_id": conversation.id,

#         "data": {
#             "id": new_message.id,
#             "sender_id": new_message.sender_id,
#             "sender_role": new_message.sender_role,
#             "message": new_message.message,
#             "is_read": new_message.is_read,
#             "created_at": new_message.created_at
#         }
#     }


# # =========================================================
# # BRANCH ADMIN - GET OWN MESSAGES
# # =========================================================

# @router.get(
#     "/my",
#     tags=["Branch Admin - Messages"]
# )
# def get_my_messages(
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):

#     # -----------------------------------------------------
#     # Check Branch Admin
#     # -----------------------------------------------------

#     if current_user.role != "branch_admin":

#         raise HTTPException(
#             status_code=403,
#             detail="Branch admin access required"
#         )

#     # -----------------------------------------------------
#     # Find conversation
#     # -----------------------------------------------------

#     conversation = (
#         db.query(MessageConversation)
#         .filter(
#             MessageConversation.branch_admin_id
#             == current_user.id
#         )
#         .first()
#     )

#     # -----------------------------------------------------
#     # No conversation
#     # -----------------------------------------------------

#     if not conversation:

#         return {
#             "conversation_id": None,
#             "messages": []
#         }

#     # -----------------------------------------------------
#     # Mark Super Admin messages as READ
#     #
#     # When Branch Admin opens the conversation,
#     # all messages received from Super Admin become read.
#     # -----------------------------------------------------

#     (
#         db.query(Message)
#         .filter(
#             Message.conversation_id == conversation.id,
#             Message.sender_role == "super_admin",
#             Message.is_read == False
#         )
#         .update(
#             {
#                 Message.is_read: True
#             },
#             synchronize_session=False
#         )
#     )

#     db.commit()

#     # -----------------------------------------------------
#     # Get messages
#     # -----------------------------------------------------

#     messages = (
#         db.query(Message)
#         .filter(
#             Message.conversation_id
#             == conversation.id
#         )
#         .order_by(
#             Message.created_at.asc()
#         )
#         .all()
#     )

#     # -----------------------------------------------------
#     # Response
#     # -----------------------------------------------------

#     return {
#         "conversation_id": conversation.id,

#         "messages": [
#             {
#                 "id": message.id,
#                 "sender_id": message.sender_id,
#                 "sender_role": message.sender_role,
#                 "message": message.message,
#                 "is_read": message.is_read,
#                 "created_at": message.created_at
#             }
#             for message in messages
#         ]
#     }


# # =========================================================
# # SUPER ADMIN - GET CONVERSATION
# # =========================================================

# @router.get(
#     "/super-admin/{conversation_id}",
#     tags=["Super Admin - Messages"]
# )
# def get_super_admin_conversation(
#     conversation_id: int,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):

#     # -----------------------------------------------------
#     # Check Super Admin
#     # -----------------------------------------------------

#     if current_user.role != "super_admin":

#         raise HTTPException(
#             status_code=403,
#             detail="Super admin access required"
#         )

#     # -----------------------------------------------------
#     # Find conversation
#     # -----------------------------------------------------

#     conversation = (
#         db.query(MessageConversation)
#         .filter(
#             MessageConversation.id
#             == conversation_id
#         )
#         .first()
#     )

#     # -----------------------------------------------------
#     # Conversation not found
#     # -----------------------------------------------------

#     if not conversation:

#         raise HTTPException(
#             status_code=404,
#             detail="Conversation not found"
#         )

#     # -----------------------------------------------------
#     # Mark Branch Admin messages as READ
#     #
#     # When Super Admin opens the conversation,
#     # all messages received from Branch Admin become read.
#     # -----------------------------------------------------

#     (
#         db.query(Message)
#         .filter(
#             Message.conversation_id == conversation.id,
#             Message.sender_role == "branch_admin",
#             Message.is_read == False
#         )
#         .update(
#             {
#                 Message.is_read: True
#             },
#             synchronize_session=False
#         )
#     )

#     db.commit()

#     # -----------------------------------------------------
#     # Get messages AFTER marking them as read
#     # -----------------------------------------------------

#     messages = (
#         db.query(Message)
#         .filter(
#             Message.conversation_id
#             == conversation.id
#         )
#         .order_by(
#             Message.created_at.asc()
#         )
#         .all()
#     )

#     # -----------------------------------------------------
#     # Get Branch Admin
#     # -----------------------------------------------------

#     branch_admin = (
#         db.query(User)
#         .filter(
#             User.id
#             == conversation.branch_admin_id
#         )
#         .first()
#     )

#     # -----------------------------------------------------
#     # Response
#     # -----------------------------------------------------

#     return {
#         "conversation_id": conversation.id,

#         "branch_admin_id":
#             conversation.branch_admin_id,

#         "branch_admin_name":
#             branch_admin.name
#             if branch_admin
#             else None,

#         "branch_id":
#             conversation.branch_id,

#         "messages": [
#             {
#                 "id": message.id,
#                 "sender_id": message.sender_id,
#                 "sender_role": message.sender_role,
#                 "message": message.message,
#                 "is_read": message.is_read,
#                 "created_at": message.created_at
#             }
#             for message in messages
#         ]
#     }


# # =========================================================
# # SUPER ADMIN - REPLY
# # =========================================================

# @router.post(
#     "/super-admin/{conversation_id}/reply",
#     tags=["Super Admin - Messages"]
# )
# async def super_admin_reply(
#     conversation_id: int,
#     message_data: MessageCreate,
#     db: Session = Depends(get_db),
#     current_user: User = Depends(get_current_user)
# ):

#     # -----------------------------------------------------
#     # Check Super Admin
#     # -----------------------------------------------------

#     if current_user.role != "super_admin":

#         raise HTTPException(
#             status_code=403,
#             detail="Super admin access required"
#         )

#     # -----------------------------------------------------
#     # Validate message
#     # -----------------------------------------------------

#     message_text = message_data.message.strip()

#     if not message_text:

#         raise HTTPException(
#             status_code=400,
#             detail="Message cannot be empty"
#         )

#     # -----------------------------------------------------
#     # Find conversation
#     # -----------------------------------------------------

#     conversation = (
#         db.query(MessageConversation)
#         .filter(
#             MessageConversation.id
#             == conversation_id
#         )
#         .first()
#     )

#     if not conversation:

#         raise HTTPException(
#             status_code=404,
#             detail="Conversation not found"
#         )

#     # -----------------------------------------------------
#     # Create message
#     # -----------------------------------------------------

#     new_message = Message(
#         conversation_id=conversation.id,
#         sender_id=current_user.id,
#         sender_role=current_user.role,
#         message=message_text,
#         is_read=False
#     )

#     db.add(new_message)

#     db.commit()
#     db.refresh(new_message)

#     # -----------------------------------------------------
#     # Send real-time message to Branch Admin
#     # -----------------------------------------------------

#     await manager.send_to_user(
#         conversation.branch_admin_id,
#         {
#             "type": "new_message",

#             "conversation_id":
#                 conversation.id,

#             "message": {
#                 "id":
#                     new_message.id,

#                 "sender_id":
#                     new_message.sender_id,

#                 "sender_role":
#                     new_message.sender_role,

#                 "message":
#                     new_message.message,

#                 "is_read":
#                     new_message.is_read,

#                 "created_at": (
#                     new_message.created_at.isoformat()
#                     if new_message.created_at
#                     else None
#                 )
#             }
#         }
#     )

#     # -----------------------------------------------------
#     # Response
#     # -----------------------------------------------------

#     return {
#         "message": "Reply sent successfully",

#         "conversation_id":
#             conversation.id,

#         "data": {
#             "id":
#                 new_message.id,

#             "sender_id":
#                 new_message.sender_id,

#             "sender_role":
#                 new_message.sender_role,

#             "message":
#                 new_message.message,

#             "is_read":
#                 new_message.is_read,

#             "created_at":
#                 new_message.created_at
#         }
#     }


# # =========================================================
# # WEBSOCKET - REAL TIME MESSAGING
# # =========================================================

# @router.websocket("/ws")
# async def websocket_endpoint(
#     websocket: WebSocket
# ):

#     db = SessionLocal()

#     current_user = None

#     try:

#         # -------------------------------------------------
#         # Accept WebSocket connection
#         # -------------------------------------------------

#         await websocket.accept()

#         # -------------------------------------------------
#         # First message must contain JWT
#         # -------------------------------------------------

#         auth_data = await websocket.receive_json()

#         if auth_data.get("type") != "auth":

#             await websocket.close(
#                 code=1008
#             )

#             return

#         token = auth_data.get("token")

#         if not token:

#             await websocket.close(
#                 code=1008
#             )

#             return

#         # -------------------------------------------------
#         # Decode JWT
#         # -------------------------------------------------

#         payload = decode_access_token(token)

#         if not payload:

#             await websocket.close(
#                 code=1008
#             )

#             return

#         user_id = payload.get("sub")

#         if not user_id:

#             await websocket.close(
#                 code=1008
#             )

#             return

#         # -------------------------------------------------
#         # Get user from database
#         # -------------------------------------------------

#         current_user = (
#             db.query(User)
#             .filter(
#                 User.id == int(user_id)
#             )
#             .first()
#         )

#         if not current_user:

#             await websocket.close(
#                 code=1008
#             )

#             return

#         # -------------------------------------------------
#         # Check user status
#         # -------------------------------------------------

#         if current_user.status != "Active":

#             await websocket.close(
#                 code=1008
#             )

#             return

#         # -------------------------------------------------
#         # Only Branch Admin and Super Admin
#         # -------------------------------------------------

#         if current_user.role not in [
#             "branch_admin",
#             "super_admin"
#         ]:

#             await websocket.close(
#                 code=1008
#             )

#             return

#         # -------------------------------------------------
#         # Register connection
#         # -------------------------------------------------

#         await manager.connect(
#             current_user.id,
#             websocket
#         )

#         # -------------------------------------------------
#         # Send connection confirmation
#         # -------------------------------------------------

#         await websocket.send_json({
#             "type": "connected",
#             "user_id": current_user.id,
#             "role": current_user.role
#         })

#         # -------------------------------------------------
#         # Keep connection alive
#         # -------------------------------------------------

#         while True:

#             data = await websocket.receive_json()

#             # ---------------------------------------------
#             # Ping / Pong
#             # ---------------------------------------------

#             if data.get("type") == "ping":

#                 await websocket.send_json({
#                     "type": "pong"
#                 })

#     except WebSocketDisconnect:

#         if current_user:

#             manager.disconnect(
#                 current_user.id
#             )

#     except Exception as e:

#         print(
#             "WebSocket error:",
#             e
#         )

#         if current_user:

#             manager.disconnect(
#                 current_user.id
#             )

#     finally:

#         db.close()



























from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    WebSocket,
    WebSocketDisconnect
)

from sqlalchemy.orm import Session

from database import SessionLocal

from database_models import (
    User,
    MessageConversation,
    Message
)

from routers.auth import get_current_user

from schemas.message import MessageCreate

from utils.websocket_manager import manager

from utils.jwt import decode_access_token


router = APIRouter(
    prefix="/messages"
)


# =========================================================
# DATABASE
# =========================================================

def get_db():

    db = SessionLocal()

    try:
        yield db

    finally:
        db.close()


# =========================================================
# BRANCH ADMIN - SEND MESSAGE
# =========================================================

@router.post(
    "/send",
    tags=["Branch Admin - Messages"]
)
async def send_message(
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # -----------------------------------------------------
    # Check Branch Admin
    # -----------------------------------------------------

    if current_user.role != "branch_admin":

        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # -----------------------------------------------------
    # Check branch
    # -----------------------------------------------------

    if not current_user.branch_id:

        raise HTTPException(
            status_code=400,
            detail="Branch admin is not assigned to a branch"
        )

    # -----------------------------------------------------
    # Validate message
    # -----------------------------------------------------

    message_text = message_data.message.strip()

    if not message_text:

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    # -----------------------------------------------------
    # Find existing conversation
    # -----------------------------------------------------

    conversation = (
        db.query(MessageConversation)
        .filter(
            MessageConversation.branch_admin_id
            == current_user.id
        )
        .first()
    )

    # -----------------------------------------------------
    # Create conversation if it doesn't exist
    # -----------------------------------------------------

    if not conversation:

        conversation = MessageConversation(
            branch_admin_id=current_user.id,
            branch_id=current_user.branch_id
        )

        db.add(conversation)
        db.flush()

    # -----------------------------------------------------
    # Create message
    # -----------------------------------------------------

    new_message = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        sender_role=current_user.role,
        message=message_text,
        is_read=False
    )

    db.add(new_message)

    db.commit()
    db.refresh(new_message)

    # -----------------------------------------------------
    # Find active Super Admin
    # -----------------------------------------------------

    super_admin = (
        db.query(User)
        .filter(
            User.role == "super_admin",
            User.status == "Active"
        )
        .first()
    )

    # -----------------------------------------------------
    # Send real-time message to Super Admin
    # -----------------------------------------------------

    if super_admin:

        await manager.send_to_user(
            super_admin.id,
            {
                "type": "new_message",

                "conversation_id": conversation.id,

                "message": {
                    "id": new_message.id,
                    "sender_id": new_message.sender_id,
                    "sender_role": new_message.sender_role,
                    "message": new_message.message,
                    "is_read": new_message.is_read,
                    "created_at": (
                        new_message.created_at.isoformat()
                        if new_message.created_at
                        else None
                    )
                }
            }
        )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "message": "Message sent successfully",

        "conversation_id": conversation.id,

        "data": {
            "id": new_message.id,
            "sender_id": new_message.sender_id,
            "sender_role": new_message.sender_role,
            "message": new_message.message,
            "is_read": new_message.is_read,
            "created_at": new_message.created_at
        }
    }


# =========================================================
# BRANCH ADMIN - GET OWN MESSAGES
# =========================================================

@router.get(
    "/my",
    tags=["Branch Admin - Messages"]
)
def get_my_messages(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # -----------------------------------------------------
    # Check Branch Admin
    # -----------------------------------------------------

    if current_user.role != "branch_admin":

        raise HTTPException(
            status_code=403,
            detail="Branch admin access required"
        )

    # -----------------------------------------------------
    # Find conversation
    # -----------------------------------------------------

    conversation = (
        db.query(MessageConversation)
        .filter(
            MessageConversation.branch_admin_id
            == current_user.id
        )
        .first()
    )

    # -----------------------------------------------------
    # No conversation
    # -----------------------------------------------------

    if not conversation:

        return {
            "conversation_id": None,
            "messages": []
        }

    # -----------------------------------------------------
    # Mark Super Admin messages as READ
    #
    # When Branch Admin opens the conversation,
    # all messages received from Super Admin become read.
    # -----------------------------------------------------

    (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.sender_role == "super_admin",
            Message.is_read == False
        )
        .update(
            {
                Message.is_read: True
            },
            synchronize_session=False
        )
    )

    db.commit()

    # -----------------------------------------------------
    # Get messages
    # -----------------------------------------------------

    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id
            == conversation.id
        )
        .order_by(
            Message.created_at.asc()
        )
        .all()
    )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "conversation_id": conversation.id,

        "messages": [
            {
                "id": message.id,
                "sender_id": message.sender_id,
                "sender_role": message.sender_role,
                "message": message.message,
                "is_read": message.is_read,
                "created_at": message.created_at
            }
            for message in messages
        ]
    }


# =========================================================
# SUPER ADMIN - GET CONVERSATION
# =========================================================

@router.get(
    "/super-admin/{conversation_id}",
    tags=["Super Admin - Messages"]
)
def get_super_admin_conversation(
    conversation_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # -----------------------------------------------------
    # Check Super Admin
    # -----------------------------------------------------

    if current_user.role != "super_admin":

        raise HTTPException(
            status_code=403,
            detail="Super admin access required"
        )

    # -----------------------------------------------------
    # Find conversation
    # -----------------------------------------------------

    conversation = (
        db.query(MessageConversation)
        .filter(
            MessageConversation.id
            == conversation_id
        )
        .first()
    )

    # -----------------------------------------------------
    # Conversation not found
    # -----------------------------------------------------

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    # -----------------------------------------------------
    # Mark Branch Admin messages as READ
    #
    # When Super Admin opens the conversation,
    # all messages received from Branch Admin become read.
    # -----------------------------------------------------

    (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.sender_role == "branch_admin",
            Message.is_read == False
        )
        .update(
            {
                Message.is_read: True
            },
            synchronize_session=False
        )
    )

    db.commit()

    # -----------------------------------------------------
    # Get messages AFTER marking them as read
    # -----------------------------------------------------

    messages = (
        db.query(Message)
        .filter(
            Message.conversation_id
            == conversation.id
        )
        .order_by(
            Message.created_at.asc()
        )
        .all()
    )

    # -----------------------------------------------------
    # Get Branch Admin
    # -----------------------------------------------------

    branch_admin = (
        db.query(User)
        .filter(
            User.id
            == conversation.branch_admin_id
        )
        .first()
    )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "conversation_id": conversation.id,

        "branch_admin_id":
            conversation.branch_admin_id,

        "branch_admin_name":
            branch_admin.name
            if branch_admin
            else None,

        "branch_id":
            conversation.branch_id,

        "messages": [
            {
                "id": message.id,
                "sender_id": message.sender_id,
                "sender_role": message.sender_role,
                "message": message.message,
                "is_read": message.is_read,
                "created_at": message.created_at
            }
            for message in messages
        ]
    }


# =========================================================
# SUPER ADMIN - REPLY
# =========================================================

@router.post(
    "/super-admin/{conversation_id}/reply",
    tags=["Super Admin - Messages"]
)
async def super_admin_reply(
    conversation_id: int,
    message_data: MessageCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):

    # -----------------------------------------------------
    # Check Super Admin
    # -----------------------------------------------------

    if current_user.role != "super_admin":

        raise HTTPException(
            status_code=403,
            detail="Super admin access required"
        )

    # -----------------------------------------------------
    # Validate message
    # -----------------------------------------------------

    message_text = message_data.message.strip()

    if not message_text:

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty"
        )

    # -----------------------------------------------------
    # Find conversation
    # -----------------------------------------------------

    conversation = (
        db.query(MessageConversation)
        .filter(
            MessageConversation.id
            == conversation_id
        )
        .first()
    )

    if not conversation:

        raise HTTPException(
            status_code=404,
            detail="Conversation not found"
        )

    # -----------------------------------------------------
    # IMPORTANT:
    # When Super Admin replies, the Branch Admin's
    # previous message becomes READ.
    # -----------------------------------------------------

    (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id,
            Message.sender_role == "branch_admin",
            Message.is_read == False
        )
        .update(
            {
                Message.is_read: True
            },
            synchronize_session=False
        )
    )

    # -----------------------------------------------------
    # Create Super Admin reply
    # -----------------------------------------------------

    new_message = Message(
        conversation_id=conversation.id,
        sender_id=current_user.id,
        sender_role=current_user.role,
        message=message_text,
        is_read=False
    )

    db.add(new_message)

    db.commit()

    db.refresh(new_message)

    # -----------------------------------------------------
    # Send real-time message to Branch Admin
    # -----------------------------------------------------

    await manager.send_to_user(
        conversation.branch_admin_id,
        {
            "type": "new_message",

            "conversation_id":
                conversation.id,

            "message": {

                "id":
                    new_message.id,

                "sender_id":
                    new_message.sender_id,

                "sender_role":
                    new_message.sender_role,

                "message":
                    new_message.message,

                "is_read":
                    new_message.is_read,

                "created_at": (
                    new_message.created_at.isoformat()
                    if new_message.created_at
                    else None
                )
            }
        }
    )

    # -----------------------------------------------------
    # Response
    # -----------------------------------------------------

    return {
        "message":
            "Reply sent successfully",

        "conversation_id":
            conversation.id,

        "data": {

            "id":
                new_message.id,

            "sender_id":
                new_message.sender_id,

            "sender_role":
                new_message.sender_role,

            "message":
                new_message.message,

            "is_read":
                new_message.is_read,

            "created_at":
                new_message.created_at
        }
    }


# =========================================================
# WEBSOCKET - REAL TIME MESSAGING
# =========================================================

@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket
):

    db = SessionLocal()

    current_user = None

    try:

        # -------------------------------------------------
        # Accept WebSocket connection
        # -------------------------------------------------

        await websocket.accept()

        # -------------------------------------------------
        # First message must contain JWT
        # -------------------------------------------------

        auth_data = await websocket.receive_json()

        if auth_data.get("type") != "auth":

            await websocket.close(
                code=1008
            )

            return

        token = auth_data.get("token")

        if not token:

            await websocket.close(
                code=1008
            )

            return

        # -------------------------------------------------
        # Decode JWT
        # -------------------------------------------------

        payload = decode_access_token(token)

        if not payload:

            await websocket.close(
                code=1008
            )

            return

        user_id = payload.get("sub")

        if not user_id:

            await websocket.close(
                code=1008
            )

            return

        # -------------------------------------------------
        # Get user from database
        # -------------------------------------------------

        current_user = (
            db.query(User)
            .filter(
                User.id == int(user_id)
            )
            .first()
        )

        if not current_user:

            await websocket.close(
                code=1008
            )

            return

        # -------------------------------------------------
        # Check user status
        # -------------------------------------------------

        if current_user.status != "Active":

            await websocket.close(
                code=1008
            )

            return

        # -------------------------------------------------
        # Only Branch Admin and Super Admin
        # -------------------------------------------------

        if current_user.role not in [
            "branch_admin",
            "super_admin"
        ]:

            await websocket.close(
                code=1008
            )

            return

        # -------------------------------------------------
        # Register connection
        # -------------------------------------------------

        await manager.connect(
            current_user.id,
            websocket
        )

        # -------------------------------------------------
        # Send connection confirmation
        # -------------------------------------------------

        await websocket.send_json({
            "type": "connected",
            "user_id": current_user.id,
            "role": current_user.role
        })

        # -------------------------------------------------
        # Keep connection alive
        # -------------------------------------------------

        while True:

            data = await websocket.receive_json()

            # ---------------------------------------------
            # Ping / Pong
            # ---------------------------------------------

            if data.get("type") == "ping":

                await websocket.send_json({
                    "type": "pong"
                })

    except WebSocketDisconnect:

        if current_user:

            manager.disconnect(
                current_user.id
            )

    except Exception as e:

        print(
            "WebSocket error:",
            e
        )

        if current_user:

            manager.disconnect(
                current_user.id
            )

    finally:

        db.close()







