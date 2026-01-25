#!/usr/bin/env python3
"""Kom-Emine trip planner v3 - greedy forward with constraint relaxation."""
import sqlite3
from pathlib import Path
from dataclasses import dataclass
from typing import List, Tuple

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
    c.execute("SELECT name, lon, phone FROM huts WHERE status='working' ORDER BY lon")
    for row in c.fetchall():
        c.execute('SELECT total_km FROM route_waypoints WHERE lon IS NOT NULL ORDER BY ABS(lon - ?) LIMIT 1', (row['lon'],))
        km = c.fetchone()
        if km:
            huts.append(Hut(row['name'], km['total_km'], row['phone']))

    conn.close()
    huts.sort(key=lambda h: h.km)

    # Dedupe (keep first per 5km)
    result = []
    last = -10
    for h in huts:
        if h.km - last >= 5:
            result.append(h)
            last = h.km
    return result

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

def plan(num_days: int, max_km: float = 60) -> List[dict]:
    END = 555.3
    huts = get_huts()

    # Add virtual "huts" at start and end
    stops = [Hut("вр. Ком", 0, "")] + huts + [Hut("нос Емине", END, "")]

    # Target km per day
    target = END / num_days

    print(f"Planning {num_days} days | {END:.0f} km | ~{target:.0f} km/day target")
    print(f"Max: {max_km} km/day\n")

    # Greedy: assign each day to end at the hut closest to cumulative target
    stages = []
    current_idx = 0  # Start at Kom
    current_km = 0

    for day in range(1, num_days + 1):
        remaining_days = num_days - day + 1
        remaining_km = END - current_km
        day_target = remaining_km / remaining_days
        is_last = (day == num_days)

        # Find best end hut for this day
        ideal_end = current_km + day_target

        # On last day, must reach the end
        if is_last:
            ideal_end = END

        # Search for candidates (must advance at least 20km, max 60km unless forced)
        best = None
        best_score = float('inf')

        for i in range(current_idx + 1, len(stops)):
            hut = stops[i]
            dist = hut.km - current_km

            # Last day: only consider the endpoint
            if is_last and hut.km < END:
                continue

            if dist < 20 and hut.km < END:
                continue  # Too short (unless it's the end)

            if dist > max_km and best is not None and not is_last:
                break  # Too far and we have an option

            # Score: distance from ideal, with penalty for very long days
            score = abs(hut.km - ideal_end)
            if dist > 55:
                score += (dist - 55) * 2  # Penalize long days

            # Adjust for terrain difficulty
            factor, _ = terrain((current_km + hut.km) / 2)
            score *= factor

            if score < best_score:
                best_score = score
                best = (i, hut)

        if best is None:
            # Forced to take next available
            for i in range(current_idx + 1, len(stops)):
                if stops[i].km > current_km:
                    best = (i, stops[i])
                    break

        end_idx, end_hut = best
        hrs, gain, water = get_stats(current_km, end_hut.km)
        _, terr = terrain((current_km + end_hut.km) / 2)
        dist = end_hut.km - current_km

        # Difficulty
        if hrs > 12 or gain > 1500 or dist > 55:
            diff = "HARD"
        elif hrs > 8 or gain > 900 or dist > 40:
            diff = "moderate"
        else:
            diff = "easy"

        # Lunch options
        lunch = [s.name for s in stops[current_idx+1:end_idx]
                 if current_km + dist*0.25 < s.km < current_km + dist*0.75]

        stages.append({
            'day': day,
            'start': stops[current_idx].name,
            'end': end_hut.name,
            'start_km': current_km,
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

        current_idx = end_idx
        current_km = end_hut.km

        if current_km >= END:
            break

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
    show(stages)
