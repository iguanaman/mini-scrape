# Internals

Deep details of the frontend layout, data flow, and static mode.

## Data flow

On page load, the frontend fetches `/static/data.json` and `/api/ping` in parallel (`Promise.allSettled`). The data fetch always goes to the same URL — in live mode FastAPI intercepts it and returns fresh DB data; in static mode it's a real file written by `export_static.py`. The ping result determines `STATIC_MODE`.

`HOME_DATA` shape:
```json
{
  "manufacturers": [
    {
      "slug": "northstar", "name": "North Star", "icon": "/static/icons/northstar.png",
      "ranges": [{"slug": "...", "name": "...", "hidden": false, "categories": [...], "min_ppm": 1.2}],
      "products_by_range": {"range-slug": [{...product...}]}
    }
  ],
  "manufacturers_meta": {"slug": {"slug": "...", "name": "...", "icon": "..."}},
  "retailers": [{"slug": "goblin", "name": "Goblin Gaming", "icon": "/static/icons/goblin.webp"}],
  "wishlist_skus": ["SKU1", "SKU2"],
  "wishlist_items": [{...product...}],
  "owned_items": [{...product...}]
}
```

Product shape in `products_by_range` / `wishlist_items` / `owned_items`:
```json
{
  "sku": "SGVP003", "title": "...", "image_url": "...", "manufacturer_url": "...",
  "prices": {"goblin": {"price": 22.50, "url": "..."}, "wayland": null},
  "owned": 1, "minis": 20, "category": "minis"
}
```

`prices` is a dict of retailer slug → `{"price": float|null, "url": str}`. A null value means the retailer was searched but had no stock.

## Static mode

`STATIC_MODE = true` when `/api/ping` fails (no live server). Effects:
- Write APIs (wishlist, owned, hide, minis) are no-op'd
- Hide button not rendered
- Heart shows permanently if wishlisted, not clickable
- Owned/minis show label only (no +/− controls, no hover animation)
- Range hide/delete buttons still rendered but their API calls fail silently

### Base path (sub-path hosting)

The frontend may be served from a sub-path (e.g. GitHub Pages at `/mini-scrape/`). A `BASE` constant is derived from the directory of `location.pathname`, and a `url()` helper rewrites root-relative app URLs (`/static/...`, `/api/...`) against it. External URLs (product `image_url`, `http(s)`/protocol-relative) pass through unchanged. All `fetch()` calls and data-driven icon `src` values go through `url()`; the `<head>` favicon and the hardcoded shipping-legend icons use plain relative paths (`static/icons/...`). Routing is query-based (`?page=wishlist`), so the page always loads at the site root and relative paths stay correct.

## Frontend layout

Sticky header: left — category/sort/filter controls; centre — Wishlist · Mini Market · Owned nav; right — retailer store-filter icons (small, `w-4 h-4`).

Collapsible left sidebar: click to open, click outside to close. Free-shipping thresholds per retailer.

Home view: bordered manufacturer sections. Each section has range pills. Clicking a pill expands an inline product grid below (lazy-loaded from `HOME_DATA.products_by_range`, not a network request). Other open ranges in the same section close.

Wishlist / Owned views: flat product grids, data from `HOME_DATA.wishlist_items` / `HOME_DATA.owned_items`. Nav links use `history.pushState` so URL updates without a page reload.

## Product cards

Card anatomy (240px image area):
- **Heart** (top-left, SKU'd only): wishlist toggle. Invisible by default, fades in on hover. Stays visible when wishlisted. In static mode: shows permanently if wishlisted, no interactivity.
- **Eye/hide** (top-right, SKU'd only): hides the card visually and persists via API. Not rendered in static mode.
- **Owned counter** (bottom-left, SKU'd only): blue pill. Hidden when 0, fades in on card hover. Hover reveals +/− controls (label fades out, inputs fade in via CSS). In static mode: always visible if > 0, label only, no controls.
- **Minis counter** (bottom-right, SKU'd only): green pill. Same fade behaviour as owned. In static mode: always visible if > 0, label only.
- **Price sticker** (bottom-right of image area, above minis): cream/purple radial gradient, rotated -6°. Shows cheapest in-stock price and price-per-mini. Updates dynamically when store filter changes.

Below image: title, SKU (prefixed with manufacturer name), offer rows (expand/collapse toggle). Offer rows sorted: in-stock by price asc, then out-of-stock.

## Store filter

One icon per retailer in the header. Each icon cycles three states on click: off → **selected** (black ring) → **lowest-only** (gold/amber bg) → off. State persists in `localStorage` (`selectedStores` + `lowestStores`). The active filter set is the union of selected + gold stores.

The filter only controls **which cards are visible** — offer rows and the price sticker always show every store (sticker = cheapest across all stores). When any store is active:
- Cards where none of the active stores have stock are hidden

A **gold (lowest-only)** store additionally requires the card's cheapest price *across all stores* to come from a gold store — i.e. the card only shows where that retailer actually beats every other retailer. With multiple gold stores, a card shows if any of them is the overall cheapest.

## Category / sort / filter controls

- **Category select**: populated from `categories` field on ranges. Filters cards to matching category. "minis" is default.
- **Sort select**: SKU / Name / Price/mini / Price. Re-sorts all visible grids in place.
- **< £X/mini filter**: hides cards whose price-per-mini exceeds threshold. Also hides range pills where all products exceed it.
- **Re-sort button**: re-applies current sort (useful after changing minis counts).

## Lightbox

Click a card image → lightbox opens with full-size image, title, and overlays (owned/minis counters, sticker) cloned from the card. Click image again or press Escape to close.
