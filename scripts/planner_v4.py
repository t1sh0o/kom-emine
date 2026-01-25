#!/usr/bin/env python3
"""Kom-Emine trip planner v4 - constraint-aware with forced gap handling."""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple, Optional

DB_PATH = Path('/Users/ttonov/projects/personal/kom-emine/data/kom-emine.db')

DIFFICULTY = {
    (0, 105): (1.0, "Western"),
    (105, 175): (1.3, "Central-alpine"),
    (175, 245): (1.4, "Botev area"),
    (245, 330): (1.1, "Central East"),
    (330, 560): (1.0, "Eastern/Coast"),
}

@dataclass
class Hut:
    name: str
    km: float
    phone: str

def get_huts() -> List[Hut]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    huts = []
    c.execute("SELECT name_en, km, phone FROM huts WHERE status='working' ORDER BY km")
    for row in c.fetchall():
        huts.append(Hut(row['name_en'], row['km'], row['phone'] or ''))

    conn.close()
    return huts

def get_stats(start: float, end: float) -> Tuple[float, int, int]:
    """Return (hours, elevation_gain, water_count)."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    c.execute('SELECT sector_time, elevation_m FROM route_waypoints WHERE total_km > ? AND total_km <= ?', (start, end))
    rows = c.fetchall()

    mins = 0
    for r in rows:
        if r['sector_time']:
            p = r['sector_time'].split(':')
            if len(p) == 2:
                mins += int(p[0])*60 + int(p[1])

    gain = 0
    prev = None
    for r in rows:
        if r['elevation_m']:
            if prev and r['elevation_m'] > prev:
                gain += r['elevation_m'] - prev
            prev = r['elevation_m']

    c.execute('''SELECT COUNT(*) FROM water_points WHERE type='water' AND status='ok'
        AND lon BETWEEN (SELECT MIN(lon) FROM route_waypoints WHERE total_km BETWEEN ? AND ?)
        AND (SELECT MAX(lon) FROM route_waypoints WHERE total_km BETWEEN ? AND ?)''',
        (start, end, start, end))
    water = c.fetchone()[0]

    conn.close()
    return mins/60, gain, water

def terrain(km: float) -> Tuple[float, str]:
    for (lo, hi), (factor, name) in DIFFICULTY.items():
        if lo <= km < hi:
            return factor, name
    return 1.0, "Unknown"

def find_plan(num_days: int, stops: List[Hut], max_km: float = 60, min_km: float = 20) -> Optional[List[int]]:
    """
    Find valid sequence of stop indices using dynamic programming.
    Returns list of indices into stops array, or None if impossible.
    """
    n = len(stops)
    END = stops[-1].km

    # parent[day][idx] = previous idx that led here
    parent = [{} for _ in range(num_days + 1)]
    reachable = [set() for _ in range(num_days + 1)]

    reachable[0].add(0)

    for day in range(1, num_days + 1):
        days_left = num_days - day  # days remaining after this one

        for prev_idx in reachable[day - 1]:
            prev_km = stops[prev_idx].km

            for next_idx in range(prev_idx + 1, n):
                next_km = stops[next_idx].km
                dist = next_km - prev_km
                remaining_to_end = END - next_km

                # Can we still reach end from next_idx in days_left days?
                if days_left > 0:
                    # Need at least min_km per remaining day
                    if remaining_to_end > days_left * max_km:
                        continue  # Can't reach end in time
                    # But also not too short to fill remaining days
                    if remaining_to_end < days_left * min_km * 0.5:
                        continue  # Would have too-short days

                # Distance constraints
                if dist < min_km and remaining_to_end > 10:
                    continue  # Too short (unless near end)

                if dist > max_km:
                    continue  # Too far

                # Last day must reach end
                if days_left == 0 and next_idx != n - 1:
                    continue

                if next_idx not in reachable[day]:
                    reachable[day].add(next_idx)
                    parent[day][next_idx] = prev_idx

    # Check if we reached the end
    end_idx = n - 1
    if end_idx not in reachable[num_days]:
        return None

    # Backtrack to find path
    path = [end_idx]
    for day in range(num_days, 0, -1):
        prev = parent[day][path[-1]]
        path.append(prev)

    path.reverse()
    return path

def plan(num_days: int, max_km: float = 60) -> List[dict]:
    END = 555.3
    huts = get_huts()

    # Add virtual "huts" at start and end
    stops = [Hut("вр. Ком", 0, "")] + huts + [Hut("нос Емине", END, "")]

    print(f"Planning {num_days} days | {END:.0f} km | ~{END/num_days:.0f} km/day target")
    print(f"Max: {max_km} km/day\n")

    # Try to find a valid plan with progressively relaxed constraints
    path = None
    used_max = max_km
    for try_max in [max_km, 62, 65, 68, 70, 75]:
        for try_min in [15, 12, 10, 5]:  # Lower min to allow shorter days
            path = find_plan(num_days, stops, try_max, try_min)
            if path:
                used_max = try_max
                break
        if path:
            break

    if used_max > max_km:
        print(f"Note: Required {used_max:.0f}km max (hut gaps)\n")

    if path is None:
        print("ERROR: Cannot find valid plan")
        return []

    # Build stages from path
    stages = []
    for day in range(1, len(path)):
        start_idx = path[day - 1]
        end_idx = path[day]

        start_hut = stops[start_idx]
        end_hut = stops[end_idx]

        hrs, gain, water = get_stats(start_hut.km, end_hut.km)
        _, terr = terrain((start_hut.km + end_hut.km) / 2)
        dist = end_hut.km - start_hut.km

        # Difficulty
        if hrs > 12 or gain > 1500 or dist > 55:
            diff = "HARD"
        elif hrs > 8 or gain > 900 or dist > 40:
            diff = "moderate"
        else:
            diff = "easy"

        # Lunch options
        lunch = [s.name for s in stops[start_idx+1:end_idx]
                 if start_hut.km + dist*0.25 < s.km < start_hut.km + dist*0.75]

        stages.append({
            'day': day,
            'start': start_hut.name,
            'end': end_hut.name,
            'start_km': start_hut.km,
            'end_km': end_hut.km,
            'dist': dist,
            'hrs': hrs,
            'gain': gain,
            'water': water,
            'diff': diff,
            'terrain': terr,
            'lunch': lunch[:3],
            'phone': end_hut.phone
        })

    return stages

def show(stages: List[dict]):
    print("=" * 70)
    print("КОМ-ЕМИНЕ TRIP PLAN")
    print("=" * 70)

    total_km = sum(s['dist'] for s in stages)
    total_hrs = sum(s['hrs'] for s in stages)
    total_gain = sum(s['gain'] for s in stages)

    print(f"Total: {total_km:.0f} km | {total_hrs:.0f} hrs | +{total_gain}m\n")

    for s in stages:
        icon = {'HARD': '🔴', 'moderate': '🟡', 'easy': '🟢'}[s['diff']]
        print(f"DAY {s['day']}: {s['start']} → {s['end']}")
        print(f"  {icon} {s['dist']:.0f} km | {s['hrs']:.1f} hrs | +{s['gain']}m | {s['terrain']}")
        if s['lunch']:
            print(f"  🍽️  {', '.join(s['lunch'])}")
        if s['water'] < 3:
            print(f"  ⚠️  Low water!")
        print()

    print("=" * 70)
    print("\n📞 CONTACTS:\n")
    for s in stages:
        if s['phone']:
            print(f"  Day {s['day']} {s['end']}: {s['phone']}")

if __name__ == '__main__':
    import sys
    days = int(sys.argv[1]) if len(sys.argv) > 1 else 10
    stages = plan(days)
    if stages:
        show(stages)
