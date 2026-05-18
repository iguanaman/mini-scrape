# Manufacturer specifics

Per-manufacturer scraping notes. Each lives in `manufacturers/<slug>.py`.

## North Star Figures (`manufacturers/northstar.py`)
`GET https://www.northstarfigures.com/list.php?man=<man_id>&page=<n>`. Server-rendered HTML.
- Each product is a `p.prodpara` with: image link (`prod.php?prod=N`), `alt="Photo of <title> (<sku>)"` regex-parsed for title+SKU, `Our Price:£N.NN` text.
- Page count from `h2` text "page X of Y" — we paginate until we hit Y.
- Listing thumbs are `imgthN.jpg` (100×100). We replace `imgth` → `img` to get full-size `imgN.jpg` (better for our 240px image area).
- RANGES list with `group` for UI bucketing:
  - **Game Lines**: Frostgrave (195), Ghost Archipelago (254), Stargrave (295), Oathmark (257), Rangers of Shadow Deep (280), The Silver Bayonet (302), Dracula's America (248)
  - **North Star Historical**: 1672 (123), 1864 (204), 1866 (100), American Civil War (343), Africa! (87), Spanish Civil War (31), Kadesh (163)
  - **North Star Fantasy**: Fantasy Worlds (155), Steampunk (207)
  - **Distributed Ranges**: Great War Miniatures (20), Fireforge Games (124), Conquest Games (102), Shieldwolf Miniatures (167), Trench Crusade (339), Grey For Now Games (308), Muskets & Tomahawks (290), On The Seven Seas (173), Ronin (152), A Fistful Of Kung Fu (162)

## Wargames Atlantic (`manufacturers/wargamesatlantic.py`)
Shopify store. `GET https://wargamesatlantic.com/collections/{handle}/products.json?limit=250&page=N`. JSON.
- Each product: `title`, `handle` (→ build URL), `variants[0]` for `price` + `sku` + `available`, `images[0].src`.
- We paginate while the page is full (250). For curated collections this is usually 1 request.
- RANGES (Shopify collection handles): Plastic Box Sets, Death Fields Arena, Quar, The Barons' War, Classic Fantasy, The Age of Chivalry, World Ablaze.

## Games Workshop (`manufacturers/gamesworkshop.py`)
Queries GW's own Algolia search index directly — no WAF bypass needed (Algolia is a separate domain that accepts plain curl_cffi requests).
- Algolia app: `M5ZIQZNQ2H`, index: `prod-lazarus-product-en-gb`, public search-only API key.
- Each range uses an Algolia `filters` facet string (e.g. `GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Soulblight Gravelords"`). Fetches up to `HITS_PER_PAGE=100` hits per range.
- Each hit: `title`, `handle` (→ build warhammer.com URL), `price`, `sku` (GW product code). **SKUs are populated** — gives the search-side grouper a strong signal.
- RANGES (~70 entries) carry a `group` field for visual bucketing in the home view. Groups: Warhammer 40,000, Age of Sigmar, Skirmish (Kill Team / Warcry / Underworlds / Blood Bowl / Necromunda), Horus Heresy & Epic (HH / Legions Imperialis / Adeptus Titanicus), The Old World, Middle-earth, Hobby & Misc.

## Victrix (`manufacturers/victrix.py`)
Shopify store. `GET https://victrixlimited.com/collections/{handle}/products.json?limit=250&page=N`. Same pattern as Wargames Atlantic.
- 28mm only — 12mm and tiny-scale collections deliberately excluded.
- RANGES (collection handles): `ancients`, `dark-ages`, `medieval-dark-ages`, `28mm-napoleonics`, `british-napoleonics`, `french-napoleonics`, `28mm-wwii`, `pillage-ransack-the-middle-ages`, `28mm-army-sets`.
- `group` field buckets them into Ancients / Medieval & Dark Ages / Napoleonics / WWII / Games / Bundles.

## Mantic (`manufacturers/mantic.py`)
WooCommerce with the Store API enabled. `GET https://www.manticgames.com/wp-json/wc/store/v1/products?category={slug}&per_page=100&page=N`. JSON.
- `prices.price` is a string of pence (`"1500"` = £15.00). We divide by `prices.currency_minor_unit` (always 2 for GBP).
- Variable products (`type: "variable"`) have `prices.price = null` and use `prices.price_range.min_amount` instead — we fall back to that. Some Mantic products return as variable.
- `sku` lives top-level; `permalink` is the product URL; `images[0].src` is the image; `is_in_stock` is the stock bool (unused — manufacturer interface doesn't carry stock).
- Paginate while page is full (`per_page=100`). KoW is the biggest range (~580 items, 6 pages).
- RANGES: Kings of War, Deadzone, Firefight, Armada, Epic Warpath, The Walking Dead, Dungeon Saga, Hellboy, Halo Flashpoint.

## Warlord Games (`manufacturers/warlord.py`)
Shopify store at `store.warlordgames.com` (the marketing site at `www.warlordgames.com` is WordPress and has no products on it — it just embeds collection pages). Same JSON pattern as WA / Victrix.
- `GET https://store.warlordgames.com/collections/{handle}/products.json?limit=250&page=N`.
- Bolt Action has ~1947 products (8 pages at 250/page); the rest are smaller.
- RANGES: Bolt Action, Hail Caesar, Black Powder, Pike & Shotte Epic Battles, Epic ACW, Epic Waterloo, Black Seas, Mythic Americas, Warlords of Erehwon.
- Note: `warlord-mythic-americas-tribal-nations` was a stale handle; the real one is plain `mythic-americas`. Same pattern of "is the obvious handle on `www.` 404? try `store.` plus a different slug" applies if anything else changes.

## Perry Miniatures (`manufacturers/perry.py`)
WooCommerce, server-rendered HTML. Standard Porto theme. `GET https://www.perry-miniatures.com/product-category/{path}/[page/N/]`.
- Product cards: `li.product.type-product`. Title in `.woocommerce-loop-product__title` (Perry bakes the SKU into the title — e.g. `"FN100 Plastic French Napoleonic Infantry"` — so we regex out `^([A-Z]{1,5})\s*(\d{1,4}[A-Z0-9]*)\b` and join the two halves as SKU. Some titles like `"SPA 90 Spanish…"` have a literal space, which is why the regex allows it).
- URL: first `<a href>` inside the card containing `/product/` (not `/product-category/`).
- Price: `.price` text, parsed for `[\d,]+\.\d{2}`. Stock class: `instock` / `outofstock` on `li.product` — unused (manufacturer interface ignores stock).
- Image: prefer `data-src`, else `src`. Skip `data:image/...` placeholders.
- Pagination: detect `a.next.page-numbers`; stop when absent. URLs are `/product-category/<path>/page/2/`, etc.
- RANGES include top sub-categories under metal-ranges (Wars of the Roses, Crusades, Napoleonic French/British, ACW, AWI, ECW, Sudan, Franco-Prussian, WW2) plus the plastic box-set hub. The hub for `/napoleonic/` itself returns sub-category cards, not products — that's why we use the leaf paths (`/napoleonic/french/`, `/napoleonic/british/`).

## Gripping Beast (`manufacturers/grippingbeast.py`)
Legacy custom CMS. URLs are `/<stem>--category--<id>.html`. Server-rendered HTML, no WAF.
- The category tree is **deep**: most top-level "ranges" are HUB pages that list sub-categories rather than products. Leaf categories have `div.product-inner` cards; hub categories have `a.pcl-category-each` sub-cat links.
- We tree-walk: fetch a category, parse products if any, else recurse into sub-cat links in parallel via `asyncio.gather`. Capped at `MAX_DEPTH=4`. Sub-cat URLs are matched against `^/[^/]+--category--(\d+)\.html$`; we dedupe by cat id to avoid loops (sibling tree shares categories).
- Server accepts **any non-empty stem** for a given cat id (`/x--category--32.html` works as well as the canonical stem). RANGES only need the cat id.
- Pagination is not real here — every category page fits on one response. `?page=N` and `--page--N` are accepted but ignored.
- Product card parser: title in `<h3>` (with SKU prefix — same `[A-Z][A-Z0-9]+` prefix extraction as North Star); price in `p.pcl-product-each-price` with `£N.NN`; image in `img.pcl-product-each-image`; URL in `a.pcl-product-each[href]`; out-of-stock marker is class `pcl-product-each-out-of-stock` on the link (unused — manufacturer interface ignores stock).
- RANGES: top-level hubs — Plastic Figures (32), SAGA (10), SWORDPOINT (376), JUGULA (490), Viking Age (24), Byzantines (49), Late Romans (105), Age of Arthur (63), Front Rank Figurines (600).
- SAGA hub expands to ~364 items across many sub-cats; Viking Age and Byzantines are similarly large.

## Conquest Games — not implemented
`conquestgames.co.uk` was unreachable (ECONNREFUSED) during the initial scout. If/when the site is back, candidate approach: probably WooCommerce or a Shopify shop — re-run the platform probe before writing a module.
