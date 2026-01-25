#!/usr/bin/env python3
"""Kom-Emine web route planner."""
import re
import math
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

# POI patterns for segment preview (capture name up to comma/dash/bracket)
POI_PATTERNS = {
    'pass': [r'седло\s*[""„]?([^,\-\(\)""]+)', r'превал\s*[""„]?([^,\-\(\)""]+)', r'проход\s*[""„]?([^,\-\(\)""]+)'],
    'peak': [r'вр\.\s*[""„]?([^,\-\(\)""]+)', r'връх\s*[""„]?([^,\-\(\)""]+)'],
    'village': [r'с\.\s*[""„]?([^,\-\(\)""]+)', r'село\s*[""„]?([^,\-\(\)""]+)'],
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

def classify_pois(start_km: float, end_km: float) -> dict:
    """Extract POIs from route_waypoints in a segment."""
    rows = query('''
        SELECT total_km, description, elevation_m
        FROM route_waypoints
        WHERE total_km >= ? AND total_km <= ?
        ORDER BY total_km
    ''', (start_km, end_km))

    pois = {'passes': [], 'peaks': [], 'villages': []}

    for r in rows:
        desc = r['description'] or ''
        desc_lower = desc.lower()

        for poi_type, patterns in POI_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, desc_lower)
                if match:
                    name = match.group(1).strip().strip('/') if match.lastindex else desc[:30]
                    name = name[:25]  # Limit length
                    key = 'passes' if poi_type == 'pass' else poi_type + 's'
                    pois[key].append({
                        'km': r['total_km'],
                        'name': name.capitalize(),
                        'elevation': r['elevation_m']
                    })
                    break
    return pois


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance in km between two lat/lon points."""
    R = 6371  # Earth radius km
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    return R * 2 * math.asin(math.sqrt(a))


def water_in_segment(start_km: float, end_km: float) -> list:
    """Map water sources to track km via lat/lon proximity. Only reliable sources."""
    # Get track points with coords
    track = query('''
        SELECT km, lat, lon FROM track_profile
        WHERE km >= ? AND km <= ? AND lat IS NOT NULL
        ORDER BY km
    ''', (start_km, end_km))

    if not track:
        return []

    # Get all water points, filter in Python (SQLite LOWER doesn't handle Cyrillic)
    water = query('''
        SELECT name, lat, lon, status FROM water_points
        WHERE lat IS NOT NULL
    ''')

    # Filter: exclude only truly unreliable sources (dry/seasonal), keep detours (ОТКЛ)
    # Detours of 100-200m are acceptable for water
    unreliable_keywords = ['пресъхва', 'спряна', 'ПРЕСЪХВА', 'СПРЯНА', 'НЕ пий']
    filtered = []
    for w in water:
        name = w['name'] or ''
        status = w['status'] or 'ok'
        # Skip entries that are dry/seasonal/unsafe
        if any(kw in name for kw in unreliable_keywords):
            continue
        if status in ('dry', 'seasonal'):
            continue
        # Include named sources OR generic ВОДА with ok/weak status
        is_generic = name.upper().startswith('ВОДА')
        if not is_generic or status in ('ok', 'weak'):
            filtered.append(w)
    water = filtered

    # Get all route waypoints for cross-referencing names
    all_waypoints = query('''
        SELECT total_km, description, lat, lon FROM route_waypoints
        WHERE lat IS NOT NULL
    ''')

    results = []
    for w in water:
        # Find nearest track point
        min_dist = float('inf')
        best_km = None
        for t in track:
            dist = haversine_km(w['lat'], w['lon'], t['lat'], t['lon'])
            if dist < min_dist:
                min_dist = dist
                best_km = t['km']

        # Include if within 0.5km of track and in segment range
        if min_dist < 0.5 and best_km is not None:
            name = w['name'] or 'Water'

            # If generic ВОДА name, try to find better name from nearby waypoint
            if name.upper().startswith('ВОДА'):
                for wp in all_waypoints:
                    if wp['lat'] and wp['lon']:
                        wp_dist = haversine_km(w['lat'], w['lon'], wp['lat'], wp['lon'])
                        if wp_dist < 0.05:  # within 50m
                            wp_desc = wp['description'] or ''
                            # Use waypoint name if it's not also generic
                            if not wp_desc.upper().startswith('ВОДА'):
                                name = wp_desc[:40].strip()
                                break

            results.append({
                'km': round(best_km, 1),
                'name': name,
                'status': w['status'] or 'ok'
            })

    # Also get fountains/springs from route_waypoints
    # Filter in Python since SQLite LOWER() doesn't handle Cyrillic
    waypoints = query('''
        SELECT total_km, description FROM route_waypoints
        WHERE total_km >= ? AND total_km <= ?
        ORDER BY total_km
    ''', (start_km, end_km))

    water_keywords = ['чешм', 'извор', 'кладенец', 'вода ', 'река ', 'поток']
    for w in waypoints:
        desc = (w['description'] or '').lower()
        if any(kw in desc for kw in water_keywords):
            name = (w['description'] or '')[:40].strip()
            results.append({
                'km': round(w['total_km'], 1),
                'name': name,
                'status': 'ok'
            })

    # Sort by km, dedupe very close entries (within 0.5km) keeping the better name
    results.sort(key=lambda x: x['km'])
    deduped = []
    for r in results:
        if not deduped or abs(r['km'] - deduped[-1]['km']) > 0.5:
            deduped.append(r)
        else:
            # Keep the entry with better (non-generic) name
            prev_generic = deduped[-1]['name'].upper().startswith('ВОДА')
            curr_generic = r['name'].upper().startswith('ВОДА')
            if prev_generic and not curr_generic:
                deduped[-1] = r

    return deduped


def analyze_segments(profile: list, min_prominence: int = 100) -> list:
    """Analyze elevation profile by finding significant peaks and valleys.

    Uses prominence-based peak/valley detection to find real turning points,
    then creates segments between them.
    """
    if len(profile) < 3:
        return []

    # Step 1: Smooth the profile to reduce noise (moving average)
    window = 5
    smoothed = []
    for i in range(len(profile)):
        start = max(0, i - window // 2)
        end = min(len(profile), i + window // 2 + 1)
        avg_ele = sum(p['ele'] for p in profile[start:end]) / (end - start)
        smoothed.append({'km': profile[i]['km'], 'ele': avg_ele})

    # Step 2: Find local peaks and valleys with prominence filtering
    turning_points = [0]  # Always start at beginning

    for i in range(1, len(smoothed) - 1):
        prev_ele = smoothed[i - 1]['ele']
        curr_ele = smoothed[i]['ele']
        next_ele = smoothed[i + 1]['ele']

        is_peak = curr_ele > prev_ele and curr_ele > next_ele
        is_valley = curr_ele < prev_ele and curr_ele < next_ele

        if is_peak or is_valley:
            # Check prominence - how significant is this turning point?
            # Look back and forward to find the prominence
            if turning_points:
                last_tp = turning_points[-1]
                ele_change = abs(smoothed[i]['ele'] - smoothed[last_tp]['ele'])
                km_change = smoothed[i]['km'] - smoothed[last_tp]['km']

                # Only add if prominence is significant enough
                if ele_change >= min_prominence or (ele_change >= 50 and km_change >= 2):
                    turning_points.append(i)

    turning_points.append(len(profile) - 1)  # Always end at end

    # Step 3: Create segments between turning points
    segments = []
    for i in range(len(turning_points) - 1):
        start_idx = turning_points[i]
        end_idx = turning_points[i + 1]

        start_km = profile[start_idx]['km']
        end_km = profile[end_idx]['km']
        start_ele = profile[start_idx]['ele']
        end_ele = profile[end_idx]['ele']

        distance = round(end_km - start_km, 1)
        if distance < 0.5:
            continue

        # Calculate cumulative ascent and descent within segment
        total_ascent = 0
        total_descent = 0
        for j in range(start_idx, end_idx):
            diff = profile[j + 1]['ele'] - profile[j]['ele']
            if diff > 0:
                total_ascent += diff
            else:
                total_descent += abs(diff)

        net_change = end_ele - start_ele
        direction = 'ascent' if net_change > 0 else 'descent'
        change = abs(net_change)

        # Skip flat sections
        if change < 30:
            continue

        gradient = round((change / (distance * 1000)) * 100, 1) if distance > 0 else 0

        segments.append({
            'type': direction,
            'start_km': round(start_km, 1),
            'end_km': round(end_km, 1),
            'distance': distance,
            'change': round(change),
            'ascent': round(total_ascent),
            'descent': round(total_descent),
            'gradient': gradient,
            'start_ele': round(start_ele),
            'end_ele': round(end_ele)
        })

    # Step 4: Merge adjacent same-direction segments
    final = []
    for seg in segments:
        if final and final[-1]['type'] == seg['type']:
            # Merge with previous
            final[-1]['end_km'] = seg['end_km']
            final[-1]['end_ele'] = seg['end_ele']
            final[-1]['distance'] = round(final[-1]['end_km'] - final[-1]['start_km'], 1)
            final[-1]['change'] = abs(final[-1]['end_ele'] - final[-1]['start_ele'])
            final[-1]['ascent'] = final[-1].get('ascent', 0) + seg.get('ascent', 0)
            final[-1]['descent'] = final[-1].get('descent', 0) + seg.get('descent', 0)
            if final[-1]['distance'] > 0:
                final[-1]['gradient'] = round((final[-1]['change'] / (final[-1]['distance'] * 1000)) * 100, 1)
        else:
            final.append(seg)

    # Step 5: Ensure no gaps
    for i in range(1, len(final)):
        if final[i]['start_km'] != final[i-1]['end_km']:
            final[i]['start_km'] = final[i-1]['end_km']
            final[i]['distance'] = round(final[i]['end_km'] - final[i]['start_km'], 1)
            if final[i]['distance'] > 0:
                final[i]['gradient'] = round((final[i]['change'] / (final[i]['distance'] * 1000)) * 100, 1)

    # Ensure first segment starts at profile start
    if final and profile:
        first_km = round(profile[0]['km'], 1)
        if final[0]['start_km'] != first_km:
            final[0]['start_km'] = first_km
            final[0]['distance'] = round(final[0]['end_km'] - final[0]['start_km'], 1)
            if final[0]['distance'] > 0:
                final[0]['gradient'] = round((final[0]['change'] / (final[0]['distance'] * 1000)) * 100, 1)

    return final


@app.route('/api/segment-preview')
def api_segment_preview():
    """Return detailed segment preview with elevation profile and POIs."""
    start = float(request.args.get('start', 0))
    end = float(request.args.get('end', 0))

    if end <= start:
        return jsonify({'error': 'end must be > start'}), 400

    # Get stats
    hours, elevation_gain, elevation_loss, water_count = get_stats(start, end)

    # Get elevation profile for segment
    rows = query('''
        SELECT km, elevation FROM track_profile
        WHERE km >= ? AND km <= ?
        ORDER BY km
    ''', (start, end))

    if not rows:
        # Fallback to waypoints
        rows = query('''
            SELECT total_km as km, elevation_m as elevation
            FROM route_waypoints
            WHERE total_km >= ? AND total_km <= ? AND elevation_m IS NOT NULL
            ORDER BY total_km
        ''', (start, end))

    profile = [{'km': round(r['km'], 2), 'ele': r['elevation']} for r in rows]

    # Get huts in segment
    huts = query('''
        SELECT name_en, km, phone FROM huts
        WHERE km >= ? AND km <= ? AND status='working'
        ORDER BY km
    ''', (start, end))
    hut_list = [{'km': h['km'], 'name': h['name_en'], 'phone': h['phone']} for h in huts]

    # Get water sources
    water_list = water_in_segment(start, end)

    # Get POIs from waypoints
    pois = classify_pois(start, end)

    # Analyze ascent/descent segments
    segments = analyze_segments(profile)

    return jsonify({
        'distance_km': round(end - start, 1),
        'hours': round(hours, 1),
        'elevation_gain': elevation_gain,
        'elevation_loss': elevation_loss,
        'profile': profile,
        'segments': segments,
        'pois': {
            'huts': hut_list,
            'water': water_list,
            'villages': pois.get('villages', []),
            'passes': pois.get('passes', []),
            'peaks': pois.get('peaks', [])
        }
    })


if __name__ == '__main__':
    app.run(debug=True, port=5000)
