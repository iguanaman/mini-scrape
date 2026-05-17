"""
Capture Wayland Games cookies from your browser and save them to the DB.

Auto mode (reads cookies from browser on disk):
    uv run python scripts/capture_wayland_cookies.py [--browser chrome|firefox|edge|...]

Manual mode (paste cookie string from DevTools):
    uv run python scripts/capture_wayland_cookies.py --paste

Manual steps:
    1. Visit https://www.waylandgames.co.uk and solve any challenge.
    2. Open DevTools → Application → Cookies → waylandgames.co.uk
    3. Copy all cookies as a header string (name=value; name=value ...)
       or use the Network tab: find any request → Headers → Cookie: <value>
    4. Run with --paste and paste when prompted.
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
    "chromium": browser_cookie3.chromium,
    "edge": browser_cookie3.edge,
    "brave": browser_cookie3.brave,
    "opera": browser_cookie3.opera,
    "opera_gx": browser_cookie3.opera_gx,
    "arc": browser_cookie3.arc,
    "vivaldi": browser_cookie3.vivaldi,
    "firefox": browser_cookie3.firefox,
    "librewolf": browser_cookie3.librewolf,
}


def _save(cookie_str: str) -> None:
    cookies = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    if not cookies:
        print("No cookies parsed — check the format.")
        sys.exit(1)
    db.set_meta("wayland_cookies", cookie_str.strip())
    print(f"Saved {len(cookies)} cookies to DB.")
    print("Keys:", ", ".join(cookies.keys()))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--browser", choices=list(LOADERS), default="chrome",
                        help="Browser to read cookies from (default: chrome)")
    parser.add_argument("--paste", action="store_true",
                        help="Manually paste cookie string instead of reading from browser")
    args = parser.parse_args()

    if args.paste:
        print("Paste the cookie string (name=value; name=value ...) and press Enter:")
        cookie_str = input().strip()
        _save(cookie_str)
        return

    loader = LOADERS[args.browser]
    try:
        jar = loader(domain_name=DOMAIN)
    except Exception as e:
        print(f"Failed to read {args.browser} cookies: {e}")
        print("Try running as admin, use a different --browser, or use --paste instead.")
        sys.exit(1)

    cookies = {c.name: c.value for c in jar}
    if not cookies:
        print(f"No cookies found for {DOMAIN} in {args.browser}.")
        print("Visit https://www.waylandgames.co.uk, solve any challenge, then re-run.")
        sys.exit(1)

    _save("; ".join(f"{k}={v}" for k, v in cookies.items()))


if __name__ == "__main__":
    main()
