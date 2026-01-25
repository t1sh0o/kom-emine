// Kom-Emine Route Planner
let allWaypoints = [];
let selectedRoute = []; // Array of waypoint objects
let elevationChart = null;
let elevationData = null;

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
    const res = await fetch('/api/waypoints');
    allWaypoints = await res.json();
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
            const res = await fetch(`/api/segment?start=${start}&end=${end}`);
            selectedRoute[i].segment = await res.json();
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

        return `
            <tr data-km="${wp.km}" onclick="highlightOnChart(${wp.km})">
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
        const res = await fetch('/api/elevation-profile');
        elevationData = await res.json();
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

// Start app
init();
