import asyncio
import random
import re

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "northstar"
NAME = "North Star Figures"
ICON = "/static/icons/northstar.ico"
BASE = "https://www.northstarfigures.com"

RANGES = [
    {"slug": "frostgrave", "name": "Frostgrave", "man_id": 195},
    {"slug": "ghost-archipelago", "name": "Frostgrave: Ghost Archipelago", "man_id": 254},
    {"slug": "stargrave", "name": "Stargrave", "man_id": 295},
    {"slug": "oathmark", "name": "Oathmark", "man_id": 257},
]

_PAGES_RE = re.compile(r"page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)
_PRICE_RE = re.compile(r"£\s*([\d,]+\.\d{2})")
_ALT_RE = re.compile(r"^Photo of (.+?)\s*\(([^)]+)\)\s*$")


def _abs(u: str | None) -> str | None:
    if not u:
        return None
    if u.startswith("http"):
        return u
    return BASE + ("/" if not u.startswith("/") else "") + u


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


def _parse_page(html: str) -> tuple[list[dict], int]:
    tree = HTMLParser(html)
    total_pages = 1
    for h in tree.css("h2"):
        m = _PAGES_RE.search(h.text())
        if m:
            total_pages = int(m.group(1))
            break

    items: list[dict] = []
    for p in tree.css("p.prodpara"):
        img = p.css_first("img")
        if img is None:
            continue
        alt = img.attributes.get("alt") or ""
        m = _ALT_RE.match(alt)
        if m:
            title = m.group(1).strip()
            sku = m.group(2).strip()
        else:
            title, sku = alt, None
        a = p.css_first("a[href]")
        url = _abs(a.attributes.get("href")) if a else None
        src = img.attributes.get("src") or ""
        # Listing uses imgthN.jpg thumbnails (100x100). Full-size is imgN.jpg.
        src = src.replace("imgth", "img")
        image_url = _abs(src)
        price = _parse_price(p.text())
        items.append({
            "title": title,
            "sku": sku,
            "url": url,
            "image_url": image_url,
            "price": price,
        })
    return items, total_pages


def _parse_product_description(html: str) -> str | None:
    tree = HTMLParser(html)
    # Description lives in classless <p> tags — collect all with >20 chars of text.
    paras = []
    for p in tree.css("p"):
        if p.attributes.get("class"):
            continue
        txt = re.sub(r"\s+", " ", p.text(separator=" ")).strip()
        if len(txt) > 20:
            paras.append(txt)
    return "\n\n".join(paras) or None


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    import sys
    import db as _db
    man_id = range_def["man_id"]
    url = f"{BASE}/list.php"
    out: list[dict] = []
    page = 1
    sys.stdout.write("walking pages: ")
    sys.stdout.flush()
    while True:
        r = await client.get(url, params={"man": man_id, "page": page}, timeout=15)
        r.raise_for_status()
        items, total_pages = _parse_page(r.text)
        out.extend(items)
        sys.stdout.write(".")
        sys.stdout.flush()
        if page >= total_pages:
            break
        page += 1
    sys.stdout.write(f" {page} pages, {len(out)} products\n")
    sys.stdout.flush()
    # Fetch individual product pages for descriptions — skip ones already in DB.
    have_desc = _db.skus_with_description([it.get("sku") for it in out if it.get("sku")])
    to_fetch = [it for it in out if it.get("url") and it.get("sku") not in have_desc]
    sys.stdout.write(f"fetching {len(to_fetch)} product pages ({len(have_desc)} cached): ")
    sys.stdout.flush()
    for item in to_fetch:
        try:
            rp = await client.get(item["url"], timeout=15)
            item["description"] = _parse_product_description(rp.text)
        except Exception:
            item["description"] = None
        sys.stdout.write(".")
        sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()
    return out
