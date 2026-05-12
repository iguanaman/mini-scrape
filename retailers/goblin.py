import httpx

NAME = "Goblin Gaming"
BASE = "https://www.goblingaming.co.uk"
SEARCH_URL = BASE + "/search/suggest.json"


def _to_float(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    # Shopify suggest.json returns prices as decimal strings in major units (e.g. "19.80").
    return f if f > 0 else None


def _abs_url(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    if u.startswith("/"):
        return BASE + u
    return u


async def search(query: str, client: httpx.AsyncClient) -> list[dict]:
    params = {
        "q": query,
        "resources[type]": "product",
        "resources[limit]": "10",
    }
    r = await client.get(SEARCH_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    products = (
        data.get("resources", {})
        .get("results", {})
        .get("products", [])
    )
    out: list[dict] = []
    for p in products[:10]:
        price = _to_float(p.get("price"))
        rrp = _to_float(p.get("compare_at_price"))
        if rrp is not None and price is not None and rrp <= price:
            rrp = None
        img = (p.get("featured_image") or {}).get("url") if isinstance(p.get("featured_image"), dict) else p.get("featured_image")
        out.append({
            "retailer": NAME,
            "title": p.get("title"),
            "url": _abs_url(p.get("url")),
            "price": price,
            "rrp": rrp,
            "in_stock": bool(p.get("available")),
            "image_url": _abs_url(img),
        })
    return out
