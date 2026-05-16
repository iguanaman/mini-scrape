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
    "Given a product name and description, count the total number of individual miniature models included in the box.\n"
    "Strategy:\n"
    "1. Scan for digit-form numbers (e.g. 30, 10, 5) near model-type words (figures, infantry, cavalry, vehicles, monsters, etc.). These are the most reliable signal.\n"
    "2. If no digits, scan for written-out numbers (thirty, ten, five, etc.) near model-type words.\n"
    "3. Use the product name as context (e.g. 'Box of Elf Infantry' confirms numbers are model counts).\n"
    "4. Do not trust a number blindly — 25mm is a base size, 128 is a page count.\n"
    "5. If no figure count is mentioned, fall back to the number of bases included (e.g. 'contains 30 bases' → 30 models).\n"
    "6. If the same count is restated multiple ways ('build 30... as 30 Warriors'), count it once.\n"
    "7. Ignore copyright lines, footer text, frame names, and noise.\n"
    "Reply with ONLY one of:\n"
    "- A plain integer if you can determine the model count\n"
    "- minis  if it contains miniatures but quantity is truly unknown\n"
    "- A category word (book, paint, terrain, dice, accessory) if no miniatures\n"
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
_NS_SKIP_RE = re.compile(r"^(©|Site by|Trade Logon|Our Price)", re.IGNORECASE)
_BLOCK_TAG_RE = re.compile(r"<(script|style|head|iframe)[^>]*>.*?</(script|style|head|iframe)>", re.IGNORECASE | re.DOTALL)
_DATA_SHEETS_RE = re.compile(r"<[^>]*data-sheets-[^>]*>", re.IGNORECASE)
_HTML_RE = re.compile(r"<[^>]+>")


def _clean_description(html: str) -> str:
    text = _BLOCK_TAG_RE.sub(" ", html)
    text = _DATA_SHEETS_RE.sub(" ", text)
    text = _HTML_RE.sub(" ", text)
    return " ".join(text.split())[:1200]


def _call_llama(description: str, title: str = "") -> str:
    user_content = f"Product: {title}\n\n{_clean_description(description)}" if title else _clean_description(description)
    payload = _json.dumps({
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0,
        "thinking_budget_tokens": 0,
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
        paras = [p.text(strip=True) for p in tree.css("p")
                 if not p.attributes.get("class")
                 and len(p.text(strip=True)) > 20
                 and not _NS_SKIP_RE.match(p.text(strip=True))]
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
            """SELECT sku, title, manufacturer_slug, manufacturer_url, description
               FROM products WHERE hidden = 0"""
        ).fetchall()
    else:
        rows = conn.execute(
            """SELECT sku, title, manufacturer_slug, manufacturer_url, description
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
                raw = _call_llama(description, title=row.get("title", ""))
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
