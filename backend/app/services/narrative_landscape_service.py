"""
CXO narrative landscape: where themes show up (publication vs forum), entity share, gaps, suggested moves.
Uses entity_mentions with narrative_primary / narrative_tags and type article|forum.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

from app.core.client_config_loader import get_entity_names, load_clients
from app.core.logging import get_logger
from app.services.mongodb import get_mongo_client

logger = get_logger(__name__)

ENTITY_MENTIONS_COLLECTION = "entity_mentions"


def _str(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, str):
        return val.strip()
    return str(val)[:500]


def _iso(val: Any) -> str:
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.isoformat()
    return str(val)[:40]


def _cxo_moves(
    tag: str,
    gap_type: str,
    publication_count: int,
    forum_count: int,
    client_name: str,
) -> list[str]:
    """Template plays for exec deck (not LLM)."""
    moves: list[str] = []
    if gap_type == "sahi_absent":
        moves.append(
            f"No {client_name} voice in “{_human_tag(tag)}” in this window — seed owned content "
            "(blog/help center) and place founder/PM quotes in trade media before forums set the frame."
        )
        if forum_count > publication_count:
            moves.append(
                "Debate is forum-led: assign community monitoring + factual FAQs reps can post where policy allows."
            )
    elif gap_type == "sahi_underindexed":
        moves.append(
            f"Increase share of voice in “{_human_tag(tag)}”: pair product fixes with transparent changelog comms "
            "and target 1–2 outlets your users already cite in threads."
        )
    elif gap_type == "sahi_strong":
        moves.append(
            f"Protect the lead on “{_human_tag(tag)}”: turn positive threads into case studies and keep support "
            "response time visible — competitors will chase this narrative next."
        )
    else:
        moves.append(
            f"Contest “{_human_tag(tag)}” directly: map competitor claims in threads vs your facts sheet; "
            "publish clarifications where misinformation repeats."
        )
    if publication_count == 0 and forum_count > 0:
        moves.append(
            "Origin signal is forum-only in-window: add a publication touchpoint (press note, regulator-facing FAQ, "
            "or analyst note) so the story isn’t only community-sourced."
        )
    return moves[:3]


def _human_tag(tag: str) -> str:
    return tag.replace("_", " ") if tag else tag


async def get_narrative_landscape(
    client: Optional[str] = None,
    range_days: int = 30,
    top_tags: int = 15,
) -> dict[str, Any]:
    """
    Build per-narrative-tag rows: publication vs forum volumes, earliest examples, entity split, gap type, CXO moves.
    """
    await get_mongo_client()
    from app.services.mongodb import get_db

    db = get_db()
    em_coll = db[ENTITY_MENTIONS_COLLECTION]
    cutoff = datetime.now(timezone.utc) - timedelta(days=min(range_days, 90))

    entities_filter: Optional[list[str]] = None
    client_name = ""
    if client and client.strip():
        clients_list = await load_clients()
        client_obj = next(
            (c for c in clients_list if _str(c.get("name")).lower() == client.strip().lower()),
            None,
        )
        if client_obj:
            entities_filter = get_entity_names(client_obj)
            client_name = _str(client_obj.get("name"))

    if not entities_filter:
        return {
            "landscape": [],
            "client": client,
            "client_name": client_name,
            "range_days": range_days,
            "frame": {
                "origin": "Publication / RSS articles (type=article) — where many narratives first appear in corpus.",
                "amplifier": "Forums (type=forum) — where traders debate, reinforce, or distort the same themes.",
            },
            "error": "Unknown client or empty entity list — check clients.yaml",
        }

    base_match: dict[str, Any] = {
        "entity": {"$in": entities_filter},
        "$or": [
            {"published_at": {"$gte": cutoff}},
            {"timestamp": {"$gte": cutoff}},
        ],
    }

    pipeline: list[dict[str, Any]] = [
        {"$match": base_match},
        {
            "$addFields": {
                "tag": {
                    "$ifNull": [
                        "$narrative_primary",
                        {"$arrayElemAt": ["$narrative_tags", 0]},
                    ]
                },
                "date_sort": {"$ifNull": ["$published_at", "$timestamp"]},
            }
        },
        {"$match": {"tag": {"$nin": [None, ""]}}},
        {
            "$facet": {
                "by_tag_type": [
                    {
                        "$group": {
                            "_id": {"t": "$tag", "typ": {"$ifNull": ["$type", "unknown"]}},
                            "n": {"$sum": 1},
                        }
                    }
                ],
                "by_tag_entity": [
                    {
                        "$group": {
                            "_id": {"t": "$tag", "e": "$entity"},
                            "n": {"$sum": 1},
                        }
                    }
                ],
                "earliest_article": [
                    {"$match": {"type": "article", "date_sort": {"$ne": None}}},
                    {"$sort": {"date_sort": 1}},
                    {
                        "$group": {
                            "_id": "$tag",
                            "doc": {
                                "$first": {
                                    "title": "$title",
                                    "url": "$url",
                                    "at": "$date_sort",
                                    "entity": "$entity",
                                    "source_domain": "$source_domain",
                                }
                            },
                        }
                    },
                ],
                "earliest_forum": [
                    {"$match": {"type": "forum", "date_sort": {"$ne": None}}},
                    {"$sort": {"date_sort": 1}},
                    {
                        "$group": {
                            "_id": "$tag",
                            "doc": {
                                "$first": {
                                    "title": "$title",
                                    "url": "$url",
                                    "at": "$date_sort",
                                    "entity": "$entity",
                                    "source_domain": "$source_domain",
                                    "forum_site": "$forum_site",
                                }
                            },
                        }
                    },
                ],
            }
        },
    ]

    facet_result = await em_coll.aggregate(pipeline).to_list(length=1)
    if not facet_result:
        raw = {"by_tag_type": [], "by_tag_entity": [], "earliest_article": [], "earliest_forum": []}
    else:
        raw = facet_result[0]

    # Index: tag -> {article?, forum?, other?}
    type_by_tag: dict[str, dict[str, int]] = {}
    for row in raw.get("by_tag_type") or []:
        tid = _str((row.get("_id") or {}).get("t"))
        typ = _str((row.get("_id") or {}).get("typ")) or "unknown"
        n = int(row.get("n") or 0)
        if not tid:
            continue
        type_by_tag.setdefault(tid, {})
        type_by_tag[tid][typ] = type_by_tag[tid].get(typ, 0) + n

    entity_by_tag: dict[str, dict[str, int]] = {}
    for row in raw.get("by_tag_entity") or []:
        tid = _str((row.get("_id") or {}).get("t"))
        ent = _str((row.get("_id") or {}).get("e"))
        n = int(row.get("n") or 0)
        if not tid or not ent:
            continue
        entity_by_tag.setdefault(tid, {})
        entity_by_tag[tid][ent] = entity_by_tag[tid].get(ent, 0) + n

    earliest_article: dict[str, Any] = {}
    for row in raw.get("earliest_article") or []:
        tid = _str(row.get("_id"))
        if tid:
            earliest_article[tid] = row.get("doc")

    earliest_forum: dict[str, Any] = {}
    for row in raw.get("earliest_forum") or []:
        tid = _str(row.get("_id"))
        if tid:
            earliest_forum[tid] = row.get("doc")

    # Totals per tag
    tag_totals: list[tuple[str, int]] = []
    for tid, buckets in type_by_tag.items():
        total = sum(buckets.values())
        tag_totals.append((tid, total))
    tag_totals.sort(key=lambda x: -x[1])
    selected_tags = [t[0] for t in tag_totals[: max(1, min(top_tags, 40))]]

    landscape: list[dict[str, Any]] = []
    executive_gaps: list[dict[str, Any]] = []

    for tid in selected_tags:
        buckets = type_by_tag.get(tid, {})
        publication_count = int(buckets.get("article", 0))
        forum_count = int(buckets.get("forum", 0))
        other_count = sum(v for k, v in buckets.items() if k not in ("article", "forum"))

        ent_counts = entity_by_tag.get(tid, {})
        total_mentions = publication_count + forum_count + other_count
        sahi_count = int(ent_counts.get(client_name, 0))
        competitor_total = total_mentions - sahi_count
        sahi_share = (sahi_count / total_mentions) if total_mentions else 0.0

        if sahi_count == 0 and total_mentions >= 2:
            gap_type = "sahi_absent"
        elif sahi_share < 0.15 and total_mentions >= 4:
            gap_type = "sahi_underindexed"
        elif sahi_share >= 0.35 and sahi_count > 0:
            gap_type = "sahi_strong"
        else:
            gap_type = "competitive"

        ea = earliest_article.get(tid)
        ef = earliest_forum.get(tid)
        origin_story = (
            "Earliest **publication** signal in window (RSS/article pipeline)."
            if ea
            else "No publication-tagged mention in window — origin may be older or untagged."
        )
        amplifier_story = (
            "Earliest **forum** echo in window (trader discussion)."
            if ef
            else "No forum echo in window for this tag."
        )

        entity_breakdown = sorted(
            [{"entity": e, "count": c} for e, c in ent_counts.items()],
            key=lambda x: -x["count"],
        )[:12]

        row_out = {
            "narrative_tag": tid,
            "narrative_label": _human_tag(tid),
            "counts": {
                "publication": publication_count,
                "forum": forum_count,
                "other": other_count,
                "total": total_mentions,
            },
            "sahi": {
                "entity": client_name,
                "mentions": sahi_count,
                "share_of_voice_pct": round(sahi_share * 100, 1),
            },
            "competitor_mentions_total": competitor_total,
            "gap_type": gap_type,
            "where_it_started": {
                "publication": _format_earliest(ea),
                "caption": origin_story,
            },
            "what_amplified_it": {
                "forum": _format_earliest(ef),
                "caption": amplifier_story,
            },
            "entity_breakdown": entity_breakdown,
            "cxo_moves": _cxo_moves(tid, gap_type, publication_count, forum_count, client_name),
        }
        landscape.append(row_out)

        if gap_type in ("sahi_absent", "sahi_underindexed"):
            executive_gaps.append({
                "narrative_tag": tid,
                "gap_type": gap_type,
                "headline": _gap_headline(tid, gap_type, client_name),
            })

    return {
        "landscape": landscape,
        "executive_gaps": executive_gaps[:8],
        "client": client,
        "client_name": client_name,
        "range_days": range_days,
        "frame": {
            "origin": "Publication (type=article) — first trace in monitored media corpus in this window.",
            "amplifier": "Forum (type=forum) — where the narrative is debated and amplified among traders.",
            "gap": "sahi_absent / sahi_underindexed = whitespace or weak share vs competitors on that theme.",
        },
    }


def _format_earliest(doc: Any) -> Optional[dict[str, Any]]:
    if not doc or not isinstance(doc, dict):
        return None
    return {
        "title": _str(doc.get("title"))[:200],
        "url": _str(doc.get("url"))[:2000],
        "published_at": _iso(doc.get("at")),
        "entity": _str(doc.get("entity")),
        "source_domain": _str(doc.get("source_domain")),
        "forum_site": _str(doc.get("forum_site")) or None,
    }


def _gap_headline(tag: str, gap_type: str, client_name: str) -> str:
    label = _human_tag(tag)
    if gap_type == "sahi_absent":
        return f"{client_name} is not present in “{label}” mentions — competitors own the conversation."
    return f"{client_name} is under-represented in “{label}” vs competitors — room to increase share of voice."
