"""
Export DB to static/data.json for static (GitHub Pages) hosting.

Usage:
    uv run python scripts/export_static.py
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db
from manufacturers import MANUFACTURERS

RETAILERS = [
    {"slug": "goblin",    "name": "Goblin Gaming",           "icon": "/static/icons/goblin.webp"},
    {"slug": "wayland",   "name": "Wayland Games",           "icon": "/static/icons/wayland.png"},
    {"slug": "firestorm", "name": "Firestorm Games",         "icon": "/static/icons/firestorm.png"},
    {"slug": "element",   "name": "Element Games",           "icon": "/static/icons/element.ico"},
    {"slug": "overlord",  "name": "Overlord Games",          "icon": "/static/icons/overlord.png"},
    {"slug": "nemc",      "name": "North East Model Centre", "icon": "/static/icons/nemc.jpg"},
]

db.init()

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
            products = [p for p in products if (p.get("sku") or "").strip().upper().replace(" ", "").replace("-", "") not in hidden_skus]
        for p in products:
            p["owned"] = owned.get(db.norm_sku(p.get("sku") or ""), 0)
        products_by_range[r["slug"]] = products
    m["products_by_range"] = products_by_range

wishlist_items = db.wishlist_products()
for p in wishlist_items:
    p["owned"] = owned.get(db.norm_sku(p.get("sku") or ""), p.get("owned", 0))

owned_items = db.owned_products()

data = {
    "manufacturers": mfrs,
    "manufacturers_meta": manufacturers_meta,
    "retailers": RETAILERS,
    "wishlist_skus": [p["sku"] for p in wishlist_items if p.get("sku")],
    "wishlist_items": wishlist_items,
    "owned_items": owned_items,
}

out = ROOT / "static" / "data.json"
out.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
print(f"Written {out} ({out.stat().st_size // 1024}KB)")
