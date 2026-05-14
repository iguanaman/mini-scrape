"""Scrape every range of every manufacturer into the sqlite product cache.

Manufacturers run in parallel; ranges within a manufacturer run sequentially
with a 1-2s random gap between requests (looks human, polite per-host).

Same filter as the homepage: price >= £15, sorted by SKU before upsert.

Run with:  uv run python scripts/scrape_manufacturers.py
"""
from __future__ import annotations

import asyncio
import logging
import random
import sys
import time
from pathlib import Path

# Make project root importable when run as `python scripts/scrape_manufacturers.py`.
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from curl_cffi.requests import AsyncSession

import db
from manufacturers import MANUFACTURERS, PRICE_FLOOR
from retailers import IMPERSONATE

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("scrape")

MIN_DELAY = 0.5
MAX_DELAY = 1.5
TIMEOUT = 60
RETRY_DELAY_MIN = 2.0
RETRY_DELAY_MAX = 4.0


def _persist(man_slug: str, range_def: dict, products: list[dict]) -> int:
    range_slug = range_def["slug"]
    n = 0
    for p in products:
        sku = p.get("sku")
        if not sku:
            continue
        try:
            db.upsert_from_manufacturer(
                sku, p.get("title"), p.get("image_url"),
                man_slug, range_slug,
                url=p.get("url"),
                description=p.get("description"),
            )
            if "minis" in p or "category" in p:
                db.set_minis(sku, p.get("minis"), p.get("category") or "minis")
            n += 1
        except Exception:
            log.exception("upsert failed for %s sku=%s", man_slug, sku)
    return n


class _ThrottledSession:
    """Wraps an AsyncSession so every HTTP call waits MIN_DELAY..MAX_DELAY first.

    Applies to .get/.post/.put/.delete/.head/.patch/.request — anything the
    manufacturer modules might call. Skips the wait on the very first call so
    range-level pacing in scrape_manufacturer() stays in control of inter-range
    timing.
    """
    _METHODS = ("get", "post", "put", "delete", "head", "patch", "request", "options")

    def __init__(self, inner):
        self._inner = inner
        self._first = True

    def __getattr__(self, name):
        target = getattr(self._inner, name)
        if name not in self._METHODS:
            return target

        async def wrapped(*args, **kwargs):
            if self._first:
                self._first = False
            else:
                await asyncio.sleep(random.uniform(MIN_DELAY, MAX_DELAY))
            # Override any per-call timeout the manufacturer module set —
            # this is a batch script and we want the longer TIMEOUT we chose.
            kwargs["timeout"] = TIMEOUT
            return await target(*args, **kwargs)
        return wrapped


async def scrape_manufacturer(module) -> tuple[str, int, int, int]:
    """Returns (slug, ranges_ok, ranges_failed, products_upserted)."""
    db.upsert_manufacturer(module.SLUG, module.NAME, module.ICON)
    for range_def in module.RANGES:
        db.upsert_range(range_def["slug"], module.SLUG, range_def.get("name", ""), range_def.get("group"))
    ok = fail = total = 0
    async with AsyncSession(impersonate=IMPERSONATE, timeout=TIMEOUT) as raw:
        client = _ThrottledSession(raw)
        for range_def in module.RANGES:
            label = f"{module.SLUG}/{range_def['slug']}"
            log.info("start %s", label)
            t0 = time.monotonic()
            products = None
            for attempt in (1, 2):
                try:
                    products = await module.fetch_range(range_def, client)
                    break
                except Exception as exc:
                    if attempt == 1:
                        log.info("retry %s after %s: %s", label, type(exc).__name__, exc)
                        await asyncio.sleep(random.uniform(RETRY_DELAY_MIN, RETRY_DELAY_MAX))
                        continue
                    fail += 1
                    log.warning("FAIL %s: %s: %s", label, type(exc).__name__, exc)
            if products is None:
                continue
            products = [
                p for p in products
                if isinstance(p.get("price"), (int, float)) and p["price"] >= PRICE_FLOOR
            ]
            products.sort(key=lambda p: (p.get("sku") or "￿").upper())
            n = _persist(module.SLUG, range_def, products)
            ok += 1
            total += n
            log.info("ok   %-45s %4d products  %.1fs", label, n, time.monotonic() - t0)
    return (module.SLUG, ok, fail, total)


async def main() -> None:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--manufacturer", "-m", help="Only scrape this manufacturer slug (e.g. gamesworkshop)")
    args = parser.parse_args()

    db.init()
    targets = MANUFACTURERS
    if args.manufacturer:
        targets = [m for m in MANUFACTURERS if m.SLUG == args.manufacturer]
        if not targets:
            slugs = ", ".join(m.SLUG for m in MANUFACTURERS)
            log.error("unknown manufacturer %r. Available: %s", args.manufacturer, slugs)
            return

    log.info("scraping %d manufacturers", len(targets))
    t0 = time.monotonic()
    results = await asyncio.gather(*(scrape_manufacturer(m) for m in targets))
    elapsed = time.monotonic() - t0
    log.info("done in %.1fs", elapsed)
    log.info("%-20s %6s %6s %10s", "manufacturer", "ok", "fail", "products")
    for slug, ok, fail, total in results:
        log.info("%-20s %6d %6d %10d", slug, ok, fail, total)
    if len(results) > 1:
        log.info("%-20s %6d %6d %10d", "TOTAL",
                 sum(r[1] for r in results),
                 sum(r[2] for r in results),
                 sum(r[3] for r in results))


if __name__ == "__main__":
    asyncio.run(main())
