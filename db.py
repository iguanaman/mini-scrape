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
    manufacturer_slug TEXT,
    range_slug TEXT,
    manufacturer_url TEXT,
    prices_json TEXT,
    description TEXT,
    minis INTEGER,
    category TEXT,
    wishlisted_at TEXT,
    hidden INTEGER NOT NULL DEFAULT 0,
    owned INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS manufacturers (
    slug TEXT PRIMARY KEY,
    name TEXT,
    icon TEXT
);
CREATE TABLE IF NOT EXISTS ranges (
    slug TEXT NOT NULL,
    manufacturer_slug TEXT NOT NULL REFERENCES manufacturers(slug),
    name TEXT,
    grp TEXT,
    PRIMARY KEY (slug, manufacturer_slug)
);
CREATE TABLE IF NOT EXISTS hidden_ranges (
    man_slug   TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
"""


def _conn() -> sqlite3.Connection:
    c = sqlite3.connect(DB_PATH, timeout=30)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA busy_timeout = 30000")
    return c


def init() -> None:
    with _conn() as c:
        c.execute("PRAGMA journal_mode = WAL")
        c.execute("PRAGMA synchronous = NORMAL")
        c.executescript(_SCHEMA)
        # Idempotent migrations
        for stmt in (
            "ALTER TABLE products ADD COLUMN hidden INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE products ADD COLUMN owned INTEGER NOT NULL DEFAULT 0",
            "ALTER TABLE products ADD COLUMN manufacturer_url TEXT",
            "ALTER TABLE products ADD COLUMN description TEXT",
            "ALTER TABLE products ADD COLUMN category TEXT",
        ):
            try:
                c.execute(stmt)
            except Exception:
                pass
        c.execute(
            "CREATE INDEX IF NOT EXISTS idx_products_man_range "
            "ON products(manufacturer_slug, range_slug)"
        )
        # Drop obsolete columns from products (SQLite 3.35+)
        cols = {row[1] for row in c.execute("PRAGMA table_info(products)")}
        for col in ("url", "range_name", "range_group", "manufacturer_price"):
            if col in cols:
                c.execute(f"ALTER TABLE products DROP COLUMN {col}")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _norm_sku(sku: str) -> str:
    return sku.strip().upper().replace(" ", "").replace("-", "")


norm_sku = _norm_sku


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


def upsert_manufacturer(slug: str, name: str, icon: str) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO manufacturers (slug, name, icon) VALUES (?, ?, ?)
               ON CONFLICT(slug) DO UPDATE SET
                 name = excluded.name,
                 icon = excluded.icon""",
            (slug, name, icon),
        )


def upsert_range(slug: str, manufacturer_slug: str, name: str, group: str | None) -> None:
    with _conn() as c:
        c.execute(
            """INSERT INTO ranges (slug, manufacturer_slug, name, grp) VALUES (?, ?, ?, ?)
               ON CONFLICT(slug, manufacturer_slug) DO UPDATE SET
                 name = excluded.name,
                 grp = excluded.grp""",
            (slug, manufacturer_slug, name, group),
        )


def upsert_from_manufacturer(sku: str, title: str | None, image_url: str | None,
                             manufacturer_slug: str, range_slug: str | None,
                             url: str | None = None,
                             description: str | None = None) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, title, image_url, manufacturer_slug,
                                     range_slug, manufacturer_url, description, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 title = COALESCE(excluded.title, products.title),
                 image_url = COALESCE(excluded.image_url, products.image_url),
                 manufacturer_slug = excluded.manufacturer_slug,
                 range_slug = excluded.range_slug,
                 manufacturer_url = COALESCE(excluded.manufacturer_url, products.manufacturer_url),
                 description = COALESCE(excluded.description, products.description),
                 updated_at = excluded.updated_at""",
            (key, title, image_url, manufacturer_slug, range_slug, url, description, now),
        )


def set_minis(sku: str, count: int | None, category: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        c.execute(
            """UPDATE products SET minis = ?, category = ?, updated_at = ?
               WHERE sku = ?""",
            (count, category, _now(), key),
        )


def set_description(sku: str, description: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        c.execute(
            "UPDATE products SET description = ?, updated_at = ? WHERE sku = ?",
            (description, _now(), key),
        )


def skus_with_description(skus: list[str]) -> set[str]:
    keys = [_norm_sku(s) for s in skus if _norm_sku(s)]
    if not keys:
        return set()
    out: set[str] = set()
    with _conn() as c:
        # chunk to avoid SQLITE_MAX_VARIABLE_NUMBER
        for i in range(0, len(keys), 500):
            chunk = keys[i:i + 500]
            placeholders = ",".join("?" * len(chunk))
            rows = c.execute(
                f"SELECT sku FROM products WHERE description IS NOT NULL AND description != '' AND sku IN ({placeholders})",
                chunk,
            ).fetchall()
            out.update(r[0] for r in rows)
    return out


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


def set_owned(sku: str, count: int) -> int:
    key = _norm_sku(sku)
    if not key:
        return 0
    count = max(0, count)
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, owned, updated_at)
               VALUES (?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 owned = excluded.owned,
                 updated_at = excluded.updated_at""",
            (key, count, _now()),
        )
    return count


def owned_counts() -> dict[str, int]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sku, owned FROM products WHERE owned > 0"
        ).fetchall()
    return {r["sku"]: r["owned"] for r in rows}


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


def manufacturers_with_ranges() -> list[dict]:
    with _conn() as c:
        mfrs = c.execute(
            "SELECT slug, name, icon FROM manufacturers ORDER BY name"
        ).fetchall()
        ranges = c.execute(
            """SELECT r.slug, r.manufacturer_slug, r.name, r.grp
               FROM ranges r
               ORDER BY r.manufacturer_slug, r.name"""
        ).fetchall()
    by_man: dict[str, list] = {}
    for r in ranges:
        by_man.setdefault(r["manufacturer_slug"], []).append({
            "slug": r["slug"],
            "name": r["name"],
            "group": r["grp"],
        })
    out = []
    for m in mfrs:
        out.append({
            "slug": m["slug"],
            "name": m["name"],
            "icon": m["icon"],
            "ranges": by_man.get(m["slug"], []),
        })
    return out


def products_for_range(manufacturer_slug: str, range_slug: str) -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT sku, title, image_url, prices_json
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
                      prices_json, minis, owned, updated_at, wishlisted_at
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
            "prices": prices,
            "minis": r["minis"],
            "owned": r["owned"],
            "updated_at": r["updated_at"],
            "added_at": r["wishlisted_at"],
        })
    return out
