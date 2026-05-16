import re
import sys

from curl_cffi.requests import AsyncSession
from selectolax.parser import HTMLParser

SLUG = "crusader"
NAME = "Crusader Miniatures"
ICON = "/static/icons/crusader.ico"
BASE = "https://www.crusaderminiatures.com"

# range_def keys: slug, name, group, cat, and optionally sub
RANGES = [
    # Ancients
    {"slug": "ancient-celts", "name": "Ancient Celts", "cat": 1, "sub": 59, "group": "Ancients"},
    {"slug": "ancient-romans", "name": "Romans", "cat": 1, "sub": 2, "group": "Ancients"},
    {"slug": "roman-empire", "name": "Roman Empire", "cat": 1, "sub": 52, "group": "Ancients"},
    {"slug": "ancient-greeks", "name": "Ancient Greeks", "cat": 1, "sub": 53, "group": "Ancients"},
    {"slug": "carthaginians", "name": "Carthaginians", "cat": 1, "sub": 1, "group": "Ancients"},
    {"slug": "ancient-spanish", "name": "Spanish", "cat": 1, "sub": 3, "group": "Ancients"},
    {"slug": "ancient-germans", "name": "Ancient Germans", "cat": 1, "sub": 46, "group": "Ancients"},
    {"slug": "numidians", "name": "Numidians", "cat": 1, "sub": 30, "group": "Ancients"},
    {"slug": "persians", "name": "Persians", "cat": 1, "sub": 54, "group": "Ancients"},
    {"slug": "ancient-macedonia", "name": "Ancient Macedonia", "cat": 1, "sub": 61, "group": "Ancients"},
    # Dark Ages
    {"slug": "vikings", "name": "Vikings", "cat": 4, "sub": 14, "group": "Dark Ages"},
    {"slug": "saxons", "name": "Saxons", "cat": 4, "sub": 13, "group": "Dark Ages"},
    {"slug": "normans", "name": "Normans", "cat": 4, "sub": 12, "group": "Dark Ages"},
    {"slug": "byzantine", "name": "Byzantine", "cat": 4, "sub": 9, "group": "Dark Ages"},
    {"slug": "el-cid", "name": "El Cid", "cat": 4, "sub": 10, "group": "Dark Ages"},
    {"slug": "irish", "name": "Irish", "cat": 4, "sub": 11, "group": "Dark Ages"},
    {"slug": "scots", "name": "Scots", "cat": 4, "sub": 48, "group": "Dark Ages"},
    {"slug": "early-franks-saxons", "name": "Early Franks & Saxons", "cat": 4, "sub": 63, "group": "Dark Ages"},
    # Medieval
    {"slug": "hundred-years-war", "name": "Hundred Years War", "cat": 5, "sub": 15, "group": "Medieval"},
    {"slug": "wars-of-the-roses", "name": "Wars of the Roses", "cat": 5, "sub": 16, "group": "Medieval"},
    {"slug": "teutonic-knights", "name": "Teutonic Knights", "cat": 5, "sub": 60, "group": "Medieval"},
    {"slug": "later-crusaders", "name": "Later Crusaders", "cat": 5, "sub": 56, "group": "Medieval"},
    # Seven Years War
    {"slug": "syw-british", "name": "British", "cat": 7, "sub": 22, "group": "Seven Years War"},
    {"slug": "syw-prussians", "name": "Prussians", "cat": 7, "sub": 19, "group": "Seven Years War"},
    {"slug": "syw-austrians", "name": "Austrians", "cat": 7, "sub": 18, "group": "Seven Years War"},
    {"slug": "syw-french", "name": "French", "cat": 7, "sub": 50, "group": "Seven Years War"},
    {"slug": "syw-russian", "name": "Russian", "cat": 7, "sub": 51, "group": "Seven Years War"},
    {"slug": "woodland-indians", "name": "Woodland Indians", "cat": 7, "sub": 58, "group": "Seven Years War"},
    # Napoleonics
    {"slug": "napoleonic-french", "name": "French", "cat": 16, "sub": 23, "group": "Napoleonics"},
    # ACW
    {"slug": "acw", "name": "American Civil War", "cat": 13, "sub": 39, "group": "American Civil War"},
    # Boxer Rebellion
    {"slug": "boxers", "name": "Boxers", "cat": 19, "sub": 77, "group": "Boxer Rebellion"},
    {"slug": "imperial-chinese", "name": "Imperial Chinese", "cat": 19, "sub": 79, "group": "Boxer Rebellion"},
    {"slug": "boxer-japan", "name": "Japan", "cat": 19, "sub": 78, "group": "Boxer Rebellion"},
    {"slug": "boxer-russians", "name": "Russians", "cat": 19, "sub": 25, "group": "Boxer Rebellion"},
    # WWII
    {"slug": "ww2-british", "name": "British", "cat": 9, "sub": 22, "group": "World War II"},
    {"slug": "ww2-german", "name": "German", "cat": 9, "sub": 24, "group": "World War II"},
    {"slug": "ww2-russian", "name": "Russian", "cat": 9, "sub": 25, "group": "World War II"},
    {"slug": "ww2-us", "name": "United States", "cat": 9, "sub": 26, "group": "World War II"},
    {"slug": "ww2-french", "name": "French", "cat": 9, "sub": 23, "group": "World War II"},
    {"slug": "ww2-polish", "name": "Polish", "cat": 9, "sub": 64, "group": "World War II"},
    {"slug": "ww2-romanians", "name": "Romanians", "cat": 9, "sub": 69, "group": "World War II"},
    {"slug": "ww2-partisans", "name": "Partisans", "cat": 9, "sub": 66, "group": "World War II"},
]

_PAGES_RE = re.compile(r"page\s+\d+\s+of\s+(\d+)", re.IGNORECASE)
_PRICE_RE = re.compile(r"£\s*([\d,]+\.\d{2})")
_ALT_RE = re.compile(r"^Photo of (.+?)\s*\(([^)]+)\)\s*$")
_SKIP_RE = re.compile(r"^(©|Site by|Trade Logon|Our Price)", re.IGNORECASE)


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
        src = (img.attributes.get("src") or "").replace("imgth", "img")
        image_url = _abs(src)
        price = _parse_price(p.text())
        items.append({"title": title, "sku": sku, "url": url, "image_url": image_url, "price": price})
    return items, total_pages


def _parse_description(html: str) -> str | None:
    tree = HTMLParser(html)
    paras = []
    for p in tree.css("p"):
        if p.attributes.get("class"):
            continue
        txt = re.sub(r"\s+", " ", p.text(separator=" ")).strip()
        if len(txt) <= 20 or _SKIP_RE.match(txt):
            continue
        paras.append(txt)
    return "\n\n".join(paras) or None


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    import db as _db
    params: dict = {"cat": range_def["cat"]}
    if "sub" in range_def:
        params["sub"] = range_def["sub"]
    out: list[dict] = []
    page = 1
    sys.stdout.write("walking pages: ")
    sys.stdout.flush()
    while True:
        r = await client.get(f"{BASE}/list.php", params={**params, "page": page}, timeout=15)
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
    have_desc = _db.skus_with_description([it.get("sku") for it in out if it.get("sku")])
    to_fetch = [it for it in out if it.get("url") and it.get("sku") not in have_desc and (it.get("price") or 0) >= 20]
    sys.stdout.write(f"fetching {len(to_fetch)} product pages ({len(have_desc)} cached): ")
    sys.stdout.flush()
    for item in to_fetch:
        try:
            rp = await client.get(item["url"], timeout=15)
            item["description"] = _parse_description(rp.text)
        except Exception:
            item["description"] = None
        sys.stdout.write(".")
        sys.stdout.flush()
    sys.stdout.write("\n")
    sys.stdout.flush()
    return out
