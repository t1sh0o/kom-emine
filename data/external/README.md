# External Data Sources

Collected from various online sources for Kom-Emine trail planning.

## Files

### huts-kom-emine-bg.csv
- **Source**: https://kom-emine.bg/huts-all-en/?lang=en
- **Date**: 2026-01-24
- **Contents**: 55 huts/shelters with coordinates, phone numbers, status
- **Format**: CSV (name, region, lat, lon, phone, status)

### itinerary-21day.csv
- **Source**: https://kom-emine.bg/sample-schedule/?lang=en
- **Date**: 2026-01-24
- **Contents**: Traditional 21-day itinerary with distances and times
- **Format**: CSV (day, from, to, distance_km, duration_hrs, elevation_gain_m)

### osm-relation-254283.xml
- **Source**: https://www.openstreetmap.org/relation/254283
- **Date**: 2026-01-24
- **Contents**: OSM relation metadata (593 way/node members)
- **Note**: Contains member IDs only

### waymarked-info.json (531 KB)
- **Source**: https://hiking.waymarkedtrails.org/api/v1/details/relation/254283
- **Date**: 2026-01-24
- **Contents**: Full route with geometry (LineString coordinates)
- **Key data**:
  - Total length: 559,191 m (~559 km)
  - All way segments with geometries
  - Route metadata and tags

### planinite-stages.csv
- **Source**: http://www.planinite.info/Mejdunarodni_marshruti/Kom_Emine/Kom_Emine.htm
- **Date**: 2026-01-24
- **Contents**: Partial 24-stage breakdown (incomplete data)

## Not Downloaded (Manual Action Required)

### BGMountains GPX
- **URL**: https://bgmountains.org/en/gps-tracks/cats/download/46-stara-planina/300-kom-emine
- **Reason**: Requires browser download (login/captcha)
- **File**: 206_Kom-Emine.rar (92 KB)

### Ponor.org Google Sheet
- **URL**: https://docs.google.com/spreadsheets/d/1vsOh5NTAhdXA0o8YL_cIbh7e7SswSbQYm5frPbY4oIU
- **Reason**: Requires Google Sheets export
- **Contents**: Detailed stage distances, times, elevations

### Wikiloc GPX
- **URL**: https://www.wikiloc.com/hiking-trails/kom-emine-54334725
- **Reason**: Requires account for download
- **Contents**: 345 mi track with 16 waypoints

## Recommended Actions

1. Download BGMountains RAR manually and extract GPX
2. Export Google Sheet as CSV
3. Use waymarkedtrails.org to export OSM relation as GPX
