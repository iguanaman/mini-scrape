from curl_cffi.requests import AsyncSession

SLUG = "wargamesatlantic"
NAME = "Wargames Atlantic"
ICON = "/static/icons/wargamesatlantic.png"
BASE = "https://wargamesatlantic.com"

RANGES = [
    {"slug": "plastic-box-sets", "name": "Plastic Box Sets", "handle": "plastic-box-sets"},
    {"slug": "death-fields-arena", "name": "Death Fields Arena", "handle": "death-fields-arena"},
    {"slug": "quar", "name": "Quar", "handle": "quar"},
    {"slug": "barons-war", "name": "The Barons' War", "handle": "the-barons-war"},
    {"slug": "classic-fantasy", "name": "Classic Fantasy", "handle": "classic-fantasy"},
    {"slug": "age-of-chivalry", "name": "The Age of Chivalry", "handle": "the-age-of-chivalry"},
    {"slug": "world-ablaze", "name": "World Ablaze", "handle": "world-ablaze"},
]


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    handle = range_def["handle"]
    out: list[dict] = []
    page = 1
    while True:
        url = f"{BASE}/collections/{handle}/products.json"
        r = await client.get(url, params={"limit": 250, "page": page}, timeout=15)
        r.raise_for_status()
        data = r.json()
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            variants = p.get("variants") or []
            v = variants[0] if variants else {}
            try:
                price = float(v.get("price")) if v.get("price") is not None else None
            except (TypeError, ValueError):
                price = None
            images = p.get("images") or []
            image_url = images[0].get("src") if images else None
            out.append({
                "title": p.get("title"),
                "sku": v.get("sku"),
                "url": f"{BASE}/products/{p.get('handle')}",
                "image_url": image_url,
                "price": price,
            })
        if len(products) < 250:
            break
        page += 1
    return out
