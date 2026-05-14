"""Fill minis / category for products using local Llama.

For each non-hidden product without a category:
  - If description already in DB, use it directly.
  - If no description (North Star / Perry / Gripping Beast), fetch the product page first.
  Then call Llama and write minis (int or NULL) + category.

Run scrape_manufacturers.py first to populate descriptions.

Usage:
    uv run python scripts/fill_minis.py              # skip already-filled rows
    uv run python scripts/fill_minis.py --overwrite  # redo all non-hidden rows
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import random
import re
import sqlite3
import sys
import time
import urllib.request
import json as _json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db
from retailers import IMPERSONATE
from curl_cffi.requests import AsyncSession

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("fill_minis")

LLAMA_URL = "http://127.0.0.1:8081/v1/chat/completions"
SYSTEM_PROMPT = (
    "You are a helpful assistant that analyses miniature wargaming product descriptions. "
    "Given a product description, determine how many individual miniature figures are included in the box. "
    "Reply with ONLY one of:\n"
    "- A plain integer (e.g. 20) if you can determine the count\n"
    "- minis  if the product contains miniatures but you cannot determine the count\n"
    "- A category word (e.g. book, paint, terrain, dice, accessory) if the product does not contain miniatures\n"
    "No explanation. No punctuation. Just the value."
)

# Manufacturers whose fetch already returns descriptions at listing level
_HAS_LISTING_DESC = {"wargamesatlantic", "gamesworkshop", "victrix", "mantic", "warlord"}

# Product page description selectors for HTML-only manufacturers
_PAGE_DESC_SELECTORS = {
    "northstar": None,       # classless <p> tags — handled by custom parser
    "perry": "#tab-description",
}

_INT_RE = re.compile(r"^\d+$")


def _call_llama(description: str) -> str:
    payload = _json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": description},
        ],
        "temperature": 0,
        "max_tokens": 16,
    }).encode()
    req = urllib.request.Request(
        LLAMA_URL,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = _json.loads(resp.read())
    return (data["choices"][0]["message"]["content"] or "").strip().lower()


def _parse_llama(raw: str) -> tuple[int | None, str]:
    """Returns (count, category). category is always set; count only when numeric."""
    word = raw.strip().lower().split()[0] if raw.strip() else ""
    if _INT_RE.match(word):
        return int(word), "minis"
    return None, word if word else "minis"


def _fetch_page_description(html: str, man_slug: str) -> str | None:
    from selectolax.parser import HTMLParser
    tree = HTMLParser(html)
    if man_slug == "northstar":
        paras = [p.text(strip=True) for p in tree.css("p") if not p.attributes.get("class") and len(p.text(strip=True)) > 20]
        return "\n\n".join(paras) or None
    sel = _PAGE_DESC_SELECTORS.get(man_slug)
    if sel:
        el = tree.css_first(sel)
        return el.text(strip=True) or None if el else None
    return None


def _rows_to_process(overwrite: bool) -> list[dict]:
    conn = sqlite3.connect(db.DB_PATH)
    conn.row_factory = sqlite3.Row
    if overwrite:
        rows = conn.execute(
            """SELECT sku, manufacturer_slug, manufacturer_url, description
               FROM products WHERE hidden = 0"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT sku, manufacturer_slug, manufacturer_url, description
               FROM products
               WHERE hidden = 0 AND minis IS NULL AND category IS NULL"""
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


async def _stage2(overwrite: bool) -> None:
    log.info("filling mini counts via Llama")
    rows = _rows_to_process(overwrite)
    log.info("%d products to process", len(rows))

    ok = fail = skipped = 0
    async with AsyncSession(impersonate=IMPERSONATE, timeout=20) as client:
        for i, row in enumerate(rows):
            sku = row["sku"]
            man_slug = row["manufacturer_slug"] or ""
            description = row["description"]

            # Fetch product page if no description and we know how to get one
            if not description and man_slug in _PAGE_DESC_SELECTORS and row.get("manufacturer_url"):
                await asyncio.sleep(random.uniform(1.0, 2.0))
                try:
                    r = await client.get(row["manufacturer_url"], timeout=20)
                    description = _fetch_page_description(r.text, man_slug)
                    if description:
                        db.set_description(sku, description)
                except Exception as exc:
                    log.warning("[%d/%d] %s page fetch failed: %s", i + 1, len(rows), sku, exc)

            if not description:
                skipped += 1
                continue

            try:
                raw = _call_llama(description)
                count, category = _parse_llama(raw)
                db.set_minis(sku, count, category)
                log.info("[%d/%d] %s → %s (%s)", i + 1, len(rows), sku, count if count is not None else "?", category)
                ok += 1
            except Exception as exc:
                log.warning("[%d/%d] %s Llama failed: %s", i + 1, len(rows), sku, exc)
                fail += 1

            time.sleep(0.1)

    log.info("done — ok=%d fail=%d skipped(no desc)=%d", ok, fail, skipped)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--overwrite", action="store_true", help="Redo all non-hidden rows")
    args = parser.parse_args()

    db.init()
    await _stage2(args.overwrite)


if __name__ == "__main__":
    asyncio.run(main())
