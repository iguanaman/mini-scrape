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
    {"slug": "40k",                         "name": "Warhammer 40,000 (all)",         "filter": 'GameSystemsRoot.lvl0:"Warhammer 40,000"',                                                    "group": "Warhammer 40,000"},
    # Space Marines chapter ranges
    {"slug": "40k-space-marines",           "name": "Space Marines",                  "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Space Marines"',                    "group": "Warhammer 40,000"},
    {"slug": "40k-space-wolves",            "name": "Space Wolves",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Space Wolves"',                     "group": "Warhammer 40,000"},
    {"slug": "40k-dark-angels",             "name": "Dark Angels",                    "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Dark Angels"',                      "group": "Warhammer 40,000"},
    {"slug": "40k-blood-angels",            "name": "Blood Angels",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Blood Angels"',                     "group": "Warhammer 40,000"},
    {"slug": "40k-ultramarines",            "name": "Ultramarines",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Ultramarines"',                     "group": "Warhammer 40,000"},
    {"slug": "40k-black-templars",          "name": "Black Templars",                 "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Black Templars"',                   "group": "Warhammer 40,000"},
    {"slug": "40k-grey-knights",            "name": "Grey Knights",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Grey Knights"',                     "group": "Warhammer 40,000"},
    {"slug": "40k-deathwatch",              "name": "Deathwatch",                     "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Space Marines > Deathwatch"',                       "group": "Warhammer 40,000"},
    # Imperium
    {"slug": "40k-astra-militarum",         "name": "Astra Militarum",               "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Astra Militarum"',         "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-mechanicus",      "name": "Adeptus Mechanicus",            "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adeptus Mechanicus"',      "group": "Warhammer 40,000"},
    {"slug": "40k-adepta-sororitas",        "name": "Adepta Sororitas",              "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adepta Sororitas"',        "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-custodes",        "name": "Adeptus Custodes",              "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Adeptus Custodes"',        "group": "Warhammer 40,000"},
    {"slug": "40k-imperial-knights",        "name": "Imperial Knights",              "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Imperial Knights"',        "group": "Warhammer 40,000"},
    {"slug": "40k-imperial-agents",         "name": "Imperial Agents",               "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of the Imperium > Imperial Agents"',         "group": "Warhammer 40,000"},
    # Xenos
    {"slug": "40k-necrons",                 "name": "Necrons",                       "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Necrons"',                            "group": "Warhammer 40,000"},
    {"slug": "40k-orks",                    "name": "Orks",                          "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Orks"',                               "group": "Warhammer 40,000"},
    {"slug": "40k-tyranids",                "name": "Tyranids",                      "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Tyranids"',                           "group": "Warhammer 40,000"},
    {"slug": "40k-tau-empire",              "name": "T'au Empire",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > T\'au Empire"',                       "group": "Warhammer 40,000"},
    {"slug": "40k-aeldari",                 "name": "Aeldari",                       "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Aeldari"',                            "group": "Warhammer 40,000"},
    {"slug": "40k-drukhari",                "name": "Drukhari",                      "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Drukhari"',                           "group": "Warhammer 40,000"},
    {"slug": "40k-genestealer-cults",       "name": "Genestealer Cults",             "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Genestealer Cults"',                  "group": "Warhammer 40,000"},
    {"slug": "40k-leagues-of-votann",       "name": "Leagues of Votann",             "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Xenos Armies > Leagues of Votann"',                  "group": "Warhammer 40,000"},
    # Chaos
    {"slug": "40k-chaos-space-marines",     "name": "Chaos Space Marines",           "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Chaos Space Marines"',             "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-daemons",           "name": "Chaos Daemons",                 "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Chaos Daemons"',                   "group": "Warhammer 40,000"},
    {"slug": "40k-world-eaters",            "name": "World Eaters",                  "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > World Eaters"',                    "group": "Warhammer 40,000"},
    {"slug": "40k-death-guard",             "name": "Death Guard",                   "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Death Guard"',                     "group": "Warhammer 40,000"},
    {"slug": "40k-thousand-sons",           "name": "Thousand Sons",                 "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Thousand Sons"',                   "group": "Warhammer 40,000"},
    {"slug": "40k-emperors-children",       "name": "Emperor's Children",            "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Emperor\'s Children"',             "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-knights",           "name": "Chaos Knights",                 "filter": 'GameSystemsRoot.lvl2:"Warhammer 40,000 > Armies of Chaos > Chaos Knights"',                   "group": "Warhammer 40,000"},

    # ---- Age of Sigmar ----
    {"slug": "aos",                         "name": "Age of Sigmar (all)",           "filter": 'GameSystemsRoot.lvl0:"Age of Sigmar"',                                                       "group": "Age of Sigmar"},
    # Grand Alliance Order
    {"slug": "aos-stormcast-eternals",      "name": "Stormcast Eternals",            "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Stormcast Eternals"',           "group": "Age of Sigmar"},
    {"slug": "aos-cities-of-sigmar",        "name": "Cities of Sigmar",              "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Cities of Sigmar"',             "group": "Age of Sigmar"},
    {"slug": "aos-lumineth-realm-lords",    "name": "Lumineth Realm-lords",          "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Lumineth Realm-lords"',        "group": "Age of Sigmar"},
    {"slug": "aos-seraphon",                "name": "Seraphon",                      "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Seraphon"',                     "group": "Age of Sigmar"},
    {"slug": "aos-sylvaneth",               "name": "Sylvaneth",                     "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Sylvaneth"',                    "group": "Age of Sigmar"},
    {"slug": "aos-daughters-of-khaine",     "name": "Daughters of Khaine",           "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Daughters of Khaine"',         "group": "Age of Sigmar"},
    {"slug": "aos-idoneth-deepkin",         "name": "Idoneth Deepkin",               "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Idoneth Deepkin"',             "group": "Age of Sigmar"},
    {"slug": "aos-kharadron-overlords",     "name": "Kharadron Overlords",           "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Kharadron Overlords"',         "group": "Age of Sigmar"},
    {"slug": "aos-fyreslayers",             "name": "Fyreslayers",                   "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Order > Fyreslayers"',                 "group": "Age of Sigmar"},
    # Grand Alliance Chaos
    {"slug": "aos-skaven",                  "name": "Skaven",                        "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Skaven"',                      "group": "Age of Sigmar"},
    {"slug": "aos-slaves-to-darkness",      "name": "Slaves to Darkness",            "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Slaves to Darkness"',         "group": "Age of Sigmar"},
    {"slug": "aos-maggotkin-of-nurgle",     "name": "Maggotkin of Nurgle",           "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Maggotkin of Nurgle"',        "group": "Age of Sigmar"},
    {"slug": "aos-disciples-of-tzeentch",   "name": "Disciples of Tzeentch",         "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Disciples of Tzeentch"',     "group": "Age of Sigmar"},
    {"slug": "aos-hedonites-of-slaanesh",   "name": "Hedonites of Slaanesh",         "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Hedonites of Slaanesh"',     "group": "Age of Sigmar"},
    {"slug": "aos-blades-of-khorne",        "name": "Blades of Khorne",              "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Blades of Khorne"',           "group": "Age of Sigmar"},
    {"slug": "aos-helsmiths-of-hashut",     "name": "Helsmiths of Hashut",           "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Chaos > Helsmiths of Hashut"',        "group": "Age of Sigmar"},
    # Grand Alliance Death
    {"slug": "aos-nighthaunt",              "name": "Nighthaunt",                    "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Nighthaunt"',                  "group": "Age of Sigmar"},
    {"slug": "aos-soulblight-gravelords",   "name": "Soulblight Gravelords",         "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Soulblight Gravelords"',      "group": "Age of Sigmar"},
    {"slug": "aos-ossiarch-bonereapers",    "name": "Ossiarch Bonereapers",          "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Ossiarch Bonereapers"',       "group": "Age of Sigmar"},
    {"slug": "aos-flesh-eater-courts",      "name": "Flesh-eater Courts",            "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Death > Flesh-eater Courts"',         "group": "Age of Sigmar"},
    # Grand Alliance Destruction
    {"slug": "aos-orruk-warclans",          "name": "Orruk Warclans",                "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Destruction > Orruk Warclans"',       "group": "Age of Sigmar"},
    {"slug": "aos-gloomspite-gitz",         "name": "Gloomspite Gitz",               "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Destruction > Gloomspite Gitz"',      "group": "Age of Sigmar"},
    {"slug": "aos-ogor-mawtribes",          "name": "Ogor Mawtribes",                "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Destruction > Ogor Mawtribes"',       "group": "Age of Sigmar"},
    {"slug": "aos-sons-of-behemat",         "name": "Sons of Behemat",               "filter": 'GameSystemsRoot.lvl2:"Age of Sigmar > Grand Alliance Destruction > Sons of Behemat"',      "group": "Age of Sigmar"},

    # ---- Skirmish / Specialist ----
    {"slug": "kill-team",                   "name": "Kill Team",                     "filter": 'GameSystemsRoot.lvl1:"Other Games > Kill Team"',                                             "group": "Skirmish"},
    {"slug": "warcry",                      "name": "Warcry",                        "filter": 'GameSystemsRoot.lvl1:"Other Games > Warcry"',                                                "group": "Skirmish"},
    {"slug": "underworlds",                 "name": "Warhammer Underworlds",         "filter": 'GameSystemsRoot.lvl1:"Other Games > Warhammer Underworlds"',                                 "group": "Skirmish"},
    {"slug": "necromunda",                  "name": "Necromunda",                    "filter": 'GameSystemsRoot.lvl1:"Other Games > Necromunda"',                                             "group": "Skirmish"},
    {"slug": "blood-bowl",                  "name": "Blood Bowl",                    "filter": 'GameSystemsRoot.lvl1:"Other Games > Blood Bowl"',                                             "group": "Skirmish"},

    # ---- Horus Heresy ----
    {"slug": "horus-heresy",                "name": "The Horus Heresy",              "filter": 'GameSystemsRoot.lvl0:"The Horus Heresy"',                                                    "group": "Horus Heresy"},
    {"slug": "legions-imperialis",          "name": "Legions Imperialis",            "filter": 'GameSystemsRoot.lvl1:"Other Games > Legions Imperialis"',                                    "group": "Horus Heresy"},

    # ---- The Old World ----
    {"slug": "old-world",                   "name": "The Old World (all)",           "filter": 'GameSystemsRoot.lvl0:"The Old World"',                                                       "group": "The Old World"},
    {"slug": "tow-empire-of-man",           "name": "Empire of Man",                 "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Empire of Man"',             "group": "The Old World"},
    {"slug": "tow-orc-goblin-tribes",       "name": "Orc & Goblin Tribes",           "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Orc and Goblin Tribes"',    "group": "The Old World"},
    {"slug": "tow-dwarfen-mountain-holds",  "name": "Dwarfen Mountain Holds",        "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Dwarfen Mountain Holds"',   "group": "The Old World"},
    {"slug": "tow-warriors-of-chaos",       "name": "Warriors of Chaos",             "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Warriors of Chaos"',        "group": "The Old World"},
    {"slug": "tow-kingdom-of-bretonnia",    "name": "Kingdom of Bretonnia",          "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Kingdom Of Bretonnia"',     "group": "The Old World"},
    {"slug": "tow-high-elf-realms",         "name": "High Elf Realms",               "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > High Elf Realms"',          "group": "The Old World"},
    {"slug": "tow-tomb-kings",              "name": "Tomb Kings of Khemri",          "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Tomb Kings Of Khemri"',     "group": "The Old World"},
    {"slug": "tow-wood-elf-realms",         "name": "Wood Elf Realms",               "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Wood Elf Realms"',          "group": "The Old World"},
    {"slug": "tow-beastman-brayherds",      "name": "Beastman Brayherds",            "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Beastman Brayherds"',       "group": "The Old World"},
    {"slug": "tow-grand-cathay",            "name": "Grand Cathay",                  "filter": 'GameSystemsRoot.lvl2:"The Old World > Armies of the Old World > Grand Cathay"',             "group": "The Old World"},

    # ---- Middle-earth ----
    {"slug": "mesbg",                       "name": "Middle-earth SBG",              "filter": 'GameSystemsRoot.lvl0:"Middle-Earth"',                                                        "group": "Middle-earth"},

    # ---- Hobby / Misc ----
    {"slug": "citadel-paints",              "name": "Citadel Paints & Hobby",        "filter": 'productType:"paintSupply"',                                                                  "group": "Hobby & Misc"},
    {"slug": "black-library",               "name": "Black Library",                 "filter": 'productType:"book"',                                                                         "group": "Hobby & Misc"},
    {"slug": "white-dwarf",                 "name": "White Dwarf",                   "filter": 'productType:"magazine"',                                                                     "group": "Hobby & Misc"},
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
