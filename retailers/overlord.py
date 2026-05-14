from curl_cffi.requests import AsyncSession

SLUG = "overlord"
NAME = "Overlord Games"
ICON = "/static/icons/overlord.png"
BASE = "https://overlordgames.co.uk"
SEARCH_URL = BASE + "/search/suggest.json"


def _to_float(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _abs(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("http"):
        return u
    if u.startswith("//"):
        return "https:" + u
    return BASE + (u if u.startswith("/") else "/" + u)


async def search(query: str, client: AsyncSession) -> list[dict]:
    params = {
        "q": query,
        "resources[type]": "product",
        "resources[limit]": "40",
    }
    r = await client.get(SEARCH_URL, params=params, timeout=15)
    r.raise_for_status()
    data = r.json()
    products = (data.get("resources", {}).get("results", {}).get("products") or [])

    out: list[dict] = []
    for p in products[:40]:
        price = _to_float(p.get("price") or p.get("price_min"))
        rrp = _to_float(p.get("compare_at_price_max"))
        if rrp is not None and price is not None and rrp <= price:
            rrp = None
        url = _abs((p.get("url") or "").split("?", 1)[0])
        out.append({
            "retailer": NAME,
            "retailer_slug": SLUG,
            "retailer_icon": ICON,
            "title": p.get("title"),
            "url": url,
            "price": price,
            "rrp": rrp,
            "in_stock": bool(p.get("available")),
            "image_url": _abs(p.get("image")),
            "sku": None,
        })
    return out
