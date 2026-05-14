# db.md — sqlite cache + wishlist + hidden

Single file `main.db` at project root. Gitignored. Schema initialised on app startup via `db.init()` — `CREATE TABLE IF NOT EXISTS`, then additive `ALTER TABLE` migrations that swallow "duplicate column" errors, so they're safe to run against existing DBs.

Two tables: `products` (SKU cache, wishlist, hidden flags) and `hidden_ranges` (manufacturer range visibility).

## Schema

```sql
CREATE TABLE products (
    sku TEXT PRIMARY KEY,            -- normalised: upper, no spaces/hyphens
    title TEXT,
    image_url TEXT,
    manufacturer_slug TEXT,          -- set when seen via /manufacturer/...
    manufacturer_price REAL,
    prices_json TEXT,                -- JSON: {retailer_slug: {price, url}}
    minis INTEGER,                   -- count of miniatures in the box; manual, default NULL
    wishlisted_at TEXT,              -- ISO-8601 UTC; NULL = not on wishlist
    hidden INTEGER NOT NULL DEFAULT 0, -- 1 = hidden from search/range results
    updated_at TEXT
);
```

`hidden` was added via migration — older DBs get it automatically on first startup after the update.

No separate wishlist or hidden-SKU table — flags live on the products row.

```sql
CREATE TABLE hidden_ranges (
    man_slug   TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
```

New table, created via `_SCHEMA` (idempotent). No migration needed for existing DBs — `CREATE TABLE IF NOT EXISTS` handles it.

## SKU normalisation

`_norm_sku()` uppercases and strips spaces/hyphens before write/read. Frontend's `normSku()` does the same. All wishlist API paths receive whatever case the caller sends; the db normalises.

## Write paths

1. **`/search` → `_persist_search_groups`** (app.py): after grouping, for each group with at least one SKU, build a per-store dict like `{"goblin": {"price": 24.50, "url": "..."}, "wayland": {"price": null, "url": "..."}}` (price=null when out of stock; store omitted if retailer didn't return that SKU). Calls `db.upsert_from_retailer(sku, title, image, prices)` for each sku in the group — overwrites `prices_json` entirely on every search. For SKU queries where retailers didn't echo back a SKU, the query string itself is used as the authoritative SKU.
2. **`/manufacturer/{slug}/{range}` → `_persist_manufacturer_products`**: for each product with a SKU, calls `db.upsert_from_manufacturer(sku, title, image, mfr_slug, price)`. Sets/overwrites `manufacturer_slug` and `manufacturer_price`. Does not touch `prices_json`.
3. **`POST /api/wishlist/{sku}`**: inserts the row if missing, or sets `wishlisted_at = now` only if currently NULL (idempotent re-adds don't bump the timestamp). Uses `COALESCE(products.wishlisted_at, excluded.wishlisted_at)` in the ON CONFLICT branch.
4. **`DELETE /api/wishlist/{sku}`**: `UPDATE products SET wishlisted_at = NULL` — row stays in cache.
5. **`POST /api/hide/{sku}`**: upserts with `hidden = 1`. If the SKU has never been seen via search, this creates a skeleton row (sku + hidden + updated_at only) so the flag persists even before any price data.
6. **`DELETE /api/hide/{sku}`**: `UPDATE products SET hidden = 0`.
7. **`POST /api/hide-range/{man_slug}/{range_slug}`**: `INSERT OR IGNORE` into `hidden_ranges`.
8. **`DELETE /api/hide-range/{man_slug}/{range_slug}`**: `DELETE FROM hidden_ranges` where (man_slug, range_slug) matches.

All upserts use `COALESCE` for `title` to avoid blanking existing values. For `image_url`: retailer upserts use `COALESCE(products.image_url, excluded.image_url)` — existing image wins (manufacturer images are higher quality and shouldn't be overwritten by retailer thumbnails). Manufacturer upserts use `COALESCE(excluded.image_url, products.image_url)` — new manufacturer image wins.

## prices_json shape

```json
{
  "goblin":    {"price": 24.50, "url": "https://..."},
  "wayland":   {"price": null,  "url": "https://..."},
  "firestorm": {"price": 19.99, "url": "https://..."}
}
```

- `price` is the number when in stock, `null` when out of stock.
- A store key being absent means the retailer didn't return that SKU in the latest search.
- The whole JSON is overwritten on each search — there is no merging of older entries.
- Wishlist frontend tolerates the legacy shape `{slug: number_or_null}` too, in case rows pre-date the url addition.

## Wishlist page

`/wishlist` returns the same SPA shell. Frontend's `showWishlist()`:
1. Fetches `/api/wishlist` (items + retailer meta).
2. Converts each item's `prices` dict into the same `{offers, cheapest_*, any_in_stock, skus, title, image_url}` group shape that `/search` produces.
3. Reuses `card()` to render. The heart is filled because the SKU is in `wishlistSet`. Clicking it removes the row from the list on next render.

## Notes

- No FTS, no indexes beyond the PK — single user, table will stay small.
- Additive columns (like `hidden`) are added via ALTER TABLE migration on startup — no need to delete the DB.
- Destructive schema changes (rename/remove columns, change types) still require deleting `main.db`.
- `minis` is a manual integer column with no UI yet — populate via direct sqlite or a future admin endpoint.
