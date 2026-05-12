import asyncio
import logging
import re
import sys
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from retailers import IMPERSONATE
from retailers import goblin, wayland, firestorm, element

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(BASE_DIR / "server.txt", mode="a", encoding="utf-8"),
        logging.StreamHandler(sys.stdout),
    ],
    force=True,
)
log = logging.getLogger("mini-scrape")

app = FastAPI()
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


@app.exception_handler(Exception)
async def log_unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    raise exc


RETAILERS = [goblin, wayland, firestorm, element]
CACHE_TTL = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}


def _sort_key(r: dict):
    p = r.get("price")
    return (0, p) if isinstance(p, (int, float)) else (1, 0.0)


_SKU_RE = re.compile(r"\b([A-Z]{2,}[-\s]?\d{2,}[A-Z0-9-]*)\b")
_NORM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _query_tokens(q: str) -> list[str]:
    # Lowercase, split on non-alphanumeric, drop very short tokens.
    return [t for t in _TOKEN_RE.findall(q.lower()) if len(t) >= 2]


def _title_matches(title: str | None, tokens: list[str]) -> bool:
    if not title or not tokens:
        return bool(title)
    norm = title.lower()
    return all(t in norm for t in tokens)


_STOPWORDS = {"the", "a", "an", "of", "and", "for", "to", "in"}


def _group_key(item: dict) -> str:
    sku = (item.get("sku") or "").strip()
    if sku:
        return "sku:" + sku.upper().replace(" ", "").replace("-", "")
    title = (item.get("title") or "").strip()
    if not title:
        return ""
    m = _SKU_RE.search(title)
    if m:
        return "sku:" + m.group(1).upper().replace(" ", "").replace("-", "")
    tokens = [t for t in _TOKEN_RE.findall(title.lower()) if t not in _STOPWORDS]
    unique_sorted = sorted(set(tokens))
    return "tokens:" + " ".join(unique_sorted)


def _title_tokenset(title: str | None) -> frozenset[str]:
    if not title:
        return frozenset()
    return frozenset(
        t for t in _TOKEN_RE.findall(title.lower()) if t not in _STOPWORDS
    )


def _group_results(items: list[dict]) -> list[dict]:
    groups: dict[str, dict] = {}
    for it in items:
        key = _group_key(it)
        if not key:
            continue
        g = groups.get(key)
        if g is None:
            g = {
                "key": key,
                "title": it.get("title"),
                "image_url": it.get("image_url"),
                "title_tokens": _title_tokenset(it.get("title")),
                "offers": [],
            }
            groups[key] = g
        else:
            # Prefer a longer/cleaner title and an existing image
            if it.get("image_url") and not g.get("image_url"):
                g["image_url"] = it["image_url"]
            if it.get("title") and len(it["title"]) > len(g["title"] or ""):
                # keep shorter title; longer often has extra junk. Skip.
                pass
        g["offers"].append({
            "retailer": it.get("retailer"),
            "retailer_slug": it.get("retailer_slug"),
            "retailer_icon": it.get("retailer_icon"),
            "url": it.get("url"),
            "price": it.get("price"),
            "in_stock": it.get("in_stock", False),
        })

    # Second pass: merge groups with equivalent token-sets (handles cases where
    # some retailers gave us SKU and some didn't — same product, different keys).
    merged: list[dict] = []
    for g in groups.values():
        tokens = g["title_tokens"]
        target = None
        for m in merged:
            mt = m["title_tokens"]
            if not tokens or not mt:
                continue
            if tokens == mt or tokens.issubset(mt) or mt.issubset(tokens):
                target = m
                break
        if target is None:
            merged.append(g)
        else:
            target["offers"].extend(g["offers"])
            if g.get("image_url") and not target.get("image_url"):
                target["image_url"] = g["image_url"]
            # Keep the shorter title and the union of tokens
            if g.get("title") and (not target.get("title") or len(g["title"]) < len(target["title"])):
                target["title"] = g["title"]
            target["title_tokens"] = target["title_tokens"] | tokens

    groups = {g["key"]: g for g in merged}

    def _offer_sort(o: dict):
        p = o.get("price")
        # in-stock first, then by price asc; None price last
        in_stock_rank = 0 if o.get("in_stock") else 1
        if isinstance(p, (int, float)):
            return (in_stock_rank, 0, p)
        return (in_stock_rank, 1, 0.0)

    out: list[dict] = []
    for g in groups.values():
        g["offers"].sort(key=_offer_sort)
        # Cheapest = cheapest in-stock offer if any, else first
        in_stock_offers = [o for o in g["offers"] if o.get("in_stock") and isinstance(o.get("price"), (int, float))]
        cheapest = in_stock_offers[0] if in_stock_offers else (g["offers"][0] if g["offers"] else {})
        g["cheapest_price"] = cheapest.get("price")
        g["cheapest_url"] = cheapest.get("url")
        g["cheapest_retailer"] = cheapest.get("retailer")
        g["cheapest_retailer_icon"] = cheapest.get("retailer_icon")
        g["any_in_stock"] = bool(in_stock_offers)
        g.pop("title_tokens", None)
        out.append(g)

    def _group_sort(g: dict):
        # Groups with any in-stock offer first, then by cheapest price
        in_stock_rank = 0 if g.get("any_in_stock") else 1
        p = g.get("cheapest_price")
        if isinstance(p, (int, float)):
            return (in_stock_rank, 0, p)
        return (in_stock_rank, 1, 0.0)

    out.sort(key=_group_sort)
    return out


@app.get("/search")
async def search(q: str = Query(..., min_length=1)):
    key = q.strip().lower()
    now = time.time()
    hit = _cache.get(key)
    if hit and now - hit[0] < CACHE_TTL:
        payload = dict(hit[1])
        payload["cached"] = True
        return JSONResponse(payload)

    results: list[dict] = []
    errors: dict[str, str] = {}
    async with AsyncSession(
        impersonate=IMPERSONATE,
        timeout=15,
    ) as client:
        outcomes = await asyncio.gather(
            *(r.search(q, client) for r in RETAILERS),
            return_exceptions=True,
        )
    for module, outcome in zip(RETAILERS, outcomes):
        if isinstance(outcome, Exception):
            log.exception("Retailer %s failed", module.NAME, exc_info=outcome)
            errors[module.NAME] = f"{type(outcome).__name__}: {outcome}"
        else:
            results.extend(outcome)

    tokens = _query_tokens(q)
    results = [
        r for r in results
        if _title_matches(r.get("title"), tokens)
        and r.get("in_stock")
        and isinstance(r.get("price"), (int, float))
        and r["price"] >= 15
    ]
    results.sort(key=_sort_key)
    groups = _group_results(results)
    retailers_meta = [
        {"slug": m.SLUG, "name": m.NAME, "icon": m.ICON} for m in RETAILERS
    ]
    payload = {
        "query": q,
        "cached": False,
        "results": results,
        "groups": groups,
        "retailers": retailers_meta,
        "errors": errors,
    }
    _cache[key] = (now, payload)
    return JSONResponse(payload)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
