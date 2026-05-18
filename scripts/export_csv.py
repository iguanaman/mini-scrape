"""
Export wishlist and owned products to CSV.

Usage:
    uv run python scripts/export_csv.py   # -> wishlist_export.csv, owned_export.csv
"""
import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db

COLUMNS = ["sku", "title", "manufacturer", "range", "era", "description", "min_price", "minis", "price_per_mini"]


def _strip_html(text: str | None) -> str | None:
    if not text:
        return text
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\n+", ". ", text)
    return re.sub(r" +", " ", text).strip()


def _min_price(prices: dict) -> float | None:
    raw = [v["price"] if isinstance(v, dict) else v for v in prices.values()]
    valid = [x for x in raw if isinstance(x, (int, float))]
    return min(valid) if valid else None


def _row(p: dict) -> list:
    min_price = _min_price(p.get("prices") or {})
    minis = p.get("minis")
    ppm = round(min_price / minis, 4) if min_price and minis else None
    return [p["sku"], p["title"], p["manufacturer_slug"], p.get("range_slug"), p.get("era"), _strip_html(p.get("description")), min_price, minis, ppm]


def export(rows: list, out: Path) -> None:
    with open(out, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        for p in rows:
            w.writerow(_row(p))
    print(f"Exported {len(rows)} rows -> {out}")


if __name__ == "__main__":
    export(db.wishlist_products(), ROOT / "wishlist_export.csv")
    export(db.owned_products(), ROOT / "owned_export.csv")
