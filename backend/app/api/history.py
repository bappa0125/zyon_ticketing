"""History API - GET /api/history, POST /api/new-chat."""
from fastapi import APIRouter, HTTPException

from app.services import mongodb as db
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)


@router.get("/history/{conversation_id}")
async def get_history(conversation_id: str):
    """Get all messages for a conversation."""
    messages = await db.get_messages(conversation_id)
    return {"conversation_id": conversation_id, "messages": messages}


@router.post("/new-chat")
async def new_chat():
    """Create a new conversation and return its ID."""
    conv_id = await db.create_conversation(title="New Chat")
    return {"conversation_id": conv_id}
