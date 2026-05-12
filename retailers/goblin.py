import json
import re

from curl_cffi.requests import AsyncSession

SLUG = "goblin"
NAME = "Goblin Gaming"
ICON = "/static/icons/goblin.webp"
BASE = "https://www.goblingaming.co.uk"
SEARCH_URL = BASE + "/search"

_LDJSON_RE = re.compile(
    r'<script type="application/ld\+json">(.*?)</script>', re.S
)


def _to_float(v):
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
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


def _strip_query(u: str | None) -> str | None:
    if not u:
        return None
    return u.split("?", 1)[0]


async def search(query: str, client: AsyncSession) -> list[dict]:
    r = await client.get(SEARCH_URL, params={"q": query}, timeout=15)
    r.raise_for_status()
    out: list[dict] = []
    for block in _LDJSON_RE.findall(r.text):
        try:
            data = json.loads(block)
        except json.JSONDecodeError:
            continue
        if not isinstance(data, dict) or data.get("@type") != "Product":
            continue
        offers = data.get("offers") or {}
        if isinstance(offers, list):
            offers = offers[0] if offers else {}
        availability = (offers.get("availability") or "").lower()
        in_stock = "instock" in availability  # "http://schema.org/InStock"

        price = _to_float(offers.get("price"))
        url = _abs_url(_strip_query(data.get("url") or offers.get("url")))
        image = data.get("image")
        if isinstance(image, list):
            image = image[0] if image else None
        out.append({
            "retailer": NAME,
            "retailer_slug": SLUG,
            "retailer_icon": ICON,
            "title": data.get("name"),
            "url": url,
            "price": price,
            "rrp": None,
            "in_stock": in_stock,
            "image_url": _abs_url(image),
            "sku": data.get("sku"),
        })
        if len(out) >= 10:
            break
    return out
