import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "nemc"
NAME = "North East Model Centre"
ICON = "/static/icons/nemc.jpg"
BASE = "https://northeastmodelcentre.co.uk"
SEARCH_URL = BASE + "/"

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


async def search(query: str, client: AsyncSession) -> list[dict]:
    r = await client.get(SEARCH_URL, params={"s": query}, timeout=15)
    r.raise_for_status()
    tree = HTMLParser(r.text)
    cards = tree.css(".ps-card-search")

    out: list[dict] = []
    for card in cards[:40]:
        name_el = card.css_first(".ps-name")
        title = name_el.text(strip=True) if name_el else None

        link_el = card.css_first("a[href*='/product/']")
        url = link_el.attributes.get("href") if link_el else None
        if url:
            url = url.split("?", 1)[0]

        img_el = card.css_first("img.ps-img")
        image_url = img_el.attributes.get("src") if img_el else None

        active_el = card.css_first(".ps-active-price")
        price = _parse_price(active_el.text()) if active_el else None
        rrp = None
        if active_el is not None:
            # When on sale, original price is in a sibling .ps-price with line-through
            strike_el = card.css_first(".ps-price")
            if strike_el is not None:
                rrp = _parse_price(strike_el.text())
        else:
            # Not on sale: only .ps-price exists
            plain_el = card.css_first(".ps-price")
            price = _parse_price(plain_el.text()) if plain_el else None

        if rrp is not None and price is not None and rrp <= price:
            rrp = None

        # Stock — explicit "In stock" / "Out of stock" markers
        stock_el = card.css_first(".in-stock, .out-of-stock")
        in_stock = stock_el is not None and "in-stock" in (stock_el.attributes.get("class") or "")

        # SKU — "Part no:" line
        sku = None
        for el in card.css(".ps-brand"):
            txt = el.text()
            if "Part no" in txt:
                span = el.css_first("span")
                if span is not None:
                    sku = span.text(strip=True) or None
                break

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
            "sku": sku,
        })
    return out
