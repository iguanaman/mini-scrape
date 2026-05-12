import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "firestorm"
NAME = "Firestorm Games"
ICON = "/static/icons/firestorm.png"
BASE = "https://www.firestormgames.co.uk"
SEARCH_URL = BASE + "/products"

_PRICE_RE = re.compile(r"£\s*([\d,]+\.\d{2})")
_BG_URL_RE = re.compile(r"url\(['\"]?([^'\")]+)")


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
    for item in tree.css(".product-list .item .item-inner")[:10]:
        a = item.css_first("a[href]")
        url = _abs(a.attributes.get("href")) if a else None

        title_el = item.css_first(".bottom-section .title")
        title = title_el.text(strip=True) if title_el else None

        price_block = item.css_first(".price")
        price = rrp = None
        if price_block is not None:
            classes = (price_block.attributes.get("class") or "")
            small_el = price_block.css_first(".small")
            if "special" in classes and small_el is not None:
                rrp = _parse_price(small_el.text())
                # Final price is the non-.small text in the same wrapper
                full = price_block.text(strip=True)
                small_txt = small_el.text(strip=True)
                rest = full.replace(small_txt, "", 1)
                price = _parse_price(rest)
            else:
                price = _parse_price(price_block.text())

        # Fallback to data-price on add-to-basket button if main price missing
        if price is None:
            btn = item.css_first("a.add-to-basket-list[data-price]")
            if btn is not None:
                try:
                    price = float(btn.attributes.get("data-price"))
                except (TypeError, ValueError):
                    pass

        if rrp is not None and price is not None and rrp <= price:
            rrp = None

        stock_el = item.css_first(".banner")
        stock_text = stock_el.text(strip=True).lower() if stock_el else ""
        in_stock = (
            ("stock" in stock_text or "dispatch" in stock_text)
            and "out of stock" not in stock_text
        )

        # Image is a CSS background-image on a span inside .image
        image_url = None
        bg_span = item.css_first(".image span[style]")
        if bg_span is not None:
            m = _BG_URL_RE.search(bg_span.attributes.get("style") or "")
            if m:
                image_url = _abs(m.group(1))

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
