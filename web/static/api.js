// Kom-Emine Static API Module
// Ports Flask backend logic to client-side JS

const api = (() => {
    // Cached data
    let _waypoints = null;
    let _waterPoints = null;
    let _huts = null;
    let _elevation = null;
    let _terrain = null;

    // === Data Loading ===

    async function loadData(name) {
        const res = await fetch(`static/data/${name}.json`);
        return res.json();
    }

    async function getWaypoints() {
        if (!_waypoints) {
            _waypoints = await loadData('waypoints');
        }
        return _waypoints;
    }

    async function getWaterPoints() {
        if (!_waterPoints) {
            _waterPoints = await loadData('water-points');
        }
        return _waterPoints;
    }

    async function getHuts() {
        if (!_huts) {
            _huts = await loadData('huts');
        }
        return _huts;
    }

    async function getElevation() {
        if (!_elevation) {
            _elevation = await loadData('elevation');
        }
        return _elevation;
    }

    async function getTerrain() {
        if (!_terrain) {
            _terrain = await loadData('terrain');
        }
        return _terrain;
    }

    // === Helper Functions ===

    function parseTime(timeStr) {
        // Parse "HH:MM" to minutes
        if (!timeStr) return 0;
        const parts = timeStr.split(':');
        if (parts.length !== 2) return 0;
        return parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    }

    function haversineKm(lat1, lon1, lat2, lon2) {
        // Calculate distance in km between two lat/lon points
        const R = 6371; // Earth radius km
        const dLat = (lat2 - lat1) * Math.PI / 180;
        const dLon = (lon2 - lon1) * Math.PI / 180;
        const a = Math.sin(dLat / 2) ** 2 +
                  Math.cos(lat1 * Math.PI / 180) * Math.cos(lat2 * Math.PI / 180) *
                  Math.sin(dLon / 2) ** 2;
        return R * 2 * Math.asin(Math.sqrt(a));
    }

    async function getTerrainFactor(km) {
        const terrain = await getTerrain();
        for (const t of terrain) {
            if (km >= t.startKm && km < t.endKm) {
                return { factor: t.factor, name: t.name };
            }
        }
        return { factor: 1.0, name: 'Unknown' };
    }

    // === POI Patterns (Bulgarian) ===

    const POI_PATTERNS = {
        pass: [/седло\s*["„]?([^,\-()""]+)/i, /превал\s*["„]?([^,\-()""]+)/i, /проход\s*["„]?([^,\-()""]+)/i],
        peak: [/вр\.\s*["„]?([^,\-()""]+)/i, /връх\s*["„]?([^,\-()""]+)/i],
        village: [/с\.\s*["„]?([^,\-()""]+)/i, /село\s*["„]?([^,\-()""]+)/i]
    };

    function classifyPOIs(waypoints, startKm, endKm) {
        const pois = { passes: [], peaks: [], villages: [] };
        const filtered = waypoints.filter(w => w.km >= startKm && w.km <= endKm);

        for (const w of filtered) {
            const desc = (w.description || '').toLowerCase();

            for (const [poiType, patterns] of Object.entries(POI_PATTERNS)) {
                for (const pattern of patterns) {
                    const match = desc.match(pattern);
                    if (match) {
                        let name = match[1] ? match[1].trim().replace(/\/$/, '') : desc.substring(0, 30);
                        name = name.substring(0, 25);
                        const key = poiType === 'pass' ? 'passes' : poiType + 's';
                        pois[key].push({
                            km: w.km,
                            name: name.charAt(0).toUpperCase() + name.slice(1),
                            elevation: w.elevation
                        });
                        break;
                    }
                }
            }
        }
        return pois;
    }

    // === Water Source Filtering ===

    const WATER_KEYWORDS = ['чешм', 'извор', 'кладенец', 'вода ', 'река ', 'поток'];
    const UNRELIABLE_KEYWORDS = ['пресъхва', 'спряна', 'ПРЕСЪХВА', 'СПРЯНА', 'НЕ пий'];

    async function getWaterInSegment(startKm, endKm) {
        const elevation = await getElevation();
        const waterPoints = await getWaterPoints();
        const waypoints = await getWaypoints();

        // Get track points in range
        const track = elevation.filter(p => p.km >= startKm && p.km <= endKm && p.lat);
        if (track.length === 0) return [];

        // Filter water points - exclude unreliable
        const filtered = waterPoints.filter(w => {
            const name = w.name || '';
            const status = w.status || 'ok';

            // Skip dry/seasonal
            if (UNRELIABLE_KEYWORDS.some(kw => name.includes(kw))) return false;
            if (status === 'dry' || status === 'seasonal') return false;

            // Include named sources OR generic ВОДА with ok/weak status
            const isGeneric = name.toUpperCase().startsWith('ВОДА');
            return !isGeneric || status === 'ok' || status === 'weak';
        });

        const results = [];

        // Map water sources to track km via proximity
        for (const w of filtered) {
            if (!w.lat) continue;

            let minDist = Infinity;
            let bestKm = null;

            for (const t of track) {
                const dist = haversineKm(w.lat, w.lon, t.lat, t.lon);
                if (dist < minDist) {
                    minDist = dist;
                    bestKm = t.km;
                }
            }

            if (minDist < 0.5 && bestKm !== null) {
                let name = w.name || 'Water';

                // Try to find better name from nearby waypoint for generic ВОДА
                if (name.toUpperCase().startsWith('ВОДА')) {
                    for (const wp of waypoints) {
                        if (wp.lat && wp.lon) {
                            const wpDist = haversineKm(w.lat, w.lon, wp.lat, wp.lon);
                            if (wpDist < 0.05 && !wp.description?.toUpperCase().startsWith('ВОДА')) {
                                name = (wp.description || '').substring(0, 40).trim();
                                break;
                            }
                        }
                    }
                }

                results.push({
                    km: Math.round(bestKm * 10) / 10,
                    name: name,
                    status: w.status || 'ok'
                });
            }
        }

        // Also get water from waypoint descriptions
        const wpInRange = waypoints.filter(w => w.km >= startKm && w.km <= endKm);
        for (const w of wpInRange) {
            const desc = (w.description || '').toLowerCase();
            if (WATER_KEYWORDS.some(kw => desc.includes(kw))) {
                results.push({
                    km: Math.round(w.km * 10) / 10,
                    name: (w.description || '').substring(0, 40).trim(),
                    status: 'ok'
                });
            }
        }

        // Sort and dedupe close entries
        results.sort((a, b) => a.km - b.km);
        const deduped = [];
        for (const r of results) {
            if (deduped.length === 0 || Math.abs(r.km - deduped[deduped.length - 1].km) > 0.5) {
                deduped.push(r);
            } else {
                // Keep better (non-generic) name
                const prevGeneric = deduped[deduped.length - 1].name.toUpperCase().startsWith('ВОДА');
                const currGeneric = r.name.toUpperCase().startsWith('ВОДА');
                if (prevGeneric && !currGeneric) {
                    deduped[deduped.length - 1] = r;
                }
            }
        }

        return deduped;
    }

    // === Segment Analysis ===

    function analyzeSegments(profile, minProminence = 100) {
        if (profile.length < 3) return [];

        // Smooth profile (moving average)
        const window = 5;
        const smoothed = profile.map((p, i) => {
            const start = Math.max(0, i - Math.floor(window / 2));
            const end = Math.min(profile.length, i + Math.floor(window / 2) + 1);
            const slice = profile.slice(start, end);
            const avgEle = slice.reduce((sum, pt) => sum + pt.ele, 0) / slice.length;
            return { km: p.km, ele: avgEle };
        });

        // Find turning points
        const turningPoints = [0];

        for (let i = 1; i < smoothed.length - 1; i++) {
            const prevEle = smoothed[i - 1].ele;
            const currEle = smoothed[i].ele;
            const nextEle = smoothed[i + 1].ele;

            const isPeak = currEle > prevEle && currEle > nextEle;
            const isValley = currEle < prevEle && currEle < nextEle;

            if (isPeak || isValley) {
                if (turningPoints.length > 0) {
                    const lastTp = turningPoints[turningPoints.length - 1];
                    const eleChange = Math.abs(smoothed[i].ele - smoothed[lastTp].ele);
                    const kmChange = smoothed[i].km - smoothed[lastTp].km;

                    if (eleChange >= minProminence || (eleChange >= 50 && kmChange >= 2)) {
                        turningPoints.push(i);
                    }
                }
            }
        }

        turningPoints.push(profile.length - 1);

        // Create segments
        const segments = [];
        for (let i = 0; i < turningPoints.length - 1; i++) {
            const startIdx = turningPoints[i];
            const endIdx = turningPoints[i + 1];

            const startKm = profile[startIdx].km;
            const endKm = profile[endIdx].km;
            const startEle = profile[startIdx].ele;
            const endEle = profile[endIdx].ele;

            const distance = Math.round((endKm - startKm) * 10) / 10;
            if (distance < 0.5) continue;

            let totalAscent = 0;
            let totalDescent = 0;
            for (let j = startIdx; j < endIdx; j++) {
                const diff = profile[j + 1].ele - profile[j].ele;
                if (diff > 0) totalAscent += diff;
                else totalDescent += Math.abs(diff);
            }

            const netChange = endEle - startEle;
            const direction = netChange > 0 ? 'ascent' : 'descent';
            const change = Math.abs(netChange);

            if (change < 30) continue;

            const gradient = distance > 0 ? Math.round((change / (distance * 1000)) * 1000) / 10 : 0;

            segments.push({
                type: direction,
                start_km: Math.round(startKm * 10) / 10,
                end_km: Math.round(endKm * 10) / 10,
                distance: distance,
                change: Math.round(change),
                ascent: Math.round(totalAscent),
                descent: Math.round(totalDescent),
                gradient: gradient,
                start_ele: Math.round(startEle),
                end_ele: Math.round(endEle)
            });
        }

        // Merge adjacent same-direction segments
        const merged = [];
        for (const seg of segments) {
            if (merged.length > 0 && merged[merged.length - 1].type === seg.type) {
                const prev = merged[merged.length - 1];
                prev.end_km = seg.end_km;
                prev.end_ele = seg.end_ele;
                prev.distance = Math.round((prev.end_km - prev.start_km) * 10) / 10;
                prev.change = Math.abs(prev.end_ele - prev.start_ele);
                prev.ascent = (prev.ascent || 0) + (seg.ascent || 0);
                prev.descent = (prev.descent || 0) + (seg.descent || 0);
                if (prev.distance > 0) {
                    prev.gradient = Math.round((prev.change / (prev.distance * 1000)) * 1000) / 10;
                }
            } else {
                merged.push({ ...seg });
            }
        }

        return merged;
    }

    // === API Methods ===

    async function getSegmentStats(startKm, endKm) {
        const waypoints = await getWaypoints();
        const terrain = await getTerrainFactor((startKm + endKm) / 2);

        // Get waypoints in range
        const inRange = waypoints.filter(w => w.km > startKm && w.km <= endKm);

        // Calculate time
        let totalMins = 0;
        for (const w of inRange) {
            totalMins += parseTime(w.sectorTime);
        }
        const hours = Math.round(totalMins / 60 * 10) / 10;

        // Calculate elevation using precomputed segment data
        let elevationGain = 0;
        let elevationLoss = 0;
        let hasSegmentData = false;

        for (const w of inRange) {
            if (w.segGain !== null && w.segGain !== undefined) {
                elevationGain += w.segGain;
                elevationLoss += w.segLoss || 0;
                hasSegmentData = true;
            }
        }

        // Fallback to sparse calculation if no segment data
        if (!hasSegmentData) {
            let prev = null;
            for (const w of inRange) {
                if (w.elevation) {
                    if (prev !== null) {
                        const delta = w.elevation - prev;
                        if (delta > 0) elevationGain += delta;
                        else elevationLoss += Math.abs(delta);
                    }
                    prev = w.elevation;
                }
            }
        }

        // Count water sources
        const water = await getWaterInSegment(startKm, endKm);
        const waterCount = water.length;

        // Check for technical sections
        let technical = 0;
        for (const w of inRange) {
            if (w.technical && w.technical > technical) {
                technical = w.technical;
            }
        }

        // Difficulty rating
        const distanceKm = endKm - startKm;
        let difficulty;
        if (hours > 12 || elevationGain > 1500 || elevationLoss > 2000 || distanceKm > 55) {
            difficulty = 'hard';
        } else if (hours > 8 || elevationGain > 900 || elevationLoss > 1200 || distanceKm > 40) {
            difficulty = 'moderate';
        } else {
            difficulty = 'easy';
        }

        return {
            start_km: startKm,
            end_km: endKm,
            distance_km: Math.round(distanceKm * 10) / 10,
            hours: hours,
            elevation_gain: Math.round(elevationGain),
            elevation_loss: Math.round(elevationLoss),
            water_count: waterCount,
            terrain: terrain.name,
            terrain_factor: terrain.factor,
            difficulty: difficulty,
            technical: technical
        };
    }

    async function getSegmentPreview(startKm, endKm) {
        const waypoints = await getWaypoints();
        const elevation = await getElevation();
        const huts = await getHuts();

        // Get stats
        const stats = await getSegmentStats(startKm, endKm);

        // Get elevation profile for segment
        let profile = elevation.filter(p => p.km >= startKm && p.km <= endKm);
        if (profile.length === 0) {
            // Fallback to waypoints
            profile = waypoints
                .filter(w => w.km >= startKm && w.km <= endKm && w.elevation)
                .map(w => ({ km: w.km, ele: w.elevation }));
        }

        // Get huts in segment
        const hutsInSegment = huts
            .filter(h => h.km >= startKm && h.km <= endKm)
            .map(h => ({ km: h.km, name: h.name, phone: h.phone }));

        // Get water sources
        const water = await getWaterInSegment(startKm, endKm);

        // Get POIs
        const pois = classifyPOIs(waypoints, startKm, endKm);

        // Analyze elevation segments
        const segments = analyzeSegments(profile);

        return {
            distance_km: stats.distance_km,
            hours: stats.hours,
            elevation_gain: stats.elevation_gain,
            elevation_loss: stats.elevation_loss,
            profile: profile.map(p => ({ km: Math.round(p.km * 100) / 100, ele: p.ele })),
            segments: segments,
            pois: {
                huts: hutsInSegment,
                water: water,
                villages: pois.villages,
                passes: pois.passes,
                peaks: pois.peaks
            }
        };
    }

    async function getElevationProfile() {
        const elevation = await getElevation();
        const waypoints = await getWaypoints();

        return {
            points: elevation.map(p => ({ km: Math.round(p.km * 100) / 100, ele: p.ele })),
            waypoints: waypoints.map(w => ({
                km: Math.round(w.km * 100) / 100,
                name: w.description ? w.description.substring(0, 30) : '',
                technical: w.technical || 0
            }))
        };
    }

    // Public API
    return {
        getWaypoints,
        getHuts,
        getSegmentStats,
        getSegmentPreview,
        getElevationProfile
    };
})();
