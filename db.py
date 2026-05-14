import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

DB_PATH = Path(__file__).resolve().parent / "main.db"

_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    title TEXT,
    image_url TEXT,
    url TEXT,
    manufacturer_slug TEXT,
    range_slug TEXT,
    range_name TEXT,
    range_group TEXT,
    manufacturer_price REAL,
    prices_json TEXT,
    minis INTEGER,
    wishlisted_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS hidden_ranges (
    man_slug   TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init() -> None:
    with _conn() as c:
        c.executescript(_SCHEMA)
        # Idempotent migration: add hidden column if not present
        try:
            c.execute("ALTER TABLE products ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0")
        except Exception:
            pass  # column already exists


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_sku(sku: str) -> str:
    return sku.strip().upper().replace(" ", "").replace("-", "")


def upsert_from_retailer(sku: str, title: str | None, image_url: str | None,
                         prices: dict) -> None:
    """prices: {retailer_slug: price_or_null} — overwrites prices_json entirely."""
    key = _norm_sku(sku)
    if not key:
        return
    payload = json.dumps(prices)
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, title, image_url, prices_json, updated_at)
               VALUES (?, ?, ?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 title = COALESCE(excluded.title, products.title),
                 image_url = COALESCE(products.image_url, excluded.image_url),
                 prices_json = excluded.prices_json,
                 updated_at = excluded.updated_at""",
            (key, title, image_url, payload, now),
        )


def upsert_from_manufacturer(sku: str, title: str | None, image_url: str | None,
                             url: str | None, manufacturer_slug: str,
                             range_slug: str | None, range_name: str | None,
                             range_group: str | None, price: float | None) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, title, image_url, url, manufacturer_slug,
                                     range_slug, range_name, range_group,
                                     manufacturer_price, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 title = COALESCE(excluded.title, products.title),
                 image_url = COALESCE(excluded.image_url, products.image_url),
                 url = COALESCE(excluded.url, products.url),
                 manufacturer_slug = excluded.manufacturer_slug,
                 range_slug = excluded.range_slug,
                 range_name = excluded.range_name,
                 range_group = excluded.range_group,
                 manufacturer_price = excluded.manufacturer_price,
                 updated_at = excluded.updated_at""",
            (key, title, image_url, url, manufacturer_slug, range_slug, range_name,
             range_group, price, now),
        )


def add_wishlist(sku: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, wishlisted_at, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 wishlisted_at = COALESCE(products.wishlisted_at, excluded.wishlisted_at)""",
            (key, now, now),
        )


def remove_wishlist(sku: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        c.execute("UPDATE products SET wishlisted_at = NULL WHERE sku = ?", (key,))


def hide_product(sku: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, hidden, updated_at)
               VALUES (?, 1, ?)
               ON CONFLICT(sku) DO UPDATE SET hidden = 1""",
            (key, _now()),
        )


def unhide_product(sku: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        c.execute("UPDATE products SET hidden = 0 WHERE sku = ?", (key,))


def hide_range(man_slug: str, range_slug: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO hidden_ranges (man_slug, range_slug) VALUES (?, ?)",
            (man_slug, range_slug),
        )


def unhide_range(man_slug: str, range_slug: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM hidden_ranges WHERE man_slug = ? AND range_slug = ?",
            (man_slug, range_slug),
        )


def get_hidden_ranges() -> set[tuple[str, str]]:
    with _conn() as c:
        rows = c.execute("SELECT man_slug, range_slug FROM hidden_ranges").fetchall()
    return {(r["man_slug"], r["range_slug"]) for r in rows}


def get_meta(key: str) -> str | None:
    with _conn() as c:
        row = c.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else None


def set_meta(key: str, value: str) -> None:
    with _conn() as c:
        c.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, value))


def hidden_skus() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sku FROM products WHERE hidden = 1"
        ).fetchall()
    return [r["sku"] for r in rows]


def products_for_range(manufacturer_slug: str, range_slug: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT sku, title, image_url, url, manufacturer_price, prices_json
               FROM products
               WHERE manufacturer_slug = ? AND range_slug = ?
               ORDER BY COALESCE(sku, title)""",
            (manufacturer_slug, range_slug),
        ).fetchall()
    out = []
    for r in rows:
        prices = {}
        if r["prices_json"]:
            try:
                prices = json.loads(r["prices_json"])
            except json.JSONDecodeError:
                pass
        out.append({
            "sku": r["sku"],
            "title": r["title"],
            "image_url": r["image_url"],
            "url": r["url"],
            "price": r["manufacturer_price"],
            "prices": prices,
        })
    return out


def wishlist_skus() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sku FROM products WHERE wishlisted_at IS NOT NULL ORDER BY wishlisted_at DESC"
        ).fetchall()
    return [r["sku"] for r in rows]


def wishlist_products() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT sku, title, image_url, manufacturer_slug,
                      manufacturer_price, prices_json, minis, updated_at,
                      wishlisted_at
               FROM products
               WHERE wishlisted_at IS NOT NULL
               ORDER BY wishlisted_at DESC"""
        ).fetchall()
    out = []
    for r in rows:
        prices = {}
        if r["prices_json"]:
            try:
                prices = json.loads(r["prices_json"])
            except json.JSONDecodeError:
                prices = {}
        out.append({
            "sku": r["sku"],
            "title": r["title"],
            "image_url": r["image_url"],
            "manufacturer_slug": r["manufacturer_slug"],
            "manufacturer_price": r["manufacturer_price"],
            "prices": prices,
            "minis": r["minis"],
            "updated_at": r["updated_at"],
            "added_at": r["wishlisted_at"],
        })
    return out
