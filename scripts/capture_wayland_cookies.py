"""
Capture Wayland Games cookies from your browser and save them to the DB.

Usage:
    uv run python scripts/capture_wayland_cookies.py [--browser chrome|firefox|edge]

Steps:
    1. Visit https://www.waylandgames.co.uk in your browser and solve any challenge.
    2. Run this script — it reads cookies directly from the browser's on-disk store.
    3. Cookies are saved to the DB; scrape_prices.py will use them automatically.
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import browser_cookie3
import db

DOMAIN = "waylandgames.co.uk"

LOADERS = {
    "chrome": browser_cookie3.chrome,
    "firefox": browser_cookie3.firefox,
    "edge": browser_cookie3.edge,
}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", choices=list(LOADERS), default="chrome")
    args = parser.parse_args()

    loader = LOADERS[args.browser]
    try:
        jar = loader(domain_name=DOMAIN)
    except Exception as e:
        print(f"Failed to read {args.browser} cookies: {e}")
        sys.exit(1)

    cookies = {c.name: c.value for c in jar}
    if not cookies:
        print(f"No cookies found for {DOMAIN} in {args.browser}.")
        print("Visit https://www.waylandgames.co.uk, solve any challenge, then re-run.")
        sys.exit(1)

    cookie_str = "; ".join(f"{k}={v}" for k, v in cookies.items())
    db.set_meta("wayland_cookies", cookie_str)
    print(f"Saved {len(cookies)} cookies from {args.browser} to DB.")
    print("Keys:", ", ".join(cookies.keys()))


if __name__ == "__main__":
    main()
