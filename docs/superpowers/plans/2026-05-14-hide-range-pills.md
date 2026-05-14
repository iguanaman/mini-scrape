# Hide Range Pills Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-extended-cc:subagent-driven-development (recommended) or superpowers-extended-cc:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a per-range toggle button on each manufacturer range pill that greys it out and persists the hidden state server-side.

**Architecture:** New `hidden_ranges` sqlite table; two new API endpoints mirror the existing SKU hide pattern; `/manufacturers` response gains a `hidden` bool per range; frontend adds a third button to each pill and applies greyed styling based on that flag.

**Tech Stack:** Python/FastAPI, sqlite (via existing `db.py` pattern), vanilla JS, Tailwind CDN.

---

### Task 1: Add hidden_ranges table and db helpers

**Goal:** Extend `db.py` with the `hidden_ranges` table (created via additive migration) and three helper functions.

**Files:**
- Modify: `db.py`

**Acceptance Criteria:**
- [ ] `hidden_ranges` table is created on startup if absent (idempotent)
- [ ] `hide_range(man_slug, range_slug)` inserts a row (INSERT OR IGNORE)
- [ ] `unhide_range(man_slug, range_slug)` deletes the row
- [ ] `get_hidden_ranges()` returns a `set[tuple[str, str]]` of all hidden pairs

**Verify:** Run `uv run python -c "import db; db.init(); db.hide_range('northstar','stargrave'); print(db.get_hidden_ranges()); db.unhide_range('northstar','stargrave'); print(db.get_hidden_ranges())"` → `{('northstar', 'stargrave')}` then `set()`

**Steps:**

- [ ] **Step 1: Add table creation to `_SCHEMA` in `db.py`**

In `db.py`, the `_SCHEMA` string currently ends after the `products` table. Append the new table:

```python
_SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
CREATE TABLE IF NOT EXISTS products (
    sku TEXT PRIMARY KEY,
    title TEXT,
    image_url TEXT,
    url TEXT,
    manufacturer_slug TEXT,
    range_slug TEXT,
    range_name TEXT,
    range_group TEXT,
    manufacturer_price REAL,
    prices_json TEXT,
    minis INTEGER,
    wishlisted_at TEXT,
    updated_at TEXT
);
CREATE TABLE IF NOT EXISTS hidden_ranges (
    man_slug   TEXT NOT NULL,
    range_slug TEXT NOT NULL,
    PRIMARY KEY (man_slug, range_slug)
);
"""
```

- [ ] **Step 2: Add the three helper functions to `db.py`**

Add after the `unhide_product` function (around line 146):

```python
def hide_range(man_slug: str, range_slug: str) -> None:
    with _conn() as c:
        c.execute(
            "INSERT OR IGNORE INTO hidden_ranges (man_slug, range_slug) VALUES (?, ?)",
            (man_slug, range_slug),
        )


def unhide_range(man_slug: str, range_slug: str) -> None:
    with _conn() as c:
        c.execute(
            "DELETE FROM hidden_ranges WHERE man_slug = ? AND range_slug = ?",
            (man_slug, range_slug),
        )


def get_hidden_ranges() -> set[tuple[str, str]]:
    with _conn() as c:
        rows = c.execute("SELECT man_slug, range_slug FROM hidden_ranges").fetchall()
    return {(r["man_slug"], r["range_slug"]) for r in rows}
```

- [ ] **Step 3: Commit**

```bash
git add db.py
git commit -m "feat: add hidden_ranges table and db helpers"
```

---

### Task 2: Add API endpoints and update /manufacturers response

**Goal:** Wire up two toggle endpoints and include `hidden` bool in the `/manufacturers` JSON.

**Files:**
- Modify: `app.py`

**Acceptance Criteria:**
- [ ] `POST /api/hide-range/{man_slug}/{range_slug}` returns `{"ok": true}` and persists
- [ ] `DELETE /api/hide-range/{man_slug}/{range_slug}` returns `{"ok": true}` and clears
- [ ] `/manufacturers` response: each range dict has a `"hidden": bool` key

**Verify:** Start server, then:
```
curl -s -X POST http://localhost:8000/api/hide-range/northstar/stargrave
curl -s http://localhost:8000/manufacturers | python -m json.tool | grep -A2 stargrave
curl -s -X DELETE http://localhost:8000/api/hide-range/northstar/stargrave
curl -s http://localhost:8000/manufacturers | python -m json.tool | grep -A2 stargrave
```
First manufacturers call shows `"hidden": true`, second shows `"hidden": false`.

**Steps:**

- [ ] **Step 1: Update `manufacturers_index` in `app.py` to include hidden flag**

Replace the existing `/manufacturers` handler (around line 405):

```python
@app.get("/manufacturers")
async def manufacturers_index():
    hidden = db.get_hidden_ranges()
    out = []
    for m in MANUFACTURERS:
        out.append({
            "slug": m.SLUG,
            "name": m.NAME,
            "icon": m.ICON,
            "ranges": [
                {
                    "slug": r["slug"],
                    "name": r["name"],
                    "group": r.get("group"),
                    "hidden": (m.SLUG, r["slug"]) in hidden,
                }
                for r in m.RANGES
            ],
        })
    return JSONResponse({"manufacturers": out})
```

- [ ] **Step 2: Add the two new endpoints to `app.py`**

Add after the existing `api_unhide` endpoint (after line 477):

```python
@app.post("/api/hide-range/{man_slug}/{range_slug}")
async def api_hide_range(man_slug: str, range_slug: str):
    db.hide_range(man_slug, range_slug)
    return JSONResponse({"ok": True})


@app.delete("/api/hide-range/{man_slug}/{range_slug}")
async def api_unhide_range(man_slug: str, range_slug: str):
    db.unhide_range(man_slug, range_slug)
    return JSONResponse({"ok": True})
```

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "feat: add hide-range API endpoints and hidden flag in /manufacturers"
```

---

### Task 3: Add hide toggle button and greyed styling to range pills

**Goal:** Add a third button (eye-slash icon) to each range pill in the frontend; apply greyed styling when `r.hidden` is true; wire up the toggle interaction.

**Files:**
- Modify: `templates/index.html`

**Acceptance Criteria:**
- [ ] Each range pill has a third button with an eye-slash SVG, same style as the existing download button
- [ ] Pills with `r.hidden === true` render with `data-hidden="1"` and appear visually muted (opacity-50)
- [ ] Clicking the eye-slash button toggles hidden state via POST/DELETE and flips `data-hidden` on the pill span without a full re-render
- [ ] The eye-slash button icon is visually "active" (slightly darker) when the pill is hidden

**Verify:** Load the home page, find a range pill, click the eye-slash button — pill goes muted. Reload the page — pill is still muted. Click again — pill returns to normal.

**Steps:**

- [ ] **Step 1: Update the `pill` template function to include `data-hidden` and the eye-slash button**

Find the `pill` function in `templates/index.html` (around line 557). Replace it:

```javascript
const pill = (manSlug, r) => `<span class="range-pill inline-flex items-center border rounded-full text-sm overflow-hidden${r.hidden ? ' opacity-50' : ''}" data-hidden="${r.hidden ? '1' : '0'}">
  <button type="button" data-man="${esc(manSlug)}" data-range="${esc(r.slug)}"
    class="range-btn px-3 py-1 hover:bg-gray-100">${esc(r.name)}</button>
  <button type="button" data-man="${esc(manSlug)}" data-range="${esc(r.slug)}" title="Fetch prices for ${esc(r.name)}"
    class="range-queue px-2 py-1 border-l hover:bg-gray-100 text-gray-500 hover:text-gray-800" aria-label="Fetch prices">
    <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M12 10v6m0 0-3-3m3 3 3-3M3 17V7a2 2 0 0 1 2-2h6l2 2h6a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/></svg>
  </button>
  <button type="button" data-man="${esc(manSlug)}" data-range="${esc(r.slug)}" title="Hide range"
    class="range-hide px-2 py-1 border-l hover:bg-gray-100 ${r.hidden ? 'text-gray-800' : 'text-gray-400'} hover:text-gray-800" aria-label="Hide range">
    <svg xmlns="http://www.w3.org/2000/svg" class="w-3.5 h-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" stroke-width="2"><path stroke-linecap="round" stroke-linejoin="round" d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"/><line x1="1" y1="1" x2="23" y2="23"/></svg>
  </button>
</span>`;
```

- [ ] **Step 2: Add the event listener for `.range-hide` buttons**

After the block that sets up `.range-queue` listeners (after line 615 in the original, inside the `showHome` try block), add:

```javascript
manufacturers.querySelectorAll('.range-hide').forEach(btn => {
  btn.addEventListener('click', async (e) => {
    e.stopPropagation();
    const man = btn.dataset.man, range = btn.dataset.range;
    const pill = btn.closest('.range-pill');
    const isHidden = pill.dataset.hidden === '1';
    const method = isHidden ? 'DELETE' : 'POST';
    await fetch(`/api/hide-range/${encodeURIComponent(man)}/${encodeURIComponent(range)}`, { method });
    const nowHidden = !isHidden;
    pill.dataset.hidden = nowHidden ? '1' : '0';
    pill.classList.toggle('opacity-50', nowHidden);
    btn.classList.toggle('text-gray-800', nowHidden);
    btn.classList.toggle('text-gray-400', !nowHidden);
  });
});
```

- [ ] **Step 3: Commit**

```bash
git add templates/index.html
git commit -m "feat: add hide toggle button to range pills with greyed styling"
```
