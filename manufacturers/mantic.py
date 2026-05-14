from curl_cffi.requests import AsyncSession

SLUG = "mantic"
NAME = "Mantic"
ICON = "/static/icons/mantic.ico"
BASE = "https://www.manticgames.com"

RANGES = [
    {"slug": "kings-of-war", "name": "Kings of War", "category": "kings-of-war"},
    {"slug": "deadzone", "name": "Deadzone", "category": "deadzone"},
    {"slug": "firefight", "name": "Firefight", "category": "firefight"},
    {"slug": "armada", "name": "Armada", "category": "armada"},
    {"slug": "epic-warpath", "name": "Epic Warpath", "category": "epic-warpath"},
    {"slug": "walking-dead", "name": "The Walking Dead", "category": "the-walking-dead"},
    {"slug": "dungeon-saga", "name": "Dungeon Saga", "category": "dungeon-saga"},
    {"slug": "hellboy", "name": "Hellboy", "category": "hellboy"},
    {"slug": "halo-flashpoint", "name": "Halo Flashpoint", "category": "halo-flashpoint"},
]


def _price(prices: dict) -> float | None:
    if not prices:
        return None
    raw = prices.get("price") or (prices.get("price_range") or {}).get("min_amount")
    if raw is None:
        return None
    try:
        minor = int(prices.get("currency_minor_unit", 2))
        return int(raw) / (10 ** minor)
    except (TypeError, ValueError):
        return None


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    cat = range_def["category"]
    out: list[dict] = []
    page = 1
    per_page = 100
    while True:
        r = await client.get(
            f"{BASE}/wp-json/wc/store/v1/products",
            params={"category": cat, "per_page": per_page, "page": page},
            timeout=15,
        )
        r.raise_for_status()
        products = r.json()
        if not products:
            break
        for p in products:
            images = p.get("images") or []
            out.append({
                "title": p.get("name"),
                "sku": p.get("sku") or None,
                "url": p.get("permalink"),
                "image_url": images[0].get("src") if images else None,
                "price": _price(p.get("prices") or {}),
            })
        if len(products) < per_page:
            break
        page += 1
    return out
