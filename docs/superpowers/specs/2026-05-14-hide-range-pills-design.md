# Hide Range Pills — Design Spec

Date: 2026-05-14

## Summary

Add a per-range toggle on the manufacturer home page that greys out individual range pills. State persists server-side. Greyed ranges remain visible and clickable but visually de-emphasised.

## Backend

### Schema

New sqlite table added by the existing additive migration pattern in `db.py`:

```sql
CREATE TABLE IF NOT EXISTS hidden_ranges (
    man_slug  TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
```

### New db helpers

- `hide_range(man_slug, range_slug)` — INSERT OR IGNORE
- `unhide_range(man_slug, range_slug)` — DELETE
- `get_hidden_ranges() -> set[tuple[str, str]]` — returns all hidden pairs

### New endpoints in app.py

```
POST   /api/hide-range/{man_slug}/{range_slug}   → 200 {}
DELETE /api/hide-range/{man_slug}/{range_slug}   → 200 {}
```

Both call the relevant db helper and return an empty JSON object.

### /manufacturers response change

Each range dict gains a `"hidden": bool` field, populated by checking `get_hidden_ranges()` at request time (called once per request, not per range).

## Frontend

### Pill structure change

The existing pill has two buttons (name + download icon). A third button is appended on the right:

```html
<button class="range-hide px-2 py-1 border-l hover:bg-gray-100 text-gray-400"
        data-man="..." data-range="..." title="Hide range" aria-label="Hide range">
  <!-- eye-slash SVG -->
</button>
```

### Greyed state

When a range is hidden, its `<span class="range-pill">` gets a `data-hidden="1"` attribute. CSS applied via that attribute:

- pill text/border at reduced opacity (`opacity-50` or similar)
- hide button icon styled "active" (slightly darker / filled)

The pill remains fully clickable — hiding only affects appearance.

### On load

`renderRanges` reads `r.hidden` from the API response and sets `data-hidden="1"` on the pill span at render time.

### Toggle interaction

Click on `.range-hide` button:
1. Read current `data-hidden` on the pill span.
2. `POST` or `DELETE` `/api/hide-range/{man}/{range}` accordingly.
3. On success, flip `data-hidden` on the span.

No full re-render needed.

## What's not changing

- Range click (load range) and download (fetch prices) behaviour unchanged.
- No changes to search, SKU hide, wishlist, or any other feature.
- Hidden ranges are not filtered from the manufacturer endpoint — they still load if clicked.
