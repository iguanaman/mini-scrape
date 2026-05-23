# Mini Market — project notes for Claude

Personal tool for browsing miniature wargaming products by manufacturer range, with retailer prices. Home page shows manufacturer sections with range pills — clicking a range expands inline product cards sorted by price-per-mini. Cards show a price sticker, wishlist heart, hide eye, owned counter, and minis counter. Clicking a card image opens a lightbox. Store-filter icons in the header filter cards and offer rows to selected retailers.

The card heart button cycles three states: empty (not wishlisted) → red filled (wishlisted) → gold filled (loved, a higher tier of wishlist). A 4-state nav filter button (all/not-wishlisted/wishlisted/loved) is shown in the header on all pages.

## Deep-dive references
Read these on demand — not loaded by default:
- `docs/retailers.md` — per-retailer scraping specifics.
- `docs/manufacturers.md` — per-manufacturer specifics.
- `docs/internals.md` — frontend layout, data flow, static mode details.
- `docs/db.md` — sqlite schema, write paths, wishlist behaviour.

## Stack
- Python 3.11+, uv-managed venv
- FastAPI (no Jinja2 — `index.html` served as a static file via `FileResponse`)
- **curl_cffi** for all HTTP (TLS impersonation, `chrome120`). Replaces httpx because Wayland is behind PerimeterX.
- selectolax for HTML parsing where retailers don't have JSON APIs
- **sqlite** (`main.db`) for persistent product cache + wishlist + hidden flags. Single file, additive `ALTER TABLE` migrations on startup (idempotent). See `docs/db.md`.
- Frontend: `index.html` at repo root, vanilla JS + Tailwind CDN. Fetches `/static/data.json` on load (served dynamically by FastAPI in live mode, as a real file in static mode).

## Modes

**Live mode** (`uv run uvicorn app:app`): FastAPI intercepts `GET /static/data.json` and returns fresh DB data. Write APIs (wishlist, owned, hide, minis) are active. `STATIC_MODE = false`.

**Static mode** (`python -m http.server 8080 --bind 127.0.0.1` or GitHub Pages): `index.html` and `static/` are served as files. `GET /api/ping` fails → `STATIC_MODE = true`. Write APIs silently no-op. Wishlist, owned, hide, minis are display-only. Run `export_static.py` first to generate `static/data.json`.

In static mode: owned/minis show label only (no +/− controls), hide button hidden, heart shows permanently if wishlisted but is not clickable. Settings gear icon is hidden in static mode.

**Admin mode** (live mode only): toggled via the gear icon in the nav header (after store filter icons, separated by a divider). Off by default; state persists in `localStorage`. When off, pills show a muted count badge of visible products for that range (updates with filters). When on, pills show the hide-eye and delete-× icons, and group labels show the delete icon.

## Layout
```
app.py                  FastAPI app — serves index.html, /static/data.json (live DB data),
                        write APIs (/api/wishlist, /api/hide, /api/owned, /api/minis, /api/hide-range,
                        /api/range, /api/group), /api/ping
db.py                   sqlite helpers (products + wishlist + hidden columns), schema init + migrations
index.html              Frontend (repo root) — fetches /static/data.json, renders manufacturer
                        sections + range pills + product cards, lightbox, store filters
retailers/
  __init__.py           IMPERSONATE = "chrome120"
  goblin.py             Shopify /search?q=... HTML + ld+json Product blocks
  wayland.py            Magento GraphQL via /api/graphql (productSearch op, relevance sort)
  element.py            Custom-platform HTML, selectolax
  firestorm.py          Custom-platform HTML (/products?q=), selectolax
  overlord.py           Shopify /search/suggest.json (Overlord Games)
  nemc.py               WooCommerce HTML /?s=<q> (North East Model Centre)
manufacturers/
  __init__.py           MANUFACTURERS list
  northstar.py          North Star Figures — list.php?man=<id>&page=<n>. 17 ranges in 3 groups.
  wargamesatlantic.py   Wargames Atlantic — Shopify collections/{handle}/products.json
  gamesworkshop.py      Games Workshop — Algolia search index (app M5ZIQZNQ2H, public key).
                        ~70 ranges grouped by game system.
  victrix.py            Victrix — Shopify (collections/{handle}/products.json). 28mm only.
  mantic.py             Mantic — WooCommerce Store API (/wp-json/wc/store/v1/products).
  warlord.py            Warlord Games — Shopify at store.warlordgames.com.
  perry.py              Perry Miniatures — WooCommerce HTML, top sub-categories only.
  grippingbeast.py      Gripping Beast — legacy CMS, tree-walks deep category hierarchy.
scripts/
  scrape_manufacturers.py  Batch-scrape all manufacturer ranges into the DB. Writes title,
                           image_url, manufacturer_slug, range_slug, manufacturer_url,
                           description. Never writes prices. Runs manufacturers in parallel;
                           per-host throttling via _ThrottledSession.
                           Run: uv run python scripts/scrape_manufacturers.py
  scrape_prices.py         Batch-scrape retailer prices for all SKU'd products in the DB.
                           Updates prices_json + updated_at only. Supports --manufacturer,
                           --range, --concurrency (default 3) flags.
                           Run: uv run python scripts/scrape_prices.py
  fill_minis.py            Iterates non-hidden products without a category, calls local Llama
                           to infer mini count. Writes minis (int or NULL) + category.
                           Run scrape_manufacturers.py first to populate descriptions.
                           --overwrite redoes all non-hidden rows.
                           Run: uv run python scripts/fill_minis.py [--overwrite]
  export_static.py         Writes static/data.json from the DB (manufacturers, retailers,
                           wishlist, owned). Run before serving statically.
                           Run: uv run python scripts/export_static.py
  export_csv.py            Exports both wishlist and owned products to CSV (sku, title, manufacturer,
                           description, min_price, minis, price_per_mini). Writes wishlist_export.csv
                           and owned_export.csv to .tmp/. Run: uv run python scripts/export_csv.py
docs/                   Deep-dive references (see above).
static/icons/           Retailer + manufacturer favicons
static/data.json        Exported DB snapshot for static mode. Committed (served by GitHub Pages).
.vscode/tasks.json      VS Code tasks: dev server, scrape manufacturers, scrape prices,
                        export static, serve static, fill minis, Llama server.
.tmp/                   Scratch scripts + HTML/JSON dumps. Gitignored.
server.txt              Server log (stdout + file). Gitignored.
main.db                 sqlite product cache + wishlist. Gitignored.
```

## Retailer interface
Each module exposes:
```python
SLUG: str       # short id, e.g. "goblin"
NAME: str       # display name
ICON: str       # /static/icons/<file>.<ext>
async def search(query: str, client: curl_cffi.requests.AsyncSession) -> list[dict]
```
Each returned item:
```python
{
  "retailer": str, "retailer_slug": str, "retailer_icon": str,
  "title": str, "url": str,
  "price": float | None, "rrp": float | None,
  "in_stock": bool, "image_url": str | None,
  "sku": str | None,
}
```

## Manufacturer interface
```python
SLUG: str
NAME: str
ICON: str
RANGES: list[dict]    # each has at least {"slug": str, "name": str, ...}
                      # optional "group": str — frontend renders pills under per-group headers.
async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]
```
Each returned product:
```python
{"title": str, "sku": str | None, "url": str, "image_url": str | None, "price": float | None,
 "description": str | None}
```

## Endpoints
- `GET /` / `/wishlist` / `/owned` — serve `index.html` (FileResponse)
- `GET /static/data.json` — intercepted by FastAPI, returns `_build_home_data()` fresh from DB
- `GET /api/ping` — `{"ok": true}`. Used by frontend to detect live vs static mode.
- `POST /api/wishlist/{sku}` / `DELETE /api/wishlist/{sku}` — add/remove wishlist (DELETE also clears loved)
- `POST /api/loved/{sku}` / `DELETE /api/loved/{sku}` — set/clear loved state (also ensures wishlisted)
- `POST /api/hide/{sku}` / `DELETE /api/hide/{sku}` — hide/unhide product
- `POST /api/hide-range/{man_slug}/{range_slug}` / `DELETE` — hide/unhide range pill
- `DELETE /api/range/{man_slug}/{range_slug}` — delete range and all its products
- `DELETE /api/group/{man_slug}/{group_name}` — delete a pill group
- `POST /api/owned/{sku}` — set owned count `{"count": N}`
- `POST /api/minis/{sku}` — set minis count `{"count": N}`

## "New retailer" workflow
1. Open in Playwright MCP (`browser_navigate`), find the search form, submit it.
2. Capture network calls with `browser_network_requests` — look for the actual data endpoint. Replicate via `browser_network_request`.
3. Replicate with curl_cffi. Confirm same response.
4. Write parser in `retailers/<name>.py`. Test via `.tmp/test_<name>.py`.
5. Fetch favicon into `static/icons/<slug>.{ext}`.
6. Wire into `RETAILERS` list in `app.py`. Add section to `docs/retailers.md`.

## "New manufacturer" workflow
1. Inspect the manufacturer site to find range listing pages.
2. Add module to `manufacturers/` with `SLUG`, `NAME`, `ICON`, `RANGES`, `fetch_range`.
3. Add `group` to `RANGES` entries if the manufacturer has many ranges that fall into categories.
4. Add icon to `static/icons/`. Wire into `manufacturers/__init__.py`.
5. Add section to `docs/manufacturers.md`.

## Conventions
- **Before committing any change**: update CLAUDE.md and the relevant `docs/` file to reflect the new state. This is mandatory — docs update comes before the commit, not after.
- **Always commit directly to main** — never create branches or worktrees.
- Working directory is already the project root — never `cd` before running bash commands.
- Server does not use `--reload`. Any `.py` change requires a manual server restart. After editing only `index.html` or static assets, tell the user to refresh — no restart needed.
- For ad-hoc Python probes, write a script to `.tmp/<name>.py` then run `uv run python .tmp/<name>.py`.
- Single user, localhost only — no auth, no rate limiting, no retries.
- Tmp scratch scripts go in `.tmp/` (gitignored).
- Playwright MCP is configured at project scope in `.mcp.json`.
- After completing any code change, automatically commit with a descriptive message.

## Run
```
uv run uvicorn app:app
```
or hit `Ctrl+Shift+B` in VS Code (default build task).

## Static / GitHub Pages workflow
```
uv run python scripts/export_static.py   # writes static/data.json
python -m http.server 8080 --bind 127.0.0.1   # test locally
```
For GitHub Pages: push repo, enable Pages from main branch root.

## Communication Style

The user is a developer who cares about code quality but doesn't know this specific codebase. Discuss features in plain terms. Don't reference specific files, functions, or code structure unless the user asks. Keep to a high level.

When brainstorming or designing, don't ask about implementation details — choose sensible defaults. Only ask when there's a genuine product decision the user needs to make.
