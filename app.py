#!/usr/bin/env python3
"""Kom-Emine web route planner."""
import re
from flask import Flask, jsonify, render_template, request
from scripts.planner_v4 import get_huts, get_stats, terrain, DIFFICULTY
from scripts.query import query

app = Flask(__name__)

# Patterns for sleepable locations (Bulgarian)
SLEEPABLE_PATTERNS = {
    'hut': [r'\bхижа\b', r'\bх\.', r'\bгорски дом\b'],
    'shelter': [r'\bзаслон\b', r'\bт\.с\.'],
    'village': [r'\bс\.', r'\bсело\b', r'\bсело\b'],
    'town': [r'\bгр\.', r'\bград\b', r'\bцентър\b'],
    'resort': [r'\bкурорт\b', r'\bхотел\b', r'\bвила\b'],
    'finish': [r'\bчерно море\b', r'\bнос емине\b']
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

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/waypoints')
def api_waypoints():
    """Return all route waypoints with sleepable flag."""
    rows = query('''
        SELECT id, total_km, sector_km, sector_time, description,
               lat, lon, elevation_m
        FROM route_waypoints
        ORDER BY total_km
    ''')

    waypoints = []
    for r in rows:
        sleepable = get_sleepable_type(r['description'])
        waypoints.append({
            'id': r['id'],
            'km': r['total_km'],
            'sector_km': r['sector_km'],
            'sector_time': r['sector_time'],
            'description': r['description'],
            'lat': r['lat'],
            'lon': r['lon'],
            'elevation': r['elevation_m'],
            'sleepable': sleepable
        })

    return jsonify(waypoints)

@app.route('/api/huts')
def api_huts():
    """Return all working huts."""
    huts = get_huts()
    rows = query('''
        SELECT name_en, km, phone, region, lat, lon
        FROM huts WHERE status='working'
        ORDER BY km
    ''')

    return jsonify([{
        'name': r['name_en'],
        'km': r['km'],
        'phone': r['phone'],
        'region': r['region'],
        'lat': r['lat'],
        'lon': r['lon']
    } for r in rows])

@app.route('/api/segment')
def api_segment():
    """Return stats for a route segment."""
    start = float(request.args.get('start', 0))
    end = float(request.args.get('end', 0))

    if end <= start:
        return jsonify({'error': 'end must be > start'}), 400

    hours, elevation_gain, elevation_loss, water_count = get_stats(start, end)
    distance_km = end - start
    factor, terrain_name = terrain((start + end) / 2)

    # Check for technical sections
    technical = has_technical_section(start, end)

    # Difficulty rating (consider both gain and loss)
    if hours > 12 or elevation_gain > 1500 or elevation_loss > 2000 or distance_km > 55:
        difficulty = 'hard'
    elif hours > 8 or elevation_gain > 900 or elevation_loss > 1200 or distance_km > 40:
        difficulty = 'moderate'
    else:
        difficulty = 'easy'

    return jsonify({
        'start_km': start,
        'end_km': end,
        'distance_km': round(distance_km, 1),
        'hours': round(hours, 1),
        'elevation_gain': elevation_gain,
        'elevation_loss': elevation_loss,
        'water_count': water_count,
        'terrain': terrain_name,
        'terrain_factor': factor,
        'difficulty': difficulty,
        'technical': technical
    })


def has_technical_section(start: float, end: float) -> int:
    """Check if segment contains technical sections (0=none, 1=moderate, 2=difficult)."""
    rows = query('''
        SELECT MAX(technical) as tech FROM route_waypoints
        WHERE total_km >= ? AND total_km <= ? AND technical > 0
    ''', (start, end))
    if rows and rows[0]['tech']:
        return rows[0]['tech']
    return 0


@app.route('/api/elevation-profile')
def api_elevation_profile():
    """Return simplified track for elevation chart."""
    rows = query('SELECT km, elevation FROM track_profile ORDER BY km')

    if not rows:
        # Fallback to sparse waypoint data if track not imported
        rows = query('''
            SELECT total_km as km, elevation_m as elevation
            FROM route_waypoints
            WHERE elevation_m IS NOT NULL
            ORDER BY total_km
        ''')

    points = [{'km': round(r['km'], 2), 'ele': r['elevation']} for r in rows]

    # Get waypoint markers for overlay
    waypoints = query('''
        SELECT total_km as km, description, technical
        FROM route_waypoints
        WHERE total_km IS NOT NULL
        ORDER BY total_km
    ''')
    markers = [{
        'km': round(w['km'], 2),
        'name': w['description'][:30] if w['description'] else '',
        'technical': w['technical'] or 0
    } for w in waypoints]

    return jsonify({
        'points': points,
        'waypoints': markers
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)
