"""Test search_mentions with different entities for Sahi disambiguation validation."""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def run_test(entity: str) -> dict:
    from app.services.media_mention.mention_search import search_mentions

    results = search_mentions(
        company=entity,
        use_internal=True,
        use_google_news=True,
        use_external=True,
        llm_rerank=False,
    )
    out = []
    for r in results[:8]:
        out.append({
            "title": (r.get("title") or "")[:100],
            "source": r.get("source", ""),
            "type": r.get("type", ""),
            "snippet": (r.get("snippet") or r.get("summary") or "")[:120],
        })
    return {"entity": entity, "count": len(results), "results": out}


def main():
    entities = [
        "Sahi",
        "Sahi trading app",
        "latest news on Sahi",
        "Zerodha",
    ]
    all_results = []
    for e in entities:
        try:
            out = run_test(e)
            all_results.append(out)
        except Exception as ex:
            all_results.append({"entity": e, "error": str(ex), "count": 0, "results": []})

    print(json.dumps(all_results, indent=2, default=str))


if __name__ == "__main__":
    main()
