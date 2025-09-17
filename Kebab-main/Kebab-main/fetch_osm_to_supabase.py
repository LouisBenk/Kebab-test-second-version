import os, sys, json, time, requests
from typing import Optional, Any, Dict, List

# ---- Config (GitHub Secrets / workflow inputs) ----
SUPABASE_URL = (os.environ.get("SUPABASE_URL") or "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_KEY") or ""
CITY       = os.environ.get("CITY") or os.environ.get("DEFAULT_CITY", "Paris")
AREA_NAME  = os.environ.get("AREA_NAME")  # e.g. "Paris 10e Arrondissement"

# Overpass mirrors (try each)
OVERPASS_URLS = [
    "https://overpass.kumi.systems/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.openstreetmap.ru/api/interpreter",
]

def build_query(city: str, area_name: Optional[str]) -> str:
    common = """
(
  node["cuisine"="kebab"](area.a);
  way["cuisine"="kebab"](area.a);
  relation["cuisine"="kebab"](area.a);

  /* also: name contains 'kebab' (case-insensitive) */
  node["name"~"kebab", i](area.a);
  way["name"~"kebab", i](area.a);
  relation["name"~"kebab", i](area.a);
);
out center tags;
""".strip()

    if area_name:
        return f"""[out:json][timeout:60];
area["name"="{area_name}"]["boundary"="administrative"]->.a;
{common}
"""
    return f"""[out:json][timeout:60];
area["name"="{city}"]->.a;
{common}
"""

def norm_address(tags: Dict[str, str]) -> Optional[str]:
    parts = [tags.get("addr:housenumber"), tags.get("addr:street"),
             tags.get("addr:postcode"), tags.get("addr:city")]
    s = ", ".join([p for p in parts if p])
    return s or None

def element_to_row(el: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    tags = el.get("tags", {})
    # accept rows even if 'name' missing → fallback to brand/operator/"Kebab"
    name = tags.get("name") or tags.get("brand") or tags.get("operator") or "Kebab"
    lat  = el.get("lat") or (el.get("center") or {}).get("lat")
    lon  = el.get("lon") or (el.get("center") or {}).get("lon")
    if not (lat and lon):
        return None
    typ = el.get("type")
    prefix = "n" if typ == "node" else "w" if typ == "way" else "r"
    return {
        "id": f"osm-{prefix}_{el['id']}",
        "name": name,
        "address": norm_address(tags),
        "lat": float(lat),
        "lng": float(lon),  # your schema uses 'lng'
        # "is_verified": False,
        # "source": "osm_overpass",
    }

def chunked(items: List[Any], size: int = 500):
    for i in range(0, len(items), size):
        yield items[i:i+size]

def fetch_overpass(query: str) -> Dict[str, Any]:
    last_err: Optional[Exception] = None
    for url in OVERPASS_URLS:
        try:
            r = requests.post(url, data={"data": query}, timeout=180)
            if r.status_code >= 400:
                print(f"[Overpass] {url} -> {r.status_code}\n{r.text[:800]}\n", flush=True)
                continue
            return r.json()
        except Exception as e:
            last_err = e
            print(f"[Overpass] Exception on {url}: {e}", flush=True)
    raise RuntimeError(f"All Overpass endpoints failed. Last error: {last_err}")

def main():
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Missing SUPABASE_URL or SUPABASE_SERVICE_KEY", file=sys.stderr)
        sys.exit(1)

    # 1) Query arrondissement (if provided)
    query = build_query(CITY, AREA_NAME)
    print(f"Fetching OSM kebab POIs for city={CITY} area={AREA_NAME or '(all)'} ...")
    data = fetch_overpass(query)
    elems = data.get("elements", [])
    print(f"Overpass returned {len(elems)} elements.", flush=True)

    rows: List[Dict[str, Any]] = []
    for el in elems:
        row = element_to_row(el)
        if row:
            rows.append(row)

    # 2) Fallback: if area gave nothing, retry city-wide
    if not rows and AREA_NAME:
        print("No rows after filtering (area). Retrying with whole city…", flush=True)
        data2 = fetch_overpass(build_query(CITY, None))
        elems2 = data2.get("elements", [])
        print(f"[Fallback] Overpass returned {len(elems2)} elements.", flush=True)
        for el in elems2:
            row = element_to_row(el)
            if row:
                rows.append(row)

    if not rows:
        print("No rows found after fallback. Nothing to insert.")
        return

    print(f"Prepared {len(rows)} rows. Upserting to Supabase ...")
    endpoint = f"{SUPABASE_URL}/rest/v1/shops?on_conflict=id"
    headers = {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates, return=representation",
    }

    total = 0
    for batch in chunked(rows, 500):
        resp = requests.post(endpoint, headers=headers, data=json.dumps(batch), timeout=180)
        if resp.status_code not in (200, 201, 204):
            print("Upsert error:", resp.status_code, resp.text, file=sys.stderr)
            sys.exit(1)
        total += len(batch)
        time.sleep(0.5)

    label = CITY if not AREA_NAME else f"{CITY} ({AREA_NAME})"
    print(f"Done. Upserted {total} rows for {label}.")

if __name__ == "__main__":
    main()
