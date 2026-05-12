from curl_cffi.requests import AsyncSession

NAME = "Wayland Games"
BASE = "https://www.waylandgames.co.uk"
GRAPHQL_URL = BASE + "/api/graphql"

QUERY = """query productSearch($search: String, $pageSize: Int = 10) {
  results: products(search: $search, pageSize: $pageSize) {
    items {
      url
      title: name
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


def _abs_url(path: str | None) -> str | None:
    if not path:
        return None
    if path.startswith("http"):
        return path
    return BASE + ("/" + path if not path.startswith("/") else path)


async def search(query: str, client: AsyncSession) -> list[dict]:
    payload = {
        "query": QUERY,
        "variables": {"search": query, "pageSize": 10},
        "operationName": "productSearch",
    }
    r = await client.post(
        GRAPHQL_URL,
        json=payload,
        headers={
            "content-type": "application/json",
            "content-currency": "GBP",
            "referer": f"{BASE}/search?query={query}",
        },
        timeout=15,
    )
    r.raise_for_status()
    data = r.json()
    items = (data.get("data") or {}).get("results", {}).get("items") or []
    out: list[dict] = []
    for it in items[:10]:
        pr = (it.get("price_range") or {}).get("minimum_price") or {}
        price = ((pr.get("final_price") or {}).get("value"))
        rrp = ((pr.get("regular_price") or {}).get("value"))
        if rrp is not None and price is not None and rrp <= price:
            rrp = None
        img = (it.get("image") or {}).get("url")
        out.append({
            "retailer": NAME,
            "title": it.get("title"),
            "url": _abs_url(it.get("url")),
            "price": price,
            "rrp": rrp,
            "in_stock": it.get("stock_status") == "IN_STOCK",
            "image_url": img,
        })
    return out
