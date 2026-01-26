// Kom-Emine Route Planner
let allWaypoints = [];
let selectedRoute = []; // Array of waypoint objects
let elevationChart = null;
let elevationData = null;
let segmentChart = null;

const FILTERS = ['hut', 'shelter', 'village', 'town', 'resort', 'finish'];

// DOM elements
const waypointsTable = document.querySelector('#waypoints-table tbody');
const routeTable = document.querySelector('#route-table tbody');
const waypointCount = document.getElementById('waypoint-count');
const routeDays = document.getElementById('route-days');
const routeTotals = document.getElementById('route-totals');
const warningsEl = document.getElementById('warnings');
const clearBtn = document.getElementById('clear-btn');

// Initialize
async function init() {
    await loadWaypoints();
    loadRouteFromStorage();
    setupFilters();
    clearBtn.addEventListener('click', clearRoute);
    await updateSegmentStats();
    renderWaypoints();
    renderRoute();
    await loadElevationProfile();
    restoreModalFromURL();
}

function restoreModalFromURL() {
    const params = new URLSearchParams(window.location.search);
    const day = params.get('modal');
    const start = params.get('start');
    const end = params.get('end');

    if (day && start && end) {
        const startKm = parseFloat(start);
        const endKm = parseFloat(end);
        const dayNum = parseInt(day);

        // Find names from route
        let startName = 'Start', endName = 'End';
        if (dayNum === 1) {
            startName = 'Kom Peak';
        } else if (dayNum > 1 && selectedRoute[dayNum - 2]) {
            startName = extractName(selectedRoute[dayNum - 2].description);
        }
        if (selectedRoute[dayNum - 1]) {
            endName = extractName(selectedRoute[dayNum - 1].description);
        }

        openSegmentPreview(startKm, endKm, dayNum, startName, endName);
    }
}

function loadRouteFromStorage() {
    const saved = localStorage.getItem('kom-emine-route');
    if (saved) {
        const savedKms = JSON.parse(saved);
        selectedRoute = savedKms.map(km => allWaypoints.find(w => w.km === km)).filter(Boolean);
    }
}

function saveRouteToStorage() {
    const kms = selectedRoute.map(wp => wp.km);
    localStorage.setItem('kom-emine-route', JSON.stringify(kms));
}

async function loadWaypoints() {
    allWaypoints = await api.getWaypoints();
}

function setupFilters() {
    FILTERS.forEach(type => {
        const checkbox = document.getElementById(`filter-${type}`);
        checkbox.addEventListener('change', renderWaypoints);
    });
}

function getActiveFilters() {
    return FILTERS.filter(type =>
        document.getElementById(`filter-${type}`).checked
    );
}

function renderWaypoints() {
    const activeFilters = getActiveFilters();
    const filtered = allWaypoints.filter(wp =>
        wp.sleepable && activeFilters.includes(wp.sleepable)
    );

    waypointCount.textContent = `(${filtered.length})`;

    if (filtered.length === 0) {
        waypointsTable.innerHTML = '<tr><td colspan="5" class="empty-state">No matching waypoints</td></tr>';
        return;
    }

    waypointsTable.innerHTML = filtered.map(wp => {
        const isSelected = selectedRoute.some(s => s.km === wp.km);
        const name = extractName(wp.description);

        // Calculate distance from previous selected stop
        const prevStops = selectedRoute.filter(s => s.km < wp.km);
        const prevKm = prevStops.length > 0 ? prevStops[prevStops.length - 1].km : 0;
        const distFromPrev = (wp.km - prevKm).toFixed(1);
        const prevName = prevStops.length > 0 ? extractName(prevStops[prevStops.length - 1].description) : 'Kom Peak';
        const tooltip = `${distFromPrev}km from ${prevName}`;

        return `
            <tr class="${isSelected ? 'selected' : ''}" data-dist="${tooltip}" data-km="${wp.km}">
                <td>${wp.km.toFixed(1)}</td>
                <td title="${wp.description}">${name}</td>
                <td>${wp.elevation || '-'}</td>
                <td><span class="badge badge-${wp.sleepable}">${wp.sleepable}</span></td>
                <td>
                    <button class="btn-add"
                            onclick="addToRoute(${wp.km})"
                            ${isSelected ? 'disabled' : ''}>
                        ${isSelected ? '&#10003;' : '+'}
                    </button>
                </td>
            </tr>
        `;
    }).join('');
}

function extractName(description) {
    if (!description) return '-';
    // Try to extract the meaningful name part
    const match = description.match(/(?:х\.|хижа|заслон|т\.с\.|с\.|гр\.|курорт|хотел|вила)\s*[""„]?([^""„,\-\n]+)/i);
    if (match) return match[1].trim().substring(0, 25);
    // Fallback: first 25 chars
    return description.substring(0, 25);
}

async function addToRoute(km) {
    const wp = allWaypoints.find(w => w.km === km);
    if (!wp || selectedRoute.some(s => s.km === km)) return;

    selectedRoute.push(wp);
    selectedRoute.sort((a, b) => a.km - b.km);

    saveRouteToStorage();
    await updateSegmentStats();
    renderWaypoints();
    renderRoute();
}

function removeFromRoute(km) {
    selectedRoute = selectedRoute.filter(wp => wp.km !== km);
    saveRouteToStorage();
    updateSegmentStats();
    renderWaypoints();
    renderRoute();
}

function clearRoute() {
    selectedRoute = [];
    saveRouteToStorage();
    renderWaypoints();
    renderRoute();
}

async function updateSegmentStats() {
    // Calculate stats for each segment
    for (let i = 0; i < selectedRoute.length; i++) {
        const start = i === 0 ? 0 : selectedRoute[i - 1].km;
        const end = selectedRoute[i].km;

        if (end > start) {
            selectedRoute[i].segment = await api.getSegmentStats(start, end);
        }
    }
}

function renderRoute() {
    routeDays.textContent = selectedRoute.length > 0 ? `(${selectedRoute.length} stops)` : '';

    if (selectedRoute.length === 0) {
        routeTable.innerHTML = '<tr><td colspan="7" class="empty-state">Click + to add waypoints</td></tr>';
        routeTotals.innerHTML = '';
        warningsEl.innerHTML = '';
        updateElevationChartStops([]);
        return;
    }

    let totalKm = 0, totalHrs = 0, totalGain = 0, totalLoss = 0;
    const warnings = [];

    routeTable.innerHTML = selectedRoute.map((wp, i) => {
        const seg = wp.segment || {};
        const startName = i === 0 ? 'Kom Peak' : extractName(selectedRoute[i - 1].description);
        const endName = extractName(wp.description);

        totalKm += seg.distance_km || 0;
        totalHrs += seg.hours || 0;
        totalGain += seg.elevation_gain || 0;
        totalLoss += seg.elevation_loss || 0;

        // Check for warnings
        if (seg.distance_km > 60) {
            warnings.push(`Day ${i + 1}: ${seg.distance_km}km exceeds 60km limit`);
        }
        if (seg.water_count < 2) {
            warnings.push(`Day ${i + 1}: Low water (${seg.water_count} sources)`);
        }
        if (seg.hours > 12) {
            warnings.push(`Day ${i + 1}: ${seg.hours}h exceeds 12h limit`);
        }
        if (seg.technical === 2) {
            warnings.push(`Day ${i + 1}: Very technical terrain`);
        }

        const diffClass = seg.difficulty ? `diff-${seg.difficulty}` : '';
        const techIcon = seg.technical === 2 ? ' !' : seg.technical === 1 ? ' *' : '';

        const startKm = i === 0 ? 0 : selectedRoute[i - 1].km;
        return `
            <tr data-km="${wp.km}" onclick="openSegmentPreview(${startKm}, ${wp.km}, ${i + 1}, '${startName.replace(/'/g, "\\'")}', '${endName.replace(/'/g, "\\'")}')">
                <td>${i + 1}</td>
                <td title="${startName} → ${endName}">${startName.substring(0, 10)} → ${endName.substring(0, 10)}${techIcon}</td>
                <td>${seg.distance_km || '-'}</td>
                <td class="${diffClass}">${seg.hours || '-'}</td>
                <td>+${seg.elevation_gain || 0}</td>
                <td>-${seg.elevation_loss || 0}</td>
                <td><button class="btn-remove" onclick="event.stopPropagation(); removeFromRoute(${wp.km})">x</button></td>
            </tr>
        `;
    }).join('');

    routeTotals.innerHTML = `
        <span class="total-item"><span class="total-label">Total: </span><span class="total-value">${totalKm.toFixed(1)} km</span></span>
        <span class="total-item"><span class="total-label">Time: </span><span class="total-value">${totalHrs.toFixed(1)} hrs</span></span>
        <span class="total-item"><span class="total-label">Elevation: </span><span class="total-value">+${totalGain}m / -${totalLoss}m</span></span>
    `;

    warningsEl.innerHTML = warnings.map(w => `<div class="warning-item">${w}</div>`).join('');

    // Update chart with selected stops
    const stopKms = [0, ...selectedRoute.map(wp => wp.km)];
    updateElevationChartStops(stopKms);
}

// ============ Elevation Profile Chart ============

async function loadElevationProfile() {
    try {
        elevationData = await api.getElevationProfile();
        initElevationChart();
    } catch (e) {
        console.error('Failed to load elevation profile:', e);
    }
}

function initElevationChart() {
    if (!elevationData || !elevationData.points.length) {
        document.getElementById('elevation-panel').style.display = 'none';
        return;
    }

    const ctx = document.getElementById('elevationChart').getContext('2d');
    const points = elevationData.points;

    // Prepare data - sample if too many points for performance
    const maxPoints = 1000;
    const step = Math.ceil(points.length / maxPoints);
    const sampledPoints = points.filter((_, i) => i % step === 0);

    const labels = sampledPoints.map(p => p.km.toFixed(1));
    const data = sampledPoints.map(p => p.ele);

    elevationChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Elevation (m)',
                data: data,
                fill: true,
                backgroundColor: 'rgba(22, 163, 74, 0.18)',
                borderColor: '#16a34a',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.2
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: (items) => `km ${items[0].label}`,
                        label: (item) => `${item.raw}m`
                    }
                },
                zoom: {
                    pan: {
                        enabled: true,
                        mode: 'x'
                    },
                    zoom: {
                        wheel: { enabled: true },
                        pinch: { enabled: true },
                        mode: 'x'
                    }
                },
                annotation: {
                    annotations: {}
                }
            },
            scales: {
                x: {
                    type: 'linear',
                    title: { display: true, text: 'km', color: '#64748b' },
                    ticks: { color: '#64748b', maxTicksLimit: 15 },
                    grid: { color: '#e2e8f0' },
                    min: 0,
                    max: Math.ceil(points[points.length - 1].km)
                },
                y: {
                    title: { display: true, text: 'm', color: '#64748b' },
                    ticks: { color: '#64748b' },
                    grid: { color: '#e2e8f0' },
                    min: 0,
                    max: 2500,
                    suggestedMax: 2500
                }
            },
            onClick: (e, elements) => {
                if (elements.length > 0) {
                    const km = parseFloat(labels[elements[0].index]);
                    highlightWaypointNearKm(km);
                }
            }
        }
    });

    // Initial render with current stops
    const stopKms = [0, ...selectedRoute.map(wp => wp.km)];
    updateElevationChartStops(stopKms);
}

function updateElevationChartStops(stopKms) {
    if (!elevationChart) return;

    // Create vertical line annotations for each stop
    const annotations = {};
    stopKms.forEach((km, i) => {
        if (km > 0) {
            annotations[`stop${i}`] = {
                type: 'line',
                xMin: km,
                xMax: km,
                borderColor: '#16a34a',
                borderWidth: 2,
                borderDash: [4, 4],
                label: {
                    display: true,
                    content: `${i}`,
                    position: 'start',
                    backgroundColor: '#16a34a',
                    color: '#ffffff',
                    font: { size: 9, weight: 'bold' },
                    padding: 3
                }
            };
        }
    });

    // Add subtle alternating segments between stops
    for (let i = 0; i < stopKms.length - 1; i++) {
        const startKm = stopKms[i];
        const endKm = stopKms[i + 1];
        const isOdd = i % 2 === 1;
        annotations[`segment${i}`] = {
            type: 'box',
            xMin: startKm,
            xMax: endKm,
            yMin: 0,
            yMax: 2500,
            backgroundColor: isOdd ? 'rgba(22, 163, 74, 0.06)' : 'transparent',
            borderWidth: 0
        };
    }

    // Update annotations
    elevationChart.options.plugins.annotation = { annotations };
    elevationChart.update();
}

function highlightOnChart(km) {
    if (!elevationChart) return;

    const chart = elevationChart;

    // Get current annotations or create empty object
    const currentAnnotations = chart.options.plugins.annotation?.annotations || {};

    // Add highlight marker
    currentAnnotations.highlight = {
        type: 'line',
        xMin: km,
        xMax: km,
        borderColor: '#15803d',
        borderWidth: 2,
        label: {
            display: true,
            content: `km ${km.toFixed(0)}`,
            position: 'end',
            backgroundColor: '#15803d',
            color: '#ffffff',
            font: { size: 10, weight: 'bold' },
            padding: 4
        }
    };

    chart.options.plugins.annotation = { annotations: currentAnnotations };
    chart.update();

    // Remove highlight after 2s
    setTimeout(() => {
        if (chart.options.plugins.annotation?.annotations?.highlight) {
            delete chart.options.plugins.annotation.annotations.highlight;
            chart.update();
        }
    }, 2000);
}

function highlightWaypointNearKm(km) {
    // Find closest sleepable waypoint
    const filtered = allWaypoints.filter(wp => wp.sleepable);
    let closest = filtered[0];
    let minDist = Math.abs(closest.km - km);

    for (const wp of filtered) {
        const dist = Math.abs(wp.km - km);
        if (dist < minDist) {
            minDist = dist;
            closest = wp;
        }
    }

    if (closest && minDist < 20) {
        // Scroll waypoint table to show this waypoint
        const row = document.querySelector(`#waypoints-table tr[data-km="${closest.km}"]`);
        if (row) {
            row.scrollIntoView({ behavior: 'smooth', block: 'center' });
            row.classList.add('highlight');
            setTimeout(() => row.classList.remove('highlight'), 2000);
        }
    }
}

// ============ Segment Preview Modal ============

async function openSegmentPreview(startKm, endKm, day, startName, endName) {
    const modal = document.getElementById('segment-modal');
    const title = document.getElementById('modal-title');
    const stats = document.getElementById('modal-stats');
    const poisEl = document.getElementById('modal-pois');

    title.textContent = `Day ${day}: ${startName} → ${endName}`;
    stats.innerHTML = '<span class="stat-item">Loading...</span>';
    poisEl.innerHTML = '';

    modal.hidden = false;

    // Update URL with modal state
    const url = new URL(window.location);
    url.searchParams.set('modal', day);
    url.searchParams.set('start', startKm);
    url.searchParams.set('end', endKm);
    history.replaceState(null, '', url);

    try {
        const data = await api.getSegmentPreview(startKm, endKm);

        // Render stats
        stats.innerHTML = `
            <span class="stat-item"><span class="stat-label">Distance:</span> <span class="stat-value">${data.distance_km} km</span></span>
            <span class="stat-item"><span class="stat-label">Time:</span> <span class="stat-value">${data.hours} hrs</span></span>
            <span class="stat-item"><span class="stat-label">Gain:</span> <span class="stat-value stat-gain">+${data.elevation_gain}m</span></span>
            <span class="stat-item"><span class="stat-label">Loss:</span> <span class="stat-value stat-loss">-${data.elevation_loss}m</span></span>
        `;

        // Render chart with POI markers
        createSegmentChart(data.profile, data.pois);

        // Render segments and POIs
        renderSegmentsAndPOIs(data.segments, data.pois);

    } catch (e) {
        console.error('Failed to load segment preview:', e);
        stats.innerHTML = '<span class="stat-item">Failed to load</span>';
    }
}

function createSegmentChart(profile, pois) {
    const ctx = document.getElementById('segmentChart').getContext('2d');

    // Destroy existing chart
    if (segmentChart) {
        segmentChart.destroy();
    }

    if (!profile || profile.length === 0) {
        return;
    }

    // Sample if too many points
    const maxPoints = 500;
    const step = Math.ceil(profile.length / maxPoints);
    const sampled = profile.filter((_, i) => i % step === 0);

    const labels = sampled.map(p => p.km);
    const data = sampled.map(p => p.ele);

    // Build POI annotations
    const annotations = {};
    const allPois = [
        ...(pois.huts || []).map(p => ({ ...p, type: 'hut', color: '#16a34a' })),
        ...(pois.water || []).map(p => ({ ...p, type: 'water', color: '#3b82f6' })),
        ...(pois.villages || []).map(p => ({ ...p, type: 'village', color: '#8b5cf6' })),
        ...(pois.passes || []).map(p => ({ ...p, type: 'pass', color: '#f97316' })),
        ...(pois.peaks || []).map(p => ({ ...p, type: 'peak', color: '#ef4444' }))
    ];

    allPois.forEach((poi, i) => {
        annotations[`poi${i}`] = {
            type: 'line',
            xMin: poi.km,
            xMax: poi.km,
            borderColor: poi.color,
            borderWidth: 2,
            borderDash: poi.type === 'water' ? [3, 3] : [],
            label: {
                display: true,
                content: poi.type === 'water' ? '💧' : (poi.type === 'hut' ? '🏠' : (poi.type === 'village' ? '🏘' : '⛰')),
                position: 'start',
                font: { size: 10 }
            }
        };
    });

    segmentChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Elevation',
                data: data,
                fill: true,
                backgroundColor: 'rgba(22, 163, 74, 0.15)',
                borderWidth: 2,
                pointRadius: 0,
                tension: 0.2,
                segment: {
                    borderColor: ctx => {
                        if (ctx.p0 && ctx.p1) {
                            return ctx.p1.parsed.y > ctx.p0.parsed.y ? '#dc2626' : '#2563eb';
                        }
                        return '#16a34a';
                    }
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false
            },
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        title: items => `km ${items[0].label.toFixed(1)}`,
                        label: item => `${item.raw}m`
                    }
                },
                annotation: { annotations }
            },
            scales: {
                x: {
                    type: 'linear',
                    min: sampled[0].km,
                    max: sampled[sampled.length - 1].km,
                    title: { display: true, text: 'km', color: '#64748b' },
                    ticks: { color: '#64748b', maxTicksLimit: 10 },
                    grid: { color: '#e2e8f0' }
                },
                y: {
                    title: { display: true, text: 'm', color: '#64748b' },
                    ticks: { color: '#64748b' },
                    grid: { color: '#e2e8f0' }
                }
            }
        }
    });
}

function renderSegmentsAndPOIs(segments, pois) {
    const container = document.getElementById('modal-pois');

    // Combine all POIs into one sorted list
    const allPois = [
        ...(pois.huts || []).map(p => ({ ...p, type: 'hut', icon: '🏠' })),
        ...(pois.water || []).map(p => ({ ...p, type: 'water', icon: '💧' })),
        ...(pois.villages || []).map(p => ({ ...p, type: 'village', icon: '🏘' })),
        ...(pois.passes || []).map(p => ({ ...p, type: 'pass', icon: '⛰' })),
        ...(pois.peaks || []).map(p => ({ ...p, type: 'peak', icon: '🏔' }))
    ].sort((a, b) => a.km - b.km);

    let html = '<div class="segment-details">';

    // Segments table
    if (segments && segments.length > 0) {
        html += `
            <div class="segments-section">
                <h4>Elevation Segments</h4>
                <table class="segments-table">
                    <thead>
                        <tr>
                            <th></th>
                            <th>km</th>
                            <th>Dist</th>
                            <th>+</th>
                            <th>-</th>
                            <th>Grade</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${segments.map(s => `
                            <tr class="seg-${s.type}" onclick="highlightSegmentOnChart(${s.start_km}, ${s.end_km}, this)">
                                <td class="${s.type === 'ascent' ? 'seg-ascent-icon' : 'seg-descent-icon'}">${s.type === 'ascent' ? '↗' : '↘'}</td>
                                <td>${s.start_km}–${s.end_km}</td>
                                <td>${s.distance} km</td>
                                <td class="seg-ascent-val">+${s.ascent || 0}</td>
                                <td class="seg-descent-val">-${s.descent || 0}</td>
                                <td>${s.gradient}%</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    // POIs list
    if (allPois.length > 0) {
        html += `
            <div class="pois-section">
                <h4>Points of Interest</h4>
                <table class="pois-table">
                    <thead>
                        <tr>
                            <th></th>
                            <th>Name</th>
                            <th>km</th>
                            <th>Elev</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${allPois.map(p => `
                            <tr class="poi-row poi-${p.type}" onclick="highlightPOIOnChart(${p.km}, this)">
                                <td>${p.icon}</td>
                                <td>
                                    ${p.type === 'water' ? `<span class="water-status ${getWaterStatusClass(p.status)}"></span>` : ''}
                                    ${p.name}
                                </td>
                                <td>${p.km}</td>
                                <td>${p.elevation || '-'}</td>
                            </tr>
                        `).join('')}
                    </tbody>
                </table>
            </div>
        `;
    }

    html += '</div>';
    container.innerHTML = html || '<p style="color: var(--text-muted); padding: 1rem;">No data for this segment</p>';
}

function getWaterStatusClass(status) {
    if (!status) return 'ok';
    const s = status.toLowerCase();
    if (s.includes('пресъхва') || s.includes('seasonal')) return 'seasonal';
    if (s.includes('слаба') || s.includes('weak')) return 'weak';
    if (s.includes('спряна') || s.includes('dry')) return 'dry';
    return 'ok';
}

let currentHighlightedRow = null;

function clearChartHighlights() {
    if (!segmentChart) return;

    // Clear row highlight
    if (currentHighlightedRow) {
        currentHighlightedRow.classList.remove('highlighted');
        currentHighlightedRow = null;
    }

    // Clear chart annotations
    if (segmentChart.options.plugins.annotation?.annotations) {
        delete segmentChart.options.plugins.annotation.annotations.segmentHighlight;
        delete segmentChart.options.plugins.annotation.annotations.poiHighlight;
        segmentChart.update();
    }
}

function highlightSegmentOnChart(startKm, endKm, clickedRow) {
    if (!segmentChart) return;

    // Clear previous highlights
    clearChartHighlights();

    // Highlight the clicked row
    if (clickedRow) {
        clickedRow.classList.add('highlighted');
        currentHighlightedRow = clickedRow;
    }

    // Ensure annotation plugin exists
    if (!segmentChart.options.plugins.annotation) {
        segmentChart.options.plugins.annotation = { annotations: {} };
    }
    if (!segmentChart.options.plugins.annotation.annotations) {
        segmentChart.options.plugins.annotation.annotations = {};
    }

    // Add highlight box directly to existing annotations
    segmentChart.options.plugins.annotation.annotations.segmentHighlight = {
        type: 'box',
        xMin: startKm,
        xMax: endKm,
        backgroundColor: 'rgba(251, 191, 36, 0.4)',
        borderColor: '#f59e0b',
        borderWidth: 3
    };

    segmentChart.update();
}

function highlightPOIOnChart(km, clickedRow) {
    if (!segmentChart) return;

    // Clear previous highlights
    clearChartHighlights();

    // Highlight the clicked row
    if (clickedRow) {
        clickedRow.classList.add('highlighted');
        currentHighlightedRow = clickedRow;
    }

    // Ensure annotation plugin exists
    if (!segmentChart.options.plugins.annotation) {
        segmentChart.options.plugins.annotation = { annotations: {} };
    }
    if (!segmentChart.options.plugins.annotation.annotations) {
        segmentChart.options.plugins.annotation.annotations = {};
    }

    // Add highlight line directly to existing annotations
    segmentChart.options.plugins.annotation.annotations.poiHighlight = {
        type: 'line',
        xMin: km,
        xMax: km,
        borderColor: '#f59e0b',
        borderWidth: 4,
        label: {
            display: true,
            content: `km ${km}`,
            position: 'end',
            backgroundColor: '#f59e0b',
            color: '#fff',
            font: { size: 11, weight: 'bold' },
            padding: 4
        }
    };

    segmentChart.update();
}

function closeSegmentModal() {
    const modal = document.getElementById('segment-modal');
    modal.hidden = true;
    if (segmentChart) {
        segmentChart.destroy();
        segmentChart = null;
    }

    // Clear URL params
    const url = new URL(window.location);
    url.searchParams.delete('modal');
    url.searchParams.delete('start');
    url.searchParams.delete('end');
    history.replaceState(null, '', url);
}

// Close modal on backdrop click or ESC, clear highlights on chart click
document.addEventListener('DOMContentLoaded', () => {
    const modal = document.getElementById('segment-modal');
    const backdrop = modal.querySelector('.modal-backdrop');
    const chartWrapper = document.querySelector('.segment-chart-wrapper');

    backdrop.addEventListener('click', closeSegmentModal);

    // Clear highlights when clicking on chart area
    if (chartWrapper) {
        chartWrapper.addEventListener('click', (e) => {
            // Only clear if clicking directly on chart, not on a POI marker
            if (e.target.tagName === 'CANVAS') {
                clearChartHighlights();
            }
        });
    }

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape' && !modal.hidden) {
            closeSegmentModal();
        }
    });
});

// Start app
init();
