import asyncio
import json
from datetime import datetime, timezone


async def _main() -> None:
    from app.core.client_config_loader import load_clients_sync, get_entity_names
    from app.services.narrative_strategy_engine import generate_narrative_strategy_v2

    clients = load_clients_sync()
    entities: list[str] = []
    for c in clients:
        if not isinstance(c, dict):
            continue
        for n in get_entity_names(c):
            if n and n not in entities:
                entities.append(n)

    print(json.dumps({"ok": True, "entities": entities, "count": len(entities)}, indent=2))

    vertical = "broker"  # trading bundle is broking/capital markets
    started = datetime.now(timezone.utc)
    results: dict[str, object] = {}
    for name in entities:
        try:
            rows = await generate_narrative_strategy_v2(company=name, vertical=vertical, limit=8, use_llm=True)
            results[name] = {"rows": rows}
            print(json.dumps({"entity": name, "rows": len(rows)}, indent=2))
        except Exception as e:
            results[name] = {"error": str(e)}
            print(json.dumps({"entity": name, "error": str(e)}, indent=2))

    finished = datetime.now(timezone.utc)
    out = {
        "started_at": started.isoformat(),
        "finished_at": finished.isoformat(),
        "vertical": vertical,
        "entity_count": len(entities),
        "results": results,
    }
    print(json.dumps(out, indent=2))


if __name__ == "__main__":
    asyncio.run(_main())

