# Internals

Deep details of the /search pipeline, grouping algorithm, and frontend layout.

## /search endpoint
- Runs all retailers in parallel via `asyncio.gather(return_exceptions=True)` on one shared `curl_cffi.requests.AsyncSession(impersonate="chrome120", timeout=15)`. One retailer failing doesn't break others; the exception is logged to `server.txt` and surfaced in the response `errors` map.
- 15-minute in-memory dict cache keyed on lowercased+stripped query. Process-local; wiped on `--reload`.
- Post-processing pipeline (in order):
  1. **SKU cap**: if the query is a SKU (`_is_sku_query`), take at most one result per retailer (the first). Prevents unrelated results leaking in from stores that return a broad list.
  2. **Match filter** (`_matches`): if the query looks like a SKU (`_is_sku_query`: single token, ≥4 chars, mix of letters and digits), trust every retailer's results (they all index SKU server-side, but most don't echo it back in the title). Otherwise apply the title-token filter — keep items whose title contains every ≥2-char token from the query.
  3. In-stock filter — drop anything not in stock.
  4. Price floor — drop anything below £15 or with no price.
  5. Sort by price asc.
  6. Group via `_group_results`.
  7. **Persist**: `_persist_search_groups` upserts all groups that have at least one SKU. For SKU queries where retailers didn't echo back a SKU, the query string itself is used as the authoritative SKU.
  8. **Hidden filter**: any group where at least one SKU matches a row with `hidden = 1` in the DB is dropped before returning. Uses `_norm_sku` normalisation consistent with the DB write path.
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

## /manufacturers and /manufacturer/{slug}/{range_slug}
- `/manufacturers` → JSON `{manufacturers: [{slug, name, icon, ranges: [{slug, name}]}]}`. Used by the home page to render bordered company sections.
- `/manufacturer/{man}/{range}` → JSON `{manufacturer, range, products}`. Products come from `db.products_for_range` (cached in DB from prior scrapes). Hidden SKUs are filtered out before returning.

## Grouping (`app.py:_group_results`)
Same product across multiple retailers → one card.

**Pass 1 — initial bucketing by `_group_key`:**
1. `item.sku` if present (uppercased, dashes/spaces stripped) → `sku:SGVP003`.
2. Else SKU-like pattern in title (e.g. `SGVP003`, `MUH094204`) via `_SKU_RE` → `sku:...`.
3. Else sorted unique title tokens minus stopwords (`the, a, an, of, and, for, to, in`) → `tokens:stargrave troopers`.

**Pass 2 — fuzzy merge:**
Some retailers return SKU and some don't, so the same product can land in a `sku:...` group AND a `tokens:...` group. We merge two groups when ≥70% of the smaller token-set's tokens are found in the larger set, with fuzzy token equality (Levenshtein ≤ 1 for tokens of length ≥ 4). This catches:
- "Stargrave Troopers" (tokens) vs `SGVP003` group (sku, no title overlap with SKU)
- "USA Veterand & Command" vs "Marcher: USA Veterans and Command" — `veterand` ≈ `veterans` (edit distance 1)
- "Foot Knights" (Goblin sometimes appends collection name) vs "Foot Knights"

**Guard against false merges**: if the two token-sets disagree on a sequence marker (`II`, `III`, `2`, `3`, …), reject the merge. Prevents "Stargrave Scavengers" merging with "Stargrave Scavengers II".

When merging: keep the shorter title (Goblin appends " - Range Name"), union tokens, append offers.

**Per-group fields built up:**
- `offers[]` — every offer for this group (one per matching retailer hit), sorted in-stock-first then price asc.
- `cheapest_*` — the cheapest **in-stock** offer (price / url / retailer / icon). Falls back to first offer if none in stock (rare, since post-filter drops out-of-stock).
- `any_in_stock` — bool. Used by the frontend to render "No stock" sticker when false.

Groups themselves sort: any-in-stock first, then by cheapest price asc.

## Frontend (`templates/index.html`)
- Sticky header: home link "mini-scrape" (left) + centered search input/button + store-filter icons (right, only shown when search results loaded). Search syncs with URL (`?q=...`) so it's bookmarkable; `popstate` re-runs the search; on initial load if URL has `?q=` it auto-searches, otherwise renders manufacturer sections.
- Home view (no `?q=`): bordered company sections, each with range "buttons". Click a range → expands inline, loads `/manufacturer/{slug}/{range}` lazily (once), shows product grid below the buttons. Product cards click to run a SKU-based search.
- Collapsible left sidebar: clicking anywhere on it opens; clicking outside closes. Lists free-shipping thresholds: Wayland £20, Firestorm £60, Goblin £75, Element £80.
- `#grid` is a CSS grid (4 columns) with fixed-width cards.
- **Store-filter icons** (in header, right side): one icon per retailer. Click to select that store (max one); click again or another to toggle. When a store is selected:
  - Cards where that store has no in-stock offer are pushed to end and visually `opacity-40 grayscale`.
  - Within every card, rows for *other* retailers are dimmed (icon `opacity-40`, text `text-gray-400`).
- Card anatomy (search results):
  - All cards have class `card-wrap` for hover-reveal CSS.
  - 240px image area, `object-contain`, clickable → cheapest store's product page (only if any in stock).
  - **Heart button** (top-left, SKU'd cards only): wishlist toggle. Invisible by default, fades in on card hover (500ms). Stays visible when wishlisted. Toggles `opacity-0` class on unwishlist.
  - **Eye button** (top-right, SKU'd cards only): hide toggle. Invisible by default, fades in on card hover (500ms). Clicking greys the card (`opacity-40 grayscale`) and switches to closed-eye icon; clicking again restores it. Hidden products don't appear on subsequent searches — the greyed state is just immediate visual feedback before the next load.
  - Jagged starburst sticker (CSS `clip-path` polygon, 14 points), cream/amber gradient, rotated -6°, positioned `bottom-8 right-3`. Shows cheapest price OR "No stock" when none of the offers are in stock.
  - Title under image (`line-clamp-2`).
  - Retailer rows, **sorted**: in-stock by price asc (tiebreak by free-shipping threshold asc — cheaper shipping first), then out-of-stock, then not-found. Layout: small icon + retailer name on left, price / "No stock" / "Not found" on right.
- Card anatomy (manufacturer products, simpler): image, title, SKU (small/mono), price sticker. **Click-to-fetch**: cards with no retailer prices (`data-price-state="idle"`) show a shimmer animation on first click while a background `/search?q=<sku>` runs; once resolved the sticker updates to the cheapest in-stock price (green gradient) or "No stock". Card is non-clickable during the fetch (`pointer-events: none`). Multiple clicks queue up with a 1.5s gap between fetches. Second click (state `loaded`) opens `/?q=<sku>` in a new tab. Cards that already have cached retailer prices start in `loaded` state and open the search tab immediately. Price stickers are green on all card types (search results and manufacturer products) when in stock.
