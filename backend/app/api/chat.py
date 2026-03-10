"""Chat API - POST /api/chat with streaming."""
import json
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from bs4 import BeautifulSoup

from app.config import get_config
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


# Step log prefix for temporary debug stream (config: chat.debug_step_stream)
STEP_PREFIX = "[STEP]"


def _step_event(label: str, detail: str = "") -> str:
    """Return a single line to stream when debug_step_stream is enabled; else empty string."""
    if not get_config().get("chat", {}).get("debug_step_stream"):
        return ""
    return "\n" + STEP_PREFIX + json.dumps({"label": label, "detail": detail}) + "\n"


# Number emojis for monitoring-style list (1️⃣ … 10️⃣)
_NUM_EMOJI = ("1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟")

_TYPE_LABELS = {
    "article": "News Article",
    "news": "News Article",
    "blog": "Blog",
    "forum": "Forum Mention",
    "reddit": "Reddit Mention",
    "youtube": "YouTube Mention",
    "video": "Video",
    "twitter": "Twitter Mention",
    "social": "Social",
}

# Types considered "forum or social" for filter-only requests
_FORUM_SOCIAL_TYPES = frozenset(("forum", "reddit", "youtube", "twitter"))


def _is_forum_or_social_only_request(message: str) -> bool:
    """True if the user asks to see only forum or social mentions (e.g. 'show only forum or social mentions of X')."""
    if not message or not isinstance(message, str):
        return False
    lower = message.strip().lower()
    return (
        "only forum" in lower
        or "only social" in lower
        or "forum or social" in lower
        or "forum and social" in lower
        or "forums and social" in lower
        or "just forum" in lower
        or "just social" in lower
    )


def _format_mention_date(val) -> str:
    """Format publish_date/timestamp to 'Mar 5, 2026' style."""
    if val is None:
        return ""
    from datetime import datetime
    try:
        if isinstance(val, datetime):
            return val.strftime("%b %d, %Y")
        s = str(val).strip()[:30]
        if not s:
            return ""
        if "T" in s or "-" in s:
            dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
            return dt.strftime("%b %d, %Y")
    except Exception:
        pass
    return s[:20] if s else ""


def _strip_html_summary(text: str, max_len: int = 400) -> str:
    """Strip HTML from summary/snippet so we never show raw <a href=...> in the UI."""
    if not text or not isinstance(text, str):
        return ""
    s = text.strip()[:max_len * 2]
    if "<" not in s and ">" not in s:
        return s[:max_len]
    try:
        soup = BeautifulSoup(s, "html.parser")
        return soup.get_text(separator=" ", strip=True)[:max_len]
    except Exception:
        return s[:max_len]


def _url_display(link: str, max_len: int = 60) -> str:
    """Shorten URL for display, e.g. https://economictimes… or https://reddit.com/…"""
    if not link or not isinstance(link, str):
        return ""
    s = link.strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1].rstrip("/") + "…"


def _format_articles_with_links(results: list[dict], topic: str) -> str:
    """Format search results like global monitoring tools: numbered, type label, Title/Source/Type/Date/Sentiment/Summary/URL."""
    if not results:
        return f"No mentions found for **{topic}**."
    lines = [f"Here are the latest mentions for **{topic}**:\n"]
    for i, r in enumerate(results[:25], 1):
        try:
            title = str(r.get("title") or "Untitled")[:200]
            link = r.get("link") or r.get("url") or ""
            link = str(link)[:500] if link else ""
            if link and "news.google.com" in link:
                try:
                    from app.services.media_mention.mention_search import _resolve_google_news_url, RESOLVE_GOOGLE_NEWS_TIMEOUT
                    resolved = _resolve_google_news_url(link, timeout=RESOLVE_GOOGLE_NEWS_TIMEOUT)
                    if resolved and "news.google.com" not in resolved:
                        link = resolved
                except Exception:
                    pass
            link_display = _url_display(link)
            source_raw = str(r.get("source") or r.get("source_domain") or "").strip()[:100]
            # Capitalize platforms for display: reddit -> Reddit, youtube -> YouTube
            _platform_display = {"reddit": "Reddit", "youtube": "YouTube", "twitter": "Twitter"}
            source = _platform_display.get(source_raw.lower(), source_raw) if source_raw else ""
            if not source and source_raw:
                source = source_raw[0].upper() + source_raw[1:].lower() if len(source_raw) > 1 else source_raw.upper()
            raw_type = str(r.get("type") or "article").lower()
            type_label = _TYPE_LABELS.get(raw_type) or raw_type.capitalize()
            date_str = _format_mention_date(r.get("publish_date") or r.get("timestamp"))
            sentiment = (r.get("sentiment") or "").strip()
            if sentiment:
                sentiment = sentiment.capitalize()
            summary = _strip_html_summary(str(r.get("snippet") or r.get("summary") or ""))

            emoji = _NUM_EMOJI[i - 1] if i <= len(_NUM_EMOJI) else f"{i}."
            lines.append(f"{emoji} **{type_label}**")
            lines.append("")
            lines.append(f"**Title**")
            lines.append(title)
            lines.append("")
            if source:
                lines.append(f"**Source**")
                lines.append(source)
                lines.append("")
            lines.append(f"**Type**")
            lines.append(type_label)
            lines.append("")
            if date_str:
                lines.append(f"**Date**")
                lines.append(date_str)
                lines.append("")
            if sentiment:
                lines.append(f"**Sentiment**")
                lines.append(sentiment)
                lines.append("")
            if summary:
                lines.append(f"**Summary**")
                lines.append(summary)
                lines.append("")
            lines.append(f"**URL**")
            if link:
                # Short display text; full URL in link so click goes to article
                lines.append(f"[{link_display or link[:50] + '…'}]({link})" if len(link) > 60 else link)
            else:
                lines.append("—")
            lines.append("")
            lines.append("⸻")
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
        line = _step_event("Request received", f"Message length: {len(user_message)}")
        if line:
            yield line
        logger.info("chat_stream_start", conv=conversation_id[:8], msg_len=len(user_message))
        user_msg_id = await db.add_message(conversation_id, "user", user_message)
        line = _step_event("Saved user message", f"Conversation: {conversation_id[:8]}...")
        if line:
            yield line
        logger.info("chat_after_add_message")

        last_messages = await db.get_last_messages(conversation_id, n=10)
        line = _step_event("Loaded conversation history", f"{len(last_messages)} messages")
        if line:
            yield line
        logger.info("chat_after_get_last_messages", n=len(last_messages))

        # Intent classification: gates search pipeline. No LLM calls.
        intent, search_entity = classify_intent(user_message)
        company = search_entity
        line = _step_event("Intent classification", f"Intent: {intent}" + (f", company: {company}" if company else ""))
        if line:
            yield line

        # Greetings first: never search, go straight to LLM
        if is_greeting_or_casual(user_message):
            line = _step_event("Greeting or casual message detected", "Skipping search, going to LLM")
            if line:
                yield line
            preliminary = "Thinking...\n\n"
            yield preliminary
            full_response.append(preliminary)
            skip_vector = len(user_message.strip()) < 25
            line = _step_event("Fetching vector context", "Qdrant similarity search" if not skip_vector else "Skipped (short message)")
            if line:
                yield line
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
            if vector_context:
                ctx = "\n".join(f"{c['role']}: {c['content'][:200]}" for c in vector_context)
                msgs.append({"role": "system", "content": f"Relevant context:\n{ctx}"})
            for m in last_messages:
                msgs.append({"role": m["role"], "content": m["content"]})
            msgs.append({"role": "user", "content": user_message})
            line = _step_event("Streaming LLM response", "Greeting reply")
            if line:
                yield line
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

        # Resolve to canonical entity for search (e.g. "latest news on Sahi" -> "Sahi")
        try:
            from app.services.mention_context_validation import resolve_to_canonical_entity
            resolved_entity = resolve_to_canonical_entity(search_query or company or "")
            mention_entity = resolved_entity if resolved_entity else (search_query or company)
        except Exception:
            mention_entity = search_query or company

        # Out of scope: not greeting, not recall, not follow-up, and not article/mention search
        # -> immediately show suggested prompts, no search, no LLM
        if (
            not is_greeting_or_casual(user_message)
            and not is_recall_questions_request(user_message)
            and not is_follow_up_request(user_message)
            and not is_in_scope_for_search(user_message)
        ):
            line = _step_event("Out of scope", "Returning suggested prompts (no search, no LLM)")
            if line:
                yield line
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
        search_gated = (intent == "search" and (company or mention_entity)) or (intent == "chat" and is_follow_up_request(user_message) and (company or mention_entity))
        use_web_search = search_gated and (search_query is not None or mention_entity is not None) and (company is not None or mention_entity is not None)
        url_results = None
        is_follow_up = company and is_follow_up_request(user_message)
        forum_only = _is_forum_or_social_only_request(user_message)
        skip_vector = len(user_message.strip()) < 25
        if is_recall_questions_request(user_message):
            line = _step_event("Recall questions", "Loading history and retrieving your questions")
            if line:
                yield line
            status = "Looking through your conversation history...\n\n"
            yield status
            full_response.append(status)
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            status2 = "Retrieving your questions...\n\n"
            yield status2
            full_response.append(status2)
        elif use_web_search and (search_query or mention_entity):
            line = _step_event("Search gated", f"Query: {search_query or mention_entity}, company: {company or mention_entity}")
            if line:
                yield line
            status1 = "Looking through your conversation history...\n\n"
            yield status1
            full_response.append(status1)
            vector_task = asyncio.create_task(asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5))
            line = _step_event("Searching mentions", "RSS, articles, Reddit, YouTube, Twitter")
            if line:
                yield line
            status2 = f"Searching RSS feeds, articles, Reddit, YouTube, and Twitter for **{search_query or mention_entity}**...\n\n"
            yield status2
            full_response.append(status2)
            try:
                from app.services.media_mention.mention_search import search_mentions
                url_results = await asyncio.wait_for(
                    asyncio.to_thread(
                        search_mentions,
                        mention_entity or search_query,
                        llm_rerank=not is_follow_up,
                        forum_only=forum_only,
                    ),
                    timeout=25.0,
                )
                if url_results:
                    url_results = [
                        {
                            "title": r.get("title", ""),
                            "link": r.get("link", r.get("url", "")),
                            "url": r.get("link", r.get("url", "")),
                            "source": r.get("source") or r.get("source_domain", ""),
                            "score": r.get("score"),
                            "publish_date": r.get("publish_date", r.get("timestamp", "")),
                            "snippet": r.get("snippet", r.get("summary", "")),
                            "summary": r.get("summary", r.get("snippet", "")),
                            "sentiment": r.get("sentiment"),
                            "type": r.get("type", "article"),
                        }
                        for r in url_results
                    ]
                    line = _step_event("Mention search complete", f"Found {len(url_results)} results")
                    if line:
                        yield line
                    logger.info("chat_mention_search_used", query=mention_entity or search_query, count=len(url_results))
            except asyncio.TimeoutError:
                line = _step_event("Mention search", "Timeout")
                if line:
                    yield line
                logger.warning("mention_search_timeout", query=mention_entity or search_query)
            except Exception as e:
                line = _step_event("Mention search", f"Error: {str(e)[:80]}")
                if line:
                    yield line
                logger.warning("mention_search_failed", query=mention_entity or search_query, error=str(e))
            vector_context = await vector_task
        else:
            line = _step_event("Loading vector context", "Qdrant similarity search" if not skip_vector else "Skipped")
            if line:
                yield line
            status = "Looking through your conversation history...\n\n"
            yield status
            full_response.append(status)
            vector_context = [] if skip_vector else await asyncio.to_thread(qdrant.search_similar, conversation_id, user_message, 5)
            preliminary = "Thinking...\n\n"
            yield preliminary
            full_response.append(preliminary)
        # Never fall back to open-web search for "forum/social only" queries; we answer from our monitored sources only
        use_perplexity = use_web_search and not url_results and not forum_only
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

        # When user asked for "forum or social only", filter to those types; if none, say so and skip LLM
        topic = search_query or company
        display_results = list(url_results) if url_results else []
        if forum_only and (search_query or company):
            display_results = [
                r for r in display_results
                if (str(r.get("type") or "").strip().lower() in _FORUM_SOCIAL_TYPES)
            ]
            if not display_results:
                line = _step_event("Forum/social only", "No forum or social mentions found")
                if line:
                    yield line
                header = (
                    "**Source**: Monitored forums and social only (no news articles).\n\n"
                )
                no_msg = f"No forum or social mentions found for **{topic}** in our monitored sources."
                footer = (
                    "\n\n---\n\n"
                    "You can try:\n"
                    f"- **Where was {topic} mentioned?** (all sources: news, forums, social)\n"
                    f"- **Show recent news about {topic}.**\n"
                )
                for c in header + no_msg + footer:
                    yield c
                    full_response.append(c)
                display_results = None  # mark that we streamed a direct response

        streamed_direct = False
        # When we have search results to show, format and stream directly (guarantees article links)
        if display_results and (search_query or company):
            line = _step_event("Formatting search results", f"Topic: {topic}")
            if line:
                yield line
            formatted = _format_articles_with_links(display_results, topic)
            header = (
                f"**Source**: Monitored mentions from your configured news, blogs, forums, and social sources "
                f"(not full open‑web search) for **{topic}**.\n\n"
            )
            if forum_only:
                header = (
                    f"**Source**: Forum and social mentions only for **{topic}**.\n\n"
                )
            footer = (
                "\n\n---\n\n"
                "You can also ask:\n"
                f"- **Where was {topic} mentioned last week?**\n"
                f"- **Compare mentions of {topic} vs a competitor.**\n"
                f"- **Show only forum or social mentions of {topic}.**\n"
            )
            full_block = header + formatted + footer
            for c in full_block:
                yield c
                full_response.append(c)
            streamed_direct = True
        elif display_results is None:
            streamed_direct = True  # we already streamed "no forum/social" message

        if not streamed_direct and getattr(settings, "mock_llm", False):
            mock = f"[MOCK - OpenRouter skipped] Hi! You said: \"{user_message}\". The rest of the pipeline (streaming, MongoDB, nginx) is working."
            for c in mock:
                yield c
                full_response.append(c)
        elif not streamed_direct:
            line = _step_event("Streaming LLM response", "Perplexity web search" if use_perplexity else "OpenRouter")
            if line:
                yield line
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
