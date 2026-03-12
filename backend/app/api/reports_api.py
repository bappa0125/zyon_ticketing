"""Reports API — generate downloadable HTML briefs (no email sending yet)."""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import json

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from app.services.media_intelligence_service import get_dashboard
from app.services.topics_service import get_topics_analytics
from app.services.mongodb import get_mongo_client
from app.config import get_config
from app.services.llm_gateway import LLMGateway
from app.services.redis_client import get_redis

router = APIRouter(tags=["reports"])

ENTITY_MENTIONS_COLLECTION = "entity_mentions"
ARTICLE_DOCUMENTS_COLLECTION = "article_documents"

AI_BRIEF_CACHE_PREFIX = "ai_brief"
AI_BRIEF_DAILY_COUNT_KEY_PREFIX = "ai_brief_count"


class AIBriefRequest(BaseModel):
    client: str
    range: str = "7d"  # 24h | 7d | 30d


def _fmt_dt(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def _escape(s: Any) -> str:
    if s is None:
        return ""
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _normalize_domain(source: str) -> str:
    """Normalize to domain: lowercase, strip www, strip scheme/path."""
    if not source or not isinstance(source, str):
        return ""
    s = source.strip().lower()
    if s.startswith("www."):
        s = s[4:]
    if "://" in s:
        s = s.split("://", 1)[1]
    if "/" in s:
        s = s.split("/", 1)[0]
    return s[:200]


def _parse_range(range_param: str) -> timedelta:
    if range_param == "24h":
        return timedelta(hours=24)
    if range_param == "7d":
        return timedelta(days=7)
    if range_param == "30d":
        return timedelta(days=30)
    return timedelta(days=7)


def _sentiment_label(v: Any) -> str:
    s = (str(v) if v is not None else "neutral").strip().lower()
    if s in ("positive", "pos"):
        return "positive"
    if s in ("negative", "neg"):
        return "negative"
    return "neutral"


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _cache_bucket(range_param: str) -> str:
    now = datetime.now(timezone.utc)
    if range_param == "24h":
        # 6-hour buckets so refreshes don't burn free tier.
        b = (now.hour // 6) * 6
        return now.strftime(f"%Y-%m-%d-{b:02d}")
    # Daily buckets for longer ranges.
    return now.strftime("%Y-%m-%d")


def _ai_cfg() -> dict[str, Any]:
    cfg = get_config()
    return (cfg.get("reports_ai") or cfg.get("llm_reports") or cfg.get("llm_ai_brief") or {})  # backward compat


def _ai_limits(range_param: str) -> tuple[int, int]:
    cfg = _ai_cfg()
    ttl_map = {
        "24h": int(cfg.get("ai_brief_ttl_hours_24h", 6)),
        "7d": int(cfg.get("ai_brief_ttl_hours_7d", 24)),
        "30d": int(cfg.get("ai_brief_ttl_hours_30d", 48)),
    }
    ttl_hours = ttl_map.get(range_param, ttl_map["7d"])
    return max(ttl_hours, 1) * 3600, int(cfg.get("ai_brief_max_per_day", 10))


def _truncate(s: str, n: int) -> str:
    s = (s or "").strip()
    return s if len(s) <= n else s[: n - 1] + "…"


def _json_safe(obj: Any) -> Any:
    """Convert payload to JSON-serializable form (e.g. datetime -> ISO string)."""
    if obj is None:
        return None
    if isinstance(obj, datetime):
        return obj.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    if isinstance(obj, dict):
        return {k: _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_json_safe(v) for v in obj]
    if isinstance(obj, (str, int, float, bool)):
        return obj
    return str(obj)


async def _build_ai_brief_payload(client: str, range_param: str) -> dict[str, Any]:
    """
    Build a small, grounded payload for the LLM.
    Never include full article text; only headlines + URLs + aggregates.
    """
    dash = await get_dashboard(client=client, range_param=range_param)
    topics_data = await get_topics_analytics(client=client, range_param=range_param)

    topics = []
    max_topics = int(_ai_cfg().get("ai_brief_max_topics", 12))
    for t in (topics_data.get("topics") or [])[:max_topics]:
        topics.append({
            "topic": _truncate(str(t.get("topic") or ""), 80),
            "mentions": int(t.get("mentions") or 0),
            "action": t.get("action"),
            "sentiment_summary": t.get("sentiment_summary"),
            "trend_pct": t.get("trend_pct"),
        })

    # Headlines from feed (already deduped by media_intelligence_service)
    feed = dash.get("feed") or []
    max_headlines = int(_ai_cfg().get("ai_brief_max_headlines", 20))
    headlines = []
    for m in feed[: max_headlines * 3]:
        title = (m.get("title") or "").strip()
        url = ((m.get("url") or "") or (m.get("url_original") or "")).strip()
        if not title or not url:
            continue
        headlines.append({
            "title": _truncate(title, 140),
            "url": url[:500],
            "entity": (m.get("entity") or "").strip(),
            "sentiment": (m.get("sentiment") or "").strip().lower() or None,
            "source_domain": (m.get("source_domain") or "").strip(),
            "published_at": m.get("published_at"),
        })
        if len(headlines) >= max_headlines:
            break

    # Sentiment summary from reputation endpoint (cheap reuse)
    rep = await report_reputation_json(client=client, range_param=range_param)
    sentiment = rep.get("sentiment") or []

    return {
        "client": dash.get("client") or client,
        "competitors": dash.get("competitors") or [],
        "range": range_param,
        "coverage": (dash.get("coverage") or [])[:12],
        "top_publications": (dash.get("top_publications") or [])[:10],
        "topics": topics,
        "sentiment_summary": sentiment[:12],
        "headlines": headlines,
    }


async def _llm_generate_ai_brief(payload: dict[str, Any]) -> dict[str, Any]:
    cfg = get_config()
    ai_cfg = _ai_cfg()
    if not bool(ai_cfg.get("ai_brief_enabled", True)):
        raise HTTPException(status_code=403, detail="AI brief disabled")
    max_tokens = int(ai_cfg.get("ai_brief_max_tokens", cfg.get("llm", {}).get("max_tokens", 350)))
    model = (ai_cfg.get("ai_brief_model") or cfg.get("llm", {}).get("model") or "openrouter/free").strip()

    system = (
        "You are an expert PR strategist. You MUST only use the provided data. "
        "Do not invent facts, numbers, outlets, or articles. "
        "Return STRICT JSON only (no markdown) with this schema:\n"
        "{"
        "\"executive_summary\":[string],"
        "\"tone_guidance\":string,"
        "\"talk_points\":[string],"
        "\"avoid_points\":[string],"
        "\"target_outlets\":[{\"domain\":string,\"why\":string}],"
        "\"focus_articles\":[{\"title\":string,\"url\":string,\"why\":string}]"
        "}"
    )
    user = (
        "Create a concise PR action brief for the client and competitors.\n"
        "Pick 3-5 executive_summary bullets.\n"
        "Pick 5 talk_points, 3 avoid_points.\n"
        "Pick 5 target_outlets from domains present in the data.\n"
        "Pick 3-4 focus_articles strictly from the provided headlines (must match title+url). "
        "If headlines are missing/empty, return an empty focus_articles array and mention that in executive_summary.\n\n"
        f"DATA:\n{json.dumps(_json_safe(payload), ensure_ascii=False)}"
    )

    gateway = LLMGateway()
    gateway.set_model(model)
    # Non-streaming call
    out = ""
    async for chunk in gateway.chat_completion(
        messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        stream=False,
        use_web_search=False,
    ):
        out += chunk or ""

    if not out.strip():
        raise HTTPException(status_code=502, detail="LLM returned empty response")

    # Some failures return {"error": "..."} as JSON string
    try:
        obj = json.loads(out)
        if isinstance(obj, dict) and obj.get("error"):
            raise HTTPException(status_code=502, detail=str(obj.get("error")))
        if not isinstance(obj, dict):
            raise ValueError("Non-dict JSON")
        return obj
    except HTTPException:
        raise
    except Exception:
        # Fallback: wrap raw text (still return something, but mark as unstructured)
        return {
            "executive_summary": [],
            "tone_guidance": "",
            "talk_points": [],
            "avoid_points": [],
            "target_outlets": [],
            "focus_articles": [],
            "_raw": out[:4000],
        }


@router.post("/reports/ai-brief")
async def reports_ai_brief(req: AIBriefRequest):
    """
    Generate (or return cached) AI PR brief. Guardrails:
    - Explicit call only (never auto-run from UI)
    - Redis cache with TTL by range
    - Daily quota enforced via Redis counter
    """
    client = (req.client or "").strip()
    range_param = (req.range or "7d").strip()
    if not client:
        raise HTTPException(status_code=400, detail="client required")
    if range_param not in ("24h", "7d", "30d"):
        range_param = "7d"

    ai_cfg = _ai_cfg()
    if not bool(ai_cfg.get("ai_brief_enabled", True)):
        raise HTTPException(status_code=403, detail="AI brief disabled")

    try:
        ttl_seconds, max_per_day = _ai_limits(range_param)
        bucket = _cache_bucket(range_param)
        cache_key = f"{AI_BRIEF_CACHE_PREFIX}:{client}:{range_param}:{bucket}"

        r = await get_redis()
        cached = await r.get(cache_key)
        if cached:
            try:
                obj = json.loads(cached)
            except Exception:
                obj = {"_raw": cached}
            return {"cached": True, "cache_key": cache_key, "generated_at": obj.get("generated_at"), "brief": obj.get("brief") or obj}

        # Quota gate (only when cache miss)
        day_key = f"{AI_BRIEF_DAILY_COUNT_KEY_PREFIX}:{_today_key()}"
        count = await r.incr(day_key)
        if count == 1:
            await r.expire(day_key, 60 * 60 * 48)  # keep for 2 days
        if count > max_per_day:
            raise HTTPException(status_code=429, detail=f"Daily AI brief limit reached ({max_per_day}/day). Try later or use cached briefs.")

        payload = await _build_ai_brief_payload(client=client, range_param=range_param)
        brief = await _llm_generate_ai_brief(payload)
        wrapped = {
            "generated_at": _fmt_dt(datetime.now(timezone.utc)),
            "client": payload.get("client") or client,
            "range": range_param,
            "brief": brief,
            "inputs": {
                "topics_n": len(payload.get("topics") or []),
                "headlines_n": len(payload.get("headlines") or []),
            },
        }
        await r.setex(cache_key, ttl_seconds, json.dumps(_json_safe(wrapped), ensure_ascii=False))
        return {"cached": False, "cache_key": cache_key, **wrapped}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"AI brief failed: {e!s}")

def _render_pulse_html(*, client: str, range_param: str, dashboard: dict[str, Any], topics: list[dict[str, Any]]) -> str:
    now = _fmt_dt(datetime.now(timezone.utc))
    coverage = dashboard.get("coverage") or []
    top_pubs = dashboard.get("top_publications") or []

    # Keep it printable + email-safe (tables, simple CSS).
    rows_topics = []
    for t in topics[:20]:
        rows_topics.append(
            "<tr>"
            f"<td class='topic'>{_escape(t.get('topic',''))}</td>"
            f"<td class='num'>{_escape(t.get('mentions',0))}</td>"
            f"<td class='trend'>{_escape(t.get('trend_pct','—'))}{'%' if t.get('trend_pct') is not None else ''}</td>"
            f"<td class='sent'>{_escape(t.get('sentiment_summary',''))}</td>"
            f"<td class='act {_escape(t.get('action',''))}'>{_escape((t.get('action') or '').upper())}</td>"
            "</tr>"
        )
    if not rows_topics:
        rows_topics.append("<tr><td colspan='5' class='muted'>No topics available for this range.</td></tr>")

    rows_cov = []
    for c in coverage[:10]:
        rows_cov.append(
            "<tr>"
            f"<td>{_escape(c.get('entity',''))}</td>"
            f"<td class='num'>{_escape(c.get('mentions',0))}</td>"
            "</tr>"
        )
    if not rows_cov:
        rows_cov.append("<tr><td colspan='2' class='muted'>No coverage available for this range.</td></tr>")

    rows_pubs = []
    for p in top_pubs[:10]:
        rows_pubs.append(
            "<tr>"
            f"<td>{_escape(p.get('source',''))}</td>"
            f"<td class='num'>{_escape(p.get('mentions',0))}</td>"
            "</tr>"
        )
    if not rows_pubs:
        rows_pubs.append("<tr><td colspan='2' class='muted'>No publications available for this range.</td></tr>")

    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>PR Pulse — { _escape(client) }</title>
    <style>
      :root {{
        --bg: #0b0f19;
        --panel: #0f172a;
        --border: #253045;
        --text: #e5e7eb;
        --muted: #94a3b8;
        --good: #34d399;
        --warn: #f59e0b;
        --bad: #fb7185;
      }}
      body {{
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        background: var(--bg);
        color: var(--text);
        line-height: 1.35;
      }}
      .page {{ max-width: 980px; margin: 0 auto; padding: 28px 18px 60px; }}
      .header {{
        display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
        border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px;
      }}
      .title {{ font-size: 18px; letter-spacing: .04em; text-transform: uppercase; }}
      .meta {{ color: var(--muted); font-size: 12px; text-align: right; }}
      .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }}
      .card {{
        background: color-mix(in srgb, var(--panel) 92%, black);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 14px;
      }}
      h2 {{ margin: 0 0 10px; font-size: 14px; color: var(--text); letter-spacing: .02em; }}
      table {{ width: 100%; border-collapse: collapse; }}
      th, td {{ padding: 10px 10px; border-bottom: 1px solid var(--border); font-size: 12px; vertical-align: top; }}
      th {{ color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }}
      .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
      .muted {{ color: var(--muted); }}
      .topic {{ max-width: 420px; }}
      .trend {{ text-align: right; }}
      .act {{ font-weight: 700; letter-spacing: .04em; text-align: right; }}
      .act.talk {{ color: var(--good); }}
      .act.careful {{ color: var(--warn); }}
      .act.avoid {{ color: var(--bad); }}
      .footer {{ margin-top: 16px; color: var(--muted); font-size: 11px; }}
      @media print {{
        body {{ background: white; color: #0b1220; }}
        .card {{ background: white; border-color: #e5e7eb; }}
        th, td {{ border-bottom-color: #e5e7eb; }}
        .meta, .muted {{ color: #475569; }}
      }}
    </style>
  </head>
  <body>
    <div class="page">
      <div class="header">
        <div>
          <div class="title">PR Pulse — { _escape(client) }</div>
          <div class="muted">Range: { _escape(range_param) }</div>
        </div>
        <div class="meta">
          Generated: { _escape(now) }<br/>
          Source: Zyon (entity_mentions + article_documents)
        </div>
      </div>

      <div class="grid">
        <div class="card">
          <h2>Share of voice (mentions)</h2>
          <table>
            <thead><tr><th>Entity</th><th class="num">Mentions</th></tr></thead>
            <tbody>
              {''.join(rows_cov)}
            </tbody>
          </table>
        </div>

        <div class="card">
          <h2>Top publications</h2>
          <table>
            <thead><tr><th>Source</th><th class="num">Mentions</th></tr></thead>
            <tbody>
              {''.join(rows_pubs)}
            </tbody>
          </table>
        </div>
      </div>

      <div class="card" style="margin-top: 14px;">
        <h2>Trending topics</h2>
        <table>
          <thead>
            <tr>
              <th>Topic</th>
              <th class="num">Vol</th>
              <th class="trend">Trend</th>
              <th>Sentiment</th>
              <th class="act">Act</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows_topics)}
          </tbody>
        </table>
        <div class="footer">Tip: Use this page as a downloadable brief (print to PDF or forward as HTML).</div>
      </div>
    </div>
  </body>
</html>"""


@router.get("/reports/pulse")
async def report_pulse_json(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    dashboard = await get_dashboard(client=client, range_param=range_param)
    topics_data = await get_topics_analytics(client=client, range_param=range_param)
    return {
        "client": client,
        "range": range_param,
        "dashboard": dashboard,
        "topics": topics_data.get("topics") or [],
    }


@router.get("/reports/pulse.html", response_class=HTMLResponse)
async def report_pulse_html(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    dashboard = await get_dashboard(client=client, range_param=range_param)
    topics_data = await get_topics_analytics(client=client, range_param=range_param)
    html = _render_pulse_html(
        client=client,
        range_param=range_param,
        dashboard=dashboard,
        topics=topics_data.get("topics") or [],
    )
    return HTMLResponse(content=html, headers={"Content-Disposition": f'attachment; filename=\"pr-pulse-{client}-{range_param}.html\"'})


def _html_to_pdf_sync(html: str) -> bytes:
    """Generate PDF from HTML using Playwright (blocking). Run in executor."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        try:
            page = browser.new_page()
            page.set_content(html, wait_until="networkidle")
            pdf_bytes = page.pdf(format="A4", print_background=True, margin={"top": "12mm", "right": "12mm", "bottom": "12mm", "left": "12mm"})
            return pdf_bytes
        finally:
            browser.close()


@router.get("/reports/pulse.pdf")
async def report_pulse_pdf(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    dashboard = await get_dashboard(client=client, range_param=range_param)
    topics_data = await get_topics_analytics(client=client, range_param=range_param)
    html = _render_pulse_html(
        client=client,
        range_param=range_param,
        dashboard=dashboard,
        topics=topics_data.get("topics") or [],
    )
    loop = asyncio.get_event_loop()
    try:
        pdf_bytes = await loop.run_in_executor(None, _html_to_pdf_sync, html)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e!s}")
    filename = f"pr-pulse-{client}-{range_param}.pdf"
    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _base_css() -> str:
    # Shared CSS across report types.
    return """
      :root {
        --bg: #0b0f19;
        --panel: #0f172a;
        --border: #253045;
        --text: #e5e7eb;
        --muted: #94a3b8;
        --good: #34d399;
        --warn: #f59e0b;
        --bad: #fb7185;
      }
      body {
        margin: 0;
        font-family: ui-sans-serif, system-ui, -apple-system, Segoe UI, Roboto, Arial;
        background: var(--bg);
        color: var(--text);
        line-height: 1.35;
      }
      .page { max-width: 980px; margin: 0 auto; padding: 28px 18px 60px; }
      .header {
        display: flex; justify-content: space-between; gap: 12px; align-items: baseline;
        border-bottom: 1px solid var(--border); padding-bottom: 14px; margin-bottom: 18px;
      }
      .title { font-size: 18px; letter-spacing: .04em; text-transform: uppercase; }
      .meta { color: var(--muted); font-size: 12px; text-align: right; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
      .card {
        background: color-mix(in srgb, var(--panel) 92%, black);
        border: 1px solid var(--border);
        border-radius: 14px;
        padding: 14px;
      }
      h2 { margin: 0 0 10px; font-size: 14px; color: var(--text); letter-spacing: .02em; }
      table { width: 100%; border-collapse: collapse; }
      th, td { padding: 10px 10px; border-bottom: 1px solid var(--border); font-size: 12px; vertical-align: top; }
      th { color: var(--muted); text-transform: uppercase; letter-spacing: .06em; font-weight: 600; }
      .num { text-align: right; font-variant-numeric: tabular-nums; }
      .muted { color: var(--muted); }
      .pill { display:inline-block; padding: 2px 8px; border-radius: 999px; border: 1px solid var(--border); font-size: 11px; color: var(--muted); }
      .pill.good { color: var(--good); border-color: color-mix(in srgb, var(--good) 50%, var(--border)); }
      .pill.warn { color: var(--warn); border-color: color-mix(in srgb, var(--warn) 50%, var(--border)); }
      .pill.bad  { color: var(--bad);  border-color: color-mix(in srgb, var(--bad) 50%, var(--border)); }
      .footer { margin-top: 16px; color: var(--muted); font-size: 11px; }
      @media print {
        body { background: white; color: #0b1220; }
        .card { background: white; border-color: #e5e7eb; }
        th, td { border-bottom-color: #e5e7eb; }
        .meta, .muted { color: #475569; }
      }
    """


def _html_doc(*, title: str, subtitle: str, client: str, range_param: str, body_html: str) -> str:
    now = _fmt_dt(datetime.now(timezone.utc))
    return f"""<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>{_escape(title)} — {_escape(client)}</title>
    <style>
    {_base_css()}
    </style>
  </head>
  <body>
    <div class="page">
      <div class="header">
        <div>
          <div class="title">{_escape(title)} — {_escape(client)}</div>
          <div class="muted">{_escape(subtitle)} • Range: {_escape(range_param)}</div>
        </div>
        <div class="meta">
          Generated: {_escape(now)}<br/>
          Source: Zyon (entity_mentions + article_documents)
        </div>
      </div>
      {body_html}
    </div>
  </body>
</html>"""


async def _get_client_entities(client: str) -> tuple[str, list[str], list[str]]:
    """Return (client_name, entities=[client+competitors], competitor_names)."""
    from app.core.client_config_loader import get_entity_names, get_competitor_names, load_clients

    clients_list = await load_clients()
    client_obj = next(
        (c for c in clients_list if (c.get("name") or "").strip().lower() == client.strip().lower()),
        None,
    )
    if not client_obj:
        return (client, [], [])
    client_name = (client_obj.get("name") or "").strip() or client
    entities = get_entity_names(client_obj)
    competitors = get_competitor_names(client_obj)
    return (client_name, entities, competitors)


async def _join_topics_for_urls(urls: list[str]) -> dict[str, list[str]]:
    """Map url -> topics[] from article_documents (url or url_resolved)."""
    if not urls:
        return {}
    from app.services.mongodb import get_db

    db = get_db()
    art = db[ARTICLE_DOCUMENTS_COLLECTION]
    q = {"$or": [{"url": {"$in": urls}}, {"url_resolved": {"$in": urls}}], "topics": {"$exists": True, "$type": "array", "$ne": []}}
    out: dict[str, list[str]] = {}
    async for doc in art.find(q, {"url": 1, "url_resolved": 1, "topics": 1}):
        topics = [t for t in (doc.get("topics") or []) if t]
        u1 = (doc.get("url") or "").strip()
        u2 = (doc.get("url_resolved") or "").strip()
        if u1 and topics:
            out[u1] = topics
        if u2 and topics:
            out[u2] = topics
    return out


@router.get("/reports/reputation")
async def report_reputation_json(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    """
    Reputation report (JSON): sentiment summary + negative drivers by topic/source.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitors = await _get_client_entities(client)
    if not entities:
        return {"client": client_name, "range": range_param, "sentiment": [], "negative_topics": [], "negative_sources": []}

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta
    db = get_db()
    em = db[ENTITY_MENTIONS_COLLECTION]

    match = {
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }

    # 1) Sentiment summary per entity
    pipeline_sent = [
        {"$match": match},
        {"$project": {"entity": 1, "sentiment": {"$ifNull": ["$sentiment", "neutral"]}}},
        {
            "$group": {
                "_id": "$entity",
                "positive": {"$sum": {"$cond": [{"$eq": ["$sentiment", "positive"]}, 1, 0]}},
                "neutral": {"$sum": {"$cond": [{"$eq": ["$sentiment", "neutral"]}, 1, 0]}},
                "negative": {"$sum": {"$cond": [{"$eq": ["$sentiment", "negative"]}, 1, 0]}},
                "total": {"$sum": 1},
            }
        },
        {"$project": {"entity": "$_id", "positive": 1, "neutral": 1, "negative": 1, "total": 1, "_id": 0}},
        {"$sort": {"total": -1}},
    ]
    sentiment_rows: list[dict[str, Any]] = []
    async for doc in em.aggregate(pipeline_sent):
        sentiment_rows.append(doc)

    # 2) Negative mentions for drivers
    neg_match = {**match, "sentiment": "negative"}
    neg_cursor = em.find(neg_match, {"url": 1, "source": 1, "source_domain": 1, "title": 1, "entity": 1}).limit(500)
    neg_docs: list[dict[str, Any]] = []
    urls: list[str] = []
    async for d in neg_cursor:
        url = (d.get("url") or "").strip()
        if url:
            urls.append(url)
        neg_docs.append(d)

    url_topics = await _join_topics_for_urls(urls)
    topic_counts: dict[str, int] = {}
    source_counts: dict[str, int] = {}
    sample_headlines: dict[str, list[str]] = {}

    for d in neg_docs:
        url = (d.get("url") or "").strip()
        topics = url_topics.get(url, [])
        src = _normalize_domain(d.get("source_domain") or d.get("source") or "")
        title = (d.get("title") or "").strip()

        if src:
            source_counts[src] = source_counts.get(src, 0) + 1
        for t in topics:
            topic_counts[t] = topic_counts.get(t, 0) + 1
            if title:
                sample_headlines.setdefault(t, [])
                if len(sample_headlines[t]) < 3 and title not in sample_headlines[t]:
                    sample_headlines[t].append(title)

    negative_topics = [
        {"topic": t, "mentions": n, "sample_headlines": sample_headlines.get(t, [])}
        for t, n in sorted(topic_counts.items(), key=lambda x: -x[1])[:12]
    ]
    negative_sources = [
        {"source_domain": s, "mentions": n}
        for s, n in sorted(source_counts.items(), key=lambda x: -x[1])[:12]
    ]

    return {
        "client": client_name,
        "competitors": competitors,
        "range": range_param,
        "sentiment": sentiment_rows,
        "negative_topics": negative_topics,
        "negative_sources": negative_sources,
    }


@router.get("/reports/reputation.html", response_class=HTMLResponse)
async def report_reputation_html(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    data = await report_reputation_json(client=client, range_param=range_param)

    sent_rows = []
    for r in data.get("sentiment") or []:
        sent_rows.append(
            "<tr>"
            f"<td>{_escape(r.get('entity',''))}</td>"
            f"<td class='num'>{_escape(r.get('total',0))}</td>"
            f"<td class='num'><span class='pill good'>+ {_escape(r.get('positive',0))}</span></td>"
            f"<td class='num'><span class='pill'>= {_escape(r.get('neutral',0))}</span></td>"
            f"<td class='num'><span class='pill bad'>- {_escape(r.get('negative',0))}</span></td>"
            "</tr>"
        )
    if not sent_rows:
        sent_rows.append("<tr><td colspan='5' class='muted'>No sentiment data in this range.</td></tr>")

    topic_rows = []
    for t in (data.get("negative_topics") or [])[:12]:
        headlines = t.get("sample_headlines") or []
        h = "<br/>".join(f"<span class='muted'>• {_escape(x)}</span>" for x in headlines)
        topic_rows.append(
            "<tr>"
            f"<td>{_escape(t.get('topic',''))}<div style='margin-top:6px'>{h}</div></td>"
            f"<td class='num'>{_escape(t.get('mentions',0))}</td>"
            "</tr>"
        )
    if not topic_rows:
        topic_rows.append("<tr><td colspan='2' class='muted'>No negative topic drivers found.</td></tr>")

    src_rows = []
    for s in (data.get("negative_sources") or [])[:12]:
        src_rows.append(
            "<tr>"
            f"<td>{_escape(s.get('source_domain',''))}</td>"
            f"<td class='num'>{_escape(s.get('mentions',0))}</td>"
            "</tr>"
        )
    if not src_rows:
        src_rows.append("<tr><td colspan='2' class='muted'>No negative source drivers found.</td></tr>")

    body = f"""
      <div class="grid">
        <div class="card">
          <h2>Sentiment summary</h2>
          <table>
            <thead><tr><th>Entity</th><th class="num">Total</th><th class="num">Pos</th><th class="num">Neu</th><th class="num">Neg</th></tr></thead>
            <tbody>{''.join(sent_rows)}</tbody>
          </table>
        </div>
        <div class="card">
          <h2>Top negative sources</h2>
          <table>
            <thead><tr><th>Domain</th><th class="num">Neg mentions</th></tr></thead>
            <tbody>{''.join(src_rows)}</tbody>
          </table>
        </div>
      </div>
      <div class="card" style="margin-top:14px;">
        <h2>Negative drivers by topic (from article_documents.topics)</h2>
        <table>
          <thead><tr><th>Topic</th><th class="num">Neg mentions</th></tr></thead>
          <tbody>{''.join(topic_rows)}</tbody>
        </table>
        <div class="footer">Use this as a reputation/risk brief. Next iteration: add sentiment-by-topic and spike annotations.</div>
      </div>
    """

    html = _html_doc(
        title="Reputation & Sentiment Brief",
        subtitle="Negative drivers + sentiment mix",
        client=str(data.get("client") or client),
        range_param=range_param,
        body_html=body,
    )
    return HTMLResponse(content=html, headers={"Content-Disposition": f'attachment; filename=\"reputation-{client}-{range_param}.html\"'})


@router.get("/reports/alerts")
async def report_alerts_json(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    """
    Alerts report (JSON): detect mention spikes for client entities vs previous baseline.
    MVP: compare last 24h to previous 7d average (or range-derived baseline).
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitors = await _get_client_entities(client)
    if not entities:
        return {"client": client_name, "range": range_param, "spikes": []}

    now = datetime.now(timezone.utc)
    window = timedelta(hours=24)
    cur_start = now - window
    base_days = 7 if range_param != "24h" else 3
    base_start = cur_start - timedelta(days=base_days)

    db = get_db()
    em = db[ENTITY_MENTIONS_COLLECTION]

    def _match(dt_start: datetime, dt_end: datetime | None) -> dict[str, Any]:
        time_filter: list[dict[str, Any]] = []
        if dt_end is None:
            time_filter = [{"published_at": {"$gte": dt_start}}, {"timestamp": {"$gte": dt_start}}]
        else:
            time_filter = [
                {"published_at": {"$gte": dt_start, "$lt": dt_end}},
                {"timestamp": {"$gte": dt_start, "$lt": dt_end}},
            ]
        return {"entity": {"$in": entities}, "$or": time_filter}

    # Current 24h counts by entity
    pipe_cur = [
        {"$match": _match(cur_start, None)},
        {"$group": {"_id": "$entity", "mentions": {"$sum": 1}}},
    ]
    cur_counts: dict[str, int] = {}
    async for d in em.aggregate(pipe_cur):
        cur_counts[d["_id"]] = int(d.get("mentions", 0))

    # Baseline counts by entity (previous base_days window), compute daily avg
    pipe_base = [
        {"$match": _match(base_start, cur_start)},
        {"$group": {"_id": "$entity", "mentions": {"$sum": 1}}},
    ]
    base_counts: dict[str, int] = {}
    async for d in em.aggregate(pipe_base):
        base_counts[d["_id"]] = int(d.get("mentions", 0))

    spikes: list[dict[str, Any]] = []
    for e in entities:
        cur = cur_counts.get(e, 0)
        base_total = base_counts.get(e, 0)
        base_avg = base_total / float(base_days) if base_days > 0 else 0.0
        ratio = (cur / base_avg) if base_avg > 0 else (999.0 if cur > 0 else 0.0)
        delta = cur - base_avg
        # Spike threshold: at least 5 mentions and >2x baseline
        if cur >= 5 and ratio >= 2.0:
            spikes.append({
                "entity": e,
                "current_24h": cur,
                "baseline_daily_avg": round(base_avg, 1),
                "ratio": round(ratio, 2) if ratio != 999.0 else None,
                "delta": round(delta, 1),
            })

    spikes.sort(key=lambda x: -(x.get("ratio") or 0))
    return {
        "client": client_name,
        "competitors": competitors,
        "range": range_param,
        "spikes": spikes[:15],
        "window": {"current_start": _fmt_dt(cur_start), "current_end": _fmt_dt(now), "baseline_days": base_days},
    }


@router.get("/reports/alerts.html", response_class=HTMLResponse)
async def report_alerts_html(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    data = await report_alerts_json(client=client, range_param=range_param)
    spikes = data.get("spikes") or []
    rows = []
    for s in spikes:
        rows.append(
            "<tr>"
            f"<td>{_escape(s.get('entity',''))}</td>"
            f"<td class='num'>{_escape(s.get('current_24h',''))}</td>"
            f"<td class='num'>{_escape(s.get('baseline_daily_avg',''))}</td>"
            f"<td class='num'>{_escape(s.get('ratio','—'))}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='4' class='muted'>No spikes detected with current thresholds.</td></tr>")

    w = data.get("window") or {}
    body = f"""
      <div class="card">
        <h2>Spike monitor (mentions)</h2>
        <div class="muted" style="margin-bottom:10px;">
          Window: {_escape(w.get('current_start'))} → {_escape(w.get('current_end'))} • Baseline: last {_escape(w.get('baseline_days'))} days (daily avg)
        </div>
        <table>
          <thead><tr><th>Entity</th><th class="num">Current 24h</th><th class="num">Baseline/day</th><th class="num">x</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="footer">Next iteration: attach top headlines for each spike and flag negative spikes first.</div>
      </div>
    """
    html = _html_doc(
        title="Alerts & Spike Brief",
        subtitle="What’s spiking right now",
        client=str(data.get("client") or client),
        range_param=range_param,
        body_html=body,
    )
    return HTMLResponse(content=html, headers={"Content-Disposition": f'attachment; filename=\"alerts-{client}-{range_param}.html\"'})


@router.get("/reports/targets")
async def report_targets_json(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    """
    Publication targeting report (JSON):
    Domains that cover competitors but have little/no client coverage in the same range.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    client_name, entities, competitors = await _get_client_entities(client)
    if not entities:
        return {"client": client_name, "range": range_param, "targets": []}

    delta = _parse_range(range_param)
    cutoff = datetime.now(timezone.utc) - delta
    db = get_db()
    em = db[ENTITY_MENTIONS_COLLECTION]

    match = {
        "entity": {"$in": entities},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}],
    }

    # Aggregate domain counts by entity
    pipeline = [
        {"$match": match},
        {"$project": {"entity": 1, "source": {"$ifNull": ["$source_domain", "$source"]}}},
        {"$group": {"_id": {"domain": "$source", "entity": "$entity"}, "mentions": {"$sum": 1}}},
    ]
    # Build dict: domain -> {entity: mentions}
    domain_map: dict[str, dict[str, int]] = {}
    async for d in em.aggregate(pipeline):
        dom_raw = d["_id"]["domain"]
        dom = _normalize_domain(dom_raw or "")
        ent = d["_id"]["entity"]
        if not dom or not ent:
            continue
        domain_map.setdefault(dom, {})
        domain_map[dom][ent] = int(d.get("mentions", 0))

    targets: list[dict[str, Any]] = []
    for dom, counts in domain_map.items():
        client_mentions = counts.get(client_name, 0)
        competitor_mentions = sum(counts.get(c, 0) for c in competitors) if competitors else 0
        if competitor_mentions >= 3 and client_mentions == 0:
            targets.append({
                "domain": dom,
                "client_mentions": client_mentions,
                "competitor_mentions": competitor_mentions,
                "top_competitor": max(competitors, key=lambda c: counts.get(c, 0)) if competitors else None,
            })
    targets.sort(key=lambda x: -x.get("competitor_mentions", 0))
    return {"client": client_name, "competitors": competitors, "range": range_param, "targets": targets[:25]}


@router.get("/reports/targets.html", response_class=HTMLResponse)
async def report_targets_html(
    client: str = Query(..., description="Primary client name, e.g. Sahi"),
    range_param: str = Query("7d", alias="range", description="24h | 7d | 30d"),
):
    data = await report_targets_json(client=client, range_param=range_param)
    rows = []
    for t in (data.get("targets") or [])[:25]:
        rows.append(
            "<tr>"
            f"<td>{_escape(t.get('domain',''))}</td>"
            f"<td class='num'>{_escape(t.get('client_mentions',0))}</td>"
            f"<td class='num'>{_escape(t.get('competitor_mentions',0))}</td>"
            f"<td>{_escape(t.get('top_competitor') or '')}</td>"
            "</tr>"
        )
    if not rows:
        rows.append("<tr><td colspan='4' class='muted'>No targeting opportunities found with current thresholds.</td></tr>")

    body = f"""
      <div class="card">
        <h2>Publication targets (competitors covered, client missing)</h2>
        <table>
          <thead><tr><th>Domain</th><th class="num">Client</th><th class="num">Competitors</th><th>Top competitor</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
        <div class="footer">Use these domains for outreach: competitors have coverage but the client has none in this period.</div>
      </div>
    """
    html = _html_doc(
        title="Publication Targeting Brief",
        subtitle="Where competitors get covered, but client doesn’t",
        client=str(data.get("client") or client),
        range_param=range_param,
        body_html=body,
    )
    return HTMLResponse(content=html, headers={"Content-Disposition": f'attachment; filename=\"targets-{client}-{range_param}.html\"'})

