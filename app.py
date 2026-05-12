import asyncio
import logging
import sys
import time
from pathlib import Path

from curl_cffi.requests import AsyncSession
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
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
    payload = {"query": q, "cached": False, "results": results, "errors": errors}
    _cache[key] = (now, payload)
    return JSONResponse(payload)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html")
