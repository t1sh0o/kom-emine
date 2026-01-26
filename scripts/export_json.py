#!/usr/bin/env python3
"""Export database to static JSON files for frontend."""
import json
import re
import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent.parent / 'data' / 'kom-emine.db'
OUTPUT_DIR = Path(__file__).parent.parent / 'web' / 'data'

# Patterns for sleepable locations (Bulgarian)
SLEEPABLE_PATTERNS = {
    'hut': [r'\bхижа\b', r'\bх\.', r'\bгорски дом\b'],
    'shelter': [r'\bзаслон\b', r'\bт\.с\.'],
    'village': [r'\bс\.', r'\bсело\b'],
    'town': [r'\bгр\.', r'\bград\b', r'\bцентър\b'],
    'resort': [r'\bкурорт\b', r'\bхотел\b', r'\bвила\b'],
    'finish': [r'\bчерно море\b', r'\bнос емине\b']
}

# Terrain difficulty factors
DIFFICULTY = {
    (0, 105): (1.0, "Western"),
    (105, 175): (1.3, "Central-alpine"),
    (175, 245): (1.4, "Botev area"),
    (245, 330): (1.1, "Central East"),
    (330, 560): (1.0, "Eastern/Coast"),
}


def get_sleepable_type(description: str) -> str | None:
    """Parse description for sleepable location type."""
    if not description:
        return None
    desc_lower = description.lower()
    for loc_type, patterns in SLEEPABLE_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, desc_lower):
                return loc_type
    return None


def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(sql, params)
    rows = [dict(row) for row in c.fetchall()]
    conn.close()
    return rows


def export_waypoints():
    """Export route waypoints with sleepable flag and segment elevation data."""
    rows = query('''
        SELECT id, total_km, sector_km, sector_time, description,
               lat, lon, elevation_m, technical
        FROM route_waypoints
        ORDER BY total_km
    ''')

    # Get precomputed segment elevations
    seg_elevations = {}
    seg_rows = query('''
        SELECT from_waypoint_id, to_waypoint_id, elevation_gain, elevation_loss
        FROM segment_elevations
    ''')
    for s in seg_rows:
        seg_elevations[s['to_waypoint_id']] = {
            'gain': s['elevation_gain'],
            'loss': s['elevation_loss']
        }

    waypoints = []
    for r in rows:
        sleepable = get_sleepable_type(r['description'])
        seg = seg_elevations.get(r['id'], {})
        waypoints.append({
            'id': r['id'],
            'km': r['total_km'],
            'sectorKm': r['sector_km'],
            'sectorTime': r['sector_time'],
            'description': r['description'],
            'lat': r['lat'],
            'lon': r['lon'],
            'elevation': r['elevation_m'],
            'sleepable': sleepable,
            'technical': r['technical'] or 0,
            'segGain': seg.get('gain'),
            'segLoss': seg.get('loss')
        })

    return waypoints


def export_water_points():
    """Export water sources."""
    rows = query('''
        SELECT name, lat, lon, elevation_m, status, off_route, type
        FROM water_points
        ORDER BY lon
    ''')

    return [{
        'name': r['name'],
        'lat': r['lat'],
        'lon': r['lon'],
        'elevation': r['elevation_m'],
        'status': r['status'] or 'ok',
        'offRoute': r['off_route'],
        'type': r['type']
    } for r in rows]


def export_huts():
    """Export working huts."""
    rows = query('''
        SELECT name_en, km, phone, region, lat, lon, status
        FROM huts
        WHERE status='working'
        ORDER BY km
    ''')

    return [{
        'name': r['name_en'],
        'km': r['km'],
        'phone': r['phone'],
        'region': r['region'],
        'lat': r['lat'],
        'lon': r['lon']
    } for r in rows]


def export_elevation():
    """Export track elevation profile."""
    rows = query('SELECT km, elevation, lat, lon FROM track_profile ORDER BY km')

    if not rows:
        # Fallback to sparse waypoint data
        rows = query('''
            SELECT total_km as km, elevation_m as elevation, lat, lon
            FROM route_waypoints
            WHERE elevation_m IS NOT NULL
            ORDER BY total_km
        ''')

    return [{
        'km': round(r['km'], 2),
        'ele': r['elevation'],
        'lat': r['lat'],
        'lon': r['lon']
    } for r in rows]


def export_terrain():
    """Export terrain difficulty zones."""
    return [
        {'startKm': lo, 'endKm': hi, 'factor': factor, 'name': name}
        for (lo, hi), (factor, name) in DIFFICULTY.items()
    ]


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    exports = [
        ('waypoints.json', export_waypoints),
        ('water-points.json', export_water_points),
        ('huts.json', export_huts),
        ('elevation.json', export_elevation),
        ('terrain.json', export_terrain),
    ]

    for filename, export_fn in exports:
        data = export_fn()
        path = OUTPUT_DIR / filename
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, separators=(',', ':'))

        size = path.stat().st_size
        print(f"{filename}: {len(data)} items, {size/1024:.1f} KB")

    print(f"\nExported to {OUTPUT_DIR}")


if __name__ == '__main__':
    main()
