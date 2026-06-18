"""Generate ~200 markets (questions) per SUBCATEGORY, grouped by subcategory, and
write one compact JSON file per category to app/data/markets/<slug>.json.

Each subcategory has a fixed scope phrase. Questions are built from
  superlative x object_type x facet
within that scope, which guarantees uniqueness (scope differs per subcategory)
and enough volume to reach 200 per subcategory. object_types are restricted to
the types each category actually has seeded objects for, so the fuzzy search
always has real answers to match.

Run from backend/:  python scripts/build_market_seed.py
"""
import json
import os

OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "app", "data", "markets")

TARGET_PER_SUBCAT = 200

NOUN = {
    "song": "song", "album": "album", "artist": "artist",
    "film": "film", "tv_show": "TV show", "character": "character", "director": "director",
    "anime": "anime", "manga": "manga", "studio": "studio",
    "game": "game", "game_character": "game character",
    "meme": "meme", "sound": "sound", "format": "format", "creator": "creator",
    "athlete": "athlete", "team": "team", "moment": "moment",
    "sneaker": "sneaker", "brand": "brand", "product": "product", "person": "person",
    "dish": "dish", "drink": "drink", "cuisine": "cuisine",
    "book": "book", "author": "author",
    "influencer": "influencer", "place": "place", "city": "city", "venue": "venue",
    "app": "app",
}

# 13 superlatives. {n} = noun. GOAT is restricted to person-like nouns below.
SUPERLATIVES = [
    "Best {n}", "Worst {n}", "Most overrated {n}", "Most underrated {n}",
    "Most iconic {n}", "Most slept-on {n}", "Most influential {n}",
    "Most memorable {n}", "Most legendary {n}", "Most original {n}",
    "Most overhyped {n}", "Most timeless {n}", "GOAT {n}",
]

GOAT_OK = {"athlete", "team", "character", "game_character", "artist", "director", "author"}

# 10 facets (tail fragments). "" = no facet.
FACETS = [
    "", "of all time", "ever", "of the 2010s", "of the 2020s",
    "this year", "right now", "you'd defend", "that's underrated", "for the culture",
]

# Per category: object_types with seeded answers + subcategory -> scope phrase.
# Scope phrases are distinct per subcategory (so prompts never collide) and avoid
# reusing any FACETS string. One "all-time" subcategory per category uses "".
CATEGORIES = {
    "music": {
        "types": ["song", "album", "artist"],
        "subcats": {
            "hip-hop": "in hip-hop", "pop": "in pop", "rnb-alt": "in R&B",
            "rock-indie": "in rock", "desi": "in Indian music", "all-time": "",
        },
    },
    "film-tv": {
        "types": ["film", "tv_show", "character", "director"],
        "subcats": {
            "movies": "in movies", "tv": "in TV", "thriller": "in a thriller",
            "indian-cinema": "in Indian cinema", "world-cinema": "in world cinema",
            "all-time": "",
        },
    },
    "anime-manga": {
        "types": ["anime", "manga", "character", "studio"],
        "subcats": {
            "shonen": "in shonen", "seinen": "in seinen", "action": "in an action series",
            "films": "in anime films", "modern": "in modern anime", "all-time": "",
        },
    },
    "gaming": {
        "types": ["game", "game_character", "studio"],
        "subcats": {
            "rpg": "in RPGs", "open-world": "in open-world games", "indie": "in indie games",
            "fps": "in shooters", "mobile": "in mobile games", "all-time": "",
        },
    },
    "internet": {
        "types": ["meme", "sound", "format", "creator"],
        "subcats": {
            "memes": "in memes", "tiktok": "on TikTok", "youtube": "on YouTube",
            "trends": "in internet trends", "drama": "in internet drama", "all-time": "",
        },
    },
    "sports": {
        "types": ["athlete", "team", "moment"],
        "subcats": {
            "football-soccer": "in football", "cricket": "in cricket", "basketball": "in the NBA",
            "f1": "in F1", "tennis": "in tennis", "all-time": "",
        },
    },
    "fashion": {
        "types": ["sneaker", "brand", "person", "product"],
        "subcats": {
            "sneakers": "in sneakers", "streetwear": "in streetwear", "luxury": "in luxury fashion",
            "aesthetics": "in fashion aesthetics", "it-items": "in fashion this season", "all-time": "",
        },
    },
    "food-drink": {
        "types": ["dish", "drink", "cuisine"],
        "subcats": {
            "indian": "in Indian food", "street": "in street food", "comfort": "for comfort",
            "drinks": "to drink", "desserts": "for dessert", "all-time": "",
        },
    },
    "books-writing": {
        "types": ["book", "author"],
        "subcats": {
            "fiction": "in fiction", "non-fiction": "in non-fiction", "scifi": "in sci-fi",
            "fantasy": "in fantasy", "modern": "in modern writing", "all-time": "",
        },
    },
    "people": {
        "types": ["person", "creator", "influencer"],
        "subcats": {
            "creators": "among creators", "musicians": "in music", "founders": "in tech",
            "actors": "in film", "sports": "in sports", "all-time": "",
        },
    },
    "places": {
        "types": ["place", "city", "venue"],
        "subcats": {
            "cities": "to live in", "nightlife": "for nightlife", "nature": "for a getaway",
            "india": "in India", "abroad": "abroad", "all-time": "",
        },
    },
    "brands-products": {
        "types": ["product", "brand", "app"],
        "subcats": {
            "tech": "in tech", "apps": "among apps", "hype": "in hype products",
            "essentials": "for everyday use", "premium": "in premium brands", "all-time": "",
        },
    },
}


def _prompt(superlative_tpl: str, noun: str, scope: str, facet: str) -> str:
    base = superlative_tpl.format(n=noun)
    parts = [p for p in (base, scope, facet) if p]
    return " ".join(parts) + "?"


def build_subcat(types: list[str], scope: str) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    # Order so variety shows immediately: facet-major, then superlative, then type.
    for facet in FACETS:
        for sup in SUPERLATIVES:
            for otype in types:
                if sup.startswith("GOAT") and otype not in GOAT_OK:
                    continue
                p = _prompt(sup, NOUN[otype], scope, facet)
                key = p.lower()
                if key in seen:
                    continue
                seen.add(key)
                out.append({"prompt": p, "object_type": otype})
                if len(out) >= TARGET_PER_SUBCAT:
                    return out
    return out


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    grand_total = 0
    for slug, cfg in CATEGORIES.items():
        subcats = {
            name: build_subcat(cfg["types"], scope)
            for name, scope in cfg["subcats"].items()
        }
        count = sum(len(v) for v in subcats.values())
        grand_total += count
        path = os.path.join(OUT_DIR, f"{slug}.json")
        with open(path, "w") as f:
            json.dump({"category": slug, "subcategories": subcats}, f, indent=1)
        per = ", ".join(f"{n}:{len(v)}" for n, v in subcats.items())
        print(f"{slug:18} {count:4}  ({per})")
    print(f"--- total: {grand_total} questions across {len(CATEGORIES)} categories ---")


if __name__ == "__main__":
    main()
