#!/usr/bin/env python3
"""Search Open Food Facts for products sold in the UK, several searches at once.

Usage:
  python food_search.py "vegetable quarter pounders" "alpro soya unsweetened" [--brand tesco] [--top 5]

Each search prints its top matches, one per line:
  name | brand | kcal, protein, carbohydrate, fat per 100 g | product URL
A value Open Food Facts doesn't have is shown as "?".
"""
import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SEARCH = "https://search.openfoodfacts.org/search"
NUTRIENTS = ["energy-kcal_100g", "proteins_100g", "carbohydrates_100g", "fat_100g"]


def search(words, brand, top):
    query = f'{words} countries_tags:"en:united-kingdom"'
    if brand:
        query += f" brands_tags:{brand.lower()}"
    params = urllib.parse.urlencode({"q": query, "page_size": top,
                                     "fields": "code,product_name,brands,nutriments"})
    req = urllib.request.Request(f"{SEARCH}?{params}",
                                 headers={"User-Agent": "meal-recorder-skill/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            hits = json.load(resp).get("hits", [])
    except urllib.error.HTTPError as err:
        deny = err.headers.get("x-deny-reason")
        if deny:
            return [f"BLOCKED BY SANDBOX NETWORK: {deny}"]
        return [f"error: HTTP {err.code}"]
    except (urllib.error.URLError, TimeoutError) as err:
        return [f"error: {err}"]
    lines = []
    for hit in hits:
        n = hit.get("nutriments") or {}
        values = ", ".join("?" if n.get(k) is None else f"{n[k]:g}" for k in NUTRIENTS)
        brands = ", ".join(hit.get("brands") or []) if isinstance(hit.get("brands"), list) \
            else (hit.get("brands") or "")
        lines.append(f"{hit.get('product_name', '?')} | {brands} | {values} | "
                     f"https://world.openfoodfacts.org/product/{hit.get('code')}")
    return lines or ["no match"]


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("words", nargs="+", help="one search per argument")
    parser.add_argument("--brand", help="only this brand, e.g. tesco")
    parser.add_argument("--top", type=int, default=5)
    args = parser.parse_args(argv)
    with ThreadPoolExecutor(max_workers=len(args.words)) as pool:
        results = list(pool.map(lambda w: search(w, args.brand, args.top), args.words))
    for words, lines in zip(args.words, results):
        print(f"## {words}")
        print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
