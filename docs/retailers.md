# Retailer specifics

Per-retailer scraping notes. Each lives in `retailers/<slug>.py`.

## Goblin Gaming
`GET /search?q=<query>` (full HTML page). Parse all `<script type="application/ld+json">` blocks; keep entries where `@type == "Product"`. Each block has `name`, `sku`, `url` (relative), `image` (protocol-relative), `offers.price`, `offers.availability` (`http://schema.org/InStock` or `OutOfStock`).
- One page returns ~48 products natively. We slice to 40.
- Previously used `/search/suggest.json` (smaller, faster), but that endpoint doesn't index SKU lookups. The full-page response is ~300-800KB but reliably finds products by SKU and exposes the SKU back to us (needed for cross-store grouping).
- URLs from ld+json include tracking params (`?_pos=...`); we strip the query string.
- `name` values come pre-encoded (`&amp;` etc.) — we `html.unescape()` them before storing.

## Wayland Games
Behind PerimeterX — TLS fingerprinting via curl_cffi gets through; plain httpx is blocked (403). The HTML search page is a Next.js SPA that loads results client-side via GraphQL.

`POST https://www.waylandgames.co.uk/api/graphql` with op `productSearch`. Variables: `{search, pageSize, sort: {relevance: DESC}}`. We use pageSize 40. **Relevance sort is critical** — without it, "Stargrave Scavengers II" can fall outside the first 40 results for query "stargrave" even though `total_count` includes it. Magento's default order isn't relevance.

Schema (snake_case Magento): `name`, `sku`, `image.url`, `price_range.minimum_price.{regular_price, final_price}.value`, `stock_status`.

Required-looking headers: `content-type: application/json`, `content-currency: GBP`. Referer set to a `/search?query=…` URL to look natural.

Post-filter: drop items where `stock_status != "IN_STOCK"` *inside the retailer module* (Wayland returns lots of out-of-stock noise; pruning early stops it from creating solo groups).

**If you get 403s:** cookies have expired. Visit https://www.waylandgames.co.uk in Chrome, solve any challenge, then run `uv run python scripts/capture_wayland_cookies.py`. Cookies are stored in the DB `meta` table under `wayland_cookies` and injected into every GraphQL request. Default browser is Chrome; pass `--browser edge` or `--browser firefox` if needed.

## Firestorm Games
`GET https://www.firestormgames.co.uk/products?q=<query>` (custom "totalretail" platform). Server-rendered HTML, 20 items per page.
- Pagination via **`?resultpage=N`** (NOT `?page=N` — that param is ignored and returns page 1). We fetch pages 1 and 2 (= 40 max).
- Cards: `.product-list .item .item-inner`. Title in `.bottom-section .title`; image is a CSS `background-image: url(...)` on `.image span[style]`; URL is the parent `<a href>`.
- Price: `.price` block. When it also has class `.special`, there's a nested `.small` element = RRP; the remainder = final price. Otherwise just one price.
- Fallback: `.add-to-basket-list[data-price]` if `.price` parse fails.
- Stock: `.banner` text — "X in Stock" / "24HR Dispatch*" = in stock; "Out of stock" = not.
- No SKU on the listing page (only on the product page).
- No effective in-stock filter param found.

## Element Games
`GET https://elementgames.co.uk/search?q=<query>` (custom platform). Server-rendered HTML — **returns every matching product in one response** (hundreds for broad queries); we slice to 40.
- Cards: `.productgrid`. Title `h3.producttitle`; image `img.productimage[src,alt]`; URL relative `<a href>`.
- Price: `.price` element. `.oldprice` (when present) is RRP.
- Stock detection: each card contains a `.stock_popup` legend showing all four button colours (green/yellow/blue/red) — naive grep for `green-button`/`red-button` would always match. We `decompose()` the popup first, then look at the remaining text for "in stock"/"dispatch" vs "out of stock"/"unavailable".
- No SKU on the listing page (only on the product page — labelled "SKU / Product Code").
- Pagination params (`page`, `p`, etc.) are ignored — single response has everything.

## Overlord Games
Shopify store. We use `GET /search/suggest.json?q=<query>&resources[type]=product&resources[limit]=40`.
- Returns JSON: `resources.results.products[]` with `title`, `handle`, `url` (relative, with tracking query — stripped), `image`, `price`/`price_min`, `compare_at_price_max` (RRP), `available`.
- No SKU exposed by the suggest endpoint.
- The HTML `/search?q=` page is also Shopify-standard but ~580KB and would require parsing; suggest.json is much cheaper.

## North East Model Centre
WordPress + WooCommerce. `GET /?s=<query>` returns a server-rendered search page with ~25-35 results inline. **Do not pass `post_type=product`** — adding that filter strips the products out of the response (only CSS rules remain).
- The WC Store API (`/wp-json/wc/store/v1/products?search=...`) is rate-limited (429) by their host.
- Cards: `.ps-card-search`. Title `.ps-name`; image `img.ps-img[src]`; URL is the parent `<a href*='/product/']` (strip query).
- Price: `.ps-active-price` is the active price (sale or normal); when on sale, `.ps-price` (line-through sibling) is the RRP. If no `.ps-active-price`, fall back to `.ps-price` as the normal price.
- Stock: explicit `.in-stock` / `.out-of-stock` element inside the card.
- SKU: the `.ps-brand` line prefixed with "Part no:" — extract the inner `<span>` text.
