from datetime import datetime

from pydantic import BaseModel


# ==========================================
# SEND MESSAGE
# ==========================================

class MessageCreate(BaseModel):
    message: str


# ==========================================
# MESSAGE RESPONSE
# ==========================================

class MessageResponse(BaseModel):
    id: int
    conversation_id: int
    sender_id: int
    sender_role: str
    message: str
    is_read: bool
    created_at: datetime | None = None