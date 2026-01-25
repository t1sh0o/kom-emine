#!/usr/bin/env python3
"""Kom-Emine trip planner v2 - works backwards from end."""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import List

DB_PATH = Path('/Users/ttonov/projects/personal/kom-emine/data/kom-emine.db')

DIFFICULTY_ZONES = [
    (0, 70, 1.0, "Western - easy"),
    (70, 105, 1.1, "Pre-central"),
    (105, 175, 1.3, "Central West - alpine"),
    (175, 245, 1.4, "Central Core - Botev"),
    (245, 310, 1.2, "Central East"),
    (310, 400, 1.0, "Eastern"),
    (400, 560, 0.9, "Far East/Coast"),
]

@dataclass
class Hut:
    name: str
    km: float
    phone: str

@dataclass
class Stage:
    day: int
    start_name: str
    end_name: str
    start_km: float
    end_km: float
    distance: float
    time_hrs: float
    elevation_gain: int
    difficulty: str
    lunch_stops: List[str]
    water_count: int
    terrain: str

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_all_huts_with_km() -> List[Hut]:
    """Get all working huts with their km position on route."""
    conn = get_conn()
    c = conn.cursor()

    huts = []
    c.execute("SELECT name, lon, phone FROM huts WHERE status='working' ORDER BY lon")

    for row in c.fetchall():
        c.execute('''
            SELECT total_km FROM route_waypoints
            WHERE lon IS NOT NULL
            ORDER BY ABS(lon - ?) LIMIT 1
        ''', (row['lon'],))
        km_row = c.fetchone()
        km = km_row['total_km'] if km_row else 0
        huts.append(Hut(name=row['name'], km=km, phone=row['phone']))

    conn.close()
    huts.sort(key=lambda h: h.km)
    return huts

def get_segment_stats(start_km: float, end_km: float) -> dict:
    conn = get_conn()
    c = conn.cursor()

    c.execute('''
        SELECT total_km, sector_time, elevation_m
        FROM route_waypoints
        WHERE total_km > ? AND total_km <= ?
        ORDER BY total_km
    ''', (start_km, end_km))

    points = c.fetchall()

    total_min = 0
    for p in points:
        if p['sector_time']:
            parts = p['sector_time'].split(':')
            if len(parts) == 2:
                total_min += int(parts[0]) * 60 + int(parts[1])

    ele_gain = 0
    prev_ele = None
    for p in points:
        if p['elevation_m']:
            if prev_ele and p['elevation_m'] > prev_ele:
                ele_gain += p['elevation_m'] - prev_ele
            prev_ele = p['elevation_m']

    c.execute('''
        SELECT COUNT(*) FROM water_points
        WHERE type='water' AND status IN ('ok', 'weak')
        AND lon BETWEEN
            (SELECT MIN(lon) FROM route_waypoints WHERE total_km BETWEEN ? AND ?)
            AND
            (SELECT MAX(lon) FROM route_waypoints WHERE total_km BETWEEN ? AND ?)
    ''', (start_km, end_km, start_km, end_km))
    water = c.fetchone()[0]

    conn.close()
    return {'time_hrs': total_min / 60, 'elevation_gain': ele_gain, 'water': water}

def get_terrain(km: float) -> str:
    for start, end, _, desc in DIFFICULTY_ZONES:
        if start <= km < end:
            return desc
    return "Unknown"

def get_difficulty_factor(km: float) -> float:
    for start, end, factor, _ in DIFFICULTY_ZONES:
        if start <= km < end:
            return factor
    return 1.0

def plan_trip(num_days: int, max_km: float = 58, min_km: float = 25) -> List[Stage]:
    """Plan trip by finding optimal overnight stops."""
    END_KM = 555.3
    START_KM = 0.0
    TOTAL = END_KM - START_KM

    huts = get_all_huts_with_km()

    # Dedupe huts (keep first at each ~5km)
    unique = []
    last_km = -10
    for h in huts:
        if h.km - last_km >= 5:
            unique.append(h)
            last_km = h.km
    huts = unique

    target_daily = TOTAL / num_days
    print(f"Planning {num_days} days | {TOTAL:.0f} km | ~{target_daily:.0f} km/day")
    print(f"Constraints: {min_km}-{max_km} km/day\n")

    # BACKWARDS PLANNING: Start from end, find where each day should START
    # day_starts[i] = km where day i+1 starts (day 1 starts at 0)
    day_ends = [END_KM]  # Day N ends at cape

    current_end = END_KM

    for days_remaining in range(num_days - 1, 0, -1):
        # We have days_remaining days to cover from 0 to current_end
        km_remaining = current_end - START_KM
        ideal_day_km = km_remaining / days_remaining

        # Adjust for terrain
        mid_km = current_end - ideal_day_km / 2
        factor = get_difficulty_factor(mid_km)
        if factor > 1.2:
            ideal_day_km *= 0.9  # Shorter day in hard terrain

        # Ideal start for this day
        ideal_start = current_end - ideal_day_km

        # Find hut nearest to ideal_start within constraints
        day_min_start = current_end - max_km
        day_max_start = current_end - min_km

        candidates = [h for h in huts if day_min_start <= h.km <= day_max_start]

        if candidates:
            best = min(candidates, key=lambda h: abs(h.km - ideal_start))
            day_ends.insert(0, best.km)
            current_end = best.km
        else:
            # No hut in ideal range - find closest hut that works
            all_before = [h for h in huts if h.km < current_end - 15]
            if all_before:
                # Take the hut that gets us closest to ideal without exceeding max
                valid = [h for h in all_before if current_end - h.km <= max_km]
                if valid:
                    best = min(valid, key=lambda h: abs(h.km - ideal_start))
                else:
                    best = max(all_before, key=lambda h: h.km)  # Closest to current
                day_ends.insert(0, best.km)
                current_end = best.km
            else:
                # No huts - use ideal point
                day_ends.insert(0, max(ideal_start, START_KM))
                current_end = ideal_start

    day_ends.insert(0, START_KM)

    # Build stages
    hut_map = {round(h.km): h for h in huts}
    stages = []

    for i in range(len(day_ends) - 1):
        start_km = day_ends[i]
        end_km = day_ends[i + 1]
        day = i + 1

        # Names
        if start_km == 0:
            start_name = "вр. Ком (2016m)"
        else:
            key = round(start_km)
            start_name = hut_map[key].name if key in hut_map else f"km {start_km:.0f}"

        if end_km >= 555:
            end_name = "нос Емине (Black Sea)"
        else:
            key = round(end_km)
            end_name = hut_map[key].name if key in hut_map else f"km {end_km:.0f}"

        stats = get_segment_stats(start_km, end_km)
        terrain = get_terrain((start_km + end_km) / 2)
        distance = end_km - start_km

        if stats['time_hrs'] > 12 or stats['elevation_gain'] > 1800 or distance > 50:
            diff = "HARD"
        elif stats['time_hrs'] > 8 or stats['elevation_gain'] > 1000 or distance > 35:
            diff = "moderate"
        else:
            diff = "easy"

        # Lunch stops
        mid_start = start_km + distance * 0.3
        mid_end = start_km + distance * 0.7
        lunch = [h.name for h in huts if mid_start < h.km < mid_end]

        stages.append(Stage(
            day=day, start_name=start_name, end_name=end_name,
            start_km=start_km, end_km=end_km, distance=distance,
            time_hrs=stats['time_hrs'], elevation_gain=stats['elevation_gain'],
            difficulty=diff, lunch_stops=lunch, water_count=stats['water'],
            terrain=terrain
        ))

    return stages

def print_plan(stages: List[Stage]):
    print("=" * 70)
    print("КОМ-ЕМИНЕ TRIP PLAN")
    print("=" * 70)

    total_km = sum(s.distance for s in stages)
    total_hrs = sum(s.time_hrs for s in stages)
    total_gain = sum(s.elevation_gain for s in stages)

    print(f"Total: {total_km:.1f} km | {total_hrs:.0f} hrs walking | +{total_gain}m\n")

    for s in stages:
        icon = "🔴" if s.difficulty == "HARD" else "🟡" if s.difficulty == "moderate" else "🟢"
        print(f"DAY {s.day}: {s.start_name} → {s.end_name}")
        print(f"  {icon} {s.distance:.1f} km | {s.time_hrs:.1f} hrs | +{s.elevation_gain}m | {s.terrain}")

        if s.lunch_stops:
            print(f"  🍽️  Lunch: {', '.join(s.lunch_stops[:3])}")
        if s.water_count < 3:
            print(f"  ⚠️  Low water ({s.water_count}) - carry extra!")
        print()

    print("=" * 70)

def print_contacts(stages: List[Stage]):
    huts = get_all_huts_with_km()
    phones = {h.name: h.phone for h in huts}
    print("\n📞 HUT CONTACTS:\n")
    for s in stages:
        if s.end_name in phones:
            print(f"  Day {s.day} {s.end_name}: {phones[s.end_name]}")

if __name__ == '__main__':
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    max_km = float(sys.argv[2]) if len(sys.argv) > 2 else 58
    min_km = float(sys.argv[3]) if len(sys.argv) > 3 else 25

    stages = plan_trip(days, max_km, min_km)
    print_plan(stages)
    print_contacts(stages)
