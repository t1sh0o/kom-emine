#!/usr/bin/env python3
"""Query examples for Kom-Emine database."""
import sqlite3
from pathlib import Path

DB_PATH = Path('/Users/ttonov/projects/personal/kom-emine/data/kom-emine.db')

def query(sql, params=()):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute(sql, params)
    rows = c.fetchall()
    conn.close()
    return rows

def water_between_km(start_km, end_km):
    """Find water sources between two km markers."""
    # Get lon range from route waypoints
    points = query('''
        SELECT MIN(lon) as min_lon, MAX(lon) as max_lon
        FROM route_waypoints
        WHERE total_km BETWEEN ? AND ?
    ''', (start_km, end_km))

    if not points or not points[0]['min_lon']:
        return []

    min_lon, max_lon = points[0]['min_lon'], points[0]['max_lon']

    return query('''
        SELECT name, status, off_route, elevation_m, lat, lon
        FROM water_points
        WHERE type = 'water' AND lon BETWEEN ? AND ?
        ORDER BY lon
    ''', (min_lon, max_lon))

def huts_between_km(start_km, end_km):
    """Find huts between two km markers."""
    points = query('''
        SELECT MIN(lon) as min_lon, MAX(lon) as max_lon
        FROM route_waypoints
        WHERE total_km BETWEEN ? AND ?
    ''', (start_km, end_km))

    if not points or not points[0]['min_lon']:
        return []

    min_lon, max_lon = points[0]['min_lon'], points[0]['max_lon']

    return query('''
        SELECT name, phone, status, lat, lon
        FROM huts
        WHERE lon BETWEEN ? AND ? AND status = 'working'
        ORDER BY lon
    ''', (min_lon - 0.1, max_lon + 0.1))

def route_segment(start_km, end_km):
    """Get route waypoints for a segment."""
    return query('''
        SELECT total_km, sector_time, description, elevation_m
        FROM route_waypoints
        WHERE total_km BETWEEN ? AND ?
        ORDER BY total_km
    ''', (start_km, end_km))

def reliable_water():
    """Get all reliable (non-seasonal) water sources."""
    return query('''
        SELECT name, elevation_m, lat, lon, off_route
        FROM water_points
        WHERE type = 'water' AND status = 'ok'
        ORDER BY lon
    ''')

if __name__ == '__main__':
    print("=== Water between km 100-150 ===")
    for w in water_between_km(100, 150):
        status = f"[{w['status']}]" if w['status'] != 'ok' else ''
        detour = ' (detour)' if w['off_route'] else ''
        print(f"  {w['name']} {w['elevation_m']}m {status}{detour}")

    print("\n=== Huts between km 100-150 ===")
    for h in huts_between_km(100, 150):
        print(f"  {h['name']} - {h['phone']}")

    print("\n=== Route km 200-210 ===")
    for r in route_segment(200, 210):
        print(f"  km {r['total_km']}: {r['description'][:50]}... ({r['elevation_m']}m)")

    print(f"\n=== Reliable water count: {len(reliable_water())} ===")
