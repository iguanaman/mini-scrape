"""Gripping Beast — legacy custom CMS.

The category tree is deep: most top-level "ranges" are HUB pages that list
sub-categories rather than products. Leaf categories are the only ones with
`div.product-inner` cards. We tree-walk from a top-level cat, following
`a.pcl-category-each` sub-cat links until we hit leaves, accumulating products.

Pagination is not real here — every category, leaf or hub, fits on one page.
"""
import asyncio
import random
import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "grippingbeast"
NAME = "Gripping Beast"
ICON = "/static/icons/grippingbeast.ico"
BASE = "https://www.grippingbeast.co.uk"

RANGES = [
    {"slug": "plastics", "name": "Plastic Figures", "cat": 32, "group": "Plastics"},
    {"slug": "saga", "name": "SAGA", "cat": 10, "group": "Games"},
    {"slug": "swordpoint", "name": "SWORDPOINT", "cat": 376, "group": "Games"},
    {"slug": "jugula", "name": "JUGULA", "cat": 490, "group": "Games"},
    {"slug": "vikings", "name": "Viking Age", "cat": 24, "group": "Dark Ages"},
    {"slug": "byzantines", "name": "Byzantine / Rus / Slavs", "cat": 49, "group": "Dark Ages"},
    {"slug": "late-romans", "name": "Late Romans / Huns / Sassanids", "cat": 105, "group": "Dark Ages"},
    {"slug": "age-of-arthur", "name": "Age of Arthur", "cat": 63, "group": "Dark Ages"},
    {"slug": "front-rank", "name": "Front Rank Figurines", "cat": 600, "group": "Acquired Ranges"},
]

_SKU_TITLE_RE = re.compile(r"^([A-Z][A-Z0-9]{1,12})\s+(.+)$")
_PRICE_RE = re.compile(r"£\s*([\d,]+\.\d{2})")
_CAT_URL_RE = re.compile(r"^/[^/]+--category--(\d+)\.html$")
MAX_DEPTH = 4  # safety cap on tree descent


def _abs(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("http"):
        return u
    return BASE + ("/" if not u.startswith("/") else "") + u


def _parse_products(tree: HTMLParser) -> list[dict]:
    items: list[dict] = []
    for card in tree.css("div.product-inner"):
        a = card.css_first("a.pcl-product-each")
        if a is None:
            continue
        href = _abs(a.attributes.get("href"))
        classes = a.attributes.get("class") or ""
        in_stock = "pcl-product-each-out-of-stock" not in classes
        h3 = card.css_first("h3")
        raw_title = h3.text(strip=True) if h3 else ""
        sku, title = None, raw_title
        m = _SKU_TITLE_RE.match(raw_title)
        if m:
            sku, title = m.group(1), m.group(2)
        price = None
        price_el = card.css_first("p.pcl-product-each-price")
        if price_el:
            pm = _PRICE_RE.search(price_el.text())
            if pm:
                try:
                    price = float(pm.group(1).replace(",", ""))
                except ValueError:
                    price = None
        img = card.css_first("img.pcl-product-each-image")
        items.append({
            "title": title,
            "sku": sku,
            "url": href,
            "image_url": _abs(img.attributes.get("src")) if img else None,
            "price": price,
            "_in_stock": in_stock,
        })
    return items


def _sub_cat_ids(tree: HTMLParser) -> list[tuple[int, str]]:
    out: list[tuple[int, str]] = []
    for a in tree.css("a.pcl-category-each"):
        href = a.attributes.get("href") or ""
        m = _CAT_URL_RE.match(href)
        if m:
            out.append((int(m.group(1)), href))
    return out


async def _fetch_cat(client: AsyncSession, href: str) -> HTMLParser | None:
    url = _abs(href)
    r = await client.get(url, timeout=20)
    if r.status_code != 200:
        return None
    return HTMLParser(r.text)


async def _walk(client: AsyncSession, href: str, seen: set[int], depth: int) -> list[dict]:
    if depth > MAX_DEPTH:
        return []
    tree = await _fetch_cat(client, href)
    if tree is None:
        return []
    items = _parse_products(tree)
    if items:
        return items
    # No products → hub. Recurse into sub-categories in parallel.
    subs = _sub_cat_ids(tree)
    fresh = [(cid, h) for (cid, h) in subs if cid not in seen]
    for cid, _h in fresh:
        seen.add(cid)
    if not fresh:
        return []
    results = await asyncio.gather(
        *[_walk(client, h, seen, depth + 1) for _cid, h in fresh],
        return_exceptions=True,
    )
    out: list[dict] = []
    for r in results:
        if isinstance(r, list):
            out.extend(r)
    return out


def _parse_product_description(html: str) -> str | None:
    tree = HTMLParser(html)
    el = tree.css_first(".product-description")
    if not el:
        return None
    return el.text(strip=True) or None


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    cat = range_def["cat"]
    # Best-effort URL — server accepts any stem for a given cat id, redirecting
    # to canonical. Use the slug-equivalent if known, else a placeholder.
    href = f"/x--category--{cat}.html"
    seen = {cat}
    items = await _walk(client, href, seen, depth=0)
    # Dedupe by URL.
    seen_urls: set[str] = set()
    out: list[dict] = []
    for it in items:
        u = it.get("url")
        if not u or u in seen_urls:
            continue
        seen_urls.add(u)
        it.pop("_in_stock", None)
        out.append(it)
    # Fetch individual product pages for descriptions
    for item in out:
        if item.get("url"):
            await asyncio.sleep(random.uniform(1.0, 2.0))
            try:
                rp = await client.get(item["url"], timeout=20)
                item["description"] = _parse_product_description(rp.text)
            except Exception:
                item["description"] = None
    return out
