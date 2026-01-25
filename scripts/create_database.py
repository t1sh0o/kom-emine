#!/usr/bin/env python3
"""Create unified SQLite database from parsed data."""
import sqlite3
import csv
from pathlib import Path

BASE = Path('/Users/ttonov/projects/personal/kom-emine')
DB_PATH = BASE / 'data' / 'kom-emine.db'

def create_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Route waypoints from PDF
    c.execute('''CREATE TABLE IF NOT EXISTS route_waypoints (
        id INTEGER PRIMARY KEY,
        sector_km REAL,
        total_km REAL,
        sector_time TEXT,
        direction TEXT,
        description TEXT,
        lat REAL,
        lon REAL,
        elevation_m INTEGER,
        technical INTEGER DEFAULT 0
    )''')

    # Precomputed segment elevation gain/loss (from GPX track)
    c.execute('''CREATE TABLE IF NOT EXISTS segment_elevations (
        from_waypoint_id INTEGER,
        to_waypoint_id INTEGER,
        elevation_gain INTEGER,
        elevation_loss INTEGER,
        track_points INTEGER,
        PRIMARY KEY (from_waypoint_id, to_waypoint_id)
    )''')

    # Simplified track points for elevation profile (~100m intervals)
    c.execute('''CREATE TABLE IF NOT EXISTS track_profile (
        id INTEGER PRIMARY KEY,
        km REAL,
        elevation INTEGER,
        lat REAL,
        lon REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_track_km ON track_profile(km)')

    # Water/POI from GPX
    c.execute('''CREATE TABLE IF NOT EXISTS water_points (
        id INTEGER PRIMARY KEY,
        name TEXT,
        type TEXT,
        lat REAL,
        lon REAL,
        elevation_m REAL,
        status TEXT,
        off_route INTEGER,
        comment TEXT
    )''')

    # Huts - on-route from PDF
    c.execute('''CREATE TABLE IF NOT EXISTS huts (
        id INTEGER PRIMARY KEY,
        name TEXT,
        name_en TEXT,
        km REAL,
        region TEXT,
        lat REAL,
        lon REAL,
        phone TEXT,
        status TEXT
    )''')

    # 21-day itinerary
    c.execute('''CREATE TABLE IF NOT EXISTS itinerary_21day (
        day INTEGER PRIMARY KEY,
        from_location TEXT,
        to_location TEXT,
        distance_km REAL,
        duration_hrs REAL,
        elevation_gain_m INTEGER
    )''')

    conn.commit()
    return conn

def load_pdf_waypoints(conn):
    c = conn.cursor()
    c.execute('DELETE FROM route_waypoints')

    count = 0
    with open(BASE / 'data/parsed/pdf-waypoints.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            c.execute('''INSERT INTO route_waypoints
                (sector_km, total_km, sector_time, direction, description, lat, lon, elevation_m)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    float(row['sector_km']) if row['sector_km'] else None,
                    float(row['total_km']) if row['total_km'] else None,
                    row['sector_time'],
                    row['direction'],
                    row['description'],
                    float(row['lat']) if row['lat'] else None,
                    float(row['lon']) if row['lon'] else None,
                    int(row['elevation_m']) if row['elevation_m'] else None
                ))
            count += 1
    conn.commit()
    print(f"Loaded {count} route waypoints")

def load_gpx_waypoints(conn):
    c = conn.cursor()
    c.execute('DELETE FROM water_points')

    count = 0
    with open(BASE / 'data/parsed/gpx-waypoints.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            c.execute('''INSERT INTO water_points
                (name, type, lat, lon, elevation_m, status, off_route, comment)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)''',
                (
                    row['name'],
                    row['type'],
                    float(row['lat']),
                    float(row['lon']),
                    float(row['elevation_m']) if row['elevation_m'] else None,
                    row['status'],
                    1 if row['off_route'] == 'True' else 0,
                    row['comment']
                ))
            count += 1
    conn.commit()
    print(f"Loaded {count} water/POI points")

def load_huts(conn):
    """Extract on-route huts from PDF waypoints data."""
    c = conn.cursor()
    c.execute('DROP TABLE IF EXISTS huts')
    c.execute('''CREATE TABLE huts (
        id INTEGER PRIMARY KEY,
        name TEXT,
        name_en TEXT,
        km REAL,
        region TEXT,
        lat REAL,
        lon REAL,
        phone TEXT,
        status TEXT
    )''')

    # Bulgarian to English name translations
    translations = {
        'Петрохан': 'Petrohan',
        'Тръстена': 'Trastena',
        'Лескова': 'Leskova',
        'Витиня': 'Vitinya',
        'Кашана': 'Kashana',
        'Ехо': 'Echo',
        'Козя Стена': 'Kozya Stena',
        'Дерменка': 'Dermenka',
        'Добрила': 'Dobrila',
        'Ботев': 'Botev Shelter',
        'Тъжа': 'Tazha',
        'Мазалат': 'Mazalat',
        'Партизанска Песен': 'Partizanska Pesen',
        'Узана': 'Uzana',
        'Бузлуджа': 'Buzludzha',
        'Грамадлива': 'Gramadliva',
        'Химик': 'Himik',
        'Предела': 'Predela',
        'Караиваново': 'Karaivanovo Shelter',
        'Буковец': 'Bukovets',
        'Чумерна': 'Chumerna',
        'Набожниково': 'Naboznikovo Shelter',
        'Варбишки': 'Varbishki Pass',
        'Хазим': 'Hazim Shelter',
        'Ральо': 'Ralio Villa',
        'Дъскотна': 'Daskotna',
        'Добра Поляна': 'Topchiysko',
        'Козичино': 'Kozichino',
        'Емона': 'Emona',
        'Върбица': 'Varbitsa',
        'Котел': 'Kotel',
    }

    # Phone numbers (from external sources)
    phones = {
        'Leskova': '0877770184',
        'Vitinya': '0882966497',
        'Dobrila': '0884102501',
        'Partizanska Pesen': '0897952532',
        'Uzana': '0886792982',
        'Buzludzha': '0897083077',
        'Gramadliva': '0898765424',
        'Bukovets': '0896693170',
        'Chumerna': '0896693176',
        'Varbishki Pass': '0888855412',
        'Ralio Villa': '0887795896',
        'Topchiysko': '0884473735',
        'Kozichino': '0896715934',
        'Varbitsa': '0888855412',
    }

    # Keywords indicating accommodation (at start of description or after prefix)
    # Note: 'заслон' (shelter) excluded - can't sleep there
    hut_keywords = ['хижа ', 'т.с. ', 'Ски-база ', 'курорт ']
    village_keywords = ['Туристическа спалня', 'спи се в вилата', 'влизаме в село Емона', 'КОТЕЛ - център']

    # Query waypoints for huts (include entries without coords - will estimate)
    c.execute('''SELECT total_km, lat, lon, description FROM route_waypoints
                 ORDER BY total_km''')

    seen_names = set()  # Avoid duplicates
    count = 0

    for row in c.fetchall():
        km, lat, lon, desc = row

        # Skip if marked as detour with significant distance (+1000m or more)
        if '+' in desc:
            import re
            detour = re.search(r'\+(\d+)/', desc) or re.search(r'\+(\d+)$', desc)
            if detour and int(detour.group(1)) >= 1000:
                continue

        # Skip "shortcut" entries, but NOT "razkloni" (junctions) to huts
        if 'Шорткът' in desc:
            continue
        # Skip razkloni that are just for other destinations (not huts)
        if 'разклон за' in desc.lower() and 'хижа' not in desc.lower():
            continue

        # Check if this is a hut entry
        is_hut = any(desc.startswith(kw) or f' {kw}' in desc for kw in hut_keywords)
        is_village = any(kw in desc for kw in village_keywords)

        if not is_hut and not is_village:
            continue

        # Extract hut name from description
        name_bg = desc
        for prefix in hut_keywords:
            if prefix in name_bg:
                # Get text after the prefix
                idx = name_bg.find(prefix) + len(prefix)
                name_bg = name_bg[idx:].split('/')[0].split('(')[0].split('+')[0].strip()
                break

        # Handle village accommodations
        if is_village:
            if 'вилата на Ральо' in desc:
                name_bg = 'Вила Ральо'
            elif 'Козичино' in desc:
                name_bg = 'Козичино'
            elif 'Емона' in desc:
                name_bg = 'Емона'
            elif 'КОТЕЛ' in desc or 'Котел' in desc:
                name_bg = 'Котел'

        # Skip if we've seen this name already (avoid duplicates)
        if name_bg in seen_names:
            continue
        seen_names.add(name_bg)

        # Get English translation
        name_en = None
        for bg, en in translations.items():
            if bg in name_bg or bg in desc:
                name_en = en
                break

        if not name_en:
            name_en = name_bg  # Keep Bulgarian if no translation

        # Determine region based on km
        if km < 105:
            region = 'Western'
        elif km < 245:
            region = 'Central'
        elif km < 500:
            region = 'Eastern'
        else:
            region = 'Coast'

        # Get phone if available
        phone = phones.get(name_en, '')

        # Estimate coordinates if missing (interpolate from nearby waypoints)
        if lat is None or lon is None:
            c.execute('''SELECT lat, lon FROM route_waypoints
                         WHERE lat IS NOT NULL AND total_km < ?
                         ORDER BY total_km DESC LIMIT 1''', (km,))
            prev = c.fetchone()
            c.execute('''SELECT lat, lon FROM route_waypoints
                         WHERE lat IS NOT NULL AND total_km > ?
                         ORDER BY total_km LIMIT 1''', (km,))
            next_pt = c.fetchone()
            if prev and next_pt:
                lat = (prev[0] + next_pt[0]) / 2
                lon = (prev[1] + next_pt[1]) / 2

        c.execute('''INSERT INTO huts
            (name, name_en, km, region, lat, lon, phone, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, 'working')''',
            (name_bg, name_en, km, region, lat, lon, phone))
        count += 1

    conn.commit()
    print(f"Loaded {count} on-route huts from PDF")

def load_itinerary(conn):
    c = conn.cursor()
    c.execute('DELETE FROM itinerary_21day')

    with open(BASE / 'data/external/itinerary-21day.csv', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            c.execute('''INSERT INTO itinerary_21day
                (day, from_location, to_location, distance_km, duration_hrs, elevation_gain_m)
                VALUES (?, ?, ?, ?, ?, ?)''',
                (
                    int(row['day']),
                    row['from'],
                    row['to'],
                    float(row['distance_km']),
                    float(row['duration_hrs']),
                    int(row['elevation_gain_m'])
                ))
    conn.commit()
    print(f"Loaded 21-day itinerary")

def print_stats(conn):
    c = conn.cursor()

    print("\n=== Database Stats ===")

    c.execute('SELECT COUNT(*) FROM route_waypoints')
    print(f"Route waypoints: {c.fetchone()[0]}")

    c.execute('SELECT COUNT(*) FROM water_points')
    print(f"Water/POI points: {c.fetchone()[0]}")

    c.execute("SELECT COUNT(*) FROM water_points WHERE type='water'")
    print(f"  - Water sources: {c.fetchone()[0]}")

    c.execute("SELECT status, COUNT(*) FROM water_points WHERE type='water' GROUP BY status")
    print("  - By status:", dict(c.fetchall()))

    c.execute('SELECT COUNT(*) FROM huts')
    print(f"Huts: {c.fetchone()[0]}")

    c.execute('SELECT SUM(distance_km), SUM(duration_hrs) FROM itinerary_21day')
    row = c.fetchone()
    print(f"21-day total: {row[0]} km, {row[1]} hrs")

if __name__ == '__main__':
    conn = create_db()
    load_pdf_waypoints(conn)
    load_gpx_waypoints(conn)
    load_huts(conn)
    load_itinerary(conn)
    print_stats(conn)
    conn.close()
    print(f"\nDatabase created: {DB_PATH}")
