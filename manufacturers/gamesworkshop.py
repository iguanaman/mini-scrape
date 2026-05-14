"""Games Workshop manufacturer — sources catalogue from Goblin Gaming (Shopify).

GW's own site is behind AWS WAF so we can't hit it directly. Goblin Gaming
stocks the full GW range and exposes Shopify's `collections/{handle}/products.json`
endpoint, which gives us SKUs in variant fields — much better for grouping
than the previous Element-based source.
"""
from curl_cffi.requests import AsyncSession

SLUG = "gamesworkshop"
NAME = "Games Workshop"
ICON = "/static/icons/gamesworkshop.ico"
BASE = "https://www.goblingaming.co.uk"

RANGES = [
    # ---- Warhammer 40,000 ----
    {"slug": "40k",                       "name": "Warhammer 40,000 (all)",         "handle": "warhammer-40k",                                                          "group": "Warhammer 40,000"},
    {"slug": "40k-starter-sets",          "name": "Starter Sets & Combat Patrols",  "handle": "warhammer-40k-starter-sets-combat-patrols-goblin-gaming",                "group": "Warhammer 40,000"},
    {"slug": "40k-scenery",               "name": "Scenery & Terrain",              "handle": "warhammer-40k-scenery",                                                  "group": "Warhammer 40,000"},
    {"slug": "40k-essentials",            "name": "Essentials",                     "handle": "warhammer-40k-essentials",                                               "group": "Warhammer 40,000"},
    {"slug": "40k-space-marines",         "name": "Space Marines",                  "handle": "warhammer-40k-adeptus-astartes-space-marines",                           "group": "Warhammer 40,000"},
    {"slug": "40k-space-wolves",          "name": "Space Wolves",                   "handle": "warhammer-40k-space-wolves",                                             "group": "Warhammer 40,000"},
    {"slug": "40k-grey-knights",          "name": "Grey Knights",                   "handle": "warhammer-40k-grey-knights",                                             "group": "Warhammer 40,000"},
    {"slug": "40k-adepta-sororitas",      "name": "Adepta Sororitas",               "handle": "sisters-of-battle",                                                      "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-custodes",      "name": "Adeptus Custodes",               "handle": "adeptus-custodes",                                                       "group": "Warhammer 40,000"},
    {"slug": "40k-adeptus-mechanicus",    "name": "Adeptus Mechanicus",             "handle": "warhammer-40k-adeptus-mechanicus",                                       "group": "Warhammer 40,000"},
    {"slug": "40k-astra-militarum",       "name": "Astra Militarum",                "handle": "warhammer-40k-astra-militarum",                                          "group": "Warhammer 40,000"},
    {"slug": "40k-imperial-knights",      "name": "Imperial Knights",               "handle": "warhammer-40k-imperial-knights",                                         "group": "Warhammer 40,000"},
    {"slug": "40k-imperial-agents",       "name": "Imperial Agents",                "handle": "warhammer-40000-imperial-agents",                                        "group": "Warhammer 40,000"},
    {"slug": "40k-imperial-forces",       "name": "Imperial Forces (misc)",         "handle": "warhammer-40k-imperial-forces",                                          "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-space-marines",   "name": "Chaos Space Marines",            "handle": "warhammer-40k-chaos-space-marines",                                      "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-daemons",         "name": "Chaos Daemons",                  "handle": "warhammer-40k-chaos-daemons",                                            "group": "Warhammer 40,000"},
    {"slug": "40k-chaos-knights",         "name": "Chaos Knights",                  "handle": "warhammer-40k-chaos-knights",                                            "group": "Warhammer 40,000"},
    {"slug": "40k-world-eaters",          "name": "World Eaters",                   "handle": "40k-world-eaters",                                                       "group": "Warhammer 40,000"},
    {"slug": "40k-aeldari",               "name": "Aeldari",                        "handle": "warhammer-40k-aeldari",                                                  "group": "Warhammer 40,000"},
    {"slug": "40k-harlequins",            "name": "Aeldari Harlequins",             "handle": "warhammer-40k-eldar-harlequins",                                         "group": "Warhammer 40,000"},
    {"slug": "40k-drukhari",              "name": "Drukhari",                       "handle": "warhammer-40k-dark-eldar",                                               "group": "Warhammer 40,000"},
    {"slug": "40k-necrons",               "name": "Necrons",                        "handle": "warhammer-40k-necrons",                                                  "group": "Warhammer 40,000"},
    {"slug": "40k-orks",                  "name": "Orks",                           "handle": "warhammer-40k-orks",                                                     "group": "Warhammer 40,000"},
    {"slug": "40k-tau-empire",            "name": "T'au Empire",                    "handle": "warhammer-40k-tau-empire",                                               "group": "Warhammer 40,000"},
    {"slug": "40k-tyranids",              "name": "Tyranids",                       "handle": "warhammer-40k-tyranids",                                                 "group": "Warhammer 40,000"},
    {"slug": "40k-genestealer-cults",     "name": "Genestealer Cults",              "handle": "warhammer-40k-genestealer-cults",                                        "group": "Warhammer 40,000"},

    # ---- Age of Sigmar ----
    {"slug": "aos",                       "name": "Age of Sigmar (all)",            "handle": "warhammer-age-of-sigmar",                                                "group": "Age of Sigmar"},
    {"slug": "aos-starter-sets",          "name": "Starter Sets & Spearhead",       "handle": "warhammer-age-of-sigmar-starter-sets-spearhead-boxes",                   "group": "Age of Sigmar"},
    {"slug": "aos-scenery",               "name": "Scenery & Terrain",              "handle": "warhammer-age-of-sigmar-scenery",                                        "group": "Age of Sigmar"},
    {"slug": "aos-essentials",            "name": "Essentials",                     "handle": "warhammer-age-of-sigmar-essentials",                                     "group": "Age of Sigmar"},
    {"slug": "aos-stormcast-eternals",    "name": "Stormcast Eternals",             "handle": "warhammer-age-of-sigmar-grand-alliance-of-order-stormcast-eternals",     "group": "Age of Sigmar"},
    {"slug": "aos-cities-of-sigmar",      "name": "Cities of Sigmar",               "handle": "warhammer-age-of-sigmar-grand-alliance-order-free-people",               "group": "Age of Sigmar"},
    {"slug": "aos-daughters-of-khaine",   "name": "Daughters of Khaine",            "handle": "warhammer-age-of-sigmar-grand-alliance-of-order-daughters-of-khaine",    "group": "Age of Sigmar"},
    {"slug": "aos-fyreslayers",           "name": "Fyreslayers",                    "handle": "warhammer-age-of-sigmar-grand-alliance-order-fyreslayers",               "group": "Age of Sigmar"},
    {"slug": "aos-idoneth-deepkin",       "name": "Idoneth Deepkin",                "handle": "warhammer-age-of-sigmar-grand-alliance-order-idoneth-deepkin",           "group": "Age of Sigmar"},
    {"slug": "aos-kharadron-overlords",   "name": "Kharadron Overlords",            "handle": "warhammer-age-of-sigmar-grand-alliance-order-kharadron-overlords",       "group": "Age of Sigmar"},
    {"slug": "aos-lumineth-realm-lords",  "name": "Lumineth Realm-Lords",           "handle": "lumineth-realm-lords",                                                   "group": "Age of Sigmar"},
    {"slug": "aos-seraphon",              "name": "Seraphon",                       "handle": "warhammer-age-of-sigmar-grand-alliance-of-order-seraphon",               "group": "Age of Sigmar"},
    {"slug": "aos-sylvaneth",             "name": "Sylvaneth",                      "handle": "warhammer-age-of-sigmar-grand-alliance-order-sylvaneth",                 "group": "Age of Sigmar"},
    {"slug": "aos-duardin",               "name": "Duardin (misc)",                 "handle": "warhammer-age-of-sigmar-grand-alliance-order-duardins",                  "group": "Age of Sigmar"},
    {"slug": "aos-blades-of-khorne",      "name": "Blades of Khorne",               "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-blades-of-khorne",          "group": "Age of Sigmar"},
    {"slug": "aos-disciples-of-tzeentch", "name": "Disciples of Tzeentch",          "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-disciples-of-tzeentch",     "group": "Age of Sigmar"},
    {"slug": "aos-maggotkin-of-nurgle",   "name": "Maggotkin of Nurgle",            "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-maggotkin-of-nurgle",       "group": "Age of Sigmar"},
    {"slug": "aos-hedonites-of-slaanesh", "name": "Hedonites of Slaanesh",          "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-hedonites-of-slaanesh",     "group": "Age of Sigmar"},
    {"slug": "aos-skaven",                "name": "Skaven",                         "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-skaven-clans",              "group": "Age of Sigmar"},
    {"slug": "aos-slaves-to-darkness",    "name": "Slaves to Darkness",             "handle": "warhammer-age-of-sigmar-grand-alliance-chaos-slaves-to-darkness",        "group": "Age of Sigmar"},
    {"slug": "aos-gloomspite-gitz",       "name": "Gloomspite Gitz",                "handle": "warhammer-age-of-sigmar-grand-alliance-of-destruction-gloomspite-gitz",  "group": "Age of Sigmar"},
    {"slug": "aos-ogor-mawtribes",        "name": "Ogor Mawtribes",                 "handle": "warhammer-age-of-sigmar-grand-alliance-of-destruction-ogres",            "group": "Age of Sigmar"},
    {"slug": "aos-orruk-warclans",        "name": "Orruk Warclans",                 "handle": "warhammer-age-of-sigmar-grand-alliance-of-destruction-orruk-warclans",   "group": "Age of Sigmar"},
    {"slug": "aos-sons-of-behemat",       "name": "Sons of Behemat",                "handle": "sons-of-behemat-warhammer-age-of-sigmar-grand-alliance-of-destruction",  "group": "Age of Sigmar"},
    {"slug": "aos-flesh-eater-courts",    "name": "Flesh-eater Courts",             "handle": "warhammer-age-of-sigmar-grand-alliance-death-flesh-eater-courts",        "group": "Age of Sigmar"},
    {"slug": "aos-nighthaunt",            "name": "Nighthaunt",                     "handle": "warhammer-age-of-sigmar-grand-alliance-death-nighthaunt",                "group": "Age of Sigmar"},
    {"slug": "aos-ossiarch-bonereapers",  "name": "Ossiarch Bonereapers",           "handle": "warhammer-age-of-sigmar-grand-alliance-death-deathrattle",               "group": "Age of Sigmar"},
    {"slug": "aos-soulblight-gravelords", "name": "Soulblight Gravelords",          "handle": "warhammer-age-of-sigmar-soulblight-gravelords",                          "group": "Age of Sigmar"},

    # ---- Skirmish / Specialist ----
    {"slug": "kill-team",                 "name": "Kill Team",                      "handle": "warhammer-40k-kill-team",                                                "group": "Skirmish"},
    {"slug": "warcry",                    "name": "Warcry",                         "handle": "warcry",                                                                 "group": "Skirmish"},
    {"slug": "underworlds",               "name": "Warhammer Underworlds",          "handle": "warhammer-underworlds",                                                  "group": "Skirmish"},
    {"slug": "blood-bowl",                "name": "Blood Bowl",                     "handle": "blood-bowl",                                                             "group": "Skirmish"},
    {"slug": "necromunda",                "name": "Necromunda",                     "handle": "necromunda",                                                             "group": "Skirmish"},

    # ---- Horus Heresy / Epic ----
    {"slug": "horus-heresy",              "name": "The Horus Heresy",               "handle": "the-horus-heresy",                                                       "group": "Horus Heresy & Epic"},
    {"slug": "legions-imperialis",        "name": "Legions Imperialis",             "handle": "legions-imperialis",                                                     "group": "Horus Heresy & Epic"},
    {"slug": "adeptus-titanicus",         "name": "Adeptus Titanicus",              "handle": "adeptus-titanicus",                                                      "group": "Horus Heresy & Epic"},

    # ---- The Old World ----
    {"slug": "old-world",                 "name": "The Old World (all)",            "handle": "warhammer-the-old-world",                                                "group": "The Old World"},
    {"slug": "old-world-bretonnia",       "name": "Kingdom of Bretonnia",           "handle": "kingdom-of-bretonnia-warhammer-the-old-world",                           "group": "The Old World"},
    {"slug": "old-world-dwarfs",          "name": "Dwarfen Mountain Holds",         "handle": "dwarfen-mountain-holds-warhammer-the-old-world",                         "group": "The Old World"},
    {"slug": "old-world-orcs-goblins",    "name": "Orcs & Goblin Tribes",           "handle": "orcs-goblin-tribes-warhammer-the-old-world",                             "group": "The Old World"},
    {"slug": "old-world-tomb-kings",      "name": "Tomb Kings of Khemri",           "handle": "tomb-kings-of-khemri-warhammer-the-old-world",                           "group": "The Old World"},

    # ---- Middle-earth ----
    {"slug": "mesbg",                     "name": "Middle-earth SBG",               "handle": "the-lord-of-the-rings",                                                  "group": "Middle-earth"},
    {"slug": "mesbg-hobbit",              "name": "The Hobbit",                     "handle": "the-hobbit",                                                             "group": "Middle-earth"},

    # ---- Hobby / Misc ----
    {"slug": "citadel-paints",            "name": "Citadel Paints & Hobby",         "handle": "citadel",                                                                "group": "Hobby & Misc"},
    {"slug": "gw-terrain",                "name": "Terrain & Scenery (all)",        "handle": "terrain-games-workshop",                                                 "group": "Hobby & Misc"},
    {"slug": "gw-dice",                   "name": "Dice",                           "handle": "dice-games-workshop",                                                    "group": "Hobby & Misc"},
    {"slug": "battleforces",              "name": "Battleforces (boxed deals)",     "handle": "warhammer-battleforces",                                                 "group": "Hobby & Misc"},
    {"slug": "white-dwarf",               "name": "White Dwarf",                    "handle": "white-dwarf",                                                            "group": "Hobby & Misc"},
    {"slug": "black-library",             "name": "Black Library",                  "handle": "books-the-black-library",                                                "group": "Hobby & Misc"},
]


async def fetch_range(range_def: dict, client: AsyncSession) -> list[dict]:
    handle = range_def["handle"]
    out: list[dict] = []
    page = 1
    while True:
        url = f"{BASE}/collections/{handle}/products.json"
        r = await client.get(url, params={"limit": 250, "page": page}, timeout=15)
        r.raise_for_status()
        data = r.json()
        products = data.get("products", [])
        if not products:
            break
        for p in products:
            variants = p.get("variants") or []
            v = variants[0] if variants else {}
            try:
                price = float(v.get("price")) if v.get("price") is not None else None
            except (TypeError, ValueError):
                price = None
            images = p.get("images") or []
            image_url = images[0].get("src") if images else None
            out.append({
                "title": p.get("title"),
                "sku": v.get("sku"),
                "url": f"{BASE}/products/{p.get('handle')}",
                "image_url": image_url,
                "price": price,
            })
        if len(products) < 250:
            break
        page += 1
    return out
