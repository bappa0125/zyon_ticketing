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


def _format_articles_with_links(results: list[dict], topic: str) -> str:
    """Format search results as markdown: title links, metadata, summary. Paragraph structure for clean UI."""
    if not results:
        return f"No mentions found for **{topic}**."
    lines = [f"Here are the latest mentions for **{topic}**:\n"]
    for i, r in enumerate(results[:10], 1):
        try:
            title = str(r.get("title") or "Untitled")[:200]
            link = r.get("link") or r.get("url") or ""
            link = str(link)[:500] if link else ""
            source = str(r.get("source") or "")[:100]
            date_str = r.get("publish_date") or r.get("timestamp") or ""
            date_str = str(date_str)[:30] if date_str else ""
            snippet = str(r.get("snippet") or r.get("summary") or "")[:300]
            t = str(r.get("type") or "article").capitalize()
            lines.append(f"---")
            lines.append("")
            if link:
                lines.append(f"**[{i}] [{title}]({link})**")
            else:
                lines.append(f"**[{i}] {title}**")
            lines.append("")
            meta = []
            if source:
                meta.append(f"Source: {source}")
            if date_str:
                meta.append(f"Date: {date_str}")
            if t and t != "Article":
                meta.append(f"Type: {t}")
            if meta:
                lines.append(" · ".join(meta))
                lines.append("")
            if snippet:
                lines.append(snippet)
            lines.append("")
        except Exception:
            continue
    return "\n".join(lines) if len(lines) > 1 else f"No mentions found for **{topic}**."


def build_messages(
    conversation_id: str,
    user_message: str,
    vector_context: list[dict],
    url_results: list[dict] | None = None,
    search_attempted_no_results: bool = False,
    company: str | None = None,
    use_web_search: bool = False,
    last_user_questions: list[str] | None = None,
) -> list[dict]:
    """Build prompt pipeline. url_results = real search results from Tavily/DuckDuckGo."""
    if use_web_search and company:
        if url_results:
            lines = [f"Search results for {company}. Format each with title, summary, link, source, date:"]
            for i, r in enumerate(url_results[:5], 1):
                title = r.get("title", "Untitled")
                link = r.get("link", r.get("url", r.get("source", "")))
                source = r.get("source", "")
                score = r.get("score")
                date_str = r.get("publish_date", "")
                snippet = (r.get("snippet", "") or "")[:250]
                block = [f"{i}. Title: {title}", f"   URL: {link}", f"   Source: {source}"]
                if date_str:
                    block.append(f"   Date: {date_str}")
                if score is not None:
                    block.append(f"   Score: {score}")
                if snippet:
                    block.append(f"   Summary: {snippet}")
                lines.append("\n".join(block))
            return [
                {
                    "role": "system",
                    "content": (
                        "You MUST format these articles as a numbered list with full URLs. For EACH article use:\n\n"
                        "1. **Title** – [Title](full URL here)\n"
                        "   Summary: one sentence\n"
                        "   Source: domain | Date (if given)\n\n"
                        "CRITICAL: Include the exact URL for every article in [Title](URL) format so users can click. "
                        "Do NOT omit or shorten URLs. Use the URLs provided in the data."
                    ),
                },
                {"role": "user", "content": "\n\n".join(lines)},
            ]
        search_query = (
            f"List 5 recent news articles that mention {company}. "
            "For each: exact title, full URL, 1-sentence summary. Output numbered list."
        )
        return [
            {"role": "system", "content": "Search the web. Return 5 articles. Format: 1. [Title](url) - summary."},
            {"role": "user", "content": search_query},
        ]

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if last_user_questions:
        qlist = "\n".join(f"{i}. {q}" for i, q in enumerate(last_user_questions, 1))
        messages.append({
            "role": "system",
            "content": f"The user asked to recall their previous questions. Here are their actual last {len(last_user_questions)} user messages (in order):\n{qlist}\n\nUse this exact list when answering. Do not invent or paraphrase.",
        })
    elif vector_context:
        ctx_text = "\n".join(f"{c['role']}: {c['content'][:200]}" for c in vector_context)
        messages.append({
            "role": "system",
            "content": f"Relevant context from past messages:\n{ctx_text}",
        })

    return messages


async def chat_stream(conversation_id: str, user_message: str):
    """Stream chat response. Uses intent classifier to gate search; OpenRouter :online for search intent."""
    import asyncio
    from app.services.intent_classifier import classify_intent
    from app.services.url_discovery.intent_detector import (
        extract_company_from_text,
        extract_company_or_topic,
        extract_search_query,
        is_follow_up_request,
        is_recall_questions_request,
        is_greeting_or_casual,
        is_in_scope_for_search,
        get_out_of_scope_message,
    )

    full_response: list[str] = []
    user_msg_id = None
    preliminary = ""

    try:
        logger.info("chat_stream_start", conv=conversation_id[:8], msg_len=len(user_message))
        user_msg_id = await db.add_message(conversation_id, "user", user_message)
        logger.info("chat_after_add_message")

        last_messages = await db.get_last_messages(conversation_id, n=10)
        logger.info("chat_after_get_last_messages", n=len(last_messages))

        # Intent classification: gates search pipeline. No LLM calls.
        intent, search_entity = classify_intent(user_message)
        company = search_entity

        # Greetings first: never search, go straight to LLM
        if is_greeting_or_casual(user_message):
            preliminary = "Thinking...\n\n"
            yield preliminary
            full_response.append(preliminary)
            skip_vector = len(user_message.strip()) < 25
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
            if vector_context:
                ctx = "\n".join(f"{c['role']}: {c['content'][:200]}" for c in vector_context)
                msgs.append({"role": "system", "content": f"Relevant context:\n{ctx}"})
            for m in last_messages:
                msgs.append({"role": m["role"], "content": m["content"]})
            msgs.append({"role": "user", "content": user_message})
            gateway = LLMGateway()
            try:
                async for chunk in gateway.chat_completion(msgs, stream=True, use_web_search=False):
                    full_response.append(chunk)
                    yield chunk
            except Exception as e:
                logger.error("chat_stream_failed", error=str(e))
                fallback = "Hello! I'm doing well, thanks for asking. How can I help you today?"
                yield fallback
                full_response.append(fallback)
            response_text = "".join(full_response)
            if user_msg_id is not None:
                async def _store():
                    try:
                        asst_id = await db.add_message(conversation_id, "assistant", response_text)
                        await asyncio.to_thread(qdrant.upsert_message, conversation_id, user_msg_id, "user", user_message)
                        await asyncio.to_thread(qdrant.upsert_message, conversation_id, asst_id, "assistant", response_text)
                    except Exception as e:
                        logger.warning("chat_store_failed", error=str(e))
                asyncio.create_task(_store())
            return

        # Follow-up: resolve company from previous user message when current message has no entity
        if company is None and is_follow_up_request(user_message):
            for m in last_messages:
                if m.get("role") == "user" and m.get("content") != user_message:
                    company = extract_company_or_topic(m["content"]) or extract_company_from_text(m["content"])
                    if company:
                        break

        search_query = extract_search_query(user_message)
        if company and not search_query:
            search_query = company

        # Out of scope: not greeting, not recall, not follow-up, and not article/mention search
        # -> immediately show suggested prompts, no search, no LLM
        if (
            not is_greeting_or_casual(user_message)
            and not is_recall_questions_request(user_message)
            and not is_follow_up_request(user_message)
            and not is_in_scope_for_search(user_message)
        ):
            out_msg = get_out_of_scope_message()
            yield out_msg
            full_response.append(out_msg)
            response_text = "".join(full_response)
            if user_msg_id is not None:
                async def _store_out_of_scope():
                    try:
                        await db.add_message(conversation_id, "assistant", response_text)
                    except Exception as e:
                        logger.warning("chat_store_after_stream_failed", error=str(e))
                asyncio.create_task(_store_out_of_scope())
            return

        # Gate: only run search when intent is search (or follow-up with company from context)
        search_gated = (intent == "search" and company) or (intent == "chat" and is_follow_up_request(user_message) and company)
        use_web_search = search_gated and (search_query is not None) and (company is not None)
        url_results = None
        is_follow_up = company and is_follow_up_request(user_message)
        skip_vector = len(user_message.strip()) < 25
        if is_recall_questions_request(user_message):
            status = "Looking through your conversation history...\n\n"
            yield status
            full_response.append(status)
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            status2 = "Retrieving your questions...\n\n"
            yield status2
            full_response.append(status2)
        elif use_web_search and search_query:
            status1 = "Looking through your conversation history...\n\n"
            yield status1
            full_response.append(status1)
            vector_task = asyncio.create_task(asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5))
            status2 = f"Searching RSS feeds, articles, Reddit, YouTube, and Twitter for **{search_query}**...\n\n"
            yield status2
            full_response.append(status2)
            try:
                from app.services.media_mention.mention_search import search_mentions
                url_results = await asyncio.wait_for(
                    asyncio.to_thread(search_mentions, search_query, llm_rerank=not is_follow_up),
                    timeout=25.0,
                )
                if url_results:
                    url_results = [
                        {
                            "title": r.get("title", ""),
                            "link": r.get("link", r.get("url", "")),
                            "source": r.get("source", ""),
                            "score": r.get("score"),
                            "publish_date": r.get("publish_date", r.get("timestamp", "")),
                            "snippet": r.get("snippet", r.get("summary", "")),
                            "type": r.get("type", "article"),
                        }
                        for r in url_results
                    ]
                    logger.info("chat_mention_search_used", query=search_query, count=len(url_results))
            except asyncio.TimeoutError:
                logger.warning("mention_search_timeout", query=search_query)
            except Exception as e:
                logger.warning("mention_search_failed", query=search_query, error=str(e))
            vector_context = await vector_task
        else:
            status = "Looking through your conversation history...\n\n"
            yield status
            full_response.append(status)
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            preliminary = "Thinking...\n\n"
            yield preliminary
            full_response.append(preliminary)
        use_perplexity = use_web_search and not url_results
        last_user_questions = None
        if is_recall_questions_request(user_message):
            user_msgs = [m["content"] for m in last_messages if m.get("role") == "user" and m.get("content") != user_message]
            last_user_questions = user_msgs[-5:] if len(user_msgs) >= 5 else user_msgs

        msgs_for_llm = build_messages(
            conversation_id, user_message, vector_context,
            url_results=url_results,
            search_attempted_no_results=use_web_search and not url_results,
            company=search_query or company,
            use_web_search=use_web_search,
            last_user_questions=last_user_questions,
        )
        if not use_web_search:
            for m in last_messages:
                msgs_for_llm.append({"role": m["role"], "content": m["content"]})
            msgs_for_llm.append({"role": "user", "content": user_message})

        from app.config import get_config
        settings = get_config()["settings"]

        # When we have search results, format and stream directly (guarantees article links)
        if url_results and (search_query or company):
            topic = search_query or company
            formatted = _format_articles_with_links(url_results, topic)
            for c in formatted:
                yield c
                full_response.append(c)
        elif getattr(settings, "mock_llm", False):
            mock = f"[MOCK - OpenRouter skipped] Hi! You said: \"{user_message}\". The rest of the pipeline (streaming, MongoDB, nginx) is working."
            for c in mock:
                yield c
                full_response.append(c)
        else:
            gateway = LLMGateway()
            try:
                got_llm_response = False
                async for chunk in gateway.chat_completion(msgs_for_llm, stream=True, use_web_search=use_perplexity):
                    full_response.append(chunk)
                    yield chunk
                    got_llm_response = True
                if not got_llm_response and len(full_response) == 1:
                    msg = "No response from the LLM. Check OPENROUTER_API_KEY in .env and restart."
                    yield msg
                    full_response.append(msg)
            except Exception as e:
                logger.error("chat_stream_failed", error=str(e))
                fallback = "Sorry, I couldn't complete the request right now. Please try again."
                yield fallback
                full_response.append(fallback)

    except Exception as e:
        logger.exception("chat_stream_error")
        if not full_response:
            err_msg = "Sorry, something went wrong while fetching articles. Please try again or rephrase your question."
            yield err_msg
            full_response.append(err_msg)

    # Store assistant response + Qdrant in background - do NOT block stream close
    response_text = "".join(full_response)
    if user_msg_id is not None:
        async def _store_after_stream():
            try:
                asst_msg_id = await db.add_message(conversation_id, "assistant", response_text)
                await asyncio.to_thread(qdrant.upsert_message, conversation_id, user_msg_id, "user", user_message)
                await asyncio.to_thread(qdrant.upsert_message, conversation_id, asst_msg_id, "assistant", response_text)
            except Exception as e:
                logger.warning("chat_store_after_stream_failed", error=str(e))

        asyncio.create_task(_store_after_stream())


@router.post("/chat")
async def chat(request: ChatRequest):
    """Stream chat response."""
    if not request.conversation_id or not request.message:
        raise HTTPException(status_code=400, detail="conversation_id and message required")

    return StreamingResponse(
        chat_stream(request.conversation_id, request.message),
        media_type="text/plain; charset=utf-8",
        headers={"X-Accel-Buffering": "no"},
    )
