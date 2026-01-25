#!/usr/bin/env python3
"""Kom-Emine trip planner."""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional

DB_PATH = Path('/Users/ttonov/projects/personal/kom-emine/data/kom-emine.db')

# Difficulty multipliers for sections (based on terrain)
# Central Balkan (alpine, technical) is hardest
DIFFICULTY_ZONES = [
    (0, 70, 1.0, "Western Balkan - easy forest/ridge"),
    (70, 105, 1.1, "Pre-central - moderate"),
    (105, 175, 1.3, "Central Balkan West - alpine, 2000m+ peaks"),
    (175, 245, 1.5, "Central Balkan Core - technical, Botev area"),
    (245, 310, 1.2, "Central Balkan East - high but easier"),
    (310, 400, 1.0, "Eastern Balkan - lower, easier"),
    (400, 480, 0.9, "Far East - low hills"),
    (480, 560, 1.0, "Coast approach - mixed"),
]

@dataclass
class Hut:
    name: str
    km: float
    lon: float
    phone: str
    has_food: bool = True

@dataclass
class Stage:
    day: int
    start_km: float
    end_km: float
    start_name: str
    end_name: str
    distance_km: float
    time_hrs: float
    elevation_gain: int
    difficulty: str
    lunch_options: List[str]
    water_count: int
    notes: str

def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def get_huts_on_route():
    """Get huts sorted by approximate km position."""
    conn = get_conn()
    c = conn.cursor()

    # Get huts with their lon, then match to route km
    huts = []
    c.execute('''
        SELECT h.name, h.lon, h.phone, h.status
        FROM huts h
        WHERE h.status = 'working'
        ORDER BY h.lon
    ''')

    for row in c.fetchall():
        # Find closest route km for this hut
        c.execute('''
            SELECT total_km FROM route_waypoints
            WHERE lon IS NOT NULL
            ORDER BY ABS(lon - ?)
            LIMIT 1
        ''', (row['lon'],))
        km_row = c.fetchone()
        km = km_row['total_km'] if km_row else 0

        huts.append(Hut(
            name=row['name'],
            km=km,
            lon=row['lon'],
            phone=row['phone']
        ))

    conn.close()
    # Sort by km and remove duplicates (keep first)
    huts.sort(key=lambda h: h.km)
    return huts

def get_segment_stats(start_km: float, end_km: float) -> dict:
    """Get stats for a route segment."""
    conn = get_conn()
    c = conn.cursor()

    # Get waypoints in range
    c.execute('''
        SELECT total_km, sector_time, elevation_m, description
        FROM route_waypoints
        WHERE total_km BETWEEN ? AND ?
        ORDER BY total_km
    ''', (start_km, end_km))

    points = c.fetchall()

    # Calculate elevation gain
    elevation_gain = 0
    prev_ele = None
    for p in points:
        if p['elevation_m'] and prev_ele:
            diff = p['elevation_m'] - prev_ele
            if diff > 0:
                elevation_gain += diff
        prev_ele = p['elevation_m']

    # Sum walking time
    total_minutes = 0
    for p in points:
        if p['sector_time']:
            parts = p['sector_time'].split(':')
            if len(parts) == 2:
                total_minutes += int(parts[0]) * 60 + int(parts[1])

    # Count water sources
    c.execute('''
        SELECT COUNT(*) as cnt FROM water_points
        WHERE type = 'water' AND status = 'ok'
        AND lon BETWEEN
            (SELECT lon FROM route_waypoints WHERE total_km >= ? ORDER BY total_km LIMIT 1)
            AND
            (SELECT lon FROM route_waypoints WHERE total_km <= ? ORDER BY total_km DESC LIMIT 1)
    ''', (start_km, end_km))
    water = c.fetchone()['cnt']

    conn.close()

    return {
        'distance': end_km - start_km,
        'time_hrs': total_minutes / 60,
        'elevation_gain': elevation_gain,
        'water_count': water
    }

def get_difficulty_factor(km: float) -> tuple:
    """Get difficulty factor and description for a km position."""
    for start, end, factor, desc in DIFFICULTY_ZONES:
        if start <= km < end:
            return factor, desc
    return 1.0, "Unknown"

def get_effective_effort(start_km: float, end_km: float) -> float:
    """Calculate effective effort considering terrain difficulty."""
    stats = get_segment_stats(start_km, end_km)
    mid_km = (start_km + end_km) / 2
    factor, _ = get_difficulty_factor(mid_km)

    # Base effort = time + elevation penalty
    base_effort = stats['time_hrs'] + (stats['elevation_gain'] / 500)
    return base_effort * factor

def find_overnight_huts(target_km: float, tolerance: float = 10) -> List[Hut]:
    """Find huts near a target km."""
    huts = get_huts_on_route()
    return [h for h in huts if abs(h.km - target_km) <= tolerance]

def plan_trip(num_days: int, start_km: float = 0, end_km: float = 555) -> List[Stage]:
    """Plan a trip for given number of days."""
    total_distance = end_km - start_km
    huts = get_huts_on_route()

    # Filter huts in range and dedupe by km (keep first)
    huts = [h for h in huts if start_km < h.km < end_km]
    seen_km = set()
    unique_huts = []
    for h in huts:
        km_rounded = round(h.km)
        if km_rounded not in seen_km:
            seen_km.add(km_rounded)
            unique_huts.append(h)
    huts = unique_huts

    if len(huts) < num_days - 1:
        print(f"Warning: Only {len(huts)} huts for {num_days} days - some camping required")

    # Calculate ideal km splits considering difficulty
    avg_km = total_distance / num_days

    # For aggressive schedules (>45km/day avg), warn user
    if avg_km > 45:
        print(f"⚠️  Warning: {avg_km:.0f} km/day average is very demanding!")
        print(f"   Consider {int(total_distance / 35)}-{int(total_distance / 25)} days instead.\n")

    # Build stages by finding best hut near each target
    stages = []
    current_km = start_km

    for day in range(1, num_days + 1):
        remaining_km = end_km - current_km
        remaining_days = num_days - day + 1
        is_last_day = (day == num_days)

        # Calculate target for this day
        target_daily = remaining_km / remaining_days

        # Adjust for terrain difficulty
        mid_km = current_km + target_daily / 2
        factor, _ = get_difficulty_factor(mid_km)

        # Hard terrain = aim for shorter day
        if factor >= 1.3:
            target_daily = target_daily * 0.85
        elif factor <= 0.95:
            target_daily = target_daily * 1.1

        target_end = current_km + target_daily

        # Find overnight stop
        if is_last_day:
            end_name = "нос Емине (Black Sea)"
            actual_end = end_km
        else:
            # Search for huts: prefer within 8km of target, minimum 15km from current
            min_km = current_km + max(15, target_daily * 0.5)
            max_km = current_km + min(target_daily * 1.5, remaining_km - 15 * (remaining_days - 1))

            candidates = [h for h in huts if min_km <= h.km <= max_km]

            if candidates:
                # Score huts: prefer close to target, penalize very long days
                def score(h):
                    dist_from_target = abs(h.km - target_end)
                    day_length = h.km - current_km
                    length_penalty = max(0, day_length - 40) * 2  # Penalize >40km
                    return dist_from_target + length_penalty

                best_hut = min(candidates, key=score)
                end_name = best_hut.name
                actual_end = best_hut.km
                # Remove used hut
                huts = [h for h in huts if h.km != best_hut.km]
            else:
                # No good hut - take any forward hut or bivouac
                forward_huts = [h for h in huts if h.km > current_km + 10]
                if forward_huts:
                    best_hut = forward_huts[0]
                    end_name = best_hut.name
                    actual_end = best_hut.km
                    huts = [h for h in huts if h.km != best_hut.km]
                else:
                    end_name = f"km {target_end:.0f} (bivouac)"
                    actual_end = min(target_end, end_km - 10)

        # Get segment stats
        stats = get_segment_stats(current_km, actual_end)
        factor, terrain_desc = get_difficulty_factor((current_km + actual_end) / 2)

        # Find lunch options (huts roughly in middle third)
        mid_start = current_km + (actual_end - current_km) * 0.25
        mid_end = current_km + (actual_end - current_km) * 0.75
        lunch_huts = [h.name for h in huts if mid_start <= h.km <= mid_end]

        # Determine difficulty rating
        effort = stats['time_hrs'] + (stats['elevation_gain'] / 400)
        if effort > 12 or stats['elevation_gain'] > 2000:
            difficulty = "HARD"
        elif effort > 8 or stats['elevation_gain'] > 1200:
            difficulty = "moderate"
        else:
            difficulty = "easy"

        # Get start name
        if day == 1:
            start_name = "вр. Ком" if start_km == 0 else f"km {current_km:.0f}"
        else:
            start_name = stages[-1].end_name

        # Notes
        notes = terrain_desc
        if stats['water_count'] < 3:
            notes += " | LOW WATER"
        if factor >= 1.3:
            notes += " | Technical terrain"

        stages.append(Stage(
            day=day,
            start_km=current_km,
            end_km=actual_end,
            start_name=start_name,
            end_name=end_name,
            distance_km=stats['distance'],
            time_hrs=stats['time_hrs'],
            elevation_gain=stats['elevation_gain'],
            difficulty=difficulty,
            lunch_options=lunch_huts,
            water_count=stats['water_count'],
            notes=notes
        ))

        current_km = actual_end

    return stages

def print_plan(stages: List[Stage]):
    """Pretty print the trip plan."""
    print("\n" + "="*70)
    print("КОМ-ЕМИНЕ TRIP PLAN")
    print("="*70)

    total_km = sum(s.distance_km for s in stages)
    total_hrs = sum(s.time_hrs for s in stages)
    total_gain = sum(s.elevation_gain for s in stages)

    print(f"Total: {total_km:.1f} km | {total_hrs:.1f} hrs | +{total_gain}m elevation")
    print("="*70)

    for s in stages:
        print(f"\n📅 DAY {s.day}: {s.start_name} → {s.end_name}")
        print(f"   Distance: {s.distance_km:.1f} km | Time: {s.time_hrs:.1f} hrs | Gain: +{s.elevation_gain}m")
        print(f"   Difficulty: {s.difficulty.upper()} | Water sources: {s.water_count}")

        if s.lunch_options:
            print(f"   🍽️  Lunch: {', '.join(s.lunch_options)}")
        else:
            print(f"   🍽️  Lunch: Pack food (no huts mid-day)")

        print(f"   📝 {s.notes}")

    print("\n" + "="*70)
    print("⚠️  NOTES:")
    print("- Book huts in advance (especially in summer)")
    print("- Central Balkan (days with 'Technical terrain') requires experience")
    print("- Check water status before trip - seasonal sources may be dry")
    print("- Times are walking time only, add breaks")
    print("="*70)

def get_hut_contacts(stages: List[Stage]):
    """Get phone numbers for overnight huts."""
    huts = get_huts_on_route()
    hut_map = {h.name: h.phone for h in huts}

    print("\n📞 HUT CONTACTS:")
    for s in stages:
        if s.end_name in hut_map:
            print(f"  Day {s.day} - {s.end_name}: {hut_map[s.end_name]}")

if __name__ == '__main__':
    import sys

    days = int(sys.argv[1]) if len(sys.argv) > 1 else 14

    print(f"\nPlanning {days}-day trip...")
    stages = plan_trip(days)
    print_plan(stages)
    get_hut_contacts(stages)
