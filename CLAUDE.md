# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Kom-Emine hike planner - tool for planning multi-day hikes on Bulgaria's Kom-Emine (E3) trail.

### Trail Overview
- **Route**: Kom Peak (2016m, Serbia border) to Cape Emine (Black Sea)
- **Distance**: ~555 km (varies by route choices)
- **Duration**: Traditional 21 days, but flexible
- **Highest point**: Botev Peak (2376m)
- **Markings**: Red/white, winter poles with azimuth plates
- **Part of**: European E3 long-distance path

### Key Sections
1. Western Balkan: Kom - Petrohan - Lakatnik (low, 400-1500m)
2. Central Balkan: Etropole - Botev Peak - Shipka (high alpine, 1500-2376m, Central Balkan National Park)
3. Eastern Balkan: Shipka - Kotel - Emine (moderate, 400-1400m)

### Traditional 21-Day Itinerary (from kom-emine.bg)
| Day | Route | km | hrs |
|-----|-------|-----|-----|
| 1 | Berkovitsa → Petrohan | 28 | 9 |
| 2 | Petrohan → Proboinitsa | 16 | 5 |
| 3 | Proboinitsa → Trastena | 28 | 7 |
| 4 | Trastena → Leskova | 22 | 7 |
| 5 | Leskova → Vitinya | 39 | 10 |
| 6 | Vitinya → Chavdar | 18 | 6 |
| 7 | Chavdar → Momina Polyana | 33 | 8 |
| 8 | Momina Polyana → Echo | 32 | 9 |
| 9 | Echo → Dobrila | 32 | 11 |
| 10 | Dobrila → Botev shelter | 14 | 10 |
| 11 | Botev → Mazalat | 24 | 10 |
| 12 | Mazalat → Buzludzha | 33 | 9 |
| 13 | Buzludzha → Gramadliva | 30 | 10 |
| 14 | Gramadliva → Chumerna | 32 | 11 |
| 15 | Chumerna → Vratnik | 27 | 9 |
| 16 | Vratnik → Kotel | 27 | 8 |
| 17 | Kotel → Varbishki prohod | 28 | 9 |
| 18 | Varbishki → Hazim shelter | 28 | 12 |
| 19 | Hazim → Topchiisko | 44 | 12 |
| 20 | Topchiisko → Kozichino | 24 | 6 |
| 21 | Kozichino → Cape Emine | 39 | 11 |

### Data Sources

**`KE-route-2020.pdf`** - detailed waypoint table (~170 points):
- Cumulative/sector km (total 555.3 km)
- Sector walking time
- Description (Bulgarian)
- GPS coords (N/E format)
- Elevation (m)
- Water sources, huts, villages, route variants

**`KE-water-2023.gpx`** - Garmin waypoints (178 total):
- ~130 water points with status notes
- ~48 huts/shelters
- Key status indicators:
  - `пресъхва` = dries up seasonally
  - `ОТКЛ.` = off-route detour
  - `слаба` = weak flow
  - `спряна` = turned off

## Goal

Extract PDF data into queryable format (CSV/SQLite) to:
- Plan custom itineraries (8-day, 20-day, etc.)
- Find accommodation options (huts, villages, camping)
- Calculate daily distances/elevation
- Identify water sources
- Choose route variants

## Data Directory

```
data/
├── kom-emine.db             # SQLite database (unified)
├── parsed/
│   ├── pdf-waypoints.csv    # 201 route points from PDF
│   └── gpx-waypoints.csv    # 178 water/POI from GPX
└── external/
    ├── huts-kom-emine-bg.csv
    ├── itinerary-21day.csv
    ├── osm-relation-254283.xml
    ├── waymarked-info.json  # Full route geometry 559km
    └── README.md
```

## Database Schema

```sql
route_waypoints (201 rows) - km markers, times, coords, elevation
water_points (178 rows)    - water sources with status (ok/seasonal/dry/weak)
huts (49 rows)             - working huts with phones
itinerary_21day (21 rows)  - traditional schedule
```

## Project Structure

```
kom-emine/
├── data/                  # SQLite + CSVs
├── scripts/               # Python tools
│   ├── build.sh           # Rebuild DB + export JSON
│   ├── create_database.py # Build SQLite
│   ├── export_json.py     # Export to web/data/
│   ├── parse_gpx.py       # GPX → CSV
│   ├── query.py           # Example queries
│   └── planner_v4.py      # DP trip planner (RECOMMENDED)
├── web/                   # Static frontend (Cloudflare Pages)
│   ├── index.html
│   ├── static/
│   │   ├── app.js         # Main app logic
│   │   ├── api.js         # Client-side data API
│   │   └── style.css
│   └── data/              # JSON exports (generated)
└── tui/                   # Rust TUI (separate)
```

## Trip Planner

```bash
# Plan 12-day trip (comfortable, max 60km/day)
python3 scripts/planner_v4.py 12

# Plan 11-day trip (challenging, needs 68km max days)
python3 scripts/planner_v4.py 11

# Plan 10-day trip (extreme, needs 75km max days)
python3 scripts/planner_v4.py 10
```

### Key Constraints

**Hut gaps forcing long days:**
- Varbitsa (416km) → Ralio Villa (475km) = **59km** via Hazim Shelter
- Bukovets (331km) → Naboznikovo (386km) = **56km** via Chumerna

**Minimum feasible days (on-route huts only):**
- **12 days**: all days ≤60km (max 59km) - recommended
- **11 days**: needs 65km max - challenging
- **10 days**: needs 68km max - very challenging

**On-route huts (27 total, extracted from PDF):** Petrohan, Trastena, Leskova, Vitinya, Kashana, Echo, Kozya Stena, Dermenka, Dobrila, Botev Shelter, Tazha, Mazalat, Partizanska Pesen, Uzana, Buzludzha, Gramadliva, Himik, Predela, Karaivanovo Shelter, Bukovets, Chumerna, Naboznikovo Shelter, Varbitsa, Hazim Shelter, Ralio Villa, Kozichino, Emona

## Getting Started

```bash
# 1. Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 2. Rebuild database and export JSON
./scripts/build.sh

# 3. Start local web server
python3 -m http.server -d web 8000
# Open http://localhost:8000
```

### Web Planner Features
- Filter waypoints by type (huts, shelters, villages, towns)
- Click row to add/remove stops (auto-sorted by km)
- Elevation profile chart with day markers (pan enabled, no scroll zoom)
- Click day row → segment preview modal with:
  - Detailed elevation chart (ascent=red, descent=blue)
  - Elevation segments table (clickable highlights)
  - POIs: huts, water sources, villages, passes, peaks
- Hover waypoint rows → tooltip shows distance from previous stop
- Route persists in localStorage

### Deployment

**Live**: https://kom-emine.pages.dev

**Cloudflare Pages** (auto-deploy on push):
- Build command: (empty - static site)
- Build output directory: `web`
- Root directory: `/`

## Usage

```bash
# Rebuild database
python3 scripts/create_database.py

# Query examples
python3 scripts/query.py
```

```python
# In Python
from scripts.query import water_between_km, huts_between_km
water_between_km(100, 150)  # Water sources km 100-150
huts_between_km(200, 250)   # Huts km 200-250
```

## External Data Sources

- [kom-emine.bg huts](https://kom-emine.bg/huts-all-en/?lang=en) - 50+ huts w/ coords, phones, status
- [Ponor.org Google Sheet](https://docs.google.com/spreadsheets/d/1vsOh5NTAhdXA0o8YL_cIbh7e7SswSbQYm5frPbY4oIU) - stage distances/times
- [OSM Relation #254283](https://www.openstreetmap.org/relation/254283) - 593 way members, full geometry
- [BGMountains GPX](https://bgmountains.org/en/gps-tracks/cats/download/46-stara-planina/300-kom-emine) - track download

## References

- [Wikipedia](https://en.wikipedia.org/wiki/Kom%E2%80%93Emine)
- [ERA E3 Page](https://www.era-ewv-ferp.org/e-paths/e3/e3-in-bulgaria/)
- [Bulguides](https://bulguides.com/product/e3-route-kom-emine-guidebook-of-balkan-mountains/)
- [kom-emine.bg](https://kom-emine.bg/)
