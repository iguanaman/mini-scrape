import logging
import sys
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.requests import Request

from manufacturers import MANUFACTURERS
import db

BASE_DIR = Path(__file__).resolve().parent

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
    force=True,
)
log = logging.getLogger("mini-market")

app = FastAPI()
INDEX = str(BASE_DIR / "index.html")
db.init()


class OwnedBody(BaseModel):
    count: int = Field(ge=0)


class MinisBody(BaseModel):
    count: int = Field(ge=0)


@app.exception_handler(Exception)
async def log_unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    raise exc


RETAILERS = [
    {"slug": "goblin",    "name": "Goblin Gaming",          "icon": "/static/icons/goblin.webp"},
    {"slug": "wayland",   "name": "Wayland Games",          "icon": "/static/icons/wayland.png"},
    {"slug": "firestorm", "name": "Firestorm Games",        "icon": "/static/icons/firestorm.png"},
    {"slug": "element",   "name": "Element Games",          "icon": "/static/icons/element.ico"},
    {"slug": "overlord",  "name": "Overlord Games",         "icon": "/static/icons/overlord.png"},
    {"slug": "nemc",      "name": "North East Model Centre","icon": "/static/icons/nemc.jpg"},
]

def _norm_sku(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().upper().replace(" ", "").replace("-", "")


def _build_home_data() -> dict:
    hidden_ranges = db.get_hidden_ranges()
    mfrs = db.manufacturers_with_ranges()
    for m in mfrs:
        for r in m["ranges"]:
            r["hidden"] = (m["slug"], r["slug"]) in hidden_ranges
    hidden_skus = set(db.hidden_skus())
    owned = db.owned_counts()
    manufacturers_meta = {
        m.SLUG: {"slug": m.SLUG, "name": m.NAME, "icon": m.ICON} for m in MANUFACTURERS
    }
    for m in mfrs:
        products_by_range = {}
        for r in m["ranges"]:
            products = db.products_for_range(m["slug"], r["slug"])
            if hidden_skus:
                products = [p for p in products if _norm_sku(p.get("sku")) not in hidden_skus]
            for p in products:
                p["owned"] = owned.get(db.norm_sku(p.get("sku") or ""), 0)
            products_by_range[r["slug"]] = products
        m["products_by_range"] = products_by_range
    wishlist_items = db.wishlist_products()
    for p in wishlist_items:
        p["owned"] = owned.get(db.norm_sku(p.get("sku") or ""), p.get("owned", 0))
    owned_items = db.owned_products()
    return {
        "manufacturers": mfrs,
        "manufacturers_meta": manufacturers_meta,
        "retailers": RETAILERS,
        "wishlist_skus": [p["sku"] for p in wishlist_items if p.get("sku")],
        "loved_skus": [p["sku"] for p in wishlist_items if p.get("sku") and p.get("loved")],
        "wishlist_items": wishlist_items,
        "owned_items": owned_items,
    }


@app.get("/api/ping")
async def ping():
    return JSONResponse({"ok": True})


@app.get("/static/data.json")
async def live_data():
    return JSONResponse(_build_home_data())


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.post("/api/wishlist/{sku}")
async def wishlist_add(sku: str):
    db.add_wishlist(sku)
    return JSONResponse({"ok": True})


@app.delete("/api/wishlist/{sku}")
async def wishlist_delete(sku: str):
    db.remove_wishlist(sku)
    return JSONResponse({"ok": True})


@app.post("/api/loved/{sku}")
async def loved_add(sku: str):
    db.set_loved(sku, True)
    return JSONResponse({"ok": True})


@app.delete("/api/loved/{sku}")
async def loved_delete(sku: str):
    db.set_loved(sku, False)
    return JSONResponse({"ok": True})


@app.post("/api/hide/{sku}")
async def api_hide(sku: str):
    db.hide_product(sku)
    return JSONResponse({"ok": True})


@app.delete("/api/hide/{sku}")
async def api_unhide(sku: str):
    db.unhide_product(sku)
    return JSONResponse({"ok": True})


@app.post("/api/hide-range/{man_slug}/{range_slug}")
async def api_hide_range(man_slug: str, range_slug: str):
    db.hide_range(man_slug, range_slug)
    return JSONResponse({"ok": True})


@app.delete("/api/hide-range/{man_slug}/{range_slug}")
async def api_unhide_range(man_slug: str, range_slug: str):
    db.unhide_range(man_slug, range_slug)
    return JSONResponse({"ok": True})


@app.delete("/api/group/{man_slug}/{group_name}")
async def api_delete_group(man_slug: str, group_name: str):
    db.delete_group(man_slug, group_name)
    return JSONResponse({"ok": True})


@app.delete("/api/range/{man_slug}/{range_slug}")
async def api_delete_range(man_slug: str, range_slug: str):
    db.delete_range(man_slug, range_slug)
    return JSONResponse({"ok": True})


@app.post("/api/owned/{sku}")
async def api_set_owned(sku: str, body: OwnedBody):
    saved = db.set_owned(sku, body.count)
    return JSONResponse({"sku": db.norm_sku(sku), "owned": saved})


@app.post("/api/minis/{sku}")
async def api_set_minis(sku: str, body: MinisBody):
    saved = db.set_minis_count(sku, body.count)
    return JSONResponse({"sku": db.norm_sku(sku), "minis": saved})


@app.get("/owned")
async def owned_page():
    return FileResponse(INDEX)


@app.get("/wishlist")
async def wishlist_page():
    return FileResponse(INDEX)


@app.get("/")
async def index():
    return FileResponse(INDEX)
