"""
Scrape retailer prices for all SKU'd products in the DB and persist them.

Usage:
    uv run python scripts/scrape_prices.py [--manufacturer SLUG] [--range SLUG]

Options:
    --wishlist      Only scrape wishlisted products
    --manufacturer  Only scrape products from this manufacturer slug
    --range         Only scrape products from this range slug (requires --manufacturer)
    --older-than    Only scrape products last updated more than N days ago
    --delay         Seconds to wait between products (default: 1)
"""
import argparse
import asyncio
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from curl_cffi.requests import AsyncSession
from tqdm import tqdm
from retailers import IMPERSONATE
from retailers import goblin, wayland, firestorm, element, overlord, nemc
from retailers.wayland import WaylandBlockedError
import db

RETAILERS = [goblin, wayland, firestorm, element, overlord, nemc]
MIN_PRICE = 15.0


class _TqdmHandler(logging.StreamHandler):
    def emit(self, record):
        tqdm.write(self.format(record))


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[_TqdmHandler(sys.stdout)],
)
log = logging.getLogger("scrape_prices")


def _norm_sku(s: str | None) -> str | None:
    if not s:
        return None
    return s.strip().upper().replace(" ", "").replace("-", "")


def _cheapest_in_stock(results: list[dict]) -> float | None:
    prices = [r["price"] for r in results if r.get("in_stock") and isinstance(r.get("price"), (int, float))]
    return min(prices) if prices else None


async def scrape_sku(sku: str, title: str | None, client: AsyncSession) -> dict[str, dict]:
    """Search all retailers for a SKU, return {retailer_slug: {price, url}} prices dict."""
    outcomes = await asyncio.gather(
        *(r.search(sku, client) for r in RETAILERS),
        return_exceptions=True,
    )
    prices: dict[str, dict] = {}
    for module, outcome in zip(RETAILERS, outcomes):
        if isinstance(outcome, Exception):
            log.warning("Retailer %s failed for SKU %s: %s", module.NAME, sku, outcome)
            continue
        norm = _norm_sku(sku)
        match = None
        for item in outcome:
            item_sku = _norm_sku(item.get("sku"))
            if item_sku and item_sku == norm:
                match = item
                break
        if match is None and outcome:
            match = next((r for r in outcome if r.get("in_stock") and isinstance(r.get("price"), (int, float))), None)
        if match is None:
            continue
        price = match.get("price")
        in_stock = match.get("in_stock", False) and isinstance(price, (int, float))
        if in_stock and price < MIN_PRICE:
            continue
        prices[module.SLUG] = {
            "price": price if in_stock else None,
            "url": match.get("url"),
        }
    return prices


async def main(args: argparse.Namespace) -> None:
    import sqlite3
    conn = sqlite3.connect(ROOT / "main.db")
    conn.row_factory = sqlite3.Row

    query = "SELECT sku, title FROM products WHERE sku IS NOT NULL AND hidden = 0"
    params: list = []
    if args.wishlist:
        query += " AND wishlisted_at IS NOT NULL"
    if args.older_than is not None:
        query += " AND (prices_updated_at IS NULL OR prices_updated_at < datetime('now', ?))"
        params.append(f"-{args.older_than} days")
    if args.manufacturer:
        query += " AND manufacturer_slug = ?"
        params.append(args.manufacturer)
    if args.range:
        query += " AND range_slug = ?"
        params.append(args.range)
    query += " ORDER BY manufacturer_slug, range_slug, sku"

    rows = conn.execute(query, params).fetchall()

    # Pre-load existing prices for price-drop detection
    skus = [r["sku"] for r in rows]
    placeholders = ",".join("?" * len(skus))
    prev_rows = conn.execute(
        f"SELECT sku, prices_json FROM products WHERE sku IN ({placeholders})", skus
    ).fetchall() if skus else []
    conn.close()
    prev_prices: dict[str, dict] = {}
    for pr in prev_rows:
        if pr["prices_json"]:
            try:
                prev_prices[pr["sku"]] = json.loads(pr["prices_json"])
            except Exception:
                pass

    if not rows:
        log.info("No products found matching filters.")
        return

    log.info("Scraping prices for %d products across %d retailers…", len(rows), len(RETAILERS))
    t0 = time.time()

    async with AsyncSession(impersonate=IMPERSONATE, timeout=20) as client:
        bar = tqdm(rows, unit="sku", dynamic_ncols=True)
        for i, row in enumerate(bar):
            try:
                prices = await scrape_sku(row["sku"], row["title"], client)
                old = prev_prices.get(row["sku"], {})
                db.upsert_from_retailer(row["sku"], row["title"], None, prices)
                cheapest = _cheapest_in_stock(
                    [{"price": v.get("price"), "in_stock": v.get("price") is not None} for v in prices.values()]
                )
                old_cheapest = _cheapest_in_stock(
                    [{"price": v.get("price") if isinstance(v, dict) else v,
                      "in_stock": (v.get("price") if isinstance(v, dict) else v) is not None}
                     for v in old.values()]
                )
                status = f"£{cheapest:.2f}" if cheapest else "no stock"
                if cheapest is not None and old_cheapest is not None:
                    if cheapest < old_cheapest:
                        status += f"  ↓ (was £{old_cheapest:.2f})"
                    elif cheapest > old_cheapest:
                        status += f"  ↑ (was £{old_cheapest:.2f})"
                log.info("%-20s %-50s %s", row["sku"], (row["title"] or "")[:50], status)
            except WaylandBlockedError:
                tqdm.write("\nWayland is blocking requests. Update cookies then press Enter to continue...")
                tqdm.write("Run in another terminal: uv run python scripts/capture_wayland_cookies.py --paste")
                input()
            except Exception:
                log.exception("Failed for SKU %s", row["sku"])
            if i < len(rows) - 1:
                await asyncio.sleep(args.delay)

    log.info("Done in %.1fs", time.time() - t0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wishlist", action="store_true", help="Only scrape wishlisted products")
    parser.add_argument("--manufacturer", help="Filter by manufacturer slug")
    parser.add_argument("--range", help="Filter by range slug (requires --manufacturer)")
    parser.add_argument("--older-than", type=int, metavar="DAYS", help="Only scrape products last updated more than N days ago")
    parser.add_argument("--delay", type=float, default=1.0, help="Seconds between products (default: 1)")
    args = parser.parse_args()
    asyncio.run(main(args))
