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
  element.py            TBD
  firestorm.py          TBD
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

### Element Games, Firestorm Games
Not implemented yet. Plan: dump a raw HTML sample first, prefer ld+json, fall back to selectolax selectors.

## Build order (from spec)
1. ✅ Scaffold FastAPI + uv
2. ✅ Goblin + /search + minimal frontend
3. ✅ Wayland (GraphQL via curl_cffi)
4. ⏳ Firestorm
5. ⏳ Element
6. ⏳ Frontend polish (per-retailer streaming, discount column already in, error display)

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
