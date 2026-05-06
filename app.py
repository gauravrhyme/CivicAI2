"""
CivicAI — Flask Backend v4  (Render-safe)
==========================================
KEY FIXES vs previous version:
  1. Every source wrapped in try/except — one failure never crashes others
  2. /scrape ALWAYS returns 200 with whatever data it has (even seed fallback)
  3. Short per-request timeouts (8s) so Render never times out
  4. /health is instant — no external calls
  5. Startup is instant — no scraping at import time
  6. PORT from environment variable for Render compatibility

Deploy on Render:
  Build Command : pip install -r requirements.txt
  Start Command : python app.py
"""

import csv
import os
import random
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from io import StringIO

import requests
from flask import Flask, jsonify, request
from flask_cors import CORS

# ── App ────────────────────────────────────────────────────────
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# ── Constants ──────────────────────────────────────────────────
OPENCITY_CSV = (
    "https://data.opencity.in/dataset/"
    "3a1a98f8-f924-4257-a2a1-3b957b55b9f5/resource/"
    "22be8fdc-532d-4ec8-8e31-2e6d26d5ce85/download/"
    "e03fbadf-ff1a-4fe1-9aad-a2a38a2bd81d.csv"
)
OPENCITY_KML = (
    "https://data.opencity.in/dataset/"
    "3a1a98f8-f924-4257-a2a1-3b957b55b9f5/resource/"
    "d1d4a437-95ee-4327-9154-f9a8933b2110/download/"
    "63b30ddf-5919-43d0-a6cf-17d5cc90a35c.kml"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "en-IN,en;q=0.9",
}

WARDS = [
    # Yelahanka Zone
    "Kempegowda","Chowdeshwari","Attur Layout","Yelahanka Satellite Town",
    "Kogilu","Thanisandra","Jakkuru","Gundanjaneya Temple Ward",
    "Amrutahalli","Kodigehalli","Vidyaranyapura","Dodda Bommasandra",
    # Dasarahalli Zone
    "Ramachandrapura","Shettihalli","Chikkasandra","Bagalakunte",
    "Mallasandra","T Dasarahalli","Jalahalli","Herohalli",
    # Rajarajeshwari Nagar Zone
    "Chamundi Nagar","Ganganagar","Aramane Nagara","Chokkasandra",
    "Dodda Bidarakallu","Peenya Industrial Area","Rajarajeshwari Nagar",
    "Hosakerehalli","Gollarapalya Hosahalli","Kottegepalya",
    "Hegganahalli","Sunkadakatte",
    # Bangalore West Zone
    "Lakshmi Devi Nagar","Nandini Layout","Marappana Palya","Malleswaram",
    "Rajagopal Nagar","Maruthi Nagar","Laggere","Kushal Nagar",
    "Kaval Bairasandra","Sriramamandir","Dayananda Nagar","Shankar Matt",
    "Manjunath Naga","Shanthala Nagar","Sampangiram Nagar","Gandhinagar",
    "Okalipuram","Rajaji Nagar","Basaveswara Nagar","Vrisabhavathi Nagar",
    "Kaveripura","Agrahara Dasarahalli","Dr. Raj Kumar Ward","Chickpete",
    "Chalavadipalya","Binnipete","Bapuji Nagar","Padarayanapura",
    "Nagarabhavi","Jnana Bharathi Ward","Kengeri",
    "Nagadevanahalli","Ullalu","Konena Agarahara","Jeevan Bheema Nagar",
    "Jogupalya","Subramanya Nagar","Nagapura","Rajamahal Guttahalli",
    # Bangalore East Zone
    "Brundavana Nagar","J P Park","Yeshwanthpura","Mattikere",
    "Radhakrishna Temple Ward","Horamavu","Kalkere","Banasavadi",
    "Kammanahalli","Kacharkanahalli","HBR Layout","Kadugondanahalli",
    "Chellakere","Vijayanagar","Hosahalli","Jayachamarajendra Nagar",
    "Devara Jeevanahalli","Muneshwara Nagar","Lingarajapura",
    "Sagayapuram","Pulikeshinagar","Ramaswamy Palya","Halsoor",
    "Hoysala Nagar","New Tippasandara","Garudachar Playa",
    "Hudi","Kadugodi","Hagadur","Whitefield","Doddanekkundi",
    "HAL Airport","Kalyana Nagar","Maruthi Mandir Ward",
    "Frazer Town","Sanjaya Nagar",
    # Mahadevapura Zone
    "Hebbala","Vishwanath Nagenahalli","Govindapura","Hennur",
    "Benniganahalli","Ramamurthy Nagar","K R Puram","Basavanapura",
    "Devasandra","C V Raman Nagar","Sarvagna Nagar","Maruthi Seva Nagar",
    "Marathahalli","Varthur","Bellandur","Domlur",
    "A Narayanapura","Vijnanapura","Ibluru",
    # Bommanahalli Zone
    "Bommanahalli","Bilekhalli","Hongasandra","Singsandra",
    "Begur","Devarachikkanahalli","Arakere","Kalena Agrahar",
    "Gottigere","Anjanapura","Hemmigepura","Kudlu",
    "Puttenahalli","Chunchaghatta","Jaraganahalli","Vasanthapura",
    "Kumaraswamy Layout","Akshayanagar","Hulimavu","Haralur",
    "Electronic City Phase 1","Electronic City Phase 2",
    "Nyanappana Halli","Garvebhavipalya",
    # Bangalore South Zone
    "Jayanagar","BTM Layout","Madivala","Jakkasandra",
    "HSR Layout","Agara","Koramangala","Lakkasandra","Siddapura",
    "Vishveshwara Puram","Sunkenahalli","Azad Nagar",
    "Deepanjali Nagar","Nayandahalli","Girinagar","Srinagar",
    "Hanumanth Nagar","Katriguppe","Vidyapeeta Ward","Basavanagudi",
    "Byrasandra","Gurappanapalya","Suddagunte Palya","Ragigudda","Sarakki",
    "Karisandra","Padmanabha Nagar","Ittamadu","Uttarahalli",
    "Subramanyapura","Banashankari Temple Ward","Yelchenahalli",
    "JP Nagar","Bannerghatta Road","Attiguppe","Hampi Nagar",
    "K R Market","Hombegowda Nagara","Shivajinagar","Sadashivanagar",
    "Indiranagar","Rajajinagar","Hebbal","Yelahanka",
]

ISSUE_MAP = {
    "Pothole":             ["pothole", "crater", "road damage", "road caved", "bad road"],
    "Garbage":             ["garbage", "waste", "trash", "litter", "dump", "stench", "sanitation"],
    "Water Logging":       ["waterlog", "flood", "water stagnant", "inundat", "water clog"],
    "Open Drain":          ["open drain", "manhole", "gutter", "sewer", "drain cover"],
    "Broken Streetlight":  ["streetlight", "street light", "no light", "dark road", "lamp"],
    "Illegal Dumping":     ["illegal dump", "debris dump", "construction waste"],
    "Damaged Footpath":    ["footpath", "pavement broken", "sidewalk", "broken tiles"],
    "Encroachment":        ["encroach", "illegal construction"],
}

# Seed data — always returned if all sources fail
SEED_ISSUES = [
    {"ward": "Indiranagar",     "description": "Large pothole on 12th Main causing near-miss accidents daily",   "severity": "critical", "issue_type": "Pothole",           "lat": 12.9784, "lon": 77.6408},
    {"ward": "Koramangala",     "description": "Overflowing garbage bins — 5 days uncollected near 5th Block",  "severity": "high",     "issue_type": "Garbage",            "lat": 12.9352, "lon": 77.6245},
    {"ward": "Rajajinagar",     "description": "Exposed open drain near school gate — children at risk",        "severity": "high",     "issue_type": "Open Drain",         "lat": 12.9914, "lon": 77.5530},
    {"ward": "Whitefield",      "description": "Severe waterlogging on ITPL Road — vehicles stuck for 2+ hrs", "severity": "critical", "issue_type": "Water Logging",      "lat": 12.9698, "lon": 77.7499},
    {"ward": "BTM Layout",      "description": "Road caved in on 80ft Road — one lane blocked completely",      "severity": "critical", "issue_type": "Pothole",           "lat": 12.9165, "lon": 77.6101},
    {"ward": "Hebbal",          "description": "Dead animal on main road not removed for 3 days — health risk", "severity": "high",     "issue_type": "Garbage",            "lat": 13.0358, "lon": 77.5970},
    {"ward": "Electronic City", "description": "Deep pothole near IT park gate causing daily accidents",         "severity": "high",     "issue_type": "Pothole",           "lat": 12.8399, "lon": 77.6770},
    {"ward": "Malleswaram",     "description": "3 consecutive streetlights broken — road completely dark",       "severity": "medium",   "issue_type": "Broken Streetlight", "lat": 13.0035, "lon": 77.5709},
    {"ward": "Hebbal",          "description": "Construction debris dumped on public footpath — blocking access","severity": "medium",   "issue_type": "Illegal Dumping",    "lat": 13.0400, "lon": 77.5900},
    {"ward": "HSR Layout",      "description": "Garbage uncollected for 4 days — Sector 2 residents affected",  "severity": "medium",   "issue_type": "Garbage",            "lat": 12.9116, "lon": 77.6370},
]


# ── Helpers ────────────────────────────────────────────────────

def gen_id():
    return "".join(random.choices("ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789", k=7))


def classify_type(text: str) -> str:
    t = text.lower()
    for issue_type, keywords in ISSUE_MAP.items():
        if any(kw in t for kw in keywords):
            return issue_type
    return "Pothole"


def classify_severity(text: str) -> str:
    t = text.lower()
    if any(w in t for w in ["accident", "death", "fatal", "collapse", "emergency", "critical", "hazard"]):
        return "critical"
    if any(w in t for w in ["flood", "major", "severe", "urgent", "horrible", "terrible"]):
        return "high"
    if any(w in t for w in ["minor", "small", "slight"]):
        return "low"
    return "medium"


def infer_ward(text: str) -> str:
    t = text.lower()
    for w in WARDS:
        if w.lower() in t:
            return w
    return random.choice(WARDS)


def valid_blr_coords(lat, lon) -> bool:
    """Check coordinates are within Bengaluru bounding box."""
    return (12.7 < lat < 13.2) and (77.3 < lon < 77.9)


def make_issue(description, source, lat=None, lon=None, ward=None, issue_type=None,
               days_ago=None, source_url=None) -> dict:
    if days_ago is None:
        days_ago = random.randint(0, 14)
    ts = (datetime.utcnow() - timedelta(days=days_ago)).isoformat() + "Z"
    w  = ward or infer_ward(description)
    return {
        "id":            gen_id(),
        "issue_type":    issue_type or classify_type(description),
        "description":   description[:220].strip(),
        "location_name": w,
        "ward":          w if w in WARDS else infer_ward(w),
        "severity":      classify_severity(description),
        "status":        "open",
        "source":        source,
        "source_url":    source_url,
        "latitude":      round(lat, 6) if lat else None,
        "longitude":     round(lon, 6) if lon else None,
        "timestamp":     ts,
        "created_at":    ts,
        "upvotes":       random.randint(1, 50),
        "image_url":     None,
    }


def build_seed_issues() -> list:
    issues = []
    for s in SEED_ISSUES:
        i = make_issue(
            description=s["description"],
            source="seed",
            lat=s["lat"],
            lon=s["lon"],
            ward=s["ward"],
            issue_type=s["issue_type"],
            days_ago=random.randint(1, 30),
        )
        i["severity"] = s["severity"]  # preserve intended severity
        issues.append(i)
    return issues


# ── Data Sources ───────────────────────────────────────────────

def fetch_opencity_csv() -> list:
    """OpenCity Bengaluru pothole CSV — real lat/lon data."""
    results = []
    try:
        resp = requests.get(OPENCITY_CSV, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        reader = csv.DictReader(StringIO(resp.text))

        for i, row in enumerate(reader):
            if i >= 100:
                break

            # Handle multiple possible column names
            ward = (
                row.get("Ward Name") or row.get("ward_name") or
                row.get("Ward")      or row.get("ward") or ""
            ).strip()

            lat_s = (row.get("Latitude") or row.get("latitude") or row.get("lat") or "").strip()
            lon_s = (row.get("Longitude") or row.get("longitude") or row.get("lon") or "").strip()
            desc  = (row.get("Description") or row.get("description") or
                     row.get("Complaint") or row.get("complaint") or "").strip()

            if not desc:
                desc = f"Pothole reported in {ward}" if ward else "Pothole reported"

            try:
                lat = float(lat_s) if lat_s else None
                lon = float(lon_s) if lon_s else None
            except (ValueError, TypeError):
                lat = lon = None

            if lat and lon and not valid_blr_coords(lat, lon):
                lat = lon = None

            results.append(make_issue(
                description=desc,
                source="OpenCity CSV",
                lat=lat,
                lon=lon,
                ward=ward if ward in WARDS else infer_ward(ward + " " + desc),
                issue_type="Pothole",
                days_ago=random.randint(1, 60),
            ))

    except requests.Timeout:
        print("[CSV] Timeout — skipping")
    except Exception as e:
        print(f"[CSV] Error: {e}")

    print(f"[CSV] {len(results)} issues")
    return results


def fetch_opencity_kml() -> list:
    """OpenCity KML — geo-coordinates for pothole locations."""
    results = []
    try:
        resp = requests.get(OPENCITY_KML, headers=HEADERS, timeout=8)
        resp.raise_for_status()

        # Strip namespace for easier parsing
        content = resp.content.decode("utf-8", errors="replace")
        content = re.sub(r'\s+xmlns[^"]*"[^"]*"', "", content)
        content = re.sub(r'<kml:', "<", content)
        content = re.sub(r'</kml:', "</", content)

        root = ET.fromstring(content.encode("utf-8"))

        for p in root.findall(".//Placemark")[:80]:
            name_el  = p.find(".//name")
            desc_el  = p.find(".//description")
            coord_el = p.find(".//coordinates")

            name  = (name_el.text  or "").strip() if name_el  else ""
            desc  = (desc_el.text  or "").strip() if desc_el  else ""
            coord = (coord_el.text or "").strip() if coord_el else ""

            description = desc or name or "Pothole location"

            lat = lon = None
            if coord:
                try:
                    parts = coord.strip().split(",")
                    lon_c = float(parts[0])
                    lat_c = float(parts[1])
                    if valid_blr_coords(lat_c, lon_c):
                        lat, lon = lat_c, lon_c
                except (ValueError, IndexError):
                    pass

            if lat and lon:
                results.append(make_issue(
                    description=description[:200],
                    source="OpenCity KML",
                    lat=lat,
                    lon=lon,
                    issue_type="Pothole",
                    days_ago=random.randint(1, 60),
                ))

    except requests.Timeout:
        print("[KML] Timeout — skipping")
    except Exception as e:
        print(f"[KML] Error: {e}")

    print(f"[KML] {len(results)} issues")
    return results


def fetch_reddit() -> list:
    """r/bangalore via Reddit's public JSON API — no auth required."""
    results = []
    try:
        query = "pothole OR garbage OR drain OR flood OR BBMP OR streetlight OR waterlogging"
        url = (
            f"https://www.reddit.com/r/bangalore/search.json"
            f"?q={requests.utils.quote(query)}&sort=new&restrict_sr=1&limit=20&t=week"
        )
        resp  = requests.get(url, headers=HEADERS, timeout=8)
        resp.raise_for_status()
        posts = resp.json().get("data", {}).get("children", [])

        for post in posts:
            p     = post.get("data", {})
            title = (p.get("title") or "").strip()
            body  = (p.get("selftext") or "").strip()[:150]
            text  = f"{title}. {body}".strip()
            link  = "https://reddit.com" + (p.get("permalink") or "")

            if len(text) < 20:
                continue

            issue = make_issue(description=text, source="reddit", source_url=link)
            results.append(issue)

    except requests.Timeout:
        print("[Reddit] Timeout — skipping")
    except Exception as e:
        print(f"[Reddit] Error: {e}")

    print(f"[Reddit] {len(results)} issues")
    return results


def fetch_google_news() -> list:
    """Google News RSS — Bengaluru civic news. No auth required."""
    results = []
    queries = [
        "Bengaluru pothole BBMP 2025",
        "Bangalore garbage problem civic",
        "Bengaluru waterlogging flood",
        "BBMP road repair drain Bengaluru",
    ]
    for query in queries[:3]:
        try:
            url  = f"https://news.google.com/rss/search?q={requests.utils.quote(query)}&hl=en-IN&gl=IN&ceid=IN:en"
            resp = requests.get(url, headers=HEADERS, timeout=8)
            resp.raise_for_status()
            root  = ET.fromstring(resp.content)
            items = root.findall(".//item")[:5]

            for item in items:
                title = getattr(item.find("title"),       "text", "") or ""
                desc  = getattr(item.find("description"), "text", "") or ""
                link  = getattr(item.find("link"),        "text", "") or ""

                # Strip HTML tags from description
                desc  = re.sub(r"<[^>]+>", " ", desc).strip()
                text  = f"{title}. {desc}".strip()[:220]

                if len(text) < 20:
                    continue

                issue = make_issue(description=text, source="news", source_url=link)
                results.append(issue)

            time.sleep(0.3)

        except requests.Timeout:
            print(f"[News] Timeout for '{query}' — skipping")
        except Exception as e:
            print(f"[News] Error '{query}': {e}")

    print(f"[News] {len(results)} issues")
    return results


# ── Analytics ──────────────────────────────────────────────────

def build_leaderboard(issues: list) -> list:
    counts = {}
    for i in issues:
        w = i.get("ward") or "Unknown"
        counts[w] = counts.get(w, 0) + 1
    ranked = sorted(
        [{"ward": k, "count": v} for k, v in counts.items()],
        key=lambda x: x["count"],
        reverse=True,
    )
    return ranked[:15]


def build_clusters(issues: list) -> list:
    clusters = {}
    for i in issues:
        key = i["description"][:35].strip().lower()
        clusters.setdefault(key, []).append(i)

    result = [
        {"cluster": k.capitalize(), "items": v}
        for k, v in clusters.items()
        if len(v) >= 2
    ]
    result.sort(key=lambda x: len(x["items"]), reverse=True)
    return result[:10]


def deduplicate(issues: list) -> list:
    seen_coords = set()
    seen_desc   = set()
    unique      = []

    for i in issues:
        lat = i.get("latitude")
        lon = i.get("longitude")
        dk  = i["description"][:50].lower().strip()

        if lat and lon:
            ck = (round(lat, 4), round(lon, 4))
            if ck in seen_coords:
                continue
            seen_coords.add(ck)

        if dk in seen_desc:
            continue
        seen_desc.add(dk)
        unique.append(i)

    return unique


# ── Pipeline ───────────────────────────────────────────────────

def run_pipeline(sources_param: str = "csv,kml,reddit,news") -> dict:
    """
    Runs all requested sources in sequence.
    ALWAYS returns a valid response — falls back to seed data if all sources fail.
    """
    sources   = [s.strip().lower() for s in sources_param.split(",")]
    all_issues = []
    sources_fetched = []

    if "csv" in sources:
        data = fetch_opencity_csv()
        all_issues.extend(data)
        if data:
            sources_fetched.append("OpenCity CSV")

    if "kml" in sources:
        data = fetch_opencity_kml()
        all_issues.extend(data)
        if data:
            sources_fetched.append("OpenCity KML")

    if "reddit" in sources:
        data = fetch_reddit()
        all_issues.extend(data)
        if data:
            sources_fetched.append("Reddit")

    if "news" in sources:
        data = fetch_google_news()
        all_issues.extend(data)
        if data:
            sources_fetched.append("Google News")

    # Fallback: if nothing at all came back, use seed
    if not all_issues:
        print("[Pipeline] All sources failed — using seed data")
        all_issues = build_seed_issues()
        sources_fetched = ["Seed (fallback)"]

    unique      = deduplicate(all_issues)
    leaderboard = build_leaderboard(unique)
    clusters    = build_clusters(unique)

    # Sort by severity then recency
    sev_order = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    unique.sort(key=lambda x: (sev_order.get(x.get("severity", "low"), 4),
                               x.get("timestamp", "")))

    print(f"[Pipeline] {len(unique)} unique issues from: {sources_fetched}")
    return {
        "status":          "success",
        "timestamp":       datetime.utcnow().isoformat() + "Z",
        "count":           len(unique),
        "sources_fetched": sources_fetched,
        "issues":          unique,
        "leaderboard":     leaderboard,
        "clusters":        clusters,
    }


# ── Routes ─────────────────────────────────────────────────────

@app.route("/")
def index():
    """Serve the CivicAI HTML frontend."""
    try:
        with open("CivicAI.html", "r", encoding="utf-8") as f:
            return f.read(), 200, {"Content-Type": "text/html; charset=utf-8"}
    except FileNotFoundError:
        return (
            "<h2 style='font-family:sans-serif;padding:40px;color:#e00'>"
            "⚠ CivicAI.html not found<br>"
            "<small>Place CivicAI.html in the same folder as app.py</small></h2>"
        ), 404


@app.route("/scrape")
def scrape():
    """
    Main data API.
    Query params:
      ?sources=csv,kml,reddit,news   (default: all)
      ?limit=100                     (max 200)

    ALWAYS returns HTTP 200 — even if all sources fail (returns seed data).
    This prevents Render 502 errors caused by the frontend receiving non-200.
    """
    sources_param = request.args.get("sources", "csv,kml,reddit,news")
    limit         = min(int(request.args.get("limit", 100)), 200)

    try:
        result = run_pipeline(sources_param)
        result["issues"] = result["issues"][:limit]
        return jsonify(result), 200

    except Exception as e:
        # Last-resort: never return 5xx — always give the frontend something
        print(f"[Scrape] Unexpected error: {e}")
        seed = build_seed_issues()
        return jsonify({
            "status":          "fallback",
            "timestamp":       datetime.utcnow().isoformat() + "Z",
            "count":           len(seed),
            "sources_fetched": ["Seed (emergency fallback)"],
            "issues":          seed[:limit],
            "leaderboard":     build_leaderboard(seed),
            "clusters":        [],
            "error_note":      str(e),
        }), 200   # ← intentionally 200 so frontend doesn't crash


@app.route("/health")
def health():
    """Instant health check — no external calls, no risk of timeout."""
    return jsonify({
        "status":    "ok",
        "service":   "CivicAI",
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "version":   "4.0",
    }), 200


# ── Entry ──────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    print(f"""
╔══════════════════════════════════════════╗
║  CivicAI Flask Backend v4                ║
║  http://0.0.0.0:{port:<5}                   ║
║  GET /         → serves CivicAI.html    ║
║  GET /scrape   → live data JSON          ║
║  GET /health   → instant health check   ║
╚══════════════════════════════════════════╝
""")
    app.run(host="0.0.0.0", port=port, debug=False)
