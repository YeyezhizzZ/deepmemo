from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class MessageCreate(BaseModel):
    role: str
    content: str


class MessageResponse(BaseModel):
    message_id: str
    session_id: str
    role: str
    content: str
    created_at: datetime


class SessionCreate(BaseModel):
    session_name: str


class SessionResponse(BaseModel):
    session_id: str
    session_name: str
    message_ids: list[str]
    session_topic: str = ""
    session_summary: str = ""
    created_at: datetime
    updated_at: datetime


class ChatToolSelection(BaseModel):
    tool_id: str
    scope: str = "next_message"


class ChatToolResponse(BaseModel):
    id: str
    name: str
    description: str
    execution_type: str


class ChatRequest(BaseModel):
    session_id: str
    user_message: str
    tool: Optional[ChatToolSelection] = None
