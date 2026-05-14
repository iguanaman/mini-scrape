from curl_cffi.requests import AsyncSession

SLUG = "victrix"
NAME = "Victrix"
ICON = "/static/icons/victrix.avif"
BASE = "https://victrixlimited.com"

# 28mm only — skip 12mm.
RANGES = [
    {"slug": "ancients", "name": "Ancients", "handle": "ancients", "group": "Ancients"},
    {"slug": "dark-ages", "name": "Dark Ages", "handle": "dark-ages", "group": "Medieval & Dark Ages"},
    {"slug": "medieval-dark-ages", "name": "Medieval", "handle": "medieval-dark-ages", "group": "Medieval & Dark Ages"},
    {"slug": "napoleonics", "name": "Napoleonics", "handle": "28mm-napoleonics", "group": "Napoleonics"},
    {"slug": "british-napoleonics", "name": "British Napoleonics", "handle": "british-napoleonics", "group": "Napoleonics"},
    {"slug": "french-napoleonics", "name": "French Napoleonics", "handle": "french-napoleonics", "group": "Napoleonics"},
    {"slug": "28mm-wwii", "name": "28mm WWII", "handle": "28mm-wwii", "group": "WWII"},
    {"slug": "pillage", "name": "Pillage, Ransack…", "handle": "pillage-ransack-the-middle-ages", "group": "Games"},
    {"slug": "army-sets", "name": "Army Sets", "handle": "28mm-army-sets", "group": "Bundles"},
]


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    handle = range_def["handle"]
    out: list[dict] = []
    page = 1
    while True:
        url = f"{BASE}/collections/{handle}/products.json"
        r = await client.get(url, params={"limit": 250, "page": page}, timeout=15)
        r.raise_for_status()
        products = r.json().get("products", [])
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
