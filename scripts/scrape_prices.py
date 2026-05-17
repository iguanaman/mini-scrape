"""
Scrape retailer prices for all SKU'd products in the DB and persist them.

Usage:
    uv run python scripts/scrape_prices.py [--manufacturer SLUG] [--range SLUG]

Options:
    --manufacturer  Only scrape products from this manufacturer slug
    --range         Only scrape products from this range slug (requires --manufacturer)
    --concurrency   Max parallel retailer requests per product (default: 6)
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
from retailers import IMPERSONATE
from retailers import goblin, wayland, firestorm, element, overlord, nemc
import db

RETAILERS = [goblin, wayland, firestorm, element, overlord, nemc]
MIN_PRICE = 15.0

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
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
        # Find best match for this SKU among results
        match = None
        for item in outcome:
            item_sku = _norm_sku(item.get("sku"))
            if item_sku and item_sku == norm:
                match = item
                break
        if match is None and outcome:
            # Fall back to first in-stock result if no SKU match
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
    if args.manufacturer:
        query += " AND manufacturer_slug = ?"
        params.append(args.manufacturer)
    if args.range:
        query += " AND range_slug = ?"
        params.append(args.range)
    query += " ORDER BY manufacturer_slug, range_slug, sku"

    rows = conn.execute(query, params).fetchall()
    conn.close()

    if not rows:
        log.info("No products found matching filters.")
        return

    log.info("Scraping prices for %d products across %d retailers…", len(rows), len(RETAILERS))
    t0 = time.time()

    sem = asyncio.Semaphore(args.concurrency)

    async def scrape_one(sku: str, title: str | None) -> None:
        async with sem:
            try:
                async with AsyncSession(impersonate=IMPERSONATE, timeout=20) as client:
                    prices = await scrape_sku(sku, title, client)
                db.upsert_from_retailer(sku, title, None, prices)
                cheapest = _cheapest_in_stock(
                    [{"price": v.get("price"), "in_stock": v.get("price") is not None} for v in prices.values()]
                )
                status = f"£{cheapest:.2f}" if cheapest else "no stock"
                log.info("%-20s %s", sku, status)
                await asyncio.sleep(1)
            except Exception:
                log.exception("Failed for SKU %s", sku)

    await asyncio.gather(*(scrape_one(row["sku"], row["title"]) for row in rows))
    log.info("Done in %.1fs", time.time() - t0)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manufacturer", help="Filter by manufacturer slug")
    parser.add_argument("--range", help="Filter by range slug (requires --manufacturer)")
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel products (default: 3)")
    args = parser.parse_args()
    asyncio.run(main(args))
