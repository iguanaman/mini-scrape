"""Backfill manufacturers + ranges tables from the module registry.

Safe to re-run — all upserts, no deletes. Existing product rows are untouched.

Run with:  uv run python scripts/update_manufacturer_meta.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import db
from manufacturers import MANUFACTURERS


def main() -> None:
    db.init()
    for module in MANUFACTURERS:
        db.upsert_manufacturer(module.SLUG, module.NAME, module.ICON)
        for r in module.RANGES:
            db.upsert_range(r["slug"], module.SLUG, r.get("name", ""), r.get("group"))
        print(f"{module.SLUG}: {len(module.RANGES)} ranges")
    print("done")


if __name__ == "__main__":
    main()
