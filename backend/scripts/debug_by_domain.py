"""Debug why by_domain returns zeros. Run inside backend container."""
import asyncio
from datetime import datetime, timedelta, timezone

# Minimal copy of service logic to trace
def _normalize_domain(source: str) -> str:
    if not source or not isinstance(source, str):
        return ""
    s = source.strip().lower()
    if s.startswith("www."):
        s = s[4:]
    if "://" in s:
        s = s.split("://", 1)[1]
    if "/" in s:
        s = s.split("/", 1)[0]
    if s.startswith("www."):
        s = s[4:]
    return s[:200]


def _domain_from_url(url: str) -> str:
    from urllib.parse import urlparse
    if not url or not isinstance(url, str):
        return ""
    parsed = urlparse((url or "").strip())
    netloc = (parsed.netloc or "").split(":")[0].lower()
    if not netloc or netloc == "news.google.com":
        return ""
    if netloc.startswith("www."):
        netloc = netloc[4:]
    return netloc[:200] if "." in netloc and " " not in netloc else ""


def _map_to_config_domain(domain: str, config_domains: set) -> str | None:
    if not domain or not isinstance(domain, str):
        return None
    d = domain.strip().lower()
    if not d or " " in d:
        return None
    if d.startswith("www."):
        d = d[4:]
    if d in config_domains:
        return d
    for cfg in config_domains:
        if d == cfg or d.endswith("." + cfg):
            return cfg
    return None


async def main():
    from app.config import get_config
    from motor.motor_asyncio import AsyncIOMotorClient
    from app.core.client_config_loader import load_clients, get_entity_names
    from app.services.monitoring_ingestion.media_source_registry import load_media_sources

    config = get_config()
    client = AsyncIOMotorClient(config["settings"].mongodb_url)
    db = client[config["mongodb"].get("database", "chat")]
    em = db["entity_mentions"]
    art = db["article_documents"]

    clients_list = await load_clients()
    client_obj = next((c for c in clients_list if (c.get("name") or "").strip().lower() == "sahi"), None)
    entities = get_entity_names(client_obj) if client_obj else ["Sahi", "Zerodha"]
    cutoff = datetime.now(timezone.utc) - timedelta(days=7)

    # Build unified-like
    raw = []
    async for doc in em.find({"entity": {"$in": list(entities)},
        "$or": [{"published_at": {"$gte": cutoff}}, {"timestamp": {"$gte": cutoff}}]}).limit(100):
        raw.append({
            "url": (doc.get("url") or "").strip(),
            "source": doc.get("source") or doc.get("source_domain") or "",
            "entity": (doc.get("entity") or "").strip(),
        })
    async for doc in art.find({"entities": {"$in": list(entities)},
        "$or": [{"published_at": {"$gte": cutoff}}, {"fetched_at": {"$gte": cutoff}}]}).limit(100):
        for e in (doc.get("entities") or []):
            if e in entities:
                raw.append({
                    "url": (doc.get("url") or doc.get("url_resolved") or "").strip(),
                    "source": doc.get("source_domain") or doc.get("source") or "",
                    "entity": str(e),
                })
                break

    # Compute source_domain like service
    source_domains = []
    for r in raw[:30]:
        url_val = r.get("url") or ""
        dom = _domain_from_url(url_val) if url_val else _normalize_domain(r.get("source") or "")
        r["_computed_domain"] = dom
        source_domains.append(dom)

    config_sources = load_media_sources()
    config_domain_set = set()
    for s in config_sources:
        d = _normalize_domain(s.get("domain") or "")
        if d:
            config_domain_set.add(d)

    print("=== debug by_domain ===\n")
    print(f"Unified-like rows: {len(raw)}")
    print(f"Config domains count: {len(config_domain_set)}")
    print(f"Sample config domains: {sorted(config_domain_set)[:10]}\n")
    print("Sample raw rows (url, source, _computed_domain, entity):")
    for r in raw[:10]:
        print(f"  url={r.get('url','')[:60]}... source={r.get('source','')[:40]} domain={r.get('_computed_domain','')} entity={r.get('entity','')}")
    print("\nMap check (first 15 computed domains):")
    mapped_ok = 0
    for sd in source_domains[:15]:
        m = _map_to_config_domain(sd, config_domain_set)
        status = "OK" if m else "FAIL"
        if m:
            mapped_ok += 1
        print(f"  {sd!r} -> {m!r} {status}")
    print(f"\nMapped OK: {mapped_ok} / {len([x for x in source_domains if x])}")


if __name__ == "__main__":
    asyncio.run(main())
