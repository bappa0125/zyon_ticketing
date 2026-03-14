"""PR Reports API — snapshots, press releases, export (reads from pr_daily_snapshots)."""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import HTMLResponse
from pydantic import BaseModel

from app.core.client_config_loader import load_clients
from app.services.pr_report_service import (
    get_snapshots,
    run_daily_snapshot_all_clients,
    list_press_releases,
    add_press_release,
    get_press_release_pickups,
    compute_press_release_pickups,
)

router = APIRouter(tags=["pr-reports"])


class AddPressReleaseRequest(BaseModel):
    client: str
    url: str
    title: str = ""
    published_at: str = ""


@router.get("/pr-reports/clients")
async def pr_reports_clients():
    """List clients for multi-client selector."""
    clients = await load_clients()
    names = [(c.get("name") or "").strip() for c in clients if (c.get("name") or "").strip()]
    return {"clients": names}


@router.get("/pr-reports/snapshots")
async def pr_reports_snapshots(
    client: str = Query(..., description="Client name"),
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
):
    """Fetch stored daily snapshots for date range. Per-day grids."""
    if not client:
        raise HTTPException(status_code=400, detail="client required")
    snapshots = await get_snapshots(client, from_date, to_date)
    # Serialize datetime for JSON
    out = []
    for s in snapshots:
        d = {k: v for k, v in s.items() if k != "_id"}
        if "computed_at" in d and d["computed_at"]:
            d["computed_at"] = d["computed_at"].strftime("%Y-%m-%dT%H:%M:%SZ") if hasattr(d["computed_at"], "strftime") else str(d["computed_at"])
        out.append(d)
    return {"client": client, "from_date": from_date, "to_date": to_date, "snapshots": out}


@router.post("/pr-reports/run-batch")
async def pr_reports_run_batch(date: Optional[str] = Query(None, description="YYYY-MM-DD (default: today)")):
    """Trigger daily snapshot batch. Typically run by scheduler."""
    result = await run_daily_snapshot_all_clients(date)
    return result


@router.get("/pr-reports/press-releases")
async def pr_reports_press_releases(client: str = Query(...)):
    """List press releases for client."""
    releases = await list_press_releases(client, limit=100)
    return {"client": client, "press_releases": releases}


@router.post("/pr-reports/press-releases")
async def pr_reports_add_press_release(body: AddPressReleaseRequest):
    """Add a press release for pickup tracking."""
    r = await add_press_release(
        body.client,
        body.url,
        body.title,
        body.published_at,
    )
    return r


@router.get("/pr-reports/press-release-pickups")
async def pr_reports_pickups(client: str = Query(...)):
    """Get press release pickups for client."""
    pickups = await get_press_release_pickups(client, limit=100)
    return {"client": client, "pickups": pickups}


@router.post("/pr-reports/compute-pickups")
async def pr_reports_compute_pickups(client: str = Query(...), date: Optional[str] = Query(None)):
    """Run pickup computation batch for client. Typically run by scheduler."""
    result = await compute_press_release_pickups(client, date)
    return result


def _escape(s) -> str:
    v = str(s) if s is not None else ""
    return v.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


@router.get("/pr-reports/export/html", response_class=HTMLResponse)
async def pr_reports_export_html(
    client: str = Query(...),
    from_date: str = Query(...),
    to_date: str = Query(...),
):
    """Export PR report as HTML from stored snapshots. No LLM, reads from DB."""
    snapshots = await get_snapshots(client, from_date, to_date)
    pickups = await get_press_release_pickups(client, limit=50)

    rows = []
    for s in sorted(snapshots, key=lambda x: x.get("date", ""), reverse=True):
        date_str = s.get("date", "")
        outreach = s.get("outreach_targets") or []
        benchmarks = s.get("benchmarks") or []
        alerts = s.get("sentiment_alerts") or []
        rows.append({
            "date": date_str,
            "outreach": outreach[:10],
            "benchmarks": benchmarks,
            "alerts": alerts,
        })

    html_parts = [
        "<!DOCTYPE html><html><head><meta charset='utf-8'><title>PR Report - ",
        _escape(client),
        "</title><style>",
        "body{font-family:system-ui,sans-serif;max-width:900px;margin:0 auto;padding:20px;}",
        "h1,h2{color:#1a1a2e;} table{border-collapse:collapse;width:100%;margin:1em 0;}",
        "th,td{border:1px solid #ccc;padding:8px;text-align:left;} th{background:#f0f0f0;}",
        ".alert-high{background:#fee;} .alert-medium{background:#ffc;}",
        ".empty{color:#999;}",
        "</style></head><body>",
        "<h1>PR Intelligence Report</h1>",
        "<p><strong>Client:</strong> ", _escape(client), " | <strong>Range:</strong> ",
        _escape(from_date), " – ", _escape(to_date), "</p>",
    ]

    for r in rows:
        html_parts.append(f"<h2>{_escape(r['date'])}</h2>")
        html_parts.append("<h3>Outreach targets</h3>")
        if r["outreach"]:
            html_parts.append("<table><tr><th>Outlet</th><th>Client</th><th>Competitors</th></tr>")
            for o in r["outreach"]:
                html_parts.append(
                    f"<tr><td>{_escape(o.get('outlet'))}</td>"
                    f"<td>{o.get('client_mentions', 0)}</td>"
                    f"<td>{o.get('competitor_mentions', 0)}</td></tr>"
                )
            html_parts.append("</table>")
        else:
            html_parts.append("<p class='empty'>None</p>")

        html_parts.append("<h3>Benchmarks</h3>")
        if r["benchmarks"]:
            html_parts.append("<table><tr><th>Entity</th><th>Mentions</th><th>Sentiment</th><th>Share of voice %</th></tr>")
            for b in r["benchmarks"]:
                html_parts.append(
                    f"<tr><td>{_escape(b.get('entity'))}</td>"
                    f"<td>{b.get('mentions', 0)}</td>"
                    f"<td>{b.get('sentiment_avg', 0)}</td>"
                    f"<td>{b.get('share_of_voice_pct', 0)}</td></tr>"
                )
            html_parts.append("</table>")
        else:
            html_parts.append("<p class='empty'>No data</p>")

        html_parts.append("<h3>Sentiment alerts</h3>")
        if r["alerts"]:
            for a in r["alerts"]:
                cls = "alert-high" if (a.get("severity") or "").lower() == "high" else "alert-medium"
                html_parts.append(
                    f"<p class='{cls}'>{_escape(a.get('alert_type'))} | "
                    f"Negative: {a.get('negative_pct', 0)}% ({a.get('negative_count', 0)}/{a.get('total_mentions', 0)})</p>"
                )
        else:
            html_parts.append("<p class='empty'>None</p>")

    if pickups:
        html_parts.append("<h2>Press release pickups</h2><table><tr><th>Article</th><th>Published</th></tr>")
        for p in pickups[:30]:
            title = (p.get("article_title") or p.get("article_url") or "")[:80]
            html_parts.append(
                f"<tr><td><a href='{_escape(p.get('article_url',''))}'>{_escape(title)}</a></td>"
                f"<td>{_escape(p.get('published_at',''))}</td></tr>"
            )
        html_parts.append("</table>")

    html_parts.append("<p><small>Generated at " + datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC") + "</small></p>")
    html_parts.append("</body></html>")
    return "".join(html_parts)
