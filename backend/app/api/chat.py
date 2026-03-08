"""Chat API - POST /api/chat with streaming."""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from app.services.llm_gateway import LLMGateway
from app.services import mongodb as db
from app.services import qdrant_service as qdrant
from app.services import redis_client as redis_svc
from app.core.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

SYSTEM_PROMPT = """You are a helpful AI assistant. Answer concisely and accurately.
Use the conversation context provided when relevant."""


class ChatRequest(BaseModel):
    conversation_id: str
    message: str


def build_messages(conversation_id: str, user_message: str, vector_context: list[dict]) -> list[dict]:
    """Build prompt pipeline: system, summary, last messages, vector context, user."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Optional: conversation summary from Redis
    # summary = await redis_svc.get_cached_summary(conversation_id)

    # Vector context
    if vector_context:
        ctx_text = "\n".join(f"{c['role']}: {c['content'][:200]}" for c in vector_context)
        messages.append({
            "role": "system",
            "content": f"Relevant context from past messages:\n{ctx_text}",
        })

    return messages


async def chat_stream(conversation_id: str, user_message: str):
    """Stream chat response - store messages, get context, call LLM."""
    import asyncio

    # Store user message
    user_msg_id = await db.add_message(conversation_id, "user", user_message)

    # Get vector context (run in thread - Qdrant/embedding are sync)
    vector_context = await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)

    # Build messages for LLM
    last_messages = await db.get_last_messages(conversation_id, n=10)
    msgs_for_llm = build_messages(conversation_id, user_message, vector_context)
    for m in last_messages:
        msgs_for_llm.append({"role": m["role"], "content": m["content"]})
    msgs_for_llm.append({"role": "user", "content": user_message})

    # Stream from LLM
    full_response = []
    gateway = LLMGateway()
    async for chunk in gateway.chat_completion(msgs_for_llm, stream=True):
        full_response.append(chunk)
        yield chunk

    # Store assistant response
    response_text = "".join(full_response)
    asst_msg_id = await db.add_message(conversation_id, "assistant", response_text)

    # Store in Qdrant (run in thread - sync)
    await asyncio.to_thread(qdrant.upsert_message, conversation_id, user_msg_id, "user", user_message)
    await asyncio.to_thread(qdrant.upsert_message, conversation_id, asst_msg_id, "assistant", response_text)


@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream chat response."""
    if not request.conversation_id or not request.message:
        raise HTTPException(status_code=400, detail="conversation_id and message required")

    return StreamingResponse(
        chat_stream(request.conversation_id, request.message),
        media_type="text/plain; charset=utf-8",
    )
