# mini-scrape — project notes for Claude

Personal localhost tool. Type a product name (or SKU), see prices from 4 UK miniature wargaming retailers as grouped product cards sorted by cheapest in-stock price.

## Stack
- Python 3.11+, uv-managed venv
- FastAPI + Jinja2
- **curl_cffi** for all HTTP (TLS impersonation, `chrome120`). Replaces httpx because Wayland is behind PerimeterX and plain httpx gets 403. Standardising on one client across all retailers.
- selectolax for HTML parsing where retailers don't have JSON APIs
- Frontend: one Jinja template + vanilla JS + Tailwind CDN (sticky search bar, flex-wrap centered cards, collapsible left sidebar with shipping thresholds)

## Layout
```
app.py                  FastAPI app, /search, grouping, in-memory cache, logging
retailers/
  __init__.py           IMPERSONATE = "chrome120"
  goblin.py             Shopify /search?q=... HTML + ld+json Product blocks
  wayland.py            Magento GraphQL via /api/graphql (productSearch op)
  element.py            Custom-platform HTML, selectolax
  firestorm.py          Custom-platform HTML (/products?q=), selectolax
static/icons/           Retailer favicons (goblin.webp, wayland.png, firestorm.png, element.ico)
templates/index.html    Frontend
.vscode/tasks.json      "uv run uvicorn app:app --reload" as default build task
tmp/                    Scratch scripts + HTML/JSON dumps. Gitignored.
server.txt              Server log (stdout + file). Gitignored.
.playwright-mcp/        Playwright MCP artefacts. Gitignored.
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

## /search endpoint
- Runs all retailers in parallel via `asyncio.gather(return_exceptions=True)` on one shared `curl_cffi.requests.AsyncSession(impersonate="chrome120", timeout=15)`. One retailer failing doesn't break others; the exception is logged to `server.txt` and surfaced in the response `errors` map.
- 15-minute in-memory dict cache keyed on lowercased+stripped query. Process-local; wiped on `--reload`.
- Post-processing pipeline (in order):
  1. Title token filter — keep items whose title contains every ≥2-char token from the query (`_query_tokens` / `_title_matches`).
  2. In-stock filter — drop anything not in stock.
  3. Price floor — drop anything below £15 or with no price.
  4. Sort by price asc.
  5. Group via `_group_results`.
- Response shape:
```json
{
  "query": "...",
  "cached": false,
  "results": [...],          // flat post-filter list, sorted by price
  "groups": [...],           // grouped product cards (see below)
  "retailers": [             // for the frontend to render "Not found" rows
    {"slug": "...", "name": "...", "icon": "..."},
    ...
  ],
  "errors": {"Retailer Name": "ExcType: msg"}
}
```

## Grouping (`app.py:_group_results`)
Same product across multiple retailers → one card.

**Pass 1 — initial bucketing by `_group_key`:**
1. `item.sku` if present (uppercased, dashes/spaces stripped) → `sku:SGVP003`.
2. Else SKU-like pattern in title (e.g. `SGVP003`, `MUH094204`) via `_SKU_RE` → `sku:...`.
3. Else sorted unique title tokens minus stopwords (`the, a, an, of, and, for, to, in`) → `tokens:stargrave troopers`.

**Pass 2 — merge equivalent groups:**
Some retailers return SKU and some don't (Goblin/Wayland have SKU; Firestorm/Element don't in listings), so the same product can land in a `sku:...` group AND a `tokens:...` group. We merge two groups when their title token-sets are equal or one is a subset of the other. Prefer the shorter title (Goblin appends collection name like " - Stargrave"); take the union of tokens.

**Per-group fields built up:**
- `offers[]` — every offer for this group (one per matching retailer hit), sorted in-stock-first then price asc.
- `cheapest_*` — the cheapest **in-stock** offer (price / url / retailer / icon). Falls back to first offer if none in stock (rare, since post-filter drops out-of-stock).
- `any_in_stock` — bool. Used by the frontend to render "No stock" sticker when false.

Groups themselves sort: any-in-stock first, then by cheapest price asc.

## Retailer specifics

### Goblin Gaming
`GET /search?q=<query>` (full HTML page). Parse all `<script type="application/ld+json">` blocks; keep entries where `@type == "Product"`. Each block has `name`, `sku`, `url` (relative), `image` (protocol-relative), `offers.price`, `offers.availability` (`http://schema.org/InStock` or `OutOfStock`).
- Previously used `/search/suggest.json` (smaller, faster), but that endpoint doesn't index SKU lookups. The full-page response is ~314KB vs ~10KB but reliably finds products by SKU and exposes the SKU back to us (needed for cross-store grouping).
- Returns up to 10 results (we slice the ld+json blocks).
- URLs from ld+json include tracking params (`?_pos=...`); we strip the query string.

### Wayland Games
Behind PerimeterX — TLS fingerprinting via curl_cffi gets through; plain httpx is blocked (403). The HTML search page is a Next.js SPA that loads results client-side via GraphQL.

`POST https://www.waylandgames.co.uk/api/graphql` with op `productSearch`. Variables: `{search, pageSize}` (we use pageSize 10). Schema is snake_case Magento — fields used: `name`, `sku`, `image.url`, `price_range.minimum_price.{regular_price, final_price}.value`, `stock_status`.

Required-looking headers: `content-type: application/json`, `content-currency: GBP`. Referer set to a `/search?query=…` URL to look natural.

Post-filter: drop items where `stock_status != "IN_STOCK"` *inside the retailer module* (Wayland returns lots of out-of-stock noise; pruning early stops it from creating solo groups).

### Firestorm Games
`GET https://www.firestormgames.co.uk/products?q=<query>` (custom "totalretail" platform). Server-rendered HTML.
- Cards: `.product-list .item .item-inner`. Title in `.bottom-section .title`; image is a CSS `background-image: url(...)` on `.image span[style]`; URL is the parent `<a href>`.
- Price: `.price` block. When it also has class `.special`, there's a nested `.small` element = RRP; the remainder = final price. Otherwise just one price.
- Fallback: `.add-to-basket-list[data-price]` if `.price` parse fails.
- Stock: `.banner` text — "X in Stock" / "24HR Dispatch*" = in stock; "Out of stock" = not.
- No SKU on the listing page (only on the product page).
- Listing capped at 20 per page; we don't paginate.

### Element Games
`GET https://elementgames.co.uk/search?q=<query>` (custom platform). Server-rendered HTML.
- Cards: `.productgrid`. Title `h3.producttitle`; image `img.productimage[src,alt]`; URL relative `<a href>`.
- Price: `.price` element. `.oldprice` (when present) is RRP.
- Stock detection: each card contains a `.stock_popup` legend showing all four button colours (green/yellow/blue/red) — naive grep for `green-button`/`red-button` would always match. We `decompose()` the popup first, then look at the remaining text for "in stock"/"dispatch" vs "out of stock"/"unavailable".
- No SKU on the listing page (only on the product page — labelled "SKU / Product Code").
- Bare `?q=...` sometimes returns 403; adding any extra param avoids it. We currently send just `q` and haven't hit issues, but worth knowing.

## Frontend (`templates/index.html`)
- Sticky header with centered search input + button. Search syncs with URL (`?q=...`) so it's bookmarkable; `popstate` re-runs the search on back/forward; on initial load if URL has `?q=` it auto-searches.
- Collapsible left sidebar (peek ~36px showing chevron) listing free-shipping thresholds: Wayland £20, Firestorm £60, Goblin £75, Element £80.
- `#grid` is `flex flex-wrap justify-center` so a single result sits centered. Each card is fixed `w-72`.
- Card anatomy:
  - 240px image area, `object-contain`, clickable → cheapest store's product page (only if any in stock).
  - Jagged starburst sticker (CSS `clip-path` polygon, 14 points), cream/amber gradient, rotated -6°, positioned `bottom-8 right-3`. Shows cheapest price OR "No stock" when none of the offers are in stock.
  - Title under image (`line-clamp-2`).
  - Four retailer rows, always all four shown:
    - In stock: clickable link → store, shows price.
    - Out of stock: clickable link → store, italic "No stock".
    - Not in this group: greyed, italic "Not found", not clickable.

## "New retailer" workflow
1. Open in Playwright MCP (`browser_navigate`), find the search form, submit it.
2. Capture network calls with `browser_network_requests` — look for the actual data endpoint (JSON, GraphQL, or HTML). Replicate the request shape via `browser_network_request` (request-body / request-headers).
3. Replicate that exact request with curl_cffi. Confirm same response.
4. Write parser in `retailers/<name>.py`. Include `SLUG`, `NAME`, `ICON`. Test standalone via `tmp/test_<name>.py`. Try to return `sku` if available — grouping is much better with it.
5. Fetch the retailer's favicon into `static/icons/<slug>.{ext}`.
6. Wire into `RETAILERS` list in `app.py`. Add a section to this file.

## Conventions
- Single user, localhost only — no auth, no rate limiting, no retries.
- 15s timeout per request.
- Errors fail loudly in dev (logged with stacktraces to server.txt), gracefully in UI.
- Tmp scratch scripts go in `tmp/` (gitignored). Use them to dump raw HTML/JSON before writing a parser.
- Playwright MCP is configured at project scope in `.mcp.json` — useful for inspecting JS-rendered pages and network calls.
- Build order from the original spec is complete (1-5); step 6 (per-retailer streaming) deferred — current UX is "one shot, all retailers, then render".

## Run
```
uv run uvicorn app:app --reload
```
or hit `Ctrl+Shift+B` in VS Code (default build task).
