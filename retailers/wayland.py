from curl_cffi.requests import AsyncSession

import db

SLUG = "wayland"
NAME = "Wayland Games"
ICON = "/static/icons/wayland.png"
BASE = "https://www.waylandgames.co.uk"
GRAPHQL_URL = BASE + "/api/graphql"

QUERY = """query productSearch($search: String, $pageSize: Int = 10, $sort: ProductAttributeSortInput = {relevance: DESC}) {
  results: products(search: $search, pageSize: $pageSize, sort: $sort) {
    items {
      url
      title: name
      sku
      image { url }
      price_range {
        minimum_price {
          regular_price { value }
          final_price { value }
        }
      }
      stock_status
    }
  }
}"""


class WaylandBlockedError(Exception):
    pass


def _abs_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return BASE + ("/" + path if not path.startswith("/") else path)


async def search(query: str, client: AsyncSession) -> list[dict]:
    payload = {
        "query": QUERY,
        "variables": {"search": query, "pageSize": 40},
        "operationName": "productSearch",
    }
    cookies = {}
    stored = db.get_meta("wayland_cookies")
    if stored:
        for part in stored.split(";"):
            part = part.strip()
            if "=" in part:
                k, v = part.split("=", 1)
                cookies[k.strip()] = v.strip()
    r = await client.post(
        GRAPHQL_URL,
        json=payload,
        headers={
            "content-type": "application/json",
            "content-currency": "GBP",
            "referer": f"{BASE}/search?query={query}",
        },
        cookies=cookies or None,
        timeout=15,
    )
    if r.status_code == 403:
        raise WaylandBlockedError("Wayland Games is blocking requests — solve the challenge in your browser")
    r.raise_for_status()
    data = r.json()
    items = (data.get("data") or {}).get("results", {}).get("items") or []
    out: list[dict] = []
    items = [it for it in items if it.get("stock_status") == "IN_STOCK"]
    for it in items[:40]:
        pr = (it.get("price_range") or {}).get("minimum_price") or {}
        price = ((pr.get("final_price") or {}).get("value"))
        rrp = ((pr.get("regular_price") or {}).get("value"))
        if rrp is not None and price is not None and rrp <= price:
            rrp = None
        img = (it.get("image") or {}).get("url")
        out.append({
            "retailer": NAME,
            "retailer_slug": SLUG,
            "retailer_icon": ICON,
            "title": it.get("title"),
            "url": _abs_url(it.get("url")),
            "price": price,
            "rrp": rrp,
            "in_stock": it.get("stock_status") == "IN_STOCK",
            "image_url": img,
            "sku": it.get("sku"),
        })
    return out
