# mini-scrape — project notes for Claude

Personal localhost tool. Type a product name (or SKU), see prices from 4 UK miniature wargaming retailers as grouped product cards sorted by cheapest in-stock price. Home page also shows hardcoded manufacturer ranges — clicking a range fetches the manufacturer's product list directly. Clicking a product card with no prices triggers a background SKU search (shimmer animation, non-clickable while loading) and updates the sticker live; a second click opens the search tab. Cards with prices already cached open the search tab immediately.

## Deep-dive references
Read these on demand — not loaded by default:
- `docs/retailers.md` — per-retailer scraping specifics (Goblin, Wayland, Firestorm, Element).
- `docs/manufacturers.md` — per-manufacturer specifics (North Star, Wargames Atlantic, Games Workshop).
- `docs/internals.md` — `/search` pipeline, grouping algorithm, frontend layout details.
- `docs/db.md` — sqlite schema, write paths, wishlist behaviour.

## Stack
- Python 3.11+, uv-managed venv
- FastAPI + Jinja2
- **curl_cffi** for all HTTP (TLS impersonation, `chrome120`). Replaces httpx because Wayland is behind PerimeterX and plain httpx gets 403. Standardising on one client across retailers + manufacturers.
- selectolax for HTML parsing where retailers don't have JSON APIs
- **sqlite** (`main.db`) for persistent product cache + wishlist + hidden flags. Single file, additive `ALTER TABLE` migrations on startup (idempotent). See `docs/db.md`.
- Frontend: one Jinja template + vanilla JS + Tailwind CDN. Sticky header (home/wishlist links + centered search + store-filter icons). Collapsible left sidebar with shipping thresholds. Grid cards with heart (wishlist) and eye (hide) icon toggles on SKU'd cards — both fade in on hover (500ms), heart stays visible when wishlisted.

## Layout
```
app.py                  FastAPI app, /search, /manufacturers, /manufacturer/{slug}/{range},
                        /wishlist (page) + /api/wishlist[...], grouping, in-memory caches, logging
db.py                   sqlite helpers (products + wishlist + hidden columns), schema init + migrations on startup
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
  northstar.py          North Star Figures — list.php?man=<id>&page=<n>
  wargamesatlantic.py   Wargames Atlantic — Shopify collections/{handle}/products.json
  gamesworkshop.py      Games Workshop — piggybacks on Goblin Gaming's Shopify storefront
                        (GW's own site is AWS-WAF walled). ~70 ranges grouped by game system,
                        SKUs populated from Goblin's variant fields.
  victrix.py            Victrix — Shopify (collections/{handle}/products.json). 28mm only.
  mantic.py             Mantic — WooCommerce Store API (/wp-json/wc/store/v1/products).
  warlord.py            Warlord Games — Shopify at store.warlordgames.com.
  perry.py              Perry Miniatures — WooCommerce HTML, top sub-categories only.
  grippingbeast.py      Gripping Beast — legacy CMS, tree-walks deep category hierarchy.
docs/                   Deep-dive references (see above).
static/icons/           Retailer + manufacturer favicons
templates/index.html    Frontend
.vscode/tasks.json      "uv run uvicorn app:app --reload" as default build task
.tmp/                   Scratch scripts + HTML/JSON dumps. Gitignored. Dot-prefix so uvicorn's watchfiles default-excludes it from --reload watching.
server.txt              Server log (stdout + file). Gitignored.
.playwright-mcp/        Playwright MCP artefacts. Gitignored.
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
  "price": float | None, "rrp": float | None,   # rrp None when not greater than price
  "in_stock": bool, "image_url": str | None,
  "sku": str | None,                            # populated by Goblin + Wayland
}
```

All retailers hard-capped at **40 items** per search (slice in each module). Per-store request counts to hit that cap:
- Goblin: 1 (~48/page native)
- Wayland: 1 (pageSize=40 via GraphQL)
- Firestorm: 2 (20/page × 2 via `?resultpage=N`)
- Element: 1 (returns everything in one shot; we slice)
- Overlord: 1 (Shopify suggest.json, limit=40)
- NEMC: 1 (~25-35 inline results per query)

## Manufacturer interface
```python
SLUG: str
NAME: str
ICON: str
RANGES: list[dict]    # each has at least {"slug": str, "name": str, ...}
                      # optional "group": str — when present, the /manufacturers
                      # endpoint relays it and the frontend renders pills under
                      # per-group headers. Used by Games Workshop to bucket
                      # ~47 ranges (40k / AoS / Skirmish / Middle-earth / Hobby).
async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]
```
Each returned product:
```python
{"title": str, "sku": str | None, "url": str, "image_url": str | None, "price": float | None}
```
The range_def dict is opaque to the caller — each module reads whatever keys it needs (`man_id` for North Star, `handle` for WA, `path` for GW).

## Endpoints (overview)
- `GET /search?q=...` — runs all retailers in parallel, filters + groups, 15-min in-memory cache. For SKU queries, takes only the first result per retailer. Upserts all groups with at least one SKU into `products` (title/image/prices); for SKU queries with no retailer-provided SKU, uses the query itself as the SKU. Full pipeline + response shape in `docs/internals.md`.
- `GET /manufacturers` — list of manufacturers and their ranges for the home view. Each range includes `"hidden": bool`.
- `GET /manufacturer/{slug}/{range_slug}` — products for one range. 15-min cache. `price >= £15`, sorted by SKU. Upserts each SKU'd product into `products` (manufacturer slug + price).
- `GET /wishlist` — SPA shell, same template as `/`. Frontend switches to wishlist mode and renders cached prices.
- `GET /api/wishlist` — wishlisted product rows with retailers meta.
- `GET /api/wishlist/skus` — list of wishlisted SKUs (used to render hearts on cards).
- `POST /api/wishlist/{sku}` / `DELETE /api/wishlist/{sku}` — toggle wishlist flag.
- `POST /api/hide/{sku}` / `DELETE /api/hide/{sku}` — hide/unhide a product. Hidden SKUs are filtered from all `/search` and `/manufacturer/{slug}/{range}` responses server-side.
- `POST /api/hide-range/{man_slug}/{range_slug}` / `DELETE /api/hide-range/{man_slug}/{range_slug}` — hide/unhide a manufacturer range pill. State persists in `hidden_ranges` table; pill is greyed out (opacity-50) in the UI but remains clickable.

## Grouping (overview)
Same product across multiple retailers collapses into one card. Bucket by SKU first (item field, or SKU-pattern found in title), else by sorted title tokens. A second pass fuzzy-merges SKU-keyed and token-keyed groups for the same product (Levenshtein ≤ 1 on tokens ≥ 4 chars, ≥ 70% overlap), with a guard against merging sequence-marker variants (II / III / 2 / 3). Algorithm details + edge cases in `docs/internals.md`.

## "New retailer" workflow
1. Open in Playwright MCP (`browser_navigate`), find the search form, submit it.
2. Capture network calls with `browser_network_requests` — look for the actual data endpoint (JSON, GraphQL, or HTML). Replicate the request shape via `browser_network_request` (request-body / request-headers).
3. Replicate that exact request with curl_cffi. Confirm same response.
4. Write parser in `retailers/<name>.py`. Include `SLUG`, `NAME`, `ICON`. Test standalone via `.tmp/test_<name>.py`. Try to return `sku` if available — grouping is much better with it.
5. Fetch the retailer's favicon into `static/icons/<slug>.{ext}`.
6. Wire into `RETAILERS` list in `app.py`. Add a section to `docs/retailers.md`.

## "New manufacturer" workflow
1. Inspect the manufacturer site (Playwright MCP if JS-heavy, or curl_cffi if not) to find their range listing pages.
2. Add a module to `manufacturers/` with `SLUG`, `NAME`, `ICON`, `RANGES`, `async def fetch_range(range_def, client)`.
3. Each `RANGES` entry needs `slug` + `name` and whatever keys the scraper needs (man_id, handle, path, …). Add `group` if the manufacturer has many ranges that fall naturally into game systems / categories — the frontend will render pills under per-group headers.
4. Add icon to `static/icons/`. Wire module into `manufacturers/__init__.py`. No further `app.py` changes — the registry is read generically.
5. If the manufacturer's own site is hostile (WAF, JS challenges), it's fine to source the catalogue from one of the retailers we already scrape (see Games Workshop → Element).
6. Add a section to `docs/manufacturers.md`.

## Conventions
- After any significant change (new retailer, new manufacturer, new feature, schema change, behaviour change), update CLAUDE.md and the relevant `docs/` file to reflect the new state.
- Working directory is already the project root — never `cd` into it (or anywhere else) before running bash commands. Use relative paths.
- After editing any `.py` file, tell the user the server needs a restart before changes take effect. (uvicorn is started with `--reload`, but the user runs it manually and doesn't always have it on — call it out so they know.)
- For ad-hoc Python probes, write a script to `.tmp/<name>.py` then run `uv run python .tmp/<name>.py`. Do NOT use `uv run python -c "…"` with inline code — long inline commands trip permission prompts.
- Single user, localhost only — no auth, no rate limiting, no retries.
- 15s timeout per request.
- Errors fail loudly in dev (logged with stacktraces to server.txt), gracefully in UI.
- Tmp scratch scripts go in `.tmp/` (gitignored). Use them to dump raw HTML/JSON before writing a parser.
- Playwright MCP is configured at project scope in `.mcp.json` — useful for inspecting JS-rendered pages and network calls.
- 15-minute in-memory caches for `/search` and `/manufacturer/{slug}/{range}`. Wiped on `--reload`.

## Run
```
uv run uvicorn app:app --reload
```
or hit `Ctrl+Shift+B` in VS Code (default build task).

## Communication Style

The user is a developer who cares about code quality but doesn't know this specific codebase and doesn't want to think about it. Discuss features and behaviour in plain terms — technical concepts are fine, but don't reference specific files, functions, or code structure unless the user asks. Keep to a high-level.

When describing how something works, talk about user-visible behaviour and modes ("reveal mode — block fades in all at once", "typing mode — types out character by character"), not implementation names. Don't say "the `typeBlock` function reserves min-height" — say "the typing path makes space appear instantly". Name code things only when the user needs to act on them.
