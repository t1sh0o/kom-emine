#!/usr/bin/env python3
"""Import GPX track for accurate elevation data.

Downloads/processes GPX track from BGMountains (206_Kom-Emine.rar) to:
1. Calculate per-segment elevation gain/loss
2. Store simplified track points (~100m intervals) for elevation profile

Usage:
    python3 scripts/import_gpx_track.py data/external/kom-emine-track.gpx
"""
import sqlite3
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import radians, cos, sin, sqrt, atan2
from pathlib import Path
from typing import List, Tuple, Optional

BASE = Path('/Users/ttonov/projects/personal/kom-emine')
DB_PATH = BASE / 'data' / 'kom-emine.db'

# Difficulty zones for technical flag (from planner_v4.py)
DIFFICULTY = {
    (0, 105): (1.0, "Western"),
    (105, 175): (1.3, "Central-alpine"),
    (175, 245): (1.4, "Botev area"),
    (245, 330): (1.1, "Central East"),
    (330, 560): (1.0, "Eastern/Coast"),
}


@dataclass
class TrackPoint:
    lat: float
    lon: float
    ele: float  # elevation in meters


def haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate distance between two points in meters."""
    R = 6371000  # Earth radius in meters

    lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
    dlat = lat2 - lat1
    dlon = lon2 - lon1

    a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
    c = 2 * atan2(sqrt(a), sqrt(1-a))

    return R * c


def parse_gpx(gpx_path: Path) -> List[TrackPoint]:
    """Parse GPX file, return list of track points with elevation."""
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    # Handle GPX namespace
    ns = {'gpx': 'http://www.topografix.com/GPX/1/1'}

    points = []

    # Try with namespace first
    for trkpt in root.findall('.//gpx:trkpt', ns):
        lat = float(trkpt.get('lat'))
        lon = float(trkpt.get('lon'))
        ele_el = trkpt.find('gpx:ele', ns)
        if ele_el is not None and ele_el.text:
            ele = float(ele_el.text)
            points.append(TrackPoint(lat, lon, ele))

    # Fallback: try without namespace
    if not points:
        for trkpt in root.findall('.//trkpt'):
            lat = float(trkpt.get('lat'))
            lon = float(trkpt.get('lon'))
            ele_el = trkpt.find('ele')
            if ele_el is not None and ele_el.text:
                ele = float(ele_el.text)
                points.append(TrackPoint(lat, lon, ele))

    print(f"Parsed {len(points)} track points from GPX")
    return points


def detect_direction(points: List[TrackPoint], conn: sqlite3.Connection) -> bool:
    """Detect if track is reversed (Emine→Kom). Return True if needs reversal."""
    if len(points) < 10:
        return False

    c = conn.cursor()

    # Get Kom Peak coords (~first waypoint)
    c.execute('SELECT lat, lon FROM route_waypoints WHERE total_km < 5 LIMIT 1')
    kom = c.fetchone()

    # Get Emine coords (~last waypoint)
    c.execute('SELECT lat, lon FROM route_waypoints WHERE total_km > 550 LIMIT 1')
    emine = c.fetchone()

    if not kom or not emine:
        return False

    # Check which end of track is closer to Kom
    start_pt = points[0]
    end_pt = points[-1]

    dist_start_kom = haversine(start_pt.lat, start_pt.lon, kom[0], kom[1])
    dist_end_kom = haversine(end_pt.lat, end_pt.lon, kom[0], kom[1])

    if dist_end_kom < dist_start_kom:
        print("Track is reversed (Emine→Kom), auto-reversing...")
        return True

    return False


def calculate_cumulative_distances(points: List[TrackPoint]) -> List[Tuple[TrackPoint, float]]:
    """Calculate cumulative distance along track, return (point, cum_km) pairs."""
    result = [(points[0], 0.0)]
    cum_dist = 0.0

    for i in range(1, len(points)):
        prev = points[i-1]
        curr = points[i]
        dist = haversine(prev.lat, prev.lon, curr.lat, curr.lon)
        cum_dist += dist / 1000  # convert to km
        result.append((curr, cum_dist))

    return result


def resample_to_intervals(points_with_dist: List[Tuple[TrackPoint, float]],
                          interval_m: float = 100) -> List[Tuple[float, int, float, float]]:
    """Resample track to fixed intervals.

    Returns list of (km, elevation, lat, lon) tuples.
    """
    interval_km = interval_m / 1000
    result = []

    if not points_with_dist:
        return result

    # Start with first point
    first_pt, _ = points_with_dist[0]
    result.append((0.0, int(first_pt.ele), first_pt.lat, first_pt.lon))

    next_km = interval_km
    i = 0

    while i < len(points_with_dist) - 1:
        curr_pt, curr_km = points_with_dist[i]
        next_pt, next_km_actual = points_with_dist[i + 1]

        # Check if next sample point is between current and next track points
        while next_km <= next_km_actual:
            # Interpolate position
            if next_km_actual > curr_km:
                t = (next_km - curr_km) / (next_km_actual - curr_km)
            else:
                t = 0

            lat = curr_pt.lat + t * (next_pt.lat - curr_pt.lat)
            lon = curr_pt.lon + t * (next_pt.lon - curr_pt.lon)
            ele = curr_pt.ele + t * (next_pt.ele - curr_pt.ele)

            result.append((next_km, int(ele), lat, lon))
            next_km += interval_km

        i += 1

    # Add last point
    last_pt, last_km = points_with_dist[-1]
    if not result or abs(result[-1][0] - last_km) > 0.01:
        result.append((last_km, int(last_pt.ele), last_pt.lat, last_pt.lon))

    return result


def snap_waypoint_to_track(wp_lat: float, wp_lon: float,
                           points_with_dist: List[Tuple[TrackPoint, float]]) -> Tuple[int, float]:
    """Find closest track point to waypoint.

    Returns (track_index, snap_distance_m).
    """
    min_dist = float('inf')
    min_idx = 0

    for i, (pt, _) in enumerate(points_with_dist):
        dist = haversine(wp_lat, wp_lon, pt.lat, pt.lon)
        if dist < min_dist:
            min_dist = dist
            min_idx = i

    return min_idx, min_dist


def calculate_segment_elevation(points: List[TrackPoint],
                                 start_idx: int, end_idx: int) -> Tuple[int, int]:
    """Calculate elevation gain and loss between two track indices."""
    gain = 0
    loss = 0

    if start_idx >= end_idx:
        return 0, 0

    for i in range(start_idx, min(end_idx, len(points) - 1)):
        delta = points[i + 1].ele - points[i].ele
        if delta > 0:
            gain += delta
        else:
            loss += abs(delta)

    return int(gain), int(loss)


def get_technical_level(km: float) -> int:
    """Get technical difficulty level for a km position."""
    for (lo, hi), (factor, _) in DIFFICULTY.items():
        if lo <= km < hi:
            if factor >= 1.4:
                return 2  # very difficult
            elif factor >= 1.3:
                return 1  # scramble/exposed
    return 0  # normal


def import_track(gpx_path: Path):
    """Main import function."""
    if not gpx_path.exists():
        print(f"ERROR: GPX file not found: {gpx_path}")
        print("\nDownload from: https://bgmountains.org/en/gps-tracks/cats/download/46-stara-planina/300-kom-emine")
        print("Extract RAR and place GPX in data/external/kom-emine-track.gpx")
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Parse GPX
    points = parse_gpx(gpx_path)
    if len(points) < 100:
        print(f"ERROR: Too few track points ({len(points)}), expected thousands")
        sys.exit(1)

    # Detect and fix direction
    if detect_direction(points, conn):
        points = points[::-1]

    # Calculate cumulative distances
    points_with_dist = calculate_cumulative_distances(points)
    total_km = points_with_dist[-1][1]
    print(f"Total track length: {total_km:.1f} km")

    # Create tables if not exist
    c.execute('''CREATE TABLE IF NOT EXISTS segment_elevations (
        from_waypoint_id INTEGER,
        to_waypoint_id INTEGER,
        elevation_gain INTEGER,
        elevation_loss INTEGER,
        track_points INTEGER,
        PRIMARY KEY (from_waypoint_id, to_waypoint_id)
    )''')

    c.execute('''CREATE TABLE IF NOT EXISTS track_profile (
        id INTEGER PRIMARY KEY,
        km REAL,
        elevation INTEGER,
        lat REAL,
        lon REAL
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_track_km ON track_profile(km)')

    # Add technical column if not exists
    try:
        c.execute('ALTER TABLE route_waypoints ADD COLUMN technical INTEGER DEFAULT 0')
        print("Added technical column to route_waypoints")
    except sqlite3.OperationalError:
        pass  # Column already exists

    # Clear existing data
    c.execute('DELETE FROM segment_elevations')
    c.execute('DELETE FROM track_profile')

    # 1. Resample and store track profile
    resampled = resample_to_intervals(points_with_dist, 100)
    print(f"Resampled to {len(resampled)} points at 100m intervals")

    for km, ele, lat, lon in resampled:
        c.execute('INSERT INTO track_profile (km, elevation, lat, lon) VALUES (?, ?, ?, ?)',
                  (km, ele, lat, lon))

    # 2. Get route waypoints and snap to track
    c.execute('SELECT id, total_km, lat, lon FROM route_waypoints WHERE lat IS NOT NULL ORDER BY total_km')
    waypoints = c.fetchall()

    # Build waypoint -> track index mapping
    wp_track_idx = {}
    snap_warnings = []

    for wp_id, wp_km, wp_lat, wp_lon in waypoints:
        idx, snap_dist = snap_waypoint_to_track(wp_lat, wp_lon, points_with_dist)
        wp_track_idx[wp_id] = idx

        if snap_dist > 200:
            snap_warnings.append(f"  Waypoint {wp_id} (km {wp_km:.1f}): {snap_dist:.0f}m off track")

    if snap_warnings:
        print(f"\nWARNING: {len(snap_warnings)} waypoints >200m from track:")
        for w in snap_warnings[:10]:
            print(w)
        if len(snap_warnings) > 10:
            print(f"  ... and {len(snap_warnings) - 10} more")

    # 3. Calculate segment elevations for consecutive waypoints
    segments_added = 0
    for i in range(len(waypoints) - 1):
        from_id = waypoints[i][0]
        to_id = waypoints[i + 1][0]

        if from_id not in wp_track_idx or to_id not in wp_track_idx:
            continue

        start_idx = wp_track_idx[from_id]
        end_idx = wp_track_idx[to_id]

        gain, loss = calculate_segment_elevation(points, start_idx, end_idx)
        track_pts = end_idx - start_idx

        c.execute('''INSERT OR REPLACE INTO segment_elevations
                     (from_waypoint_id, to_waypoint_id, elevation_gain, elevation_loss, track_points)
                     VALUES (?, ?, ?, ?, ?)''',
                  (from_id, to_id, gain, loss, track_pts))
        segments_added += 1

    print(f"Added elevation data for {segments_added} segments")

    # 4. Update technical flags based on difficulty zones
    for wp_id, wp_km, _, _ in waypoints:
        technical = get_technical_level(wp_km)
        if technical > 0:
            c.execute('UPDATE route_waypoints SET technical = ? WHERE id = ?', (technical, wp_id))

    c.execute('SELECT COUNT(*) FROM route_waypoints WHERE technical > 0')
    tech_count = c.fetchone()[0]
    print(f"Marked {tech_count} waypoints as technical")

    # Summary stats
    c.execute('SELECT SUM(elevation_gain), SUM(elevation_loss) FROM segment_elevations')
    total_gain, total_loss = c.fetchone()
    print(f"\nTotal elevation: +{total_gain}m / -{total_loss}m")

    conn.commit()
    conn.close()
    print(f"\nImport complete. Database: {DB_PATH}")


if __name__ == '__main__':
    if len(sys.argv) < 2:
        gpx_path = BASE / 'data' / 'external' / 'kom-emine-track.gpx'
    else:
        gpx_path = Path(sys.argv[1])

    import_track(gpx_path)
