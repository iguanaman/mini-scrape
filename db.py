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
    updated_at TEXT,
    prices_updated_at TEXT
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
    era TEXT,
    PRIMARY KEY (slug, manufacturer_slug)
);
CREATE TABLE IF NOT EXISTS hidden_ranges (
    man_slug   TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
CREATE TABLE IF NOT EXISTS excluded_groups (
    manufacturer_slug TEXT NOT NULL,
    group_name        TEXT NOT NULL,
    PRIMARY KEY (manufacturer_slug, group_name)
);
CREATE TABLE IF NOT EXISTS excluded_ranges (
    manufacturer_slug TEXT NOT NULL,
    range_slug        TEXT NOT NULL,
    PRIMARY KEY (manufacturer_slug, range_slug)
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
            "ALTER TABLE products ADD COLUMN blacklisted_stores TEXT",
            "ALTER TABLE products ADD COLUMN prices_updated_at TEXT",
            "ALTER TABLE ranges ADD COLUMN era TEXT",
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
    blacklisted = get_blacklisted_stores(key)
    if blacklisted:
        prices = {k: v for k, v in prices.items() if k not in blacklisted}
    payload = json.dumps(prices)
    now = _now()
    with _conn() as c:
        c.execute(
            """INSERT INTO products (sku, title, image_url, prices_json, updated_at, prices_updated_at)
               VALUES (?, ?, ?, ?, ?, ?)
               ON CONFLICT(sku) DO UPDATE SET
                 title = COALESCE(excluded.title, products.title),
                 image_url = COALESCE(products.image_url, excluded.image_url),
                 prices_json = excluded.prices_json,
                 updated_at = excluded.updated_at,
                 prices_updated_at = excluded.prices_updated_at""",
            (key, title, image_url, payload, now, now),
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


def delete_group(man_slug: str, group_name: str) -> None:
    with _conn() as c:
        range_rows = c.execute(
            "SELECT slug FROM ranges WHERE manufacturer_slug = ? AND grp = ?",
            (man_slug, group_name),
        ).fetchall()
        range_slugs = [r["slug"] for r in range_rows]
        if range_slugs:
            placeholders = ",".join("?" * len(range_slugs))
            c.execute(
                f"DELETE FROM products WHERE manufacturer_slug = ? AND range_slug IN ({placeholders})",
                [man_slug, *range_slugs],
            )
            c.execute(
                f"DELETE FROM ranges WHERE manufacturer_slug = ? AND slug IN ({placeholders})",
                [man_slug, *range_slugs],
            )
        c.execute(
            "INSERT OR REPLACE INTO excluded_groups (manufacturer_slug, group_name) VALUES (?, ?)",
            (man_slug, group_name),
        )


def delete_range(man_slug: str, range_slug: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM products WHERE manufacturer_slug = ? AND range_slug = ?",
            (man_slug, range_slug),
        )
        c.execute(
            "DELETE FROM ranges WHERE manufacturer_slug = ? AND slug = ?",
            (man_slug, range_slug),
        )
        c.execute(
            "INSERT OR REPLACE INTO excluded_ranges (manufacturer_slug, range_slug) VALUES (?, ?)",
            (man_slug, range_slug),
        )


def is_range_excluded(man_slug: str, range_slug: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM excluded_ranges WHERE manufacturer_slug = ? AND range_slug = ?",
            (man_slug, range_slug),
        ).fetchone()
    return row is not None


def is_group_excluded(man_slug: str, group_name: str) -> bool:
    with _conn() as c:
        row = c.execute(
            "SELECT 1 FROM excluded_groups WHERE manufacturer_slug = ? AND group_name = ?",
            (man_slug, group_name),
        ).fetchone()
    return row is not None


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


def set_minis_count(sku: str, count: int) -> int:
    key = _norm_sku(sku)
    if not key:
        return count
    with _conn() as c:
        c.execute(
            "UPDATE products SET minis = ?, updated_at = ? WHERE sku = ?",
            (count, _now(), key),
        )
    return count


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


def minis_counts() -> dict[str, int]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sku, minis FROM products WHERE minis IS NOT NULL AND minis > 0"
        ).fetchall()
    return {r["sku"]: r["minis"] for r in rows}


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


def get_blacklisted_stores(sku: str) -> list[str]:
    key = _norm_sku(sku)
    if not key:
        return []
    with _conn() as c:
        row = c.execute(
            "SELECT blacklisted_stores FROM products WHERE sku = ?", (key,)
        ).fetchone()
    if not row or not row["blacklisted_stores"]:
        return []
    try:
        return json.loads(row["blacklisted_stores"])
    except json.JSONDecodeError:
        return []


def delete_store_price(sku: str, retailer_slug: str) -> None:
    key = _norm_sku(sku)
    if not key:
        return
    with _conn() as c:
        row = c.execute(
            "SELECT prices_json, blacklisted_stores FROM products WHERE sku = ?", (key,)
        ).fetchone()
        if not row:
            return
        prices: dict = {}
        if row["prices_json"]:
            try:
                prices = json.loads(row["prices_json"])
            except json.JSONDecodeError:
                pass
        prices.pop(retailer_slug, None)
        blacklisted: list[str] = []
        if row["blacklisted_stores"]:
            try:
                blacklisted = json.loads(row["blacklisted_stores"])
            except json.JSONDecodeError:
                pass
        if retailer_slug not in blacklisted:
            blacklisted.append(retailer_slug)
        c.execute(
            "UPDATE products SET prices_json = ?, blacklisted_stores = ?, updated_at = ? WHERE sku = ?",
            (json.dumps(prices), json.dumps(blacklisted), _now(), key),
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
            """SELECT r.slug, r.manufacturer_slug, r.name, r.grp, r.era
               FROM ranges r
               ORDER BY r.manufacturer_slug, r.name"""
        ).fetchall()
        cat_rows = c.execute(
            """SELECT manufacturer_slug, range_slug, category, minis, prices_json
               FROM products
               WHERE manufacturer_slug IS NOT NULL AND range_slug IS NOT NULL AND hidden = 0"""
        ).fetchall()
    range_cats: dict[tuple[str, str], set[str]] = {}
    range_min_ppm: dict[tuple[str, str], float] = {}
    for row in cat_rows:
        key = (row["manufacturer_slug"], row["range_slug"])
        range_cats.setdefault(key, set()).add(row["category"] if row["category"] else "unknown")
        minis = row["minis"]
        if minis and minis > 0:
            try:
                prices_raw = json.loads(row["prices_json"] or "{}")
                prices = [
                    (v["price"] if isinstance(v, dict) else v)
                    for v in prices_raw.values()
                    if v is not None and (isinstance(v, (int, float)) or (isinstance(v, dict) and v.get("price") is not None))
                ]
                prices = [p for p in prices if isinstance(p, (int, float))]
                if prices:
                    ppm = min(prices) / minis
                    cur = range_min_ppm.get(key)
                    if cur is None or ppm < cur:
                        range_min_ppm[key] = ppm
            except Exception:
                pass
    by_man: dict[str, list] = {}
    for r in ranges:
        cats = range_cats.get((r["manufacturer_slug"], r["slug"]), set())
        min_ppm = range_min_ppm.get((r["manufacturer_slug"], r["slug"]))
        by_man.setdefault(r["manufacturer_slug"], []).append({
            "slug": r["slug"],
            "name": r["name"],
            "group": r["grp"],
            "era": r["era"],
            "categories": sorted(cats),
            "min_ppm": round(min_ppm, 4) if min_ppm is not None else None,
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
            """SELECT sku, title, image_url, prices_json, manufacturer_url, minis, category
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
            "manufacturer_url": r["manufacturer_url"],
            "minis": r["minis"],
            "category": r["category"],
        })
    return out


def wishlist_skus() -> list[str]:
    with _conn() as c:
        rows = c.execute(
            "SELECT sku FROM products WHERE wishlisted_at IS NOT NULL ORDER BY wishlisted_at DESC"
        ).fetchall()
    return [r["sku"] for r in rows]


def owned_products() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT sku, title, image_url, manufacturer_slug, range_slug, manufacturer_url,
                      prices_json, minis, owned, category, description, updated_at
               FROM products
               WHERE owned > 0
               ORDER BY manufacturer_slug NULLS LAST, sku"""
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
            "range_slug": r["range_slug"],
            "manufacturer_url": r["manufacturer_url"],
            "prices": prices,
            "minis": r["minis"],
            "owned": r["owned"],
            "category": r["category"],
            "description": r["description"],
            "updated_at": r["updated_at"],
        })
    return out


def wishlist_products() -> list[dict]:
    with _conn() as c:
        rows = c.execute(
            """SELECT sku, title, image_url, manufacturer_slug, range_slug, manufacturer_url,
                      prices_json, minis, owned, category, description, updated_at, wishlisted_at
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
            "range_slug": r["range_slug"],
            "manufacturer_url": r["manufacturer_url"],
            "prices": prices,
            "minis": r["minis"],
            "owned": r["owned"],
            "category": r["category"],
            "description": r["description"],
            "updated_at": r["updated_at"],
            "added_at": r["wishlisted_at"],
        })
    return out
