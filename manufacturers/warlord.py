from curl_cffi.requests import AsyncSession

SLUG = "warlord"
NAME = "Warlord Games"
ICON = "/static/icons/warlord.webp"
BASE = "https://store.warlordgames.com"

RANGES = [
    {"slug": "bolt-action", "name": "Bolt Action", "handle": "bolt-action", "group": "Historical"},
    {"slug": "hail-caesar", "name": "Hail Caesar", "handle": "hail-caesar", "group": "Historical"},
    {"slug": "black-powder", "name": "Black Powder", "handle": "black-powder", "group": "Historical"},
    {"slug": "pike-shotte", "name": "Pike & Shotte Epic Battles", "handle": "pike-shotte-epic-battles", "group": "Epic Battles"},
    {"slug": "epic-acw", "name": "Epic ACW", "handle": "epic-battles-american-civil-war", "group": "Epic Battles"},
    {"slug": "epic-waterloo", "name": "Epic Waterloo", "handle": "epic-battles-waterloo", "group": "Epic Battles"},
    {"slug": "black-seas", "name": "Black Seas", "handle": "black-seas", "group": "Naval"},
    {"slug": "mythic-americas", "name": "Mythic Americas", "handle": "mythic-americas", "group": "Fantasy"},
    {"slug": "erehwon", "name": "Warlords of Erehwon", "handle": "warlords-of-erehwon", "group": "Fantasy"},
]


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    import sys
    handle = range_def["handle"]
    out: list[dict] = []
    page = 1
    sys.stdout.write("fetching: ")
    sys.stdout.flush()
    while True:
        url = f"{BASE}/collections/{handle}/products.json"
        r = await client.get(url, params={"limit": 250, "page": page}, timeout=20)
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
            out.append({
                "title": p.get("title"),
                "sku": v.get("sku") or None,
                "url": f"{BASE}/products/{p.get('handle')}",
                "image_url": images[0].get("src") if images else None,
                "price": price,
                "description": p.get("body_html") or None,
            })
        sys.stdout.write(".")
        sys.stdout.flush()
        if len(products) < 250:
            break
        page += 1
    sys.stdout.write(f" {len(out)} products\n")
    sys.stdout.flush()
    return out
