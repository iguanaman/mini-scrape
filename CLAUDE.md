# mini-scrape — project notes for Claude

Personal localhost tool. Type a product name, see prices from 4 UK miniature wargaming retailers in one table sorted by price.

## Stack
- Python 3.11+, uv-managed venv
- FastAPI + Jinja2
- **curl_cffi** for all HTTP (TLS impersonation, `chrome120`). Replaces httpx because Wayland is behind PerimeterX and plain httpx gets 403. Standardising on one client across all retailers.
- selectolax for HTML parsing where retailers don't have JSON APIs
- Frontend: one Jinja template + vanilla JS + Tailwind CDN

## Layout
```
app.py                  FastAPI app, /search, in-memory cache, logging
retailers/
  __init__.py           IMPERSONATE = "chrome120"
  goblin.py             Shopify suggest.json (cleanest)
  wayland.py            Magento GraphQL via /api/graphql (productSearch op)
  element.py            Custom-platform HTML, selectolax. Stock detection ignores .stock_popup legend (contains all 4 button colours).
  firestorm.py          Custom-platform HTML (/products?q=), selectolax. Price has .special/.small for RRP, image is CSS bg-image.
templates/index.html    Frontend
.vscode/tasks.json      "uv run uvicorn app:app --reload" as default build task
tmp/                    Scratch scripts + HTML/JSON dumps. Gitignored.
server.txt              Server log (stdout + file). Gitignored.
```

## Retailer interface
Each module exposes:
```python
NAME: str
async def search(query: str, client: curl_cffi.requests.AsyncSession) -> list[dict]
```
Returns up to 10 items shaped:
```python
{
  "retailer": str, "title": str, "url": str,
  "price": float | None, "rrp": float | None,   # rrp None if not greater than price
  "in_stock": bool, "image_url": str | None,
}
```

## /search endpoint
- Runs all retailers via `asyncio.gather(return_exceptions=True)` — one failing doesn't break others.
- 15-min in-memory dict cache keyed on lowercased query.
- Response: `{query, cached, results (sorted by price asc, None last), errors: {RetailerName: msg}}`.

## Retailer specifics

### Goblin Gaming
Shopify Suggest API: `GET /search/suggest.json?q=...&resources[type]=product&resources[limit]=10`. JSON. Path: `resources.results.products[]`. Fields: `title`, `price`, `compare_at_price`, `available`, `url`, `featured_image.url`.

### Wayland Games
Behind PerimeterX — TLS fingerprinting via curl_cffi gets through; plain httpx is blocked (403). HTML search page is a Next.js SPA that loads results via GraphQL after hydration.

Endpoint: `POST https://www.waylandgames.co.uk/api/graphql` with op `productSearch`. Variables: `{search, pageSize}`. Schema is snake_case Magento (`price_range.minimum_price.regular_price.value`, `stock_status`).
Required-looking headers: `content-type: application/json`, `content-currency: GBP`. Referer set to a `/search?query=…` URL to look natural.

### Firestorm Games
Custom totalretail platform. Search at `GET /products?q=...`. Server-rendered HTML. Parse `.product-list .item .item-inner`: title in `.bottom-section .title`, price in `.price` (when has `.special` class, contains `.small` = RRP + remainder = final price), image is `background-image: url(...)` on span inside `.image`, stock text in `.banner` ("X in Stock" / "Out of stock").

### Element Games
Custom platform. Search at `GET /search?q=...`. Server-rendered HTML. Parse `.productgrid` cards: `h3.producttitle`, `.price`, `.oldprice` (RRP), `img.productimage[src,alt]`, `a[href]` for relative URL. Stock detection: strip `.stock_popup` (legend with all four button colours) then look at remaining text for "in stock"/"dispatch" vs "out of stock"/"unavailable".

## "New retailer" workflow
1. Open in Playwright MCP (`browser_navigate`), find the search form, submit it.
2. Capture network calls with `browser_network_requests` — look for the actual data endpoint (JSON, GraphQL, or HTML).
3. Replicate that exact request with curl_cffi. Confirm same response.
4. Write parser in `retailers/<name>.py`. Test standalone via `tmp/test_<name>.py`.
5. Wire into `RETAILERS` list in `app.py` + add to docs above.

## Build order (from spec)
1. ✅ Scaffold FastAPI + uv
2. ✅ Goblin + /search + minimal frontend
3. ✅ Wayland (GraphQL via curl_cffi)
4. ✅ Firestorm
5. ✅ Element
6. ⏳ Frontend polish (per-retailer streaming, error display)

## UI changes from spec
- Per user request: RRP, discount, and stock columns removed from the table; only in-stock items are shown (filtered server-side in /search). Schema still carries `rrp`/`in_stock` for completeness.

## Conventions
- Single user, localhost only — no auth, no rate limiting, no retries.
- 15s timeout per request.
- Errors fail loudly in dev (logged with stacktraces to server.txt), gracefully in UI.
- Tmp scratch scripts go in `tmp/` (gitignored). Use them to dump raw HTML/JSON before writing a parser.
- Playwright MCP is configured at project scope in `.mcp.json` — useful for inspecting JS-rendered pages and network calls.

## Run
```
uv run uvicorn app:app --reload
```
or hit `Ctrl+Shift+B` in VS Code (default build task).
