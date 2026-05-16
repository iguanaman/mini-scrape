import asyncio
import random
import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "perry"
NAME = "Perry Miniatures"
ICON = "/static/icons/perry.png"
BASE = "https://www.perry-miniatures.com"

RANGES = [
    {"slug": "plastic-box-sets", "name": "Plastic Box Sets", "path": "plastic-ranges/box-sets", "group": "Plastic"},
    {"slug": "wars-of-roses", "name": "Wars of the Roses", "path": "metal-ranges/war-of-the-roses", "group": "Medieval"},
    {"slug": "crusades", "name": "Crusades", "path": "metal-ranges/crusades", "group": "Medieval"},
    {"slug": "napoleonic-french", "name": "Napoleonic French", "path": "metal-ranges/napoleonic/french", "group": "Napoleonic"},
    {"slug": "napoleonic-british", "name": "Napoleonic British", "path": "metal-ranges/napoleonic/british", "group": "Napoleonic"},
    {"slug": "acw", "name": "American Civil War", "path": "metal-ranges/american-civil-war", "group": "19th Century"},
    {"slug": "awi", "name": "American War of Independence", "path": "metal-ranges/american-war-of-independence", "group": "18th Century"},
    {"slug": "ecw", "name": "English Civil War", "path": "metal-ranges/english-civil-war", "group": "17th Century"},
    {"slug": "sudan", "name": "Sudan", "path": "metal-ranges/sudan", "group": "19th Century"},
    {"slug": "franco-prussian", "name": "Franco-Prussian War", "path": "metal-ranges/franco-prussian-war-1870-71", "group": "19th Century"},
    {"slug": "ww2", "name": "World War 2", "path": "metal-ranges/world-war-2", "group": "20th Century"},
]

_PRICE_RE = re.compile(r"([\d,]+\.\d{2})")
_SKU_TITLE_RE = re.compile(r"^([A-Z]{1,5})\s*(\d{1,4}[A-Z0-9]*)\b\s*(.+)$")
MAX_PAGES = 20


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


def _img_src(card) -> str | None:
    for img in card.css("img"):
        for attr in ("data-src", "src"):
            v = img.attributes.get(attr)
            if v and "data:image" not in v:
                return v
    return None


def _parse_page(html: str) -> tuple[list[dict], bool]:
    tree = HTMLParser(html)
    items: list[dict] = []
    cards = tree.css("li.product.type-product")
    for c in cards:
        title_el = c.css_first(".woocommerce-loop-product__title")
        title = title_el.text(strip=True) if title_el else None
        sku = None
        if title:
            m = _SKU_TITLE_RE.match(title)
            if m:
                sku = m.group(1) + m.group(2)
        url = None
        for a in c.css("a[href]"):
            href = a.attributes.get("href", "")
            if "/product/" in href and "category" not in href:
                url = href
                break
        price = _parse_price((c.css_first(".price").text() if c.css_first(".price") else None))
        items.append({
            "title": title,
            "sku": sku,
            "url": url,
            "image_url": _img_src(c),
            "price": price,
        })
    # has_next: any .page-numbers link whose href ends with /page/N/ for N > current?
    # Simpler: detect `.next.page-numbers` link.
    has_next = tree.css_first("a.next.page-numbers") is not None
    return items, has_next


def _parse_product_description(html: str) -> str | None:
    tree = HTMLParser(html)
    el = tree.css_first("#tab-description")
    if not el:
        return None
    txt = re.sub(r"\s+", " ", el.text(separator=" ")).strip()
    return txt or None


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    import sys
    import db as _db
    path = range_def["path"]
    out: list[dict] = []
    page = 1
    sys.stdout.write("walking pages: ")
    sys.stdout.flush()
    while page <= MAX_PAGES:
        suffix = "" if page == 1 else f"page/{page}/"
        url = f"{BASE}/product-category/{path}/{suffix}"
        r = await client.get(url, timeout=20)
        if r.status_code == 404:
            break
        r.raise_for_status()
        items, has_next = _parse_page(r.text)
        if not items:
            break
        out.extend(items)
        sys.stdout.write(".")
        sys.stdout.flush()
        if not has_next:
            break
        page += 1
    sys.stdout.write(f" {page} pages, {len(out)} products\n")
    sys.stdout.flush()
    # Fetch individual product pages for descriptions — skip ones already in DB.
    have_desc = _db.skus_with_description([it.get("sku") for it in out if it.get("sku")])
    to_fetch = [it for it in out if it.get("url") and it.get("sku") not in have_desc and (it.get("price") or 0) >= 20]
    sys.stdout.write(f"fetching {len(to_fetch)} product pages ({len(have_desc)} cached): ")
    sys.stdout.flush()
    for item in to_fetch:
        try:
            rp = await client.get(item["url"], timeout=20)
            item["description"] = _parse_product_description(rp.text)
        except Exception:
            item["description"] = None
        sys.stdout.write(".")
        sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()
    return out
