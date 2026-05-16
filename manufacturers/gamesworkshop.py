"""Games Workshop manufacturer — queries GW's own Algolia search index.

Algolia app: M5ZIQZNQ2H, index: prod-lazarus-product-en-gb.
The API key is a public search-only key exposed in the warhammer.com frontend.
No WAF bypass needed — Algolia is a separate domain and accepts direct requests.
"""
import urllib.parse

from curl_cffi.requests import AsyncSession

SLUG = "gamesworkshop"
NAME = "Games Workshop"
ICON = "/static/icons/gamesworkshop.ico"
BASE = "https://www.warhammer.com/en-GB"
ALGOLIA_URL = "https://m5ziqznq2h-dsn.algolia.net/1/indexes/prod-lazarus-product-en-gb/query"
ALGOLIA_APP_ID = "M5ZIQZNQ2H"
ALGOLIA_API_KEY = "92c6a8254f9d34362df8e6d96475e5d8"
IMAGE_BASE = "https://www.warhammer.com"
HITS_PER_PAGE = 100

RANGES = [
    # ---- Warhammer 40,000 ----
    {"slug": "40k",                       "name": "Warhammer 40,000 (all)",         "filter": 'GameSystemsRoot.lvl0:"Warhammer 40,000"',                                             "group": "Warhammer 40,000"},
    {"slug": "40k-space-marines",         "name": "Space Marines",                  "filter": 'GameSystemsRoot.lvl1:"Warhammer 40,000 > Space Marines"',                             "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-space-marines",   "name": "Chaos Space Marines",            "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Chaos Space Marines"',    "group": "Warhammer 40,000"},
    {"slug": "40k-astra-militarum",       "name": "Astra Militarum",                "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Astra Militarum"', "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-mechanicus",    "name": "Adeptus Mechanicus",             "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adeptus Mechanicus"', "group": "Warhammer 40,000"},
    {"slug": "40k-adepta-sororitas",      "name": "Adepta Sororitas",               "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adepta Sororitas"', "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-custodes",      "name": "Adeptus Custodes",               "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adeptus Custodes"', "group": "Warhammer 40,000"},
    {"slug": "40k-necrons",               "name": "Necrons",                        "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Necrons"',                   "group": "Warhammer 40,000"},
    {"slug": "40k-orks",                  "name": "Orks",                           "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Orks"',                      "group": "Warhammer 40,000"},
    {"slug": "40k-tyranids",              "name": "Tyranids",                       "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Tyranids"',                  "group": "Warhammer 40,000"},
    {"slug": "40k-tau-empire",            "name": "T'au Empire",                    "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > T\'au Empire"',               "group": "Warhammer 40,000"},
    {"slug": "40k-aeldari",               "name": "Aeldari",                        "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Aeldari"',                   "group": "Warhammer 40,000"},
    {"slug": "40k-drukhari",              "name": "Drukhari",                       "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Drukhari"',                  "group": "Warhammer 40,000"},
    {"slug": "40k-genestealer-cults",     "name": "Genestealer Cults",              "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Genestealer Cults"',         "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-daemons",         "name": "Chaos Daemons",                  "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Chaos Daemons"',          "group": "Warhammer 40,000"},
    {"slug": "40k-world-eaters",          "name": "World Eaters",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > World Eaters"',           "group": "Warhammer 40,000"},

    # ---- Age of Sigmar ----
    {"slug": "aos",                       "name": "Age of Sigmar (all)",            "filter": 'GameSystemsRoot.lvl0:"Age of Sigmar"',                                               "group": "Age of Sigmar"},
    {"slug": "aos-stormcast-eternals",    "name": "Stormcast Eternals",             "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Stormcast Eternals"',  "group": "Age of Sigmar"},
    {"slug": "aos-skaven",                "name": "Skaven",                         "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Skaven"',               "group": "Age of Sigmar"},
    {"slug": "aos-nighthaunt",            "name": "Nighthaunt",                     "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Nighthaunt"',           "group": "Age of Sigmar"},
    {"slug": "aos-orruk-warclans",        "name": "Orruk Warclans",                 "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Destruction > Orruk Warclans"',"group": "Age of Sigmar"},

    # ---- Skirmish / Specialist ----
    {"slug": "kill-team",                 "name": "Kill Team",                      "filter": 'GameSystemsRoot.lvl1:"Other Games > Kill Team"',                                     "group": "Skirmish"},
    {"slug": "warcry",                    "name": "Warcry",                         "filter": 'GameSystemsRoot.lvl1:"Other Games > Warcry"',                                        "group": "Skirmish"},
    {"slug": "underworlds",               "name": "Warhammer Underworlds",          "filter": 'GameSystemsRoot.lvl1:"Other Games > Warhammer Underworlds"',                         "group": "Skirmish"},
    {"slug": "necromunda",                "name": "Necromunda",                     "filter": 'GameSystemsRoot.lvl1:"Other Games > Necromunda"',                                    "group": "Skirmish"},
    {"slug": "blood-bowl",                "name": "Blood Bowl",                     "filter": 'GameSystemsRoot.lvl1:"Other Games > Blood Bowl"',                                    "group": "Skirmish"},

    # ---- Horus Heresy ----
    {"slug": "horus-heresy",              "name": "The Horus Heresy",               "filter": 'GameSystemsRoot.lvl0:"The Horus Heresy"',                                            "group": "Horus Heresy"},
    {"slug": "legions-imperialis",        "name": "Legions Imperialis",             "filter": 'GameSystemsRoot.lvl1:"Other Games > Legions Imperialis"',                            "group": "Horus Heresy"},

    # ---- The Old World ----
    {"slug": "old-world",                 "name": "The Old World (all)",            "filter": 'GameSystemsRoot.lvl0:"The Old World"',                                               "group": "The Old World"},

    # ---- Middle-earth ----
    {"slug": "mesbg",                     "name": "Middle-earth SBG",               "filter": 'GameSystemsRoot.lvl0:"Middle-Earth"',                                                "group": "Middle-earth"},

    # ---- Hobby / Misc ----
    {"slug": "citadel-paints",            "name": "Citadel Paints & Hobby",         "filter": 'productType:"paintSupply"',                                                          "group": "Hobby & Misc"},
    {"slug": "black-library",             "name": "Black Library",                  "filter": 'productType:"book"',                                                                 "group": "Hobby & Misc"},
    {"slug": "white-dwarf",               "name": "White Dwarf",                    "filter": 'productType:"magazine"',                                                             "group": "Hobby & Misc"},
]


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    import sys
    filter_str = range_def["filter"]
    headers = {
        "x-algolia-application-id": ALGOLIA_APP_ID,
        "x-algolia-api-key": ALGOLIA_API_KEY,
        "content-type": "application/json",
    }
    out: list[dict] = []
    page = 0
    sys.stdout.write("fetching: ")
    sys.stdout.flush()
    while True:
        payload = {
            "filters": filter_str,
            "hitsPerPage": HITS_PER_PAGE,
            "page": page,
            "attributesToRetrieve": ["name", "sku", "slug", "price", "images", "description", "isInStock", "productType"],
        }
        r = await client.post(ALGOLIA_URL, json=payload, headers=headers, timeout=15)
        r.raise_for_status()
        data = r.json()
        hits = data.get("hits") or []
        for h in hits:
            images = h.get("images") or []
            image_url = f"{IMAGE_BASE}/app/resources/catalog/product/920x950/{images[0].split('/')[-1]}" if images else None
            # images[0] is already a path like /app/resources/catalog/product/920x950/...
            raw_img = images[0] if images else None
            if raw_img and raw_img.startswith("/"):
                image_url = IMAGE_BASE + raw_img
            elif raw_img:
                image_url = raw_img
            else:
                image_url = None
            sku = h.get("sku") or None
            # GW SKUs come in various forms; the real barcode is always the last 11 digits
            if sku and len(sku) > 11:
                sku = sku[-11:]
            out.append({
                "title": h.get("name"),
                "sku": sku,
                "url": f"{BASE}/shop/{h['slug']}" if h.get("slug") else None,
                "image_url": image_url,
                "price": h.get("price"),
                "description": h.get("description") or None,
            })
        sys.stdout.write(".")
        sys.stdout.flush()
        total_pages = data.get("nbPages", 1)
        if page >= total_pages - 1:
            break
        page += 1
    sys.stdout.write(f" {len(out)} products\n")
    sys.stdout.flush()
    return out
