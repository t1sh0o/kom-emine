// Kom-Emine Route Planner
let allWaypoints = [];
let selectedRoute = []; // Array of waypoint objects

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
            <tr class="${isSelected ? 'selected' : ''}" data-dist="${tooltip}">
                <td>${wp.km.toFixed(1)}</td>
                <td title="${wp.description}">${name}</td>
                <td>${wp.elevation || '-'}</td>
                <td><span class="badge badge-${wp.sleepable}">${wp.sleepable}</span></td>
                <td>
                    <button class="btn-add"
                            onclick="addToRoute(${wp.km})"
                            ${isSelected ? 'disabled' : ''}>
                        ${isSelected ? '✓' : '+'}
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
        routeTable.innerHTML = '<tr><td colspan="6" class="empty-state">Click + to add waypoints</td></tr>';
        routeTotals.innerHTML = '';
        warningsEl.innerHTML = '';
        return;
    }

    let totalKm = 0, totalHrs = 0, totalGain = 0;
    const warnings = [];

    routeTable.innerHTML = selectedRoute.map((wp, i) => {
        const seg = wp.segment || {};
        const startName = i === 0 ? 'Kom Peak' : extractName(selectedRoute[i - 1].description);
        const endName = extractName(wp.description);

        totalKm += seg.distance_km || 0;
        totalHrs += seg.hours || 0;
        totalGain += seg.elevation_gain || 0;

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

        const diffClass = seg.difficulty ? `diff-${seg.difficulty}` : '';

        return `
            <tr>
                <td>${i + 1}</td>
                <td title="${startName} → ${endName}">${startName.substring(0, 10)} → ${endName.substring(0, 10)}</td>
                <td>${seg.distance_km || '-'}</td>
                <td class="${diffClass}">${seg.hours || '-'}</td>
                <td>+${seg.elevation_gain || 0}</td>
                <td><button class="btn-remove" onclick="removeFromRoute(${wp.km})">×</button></td>
            </tr>
        `;
    }).join('');

    routeTotals.innerHTML = `
        <span class="total-item"><span class="total-label">Total: </span><span class="total-value">${totalKm.toFixed(1)} km</span></span>
        <span class="total-item"><span class="total-label">Time: </span><span class="total-value">${totalHrs.toFixed(1)} hrs</span></span>
        <span class="total-item"><span class="total-label">Elevation: </span><span class="total-value">+${totalGain} m</span></span>
    `;

    warningsEl.innerHTML = warnings.map(w => `<div class="warning-item">${w}</div>`).join('');
}

// Start app
init();
