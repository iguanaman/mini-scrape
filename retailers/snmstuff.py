import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "snmstuff"
NAME = "SnM Stuff"
ICON = "/static/icons/snmstuff.ico"
BASE = "https://www.snmstuff.co.uk"

_PRICE_RE = re.compile(r"[\d,]+\.?\d*")


def _to_float(text: str) -> float | None:
    text = text.replace("£", "").replace(",", "").strip()
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        f = float(m.group())
    except ValueError:
        return None
    return f if f > 0 else None


async def search(query: str, client: AsyncSession) -> list[dict]:
    url = f"{BASE}/search/for/{query}/"
    r = await client.get(url, timeout=15)
    r.raise_for_status()

    # No match — stayed on search results page
    if "no results were found" in r.text:
        return []

    tree = HTMLParser(r.text)

    price_node = tree.css_first(".selling_price b")
    price = _to_float(price_node.text()) if price_node else None

    sku_node = tree.css_first("#part_number")
    sku = sku_node.text(strip=True) if sku_node else None

    title_node = tree.css_first("h1")
    title = title_node.text(strip=True) if title_node else None

    # In stock: button exists and is not disabled
    basket_node = tree.css_first(".b_basket")
    in_stock = basket_node is not None and "disabled" not in (basket_node.attributes.get("class") or "")

    image_node = tree.css_first("#image img")
    image_url = BASE + image_node.attributes["src"] if image_node else None

    return [{
        "retailer": NAME,
        "retailer_slug": SLUG,
        "retailer_icon": ICON,
        "title": title,
        "url": str(r.url),
        "price": price,
        "rrp": None,
        "in_stock": in_stock,
        "image_url": image_url,
        "sku": sku,
    }]
