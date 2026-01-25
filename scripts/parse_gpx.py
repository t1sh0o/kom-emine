#!/usr/bin/env python3
"""Parse KE-water-2023.gpx into CSV."""
import xml.etree.ElementTree as ET
import csv
import re

GPX_NS = {'gpx': 'http://www.topografix.com/GPX/1/1'}

def parse_water_status(name):
    """Extract water reliability status from name."""
    name_lower = name.lower()
    status = 'ok'
    if 'пресъхва' in name_lower or 'пресъхнал' in name_lower:
        status = 'seasonal'
    elif 'спряна' in name_lower or 'няма вода' in name_lower:
        status = 'dry'
    elif 'слаба' in name_lower:
        status = 'weak'

    off_route = 'откл' in name_lower or 'отклонение' in name_lower
    return status, off_route

def parse_gpx(gpx_path, output_path):
    tree = ET.parse(gpx_path)
    root = tree.getroot()

    waypoints = []
    for wpt in root.findall('gpx:wpt', GPX_NS):
        lat = float(wpt.get('lat'))
        lon = float(wpt.get('lon'))

        ele_el = wpt.find('gpx:ele', GPX_NS)
        ele = float(ele_el.text) if ele_el is not None else None

        name_el = wpt.find('gpx:name', GPX_NS)
        name = name_el.text if name_el is not None else ''

        cmt_el = wpt.find('gpx:cmt', GPX_NS)
        cmt = cmt_el.text if cmt_el is not None else ''

        desc_el = wpt.find('gpx:desc', GPX_NS)
        desc = desc_el.text if desc_el is not None else ''

        # Determine type
        name_upper = name.upper()
        if 'ВОДА' in name_upper or name.startswith('Вода'):
            wpt_type = 'water'
            status, off_route = parse_water_status(name)
        elif any(x in name for x in ['Х.', 'х.', 'хижа', 'Хижа', 'заслон', 'Заслон', 'спалня']):
            wpt_type = 'hut'
            status, off_route = 'ok', False
        elif any(x in name for x in ['проход', 'Проход', 'превал']):
            wpt_type = 'pass'
            status, off_route = 'ok', False
        elif any(x in name for x in ['вр.', 'връх', 'Връх']):
            wpt_type = 'peak'
            status, off_route = 'ok', False
        else:
            wpt_type = 'other'
            status, off_route = 'ok', False

        waypoints.append({
            'name': name,
            'type': wpt_type,
            'lat': lat,
            'lon': lon,
            'elevation_m': round(ele, 1) if ele else '',
            'status': status,
            'off_route': off_route,
            'comment': cmt or desc
        })

    # Sort by longitude (west to east, roughly following the route)
    waypoints.sort(key=lambda x: x['lon'])

    with open(output_path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['name', 'type', 'lat', 'lon', 'elevation_m', 'status', 'off_route', 'comment'])
        writer.writeheader()
        writer.writerows(waypoints)

    print(f"Parsed {len(waypoints)} waypoints to {output_path}")

    # Stats
    types = {}
    for w in waypoints:
        types[w['type']] = types.get(w['type'], 0) + 1
    print("By type:", types)

    water_status = {}
    for w in waypoints:
        if w['type'] == 'water':
            water_status[w['status']] = water_status.get(w['status'], 0) + 1
    print("Water status:", water_status)

if __name__ == '__main__':
    parse_gpx(
        '/Users/ttonov/projects/personal/kom-emine/KE-water-2023.gpx',
        '/Users/ttonov/projects/personal/kom-emine/data/parsed/gpx-waypoints.csv'
    )
