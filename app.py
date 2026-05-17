import asyncio
import logging
import re
import sys
import time
import unicodedata
from pathlib import Path

from curl_cffi.requests import AsyncSession
from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.requests import Request

from retailers import IMPERSONATE
from retailers import goblin, wayland, firestorm, element, overlord, nemc
from retailers.wayland import WaylandBlockedError
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
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))
db.init()


class OwnedBody(BaseModel):
    count: int = Field(ge=0)


class MinisBody(BaseModel):
    count: int = Field(ge=0)


@app.exception_handler(Exception)
async def log_unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error on %s %s", request.method, request.url.path)
    raise exc


RETAILERS = [goblin, wayland, firestorm, element, overlord, nemc]
CACHE_TTL = 15 * 60
_cache: dict[str, tuple[float, dict]] = {}


def _sort_key(r: dict):
    p = r.get("price")
    return (0, p) if isinstance(p, (int, float)) else (1, 0.0)


_SKU_RE = re.compile(r"\b([A-Z]{2,}[-\s]?\d{2,}[A-Z0-9-]*)\b")
_NORM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _norm_sku(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().upper().replace(" ", "").replace("-", "")


def _fold(s: str) -> str:
    # Lowercase + strip diacritics so "Raumjäger" == "raumjager".
    return "".join(
        c for c in unicodedata.normalize("NFKD", s.lower())
        if not unicodedata.combining(c)
    )


def _query_tokens(q: str) -> list[str]:
    # Lowercase, split on non-alphanumeric, drop very short tokens.
    return [t for t in _TOKEN_RE.findall(_fold(q)) if len(t) >= 2]


def _title_matches(title: str | None, tokens: list[str]) -> bool:
    if not title or not tokens:
        return bool(title)
    norm = _fold(title)
    return all(t in norm for t in tokens)


def _is_sku_query(q: str) -> bool:
    # SKU-ish: single alphanumeric token that's either alphanumeric mixed,
    # or a long all-digit code (e.g. GW's 11-digit product codes like 60010199058).
    s = q.strip()
    if " " in s or len(s) < 4:
        return False
    has_alpha = any(c.isalpha() for c in s)
    has_digit = any(c.isdigit() for c in s)
    if has_alpha and has_digit:
        return True
    if not has_alpha and has_digit and len(s) >= 6:
        return True
    return False


def _matches(item: dict, q: str, tokens: list[str]) -> bool:
    # If query looks like a SKU, trust the retailer's search results.
    # Retailers that index SKU (all four do, at least for site search) will
    # only return relevant products; the title rarely contains the SKU literally.
    if _is_sku_query(q):
        return True
    return _title_matches(item.get("title"), tokens)


_STOPWORDS = {"the", "a", "an", "of", "and", "for", "to", "in"}


def _edit_le_1(a: str, b: str) -> bool:
    # True if Levenshtein distance ≤ 1.
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > 1:
        return False
    if la > lb:
        a, b, la, lb = b, a, lb, la
    i = j = diffs = 0
    while i < la and j < lb:
        if a[i] != b[j]:
            diffs += 1
            if diffs > 1:
                return False
            if la == lb:
                i += 1
            j += 1
        else:
            i += 1
            j += 1
    return True


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
    tokens = [t for t in _TOKEN_RE.findall(_fold(title)) if t not in _STOPWORDS]
    unique_sorted = sorted(set(tokens))
    return "tokens:" + " ".join(unique_sorted)


def _title_tokenset(title: str | None) -> frozenset[str]:
    if not title:
        return frozenset()
    return frozenset(
        t for t in _TOKEN_RE.findall(_fold(title)) if t not in _STOPWORDS
    )


def _group_results(items: list[dict], query_tokens: frozenset[str] = frozenset(), sku_query: bool = False) -> list[dict]:
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
                "skus": [],
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
        sku = (it.get("sku") or "").strip()
        if sku and sku not in g["skus"]:
            g["skus"].append(sku)
        g["offers"].append({
            "retailer": it.get("retailer"),
            "retailer_slug": it.get("retailer_slug"),
            "retailer_icon": it.get("retailer_icon"),
            "url": it.get("url"),
            "price": it.get("price"),
            "in_stock": it.get("in_stock", False),
        })

    # For SKU queries every result is the same product — collapse into one group.
    if sku_query and groups:
        combined = next(iter(groups.values()))
        for g in list(groups.values())[1:]:
            combined["offers"].extend(g["offers"])
            if g.get("image_url") and not combined.get("image_url"):
                combined["image_url"] = g["image_url"]
            if g.get("title") and (not combined.get("title") or len(g["title"]) < len(combined["title"])):
                combined["title"] = g["title"]
            combined["title_tokens"] = combined["title_tokens"] | g["title_tokens"]
            for s in g.get("skus", []):
                if s not in combined["skus"]:
                    combined["skus"].append(s)
        groups = {combined["key"]: combined}

    # Second pass: merge groups with similar token-sets (handles cases where
    # some retailers gave us SKU and some didn't, or one has a typo / extra
    # prefix word like "Marcher:"). Uses fuzzy token containment.
    def _fuzzy_in(token: str, pool: frozenset[str]) -> bool:
        if token in pool:
            return True
        # Allow Levenshtein-1 for tokens of length >= 4 (catches "veterans"/"veterand").
        if len(token) < 4:
            return False
        for p in pool:
            if abs(len(p) - len(token)) > 1 or len(p) < 4:
                continue
            # Quick edit-distance ≤ 1 check
            if _edit_le_1(token, p):
                return True
        return False

    # Distinguishing tokens that mean two products are different variants/sequels
    # (e.g. "II", "2", "3"). If one side has one and the other doesn't, never merge.
    SEQ_TOKENS = {"ii", "iii", "iv", "v", "vi", "vii", "viii", "ix",
                  "2", "3", "4", "5", "6", "7", "8", "9"}

    merged: list[dict] = []
    for g in groups.values():
        tokens = g["title_tokens"]
        target = None
        for m in merged:
            mt = m["title_tokens"]
            if not tokens or not mt:
                continue
            # Reject if sequence markers disagree.
            if (tokens & SEQ_TOKENS) != (mt & SEQ_TOKENS):
                continue
            # Subtract query tokens — products that only share the search query
            # aren't the same product (e.g. all "Star Wars Legion Starter Set"
            # faction boxes share those 5 tokens but are different products).
            t_dist = tokens - query_tokens
            mt_dist = mt - query_tokens
            if not t_dist or not mt_dist:
                # One side's title is essentially the query. Merge if the other
                # side's extra tokens are all near-duplicates of query tokens
                # (e.g. "marines" vs query "marine"); otherwise reject so that
                # unrelated products sharing only the query don't collapse.
                extra = t_dist or mt_dist
                if not all(_fuzzy_in(t, query_tokens) for t in extra):
                    continue
                target = m
                break
            small, large = (t_dist, mt_dist) if len(t_dist) <= len(mt_dist) else (mt_dist, t_dist)
            if not small:
                # Both empty after stripping query — treat as match.
                target = m
                break
            hits = sum(1 for t in small if _fuzzy_in(t, large))
            if hits / len(small) >= 0.7:
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
            for s in g.get("skus", []):
                if s not in target["skus"]:
                    target["skus"].append(s)

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


def _persist_search_groups(groups: list[dict], query_sku: str | None = None) -> None:
    for g in groups:
        skus = list(g.get("skus") or [])
        if query_sku and query_sku not in skus:
            skus.append(query_sku)
        if not skus:
            continue
        prices: dict[str, dict] = {}
        for o in g.get("offers", []):
            slug = o.get("retailer_slug")
            if not slug:
                continue
            in_stock = bool(o.get("in_stock")) and isinstance(o.get("price"), (int, float))
            prices[slug] = {
                "price": o.get("price") if in_stock else None,
                "url": o.get("url"),
            }
        for sku in skus:
            try:
                db.upsert_from_retailer(sku, g.get("title"), g.get("image_url"), prices)
            except Exception:
                log.exception("DB upsert (retailer) failed for sku=%s", sku)



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
    is_sku = _is_sku_query(q)
    wayland_blocked = False
    for module, outcome in zip(RETAILERS, outcomes):
        if isinstance(outcome, WaylandBlockedError):
            wayland_blocked = True
        elif isinstance(outcome, Exception):
            log.exception("Retailer %s failed", module.NAME, exc_info=outcome)
            errors[module.NAME] = f"{type(outcome).__name__}: {outcome}"
        else:
            results.extend(outcome[:1] if is_sku else outcome)

    tokens = _query_tokens(q)
    results = [
        r for r in results
        if _matches(r, q, tokens)
        and r.get("in_stock")
        and isinstance(r.get("price"), (int, float))
        and r["price"] >= 15
    ]
    results.sort(key=_sort_key)
    groups = _group_results(results, frozenset(tokens), sku_query=is_sku)
    if not errors:
        _persist_search_groups(groups, query_sku=_norm_sku(q) if is_sku else None)
    _hidden = set(db.hidden_skus())
    if _hidden:
        groups = [g for g in groups if not any(_norm_sku(s) in _hidden for s in (g.get("skus") or []))]
    _owned = db.owned_counts()
    _minis = db.minis_counts()
    for g in groups:
        g["owned"] = next(
            (_owned[_norm_sku(s)] for s in (g.get("skus") or []) if _norm_sku(s) in _owned),
            0
        )
        g["minis"] = next(
            (_minis[_norm_sku(s)] for s in (g.get("skus") or []) if _norm_sku(s) in _minis),
            None
        )
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
        "wayland_blocked": wayland_blocked,
    }
    if not errors:
        _cache[key] = (now, payload)
    return JSONResponse(payload)


@app.get("/manufacturers")
async def manufacturers_index():
    hidden = db.get_hidden_ranges()
    mfrs = db.manufacturers_with_ranges()
    for m in mfrs:
        for r in m["ranges"]:
            r["hidden"] = (m["slug"], r["slug"]) in hidden
    return JSONResponse({"manufacturers": mfrs})


@app.get("/manufacturer/{man_slug}/{range_slug}")
async def manufacturer_range(man_slug: str, range_slug: str):
    module = next((m for m in MANUFACTURERS if m.SLUG == man_slug), None)
    if module is None:
        return JSONResponse({"error": "unknown manufacturer"}, status_code=404)
    range_def = next((r for r in module.RANGES if r["slug"] == range_slug), None)
    if range_def is None:
        return JSONResponse({"error": "unknown range"}, status_code=404)

    products = db.products_for_range(man_slug, range_slug)
    _hidden = set(db.hidden_skus())
    if _hidden:
        products = [p for p in products if _norm_sku(p.get("sku")) not in _hidden]
    _owned = db.owned_counts()
    for p in products:
        p["owned"] = _owned.get(db.norm_sku(p.get("sku") or ""), 0)
    retailers_meta = [
        {"slug": m.SLUG, "name": m.NAME, "icon": m.ICON} for m in RETAILERS
    ]
    payload = {
        "manufacturer": {"slug": module.SLUG, "name": module.NAME, "icon": module.ICON},
        "range": {"slug": range_def["slug"], "name": range_def["name"]},
        "products": products,
        "retailers": retailers_meta,
    }
    return JSONResponse(payload)


@app.get("/api/wishlist/skus")
async def wishlist_sku_list():
    return JSONResponse({"skus": db.wishlist_skus()})


@app.post("/api/wishlist/{sku}")
async def wishlist_add(sku: str):
    db.add_wishlist(sku)
    return JSONResponse({"ok": True})


@app.delete("/api/wishlist/{sku}")
async def wishlist_delete(sku: str):
    db.remove_wishlist(sku)
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


@app.delete("/api/price/{sku}/{retailer_slug}")
async def delete_price(sku: str, retailer_slug: str):
    key = db.norm_sku(sku)
    if not key:
        return JSONResponse({"error": "invalid sku"}, status_code=400)
    db.delete_store_price(key, retailer_slug)
    return JSONResponse({"ok": True})


@app.post("/api/owned/{sku}")
async def api_set_owned(sku: str, body: OwnedBody):
    saved = db.set_owned(sku, body.count)
    return JSONResponse({"sku": db.norm_sku(sku), "owned": saved})


@app.post("/api/minis/{sku}")
async def api_set_minis(sku: str, body: MinisBody):
    saved = db.set_minis_count(sku, body.count)
    return JSONResponse({"sku": db.norm_sku(sku), "minis": saved})


@app.post("/api/wayland-cookies")
async def wayland_cookies(request: Request):
    body = await request.json()
    cookie_str = (body.get("cookies") or "").strip()
    if not cookie_str:
        return JSONResponse({"ok": False, "error": "empty"}, status_code=400)
    db.set_meta("wayland_cookies", cookie_str)
    # Bust the search cache so next search re-attempts Wayland with new cookies
    _cache.clear()
    return JSONResponse({"ok": True})


def _build_home_data() -> dict:
    hidden_ranges = db.get_hidden_ranges()
    mfrs = db.manufacturers_with_ranges()
    for m in mfrs:
        for r in m["ranges"]:
            r["hidden"] = (m["slug"], r["slug"]) in hidden_ranges
    hidden_skus = set(db.hidden_skus())
    owned = db.owned_counts()
    retailers_meta = [{"slug": m.SLUG, "name": m.NAME, "icon": m.ICON} for m in RETAILERS]
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
        "retailers": retailers_meta,
        "wishlist_skus": [p["sku"] for p in wishlist_items if p.get("sku")],
        "wishlist_items": wishlist_items,
        "owned_items": owned_items,
    }


@app.get("/owned", response_class=HTMLResponse)
async def owned_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"home_data": _build_home_data()})


@app.get("/wishlist", response_class=HTMLResponse)
async def wishlist_page(request: Request):
    return templates.TemplateResponse(request, "index.html", {"home_data": _build_home_data()})


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request, "index.html", {"home_data": _build_home_data()})
