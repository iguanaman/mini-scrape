import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "element"
NAME = "Element Games"
ICON = "/static/icons/element.ico"
BASE = "https://elementgames.co.uk"
SEARCH_URL = BASE + "/search"

_PRICE_RE = re.compile(r"£\s*([\d,]+\.\d{2})")


def _parse_price(text: str | None) -> float | None:
    if not text:
        return None
    m = _PRICE_RE.search(text)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def _abs(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("http"):
        return u
    return BASE + (u if u.startswith("/") else "/" + u)


async def search(query: str, client: AsyncSession) -> list[dict]:
    r = await client.get(SEARCH_URL, params={"q": query}, timeout=15)
    r.raise_for_status()
    tree = HTMLParser(r.text)

    out: list[dict] = []
    for card in tree.css(".productgrid")[:10]:
        title_el = card.css_first("h3.producttitle")
        title = title_el.text(strip=True) if title_el else None

        a = card.css_first("a[href]")
        url = _abs(a.attributes.get("href")) if a else None

        img_el = card.css_first("img.productimage")
        image_url = _abs(img_el.attributes.get("src")) if img_el else None

        price_el = card.css_first(".price")
        price = _parse_price(price_el.text()) if price_el else None
        old_el = card.css_first(".oldprice")
        rrp = _parse_price(old_el.text()) if old_el else None
        if rrp is not None and price is not None and rrp <= price:
            rrp = None

        # The stock-status indicator lives outside the .stock_popup legend
        # (the popup includes all four button colours as a key).
        in_stock = False
        for popup in card.css(".stock_popup"):
            popup.decompose()
        status_text = card.text(separator=" ", strip=True)
        if re.search(r"\b(?:in stock|dispatch)\b", status_text, re.I) and \
                not re.search(r"\b(?:out of stock|unavailable)\b", status_text, re.I):
            in_stock = True

        out.append({
            "retailer": NAME,
            "retailer_slug": SLUG,
            "retailer_icon": ICON,
            "title": title,
            "url": url,
            "price": price,
            "rrp": rrp,
            "in_stock": in_stock,
            "image_url": image_url,
        })
    return out
