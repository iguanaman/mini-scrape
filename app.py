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


def _group_key(item: dict) -> str:
    title = (item.get("title") or "").strip()
    if not title:
        return ""
    m = _SKU_RE.search(title)
    if m:
        return "sku:" + m.group(1).upper().replace(" ", "").replace("-", "")
    norm = _NORM_RE.sub(" ", title.lower()).strip()
    norm = re.sub(r"\s+", " ", norm)
    return "title:" + norm


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
        })

    out: list[dict] = []
    for g in groups.values():
        g["offers"].sort(key=lambda o: (0, o["price"]) if isinstance(o.get("price"), (int, float)) else (1, 0.0))
        cheapest = g["offers"][0] if g["offers"] else {}
        g["cheapest_price"] = cheapest.get("price")
        g["cheapest_url"] = cheapest.get("url")
        g["cheapest_retailer"] = cheapest.get("retailer")
        g["cheapest_retailer_icon"] = cheapest.get("retailer_icon")
        out.append(g)
    out.sort(key=lambda g: (0, g["cheapest_price"]) if isinstance(g.get("cheapest_price"), (int, float)) else (1, 0.0))
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

    results = [r for r in results if r.get("in_stock")]
    results.sort(key=_sort_key)
    groups = _group_results(results)
    payload = {"query": q, "cached": False, "results": results, "groups": groups, "errors": errors}
    _cache[key] = (now, payload)
    return JSONResponse(payload)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
