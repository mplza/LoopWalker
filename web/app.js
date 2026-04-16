const welcomeViewEl = document.getElementById('welcome-view');
const appViewEl = document.getElementById('app-view');
const appUserEl = document.getElementById('app-user');
const authStatusEl = document.getElementById('auth-status');

const registerBtn = document.getElementById('register-btn');
const loginBtn = document.getElementById('login-btn');
const resetBtn = document.getElementById('reset-btn');
const logoutBtn = document.getElementById('logout-btn');

const tabGenerateBtn = document.getElementById('tab-generate-btn');
const tabRoutesBtn = document.getElementById('tab-routes-btn');
const tabSessionsBtn = document.getElementById('tab-sessions-btn');
const tabAnalyticsBtn = document.getElementById('tab-analytics-btn');
const tabGenerateEl = document.getElementById('tab-generate');
const tabRoutesEl = document.getElementById('tab-routes');
const tabSessionsEl = document.getElementById('tab-sessions');
const tabAnalyticsEl = document.getElementById('tab-analytics');

if (!tabGenerateBtn) console.warn('tab-generate-btn not found');
if (!tabRoutesBtn) console.warn('tab-routes-btn not found');
if (!tabSessionsBtn) console.warn('tab-sessions-btn not found');
if (!tabAnalyticsBtn) console.warn('tab-analytics-btn not found');
if (!tabGenerateEl) console.warn('tab-generate section not found');
if (!tabRoutesEl) console.warn('tab-routes section not found');
if (!tabSessionsEl) console.warn('tab-sessions section not found');
if (!tabAnalyticsEl) console.warn('tab-analytics section not found');

const form = document.getElementById('route-form');
const routeNameEl = document.getElementById('route_name');
const generatedActionsEl = document.getElementById('generated-actions');
const saveRouteBtn = document.getElementById('save-route-btn');
const newRouteBtn = document.getElementById('new-route-btn');

const statusEl = document.getElementById('status');
const generateLoadingEl = document.getElementById('generate-loading');
const metricsEl = document.getElementById('metrics');
const mMinutes = document.getElementById('m-minutes');
const mKm = document.getElementById('m-km');
const mSteps = document.getElementById('m-steps');

const walkTimerEl = document.getElementById('walk-timer');
const timerElapsedEl = document.getElementById('timer-elapsed');
const timerFinalEl = document.getElementById('timer-final');
const timerStartBtn = document.getElementById('timer-start');
const timerPauseBtn = document.getElementById('timer-pause');
const timerEndBtn = document.getElementById('timer-end');

const routeProgressEl = document.getElementById('route-progress');
const pKmDoneEl = document.getElementById('p-km-done');
const pKmLeftEl = document.getElementById('p-km-left');
const pMinDoneEl = document.getElementById('p-min-done');
const pMinLeftEl = document.getElementById('p-min-left');
const pPercentEl = document.getElementById('p-percent');
const progressFillEl = document.getElementById('progress-fill');
const sameRouteSessionsListEl = document.getElementById('same-route-sessions-list');
const sameRouteSessionsEmptyEl = document.getElementById('same-route-sessions-empty');

const analyticsOverviewEl = document.getElementById('analytics-overview');
const summaryDailyBtn = document.getElementById('summary-daily-btn');
const summaryWeeklyBtn = document.getElementById('summary-weekly-btn');
const summaryMonthlyBtn = document.getElementById('summary-monthly-btn');
const analyticsMetricSelectEl = document.getElementById('analytics-metric-select');
const analyticsSelectedChartTitleEl = document.getElementById('analytics-selected-chart-title');
const analyticsSelectedChartEl = document.getElementById('analytics-selected-chart');

const historyListEl = document.getElementById('history-list');
const historyEmptyEl = document.getElementById('history-empty');
const sessionsListEl = document.getElementById('sessions-list');
const sessionsEmptyEl = document.getElementById('sessions-empty');
const sessionStatsEl = document.getElementById('session-stats');
const ssTimeEl = document.getElementById('ss-time');
const ssKmEl = document.getElementById('ss-km');
const ssStepsEl = document.getElementById('ss-steps');
const ssStartedEl = document.getElementById('ss-started');
const ssEndedEl = document.getElementById('ss-ended');

let currentUser = null;
let map = null;
let routesMap = null;
let sessionsMap = null;
let startMarker = null;
let routeLayer = null;
let routesRouteLayer = null;
let sessionsRouteLayer = null;
let liveMarker = null;
let routeProgressMarker = null;
let startPoint = null;
let geoWatchId = null;

let generatedRoute = null;

let routeCoords = [];
let routeCumKm = [];
let routeTotalKm = 0;
let plannedDurationMin = 0;
let currentRouteId = null;
let latestDoneKm = 0;

let timerRunning = false;
let timerStartTs = 0;
let timerElapsedMs = 0;
let timerIntervalId = null;
let activeDistanceKm = 0;
let activeSteps = 0;
let lastLiveLatLng = null;
let allWalkSessions = [];

let routeVariationSeed = 0;
let currentAnalyticsOverview = null;
let analyticsOffsets = {
  day: 0,
  week: 0,
  month: 0,
};
let currentSummaryPeriod = 'day';

function renderAnalyticsOverviewCard(key, title, periodData) {
  const totals = periodData?.totals || {};
  const avg = periodData?.avg_per_session || {};
  const offset = Number(periodData?.offset || 0);
  const nextDisabled = offset <= 0 ? 'disabled' : '';

  const card = document.createElement('article');
  card.className = 'analytics-card';
  card.innerHTML = `
    <div class="analytics-card-head">
      <h3>${title}</h3>
      <div class="analytics-card-nav">
        <button type="button" class="ghost small analytics-shift-btn" data-period="${key}" data-delta="1">Previous</button>
        <button type="button" class="ghost small analytics-shift-btn" data-period="${key}" data-delta="-1" ${nextDisabled}>Next</button>
      </div>
    </div>
    <p class="hint">${periodData?.label || ''}</p>
    <p><strong>Total time:</strong> ${formatDuration((Number(totals.elapsed_seconds) || 0) * 1000)}</p>
    <p><strong>Total kilometers:</strong> ${Number(totals.distance_km || 0).toFixed(2)} km</p>
    <p><strong>Total steps:</strong> ${Number(totals.steps || 0)}</p>
    <p><strong>Total sessions:</strong> ${Number(totals.sessions || 0)}</p>
    <p><strong>Avg time per session:</strong> ${formatDuration((Number(avg.elapsed_seconds) || 0) * 1000)}</p>
    <p><strong>Avg kilometers/session:</strong> ${Number(avg.distance_km || 0).toFixed(2)} km</p>
    <p><strong>Avg steps/session:</strong> ${Number(avg.steps || 0)}</p>
  `;
  return card;
}

function updateSummaryToggleButtons() {
  if (!summaryDailyBtn || !summaryWeeklyBtn || !summaryMonthlyBtn) {
    return;
  }
  summaryDailyBtn.classList.toggle('active', currentSummaryPeriod === 'day');
  summaryWeeklyBtn.classList.toggle('active', currentSummaryPeriod === 'week');
  summaryMonthlyBtn.classList.toggle('active', currentSummaryPeriod === 'month');
}

function formatMetricValue(metric, value) {
  if (metric === 'elapsed_hours') {
    return `${Number(value || 0).toFixed(2)} h`;
  }
  if (metric === 'elapsed_minutes') {
    return `${Number(value || 0).toFixed(0)} min`;
  }
  if (metric === 'distance_km') {
    return `${Number(value || 0).toFixed(2)} km`;
  }
  return `${Math.round(Number(value || 0))}`;
}

function getSeriesMetricValue(item, metric) {
  const seconds = Number(item?.elapsed_seconds || 0);
  if (metric === 'elapsed_hours') {
    return seconds / 3600;
  }
  if (metric === 'elapsed_minutes') {
    return seconds / 60;
  }
  if (metric === 'distance_km') {
    return Number(item?.distance_km || 0);
  }
  return Number(item?.steps || 0);
}

function renderMiniChart(containerEl, series, metric) {
  if (!containerEl) {
    return;
  }
  containerEl.innerHTML = '';
  const rows = Array.isArray(series) ? series : [];
  if (!rows.length) {
    const empty = document.createElement('p');
    empty.className = 'mini-chart-empty';
    empty.textContent = 'No sessions in recent periods.';
    containerEl.appendChild(empty);
    return;
  }

  const maxBars = 8;
  const shown = rows.slice(-maxBars);
  const values = shown.map((item) => getSeriesMetricValue(item, metric));
  const maxValue = Math.max(...values, 1);

  shown.forEach((item, idx) => {
    const value = values[idx];
    const col = document.createElement('div');
    col.className = 'mini-col';

    const valueEl = document.createElement('span');
    valueEl.className = 'mini-value';
    valueEl.textContent = formatMetricValue(metric, value);

    const bar = document.createElement('div');
    bar.className = 'mini-bar';

    const fill = document.createElement('div');
    fill.className = 'mini-fill';
    fill.style.height = `${Math.max(0, (value / maxValue) * 100)}%`;

    const label = document.createElement('span');
    label.className = 'mini-label';
    label.textContent = item.label || '-';

    bar.appendChild(fill);
    col.appendChild(valueEl);
    col.appendChild(bar);
    col.appendChild(label);
    containerEl.appendChild(col);
  });
}

function renderAnalyticsCharts(data) {
  const metric = analyticsMetricSelectEl?.value || 'elapsed_hours';
  const metricTitle = metric === 'distance_km' ? 'Kilometers' : metric === 'steps' ? 'Steps' : metric === 'elapsed_minutes' ? 'Minutes' : 'Hours';
  const periodTitle = currentSummaryPeriod === 'week' ? 'Weekly' : currentSummaryPeriod === 'month' ? 'Monthly' : 'Daily';

  if (analyticsSelectedChartTitleEl) {
    analyticsSelectedChartTitleEl.textContent = `${periodTitle} ${metricTitle}`;
  }

  if (currentSummaryPeriod === 'week') {
    renderMiniChart(analyticsSelectedChartEl, data?.week?.series || [], metric);
    return;
  }
  if (currentSummaryPeriod === 'month') {
    renderMiniChart(analyticsSelectedChartEl, data?.month?.series || [], metric);
    return;
  }
  renderMiniChart(analyticsSelectedChartEl, data?.day?.series || [], metric);
}

function formatDuration(ms) {
  const totalSeconds = Math.max(0, Math.floor(ms / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return `${String(hours).padStart(2, '0')}:${String(minutes).padStart(2, '0')}:${String(seconds).padStart(2, '0')}`;
}

function routePointSignature(geojson) {
  const coords = geojson?.features?.[0]?.geometry?.coordinates || [];
  if (!Array.isArray(coords) || coords.length === 0) {
    return new Set();
  }
  const step = Math.max(1, Math.floor(coords.length / 30));
  const out = new Set();
  for (let i = 0; i < coords.length; i += step) {
    const c = coords[i];
    out.add(`${Number(c[0]).toFixed(4)},${Number(c[1]).toFixed(4)}`);
  }
  return out;
}

function routeSimilarity(aGeojson, bGeojson) {
  const a = routePointSignature(aGeojson);
  const b = routePointSignature(bGeojson);
  if (a.size === 0 || b.size === 0) {
    return 0;
  }
  let common = 0;
  for (const p of a) {
    if (b.has(p)) {
      common += 1;
    }
  }
  return common / Math.max(a.size, b.size);
}

function renderGeneratedRoute(data, payload) {
  renderRouteOnMap(data.geojson, Number(data.metrics.duration_min) || 0);
  generatedRoute = {
    lat: payload.lat,
    lon: payload.lon,
    target_mode: payload.target_mode,
    target_value: payload.target_value,
    distance_km: Number(data.metrics.distance_km),
    duration_min: Number(data.metrics.duration_min),
    steps: Number(data.metrics.steps),
    route_geojson: data.geojson,
  };

  mMinutes.textContent = `${data.metrics.duration_min}`;
  mKm.textContent = `${data.metrics.distance_km}`;
  mSteps.textContent = `${data.metrics.steps}`;
  metricsEl.hidden = false;
  generatedActionsEl.hidden = false;
}

async function requestRoute(payload, previousGeojson = null) {
  const attempts = previousGeojson ? 4 : 1;
  let best = null;
  let bestSimilarity = Number.POSITIVE_INFINITY;
  let lastError = null;

  for (let i = 0; i < attempts; i += 1) {
    routeVariationSeed += 1;
    const candidatePayload = {
      ...payload,
      variation_seed: routeVariationSeed,
    };
    try {
      const response = await fetch('/api/route', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify(candidatePayload),
      });

      const data = await response.json().catch(() => ({}));
      if (!response.ok) {
        throw new Error(data.detail || 'Route request failed');
      }

      if (!previousGeojson) {
        return data;
      }

      const similarity = routeSimilarity(previousGeojson, data.geojson);
      if (similarity < bestSimilarity) {
        bestSimilarity = similarity;
        best = data;
      }
      if (similarity <= 0.12) {
        return data;
      }
    } catch (error) {
      lastError = error;
    }
  }

  if (best) {
    return best;
  }
  if (lastError) {
    throw lastError;
  }
  throw new Error('Route request failed');
}

async function generateRouteNow(previousGeojson = null) {
  if (!startPoint) {
    setStatus('Waiting for location. Allow geolocation or click map to set start point.', true);
    return;
  }

  const payload = {
    lat: startPoint.lat,
    lon: startPoint.lng,
    route_name: document.getElementById('route_name').value.trim() || null,
    target_mode: document.getElementById('target_mode').value,
    target_value: Number(document.getElementById('target_value').value),
  };

  setGenerateLoading(true);
  try {
    setStatus('');
    const data = await requestRoute(payload, previousGeojson);
    renderGeneratedRoute(data, payload);
    setStatus('Route generated successfully.');
  } finally {
    setGenerateLoading(false);
  }
}

function currentTimerMs() {
  if (!timerRunning) {
    return timerElapsedMs;
  }
  return timerElapsedMs + (Date.now() - timerStartTs);
}

function haversineKm(a, b) {
  const toRad = (v) => (v * Math.PI) / 180;
  const r = 6371;
  const dLat = toRad(b.lat - a.lat);
  const dLon = toRad(b.lng - a.lng);
  const lat1 = toRad(a.lat);
  const lat2 = toRad(b.lat);
  const x = Math.sin(dLat / 2) ** 2 + Math.sin(dLon / 2) ** 2 * Math.cos(lat1) * Math.cos(lat2);
  const y = 2 * Math.atan2(Math.sqrt(x), Math.sqrt(1 - x));
  return r * y;
}

function llToXY(ll, latRef) {
  return {
    x: ll.lng * Math.cos((latRef * Math.PI) / 180),
    y: ll.lat,
  };
}

function projectPointToSegment(point, a, b, latRef) {
  const p = llToXY(point, latRef);
  const pa = llToXY(a, latRef);
  const pb = llToXY(b, latRef);

  const vx = pb.x - pa.x;
  const vy = pb.y - pa.y;
  const wx = p.x - pa.x;
  const wy = p.y - pa.y;
  const c2 = vx * vx + vy * vy;
  const tRaw = c2 <= 0 ? 0 : (vx * wx + vy * wy) / c2;
  const t = Math.max(0, Math.min(1, tRaw));

  return {
    t,
    point: {
      lat: a.lat + (b.lat - a.lat) * t,
      lng: a.lng + (b.lng - a.lng) * t,
    },
  };
}

function extractRouteCoordinates(routeGeojson) {
  const geometry = routeGeojson?.features?.[0]?.geometry;
  if (!geometry || geometry.type !== 'LineString' || !Array.isArray(geometry.coordinates)) {
    return [];
  }
  return geometry.coordinates.map(([lng, lat]) => ({ lat, lng }));
}

function buildRouteDistanceCache() {
  routeCumKm = [0];
  for (let i = 1; i < routeCoords.length; i += 1) {
    routeCumKm.push(routeCumKm[i - 1] + haversineKm(routeCoords[i - 1], routeCoords[i]));
  }
  routeTotalKm = routeCumKm.length ? routeCumKm[routeCumKm.length - 1] : 0;
}

function setProgressUi(doneKm, leftKm, doneMin, leftMin) {
  latestDoneKm = doneKm;
  const percent = routeTotalKm > 0 ? Math.max(0, Math.min(100, (doneKm / routeTotalKm) * 100)) : 0;
  pKmDoneEl.textContent = doneKm.toFixed(2);
  pKmLeftEl.textContent = leftKm.toFixed(2);
  pMinDoneEl.textContent = doneMin.toFixed(1);
  pMinLeftEl.textContent = leftMin.toFixed(1);
  pPercentEl.textContent = percent.toFixed(0);
  progressFillEl.style.width = `${percent}%`;
}

function updateTimerDisplay() {
  timerElapsedEl.textContent = formatDuration(currentTimerMs());
  if (routeProgressEl.hidden === false && liveMarker) {
    updateLiveProgress(liveMarker.getLatLng());
  }
}

function updateTimerButtons({ started, running, ended }) {
  timerStartBtn.disabled = ended || running;
  timerPauseBtn.disabled = !running;
  timerEndBtn.disabled = ended || !started;
}

function stopTimerInterval() {
  if (timerIntervalId !== null) {
    clearInterval(timerIntervalId);
    timerIntervalId = null;
  }
}

function resetWalkTimer() {
  timerRunning = false;
  timerStartTs = 0;
  timerElapsedMs = 0;
  timerFinalEl.textContent = '-';
  stopTimerInterval();
  activeDistanceKm = 0;
  activeSteps = 0;
  lastLiveLatLng = null;
  updateTimerDisplay();
  updateTimerButtons({ started: false, running: false, ended: false });
  setProgressUi(0, routeTotalKm, 0, plannedDurationMin);
}

function startWalkTimer() {
  if (timerRunning) {
    return;
  }
  timerRunning = true;
  timerStartTs = Date.now();
  stopTimerInterval();
  timerIntervalId = setInterval(updateTimerDisplay, 250);
  updateTimerButtons({ started: true, running: true, ended: false });
}

function pauseWalkTimer() {
  if (!timerRunning) {
    return;
  }
  timerElapsedMs = currentTimerMs();
  timerRunning = false;
  stopTimerInterval();
  updateTimerDisplay();
  updateTimerButtons({ started: timerElapsedMs > 0, running: false, ended: false });
}

function endWalkTimer() {
  if (!timerRunning && timerElapsedMs <= 0) {
    return;
  }
  if (timerRunning) {
    timerElapsedMs = currentTimerMs();
    timerRunning = false;
  }
  stopTimerInterval();
  updateTimerDisplay();
  timerFinalEl.textContent = formatDuration(timerElapsedMs);
  updateTimerButtons({ started: true, running: false, ended: true });
  persistCompletedWalkSession().catch((error) => {
    setStatus(`Error saving walk session: ${error.message}`, true);
  });
}

function estimateCompletedSteps() {
  return activeSteps;
}

async function persistCompletedWalkSession() {
  if (!currentUser) {
    return;
  }

  const payload = {
    route_session_id: currentRouteId,
    elapsed_seconds: Math.max(1, Math.round(timerElapsedMs / 1000)),
    distance_km: Number(activeDistanceKm.toFixed(2)),
    steps: estimateCompletedSteps(),
  };

  const response = await fetch('/api/me/walk-sessions', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'Could not save walk session');
  }

  await Promise.all([loadSessions(), loadWalkAnalytics()]);
}

function setAuthMessage(message = '', isError = false) {
  if (!authStatusEl) {
    return;
  }
  if (!message) {
    authStatusEl.textContent = '';
    authStatusEl.hidden = true;
    return;
  }
  authStatusEl.hidden = false;
  authStatusEl.textContent = message;
  authStatusEl.style.color = isError ? '#b91c1c' : '#334155';
}

function setStatus(message, isError = false) {
  statusEl.textContent = message;
  statusEl.style.color = isError ? '#b91c1c' : '#334155';
}

function setGenerateLoading(isLoading) {
  if (!generateLoadingEl) {
    return;
  }
  generateLoadingEl.hidden = !isLoading;
}

function updateLiveProgress(userLatLng) {
  if (routeCoords.length < 2) {
    return;
  }

  const latRef = userLatLng.lat;
  let best = {
    distanceKm: Number.POSITIVE_INFINITY,
    doneKm: 0,
    point: routeCoords[0],
  };

  for (let i = 1; i < routeCoords.length; i += 1) {
    const a = routeCoords[i - 1];
    const b = routeCoords[i];
    const projected = projectPointToSegment(userLatLng, a, b, latRef);
    const distKm = haversineKm(userLatLng, projected.point);
    const segKm = haversineKm(a, b);
    const doneKm = routeCumKm[i - 1] + segKm * projected.t;

    if (distKm < best.distanceKm) {
      best = { distanceKm: distKm, doneKm, point: projected.point };
    }
  }

  const doneKm = Math.max(0, Math.min(routeTotalKm, best.doneKm));
  const leftKm = Math.max(0, routeTotalKm - doneKm);
  const doneMin = currentTimerMs() / 60000;
  let leftMin = 0;

  if (doneKm > 0 && doneMin > 0) {
    leftMin = leftKm * (doneMin / doneKm);
  } else {
    leftMin = Math.max(0, plannedDurationMin - doneMin);
  }

  if (!routeProgressMarker) {
    routeProgressMarker = L.circleMarker(best.point, {
      radius: 6,
      color: '#0f3b53',
      weight: 2,
      fillColor: '#22a0cf',
      fillOpacity: 0.95,
    }).addTo(routesMap);
  } else {
    routeProgressMarker.setLatLng(best.point);
  }

  setProgressUi(doneKm, leftKm, doneMin, leftMin);
}

function updateActiveMovement(userLatLng, speedMps = null) {
  if (!timerRunning) {
    lastLiveLatLng = userLatLng;
    return;
  }

  if (!lastLiveLatLng) {
    lastLiveLatLng = userLatLng;
    return;
  }

  const deltaKm = haversineKm(lastLiveLatLng, userLatLng);
  const deltaM = deltaKm * 1000;
  const isSmallJitter = deltaM < 2.5;
  const isUnrealisticJump = deltaM > 80;
  const speedTooLow = speedMps !== null && speedMps < 0.35 && deltaM < 6;

  if (!isSmallJitter && !isUnrealisticJump && !speedTooLow) {
    activeDistanceKm += deltaKm;
    activeSteps = Math.round((activeDistanceKm * 1000) / 0.78);
  }

  lastLiveLatLng = userLatLng;
}

function startGeolocationTracking() {
  if (!navigator.geolocation || geoWatchId !== null) {
    return;
  }

  geoWatchId = navigator.geolocation.watchPosition(
    (position) => {
      const userLatLng = L.latLng(position.coords.latitude, position.coords.longitude);
      const speedMps = typeof position.coords.speed === 'number' ? position.coords.speed : null;

      if (!liveMarker) {
        liveMarker = L.circleMarker(userLatLng, {
          radius: 7,
          color: '#ffffff',
          weight: 2,
          fillColor: '#1d4ed8',
          fillOpacity: 0.95,
        }).addTo(map);
      } else {
        liveMarker.setLatLng(userLatLng);
      }

      if (!startPoint) {
        startPoint = userLatLng;
        if (!startMarker) {
          startMarker = L.marker(startPoint).addTo(map);
          map.setView(startPoint, 14);
        } else {
          startMarker.setLatLng(startPoint);
        }
        setStatus('Using your current location as default start/end point.');
      }

      if (routeProgressEl.hidden === false) {
        updateActiveMovement(userLatLng, speedMps);
        updateLiveProgress(userLatLng);
      }
    },
    () => {
      setStatus('Location access denied. Click map to choose start point manually.', true);
    },
    {
      enableHighAccuracy: true,
      maximumAge: 3000,
      timeout: 10000,
    },
  );
}

function ensureMapInitialized() {
  if (map) {
    map.invalidateSize();
    return;
  }

  map = L.map('map').setView([59.437, 24.7536], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(map);

  map.on('click', (e) => {
    startPoint = e.latlng;
    if (!startMarker) {
      startMarker = L.marker(startPoint).addTo(map);
    } else {
      startMarker.setLatLng(startPoint);
    }
    setStatus(`Start point set at ${startPoint.lat.toFixed(5)}, ${startPoint.lng.toFixed(5)}`);
  });

  startGeolocationTracking();
}

function ensureRoutesMapInitialized() {
  if (routesMap) {
    routesMap.invalidateSize();
    return;
  }

  routesMap = L.map('routes-map').setView([59.437, 24.7536], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(routesMap);
}

function ensureSessionsMapInitialized() {
  if (sessionsMap) {
    sessionsMap.invalidateSize();
    return;
  }

  sessionsMap = L.map('sessions-map').setView([59.437, 24.7536], 12);
  L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
    maxZoom: 19,
    attribution: '&copy; OpenStreetMap contributors',
  }).addTo(sessionsMap);
}

function showWelcome() {
  document.body.classList.remove('authenticated');
  appViewEl.hidden = true;
  welcomeViewEl.hidden = false;
  setAuthMessage('');
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function showApp() {
  document.body.classList.add('authenticated');
  welcomeViewEl.hidden = true;
  appViewEl.hidden = false;
  appUserEl.textContent = `You are logged in as ${currentUser?.email || 'user'}.`;
  setActiveTab('generate');
  ensureMapInitialized();
  window.scrollTo({ top: 0, behavior: 'auto' });
}

function setActiveTab(tab) {
  const isGenerate = tab === 'generate';
  const isRoutes = tab === 'routes';
  const isSessions = tab === 'sessions';
  const isAnalytics = tab === 'analytics';

  tabGenerateBtn.classList.toggle('active', isGenerate);
  tabRoutesBtn.classList.toggle('active', isRoutes);
  tabSessionsBtn.classList.toggle('active', isSessions);
  tabAnalyticsBtn.classList.toggle('active', isAnalytics);

  tabGenerateEl.hidden = !isGenerate;
  tabRoutesEl.hidden = !isRoutes;
  tabSessionsEl.hidden = !isSessions;
  tabAnalyticsEl.hidden = !isAnalytics;

  if (isGenerate && map) {
    map.invalidateSize();
  }
  if (isRoutes) {
    ensureRoutesMapInitialized();
    if (routesMap) {
      routesMap.invalidateSize();
    }
    loadHistory().catch(() => {
      setStatus('Could not load routes.', true);
    });
  }
  if (isSessions) {
    ensureSessionsMapInitialized();
    if (sessionsMap) {
      sessionsMap.invalidateSize();
    }
    loadSessions().catch(() => {
      setStatus('Could not load sessions.', true);
    });
  }
  if (isAnalytics) {
    loadWalkAnalytics().catch(() => {
      setStatus('Could not load analytics.', true);
    });
  }
}

function renderRouteOnMap(routeGeojson, durationMin = 0) {
  ensureMapInitialized();
  setActiveTab('generate');

  if (routeLayer) {
    map.removeLayer(routeLayer);
  }
  routeLayer = L.geoJSON(routeGeojson, {
    style: { color: '#0a7ea4', weight: 5 },
  }).addTo(map);
  map.fitBounds(routeLayer.getBounds(), { padding: [20, 20] });

  routeCoords = extractRouteCoordinates(routeGeojson);
  buildRouteDistanceCache();
  plannedDurationMin = Number(durationMin) || 0;
}

function renderRouteOnRoutesMap(routeGeojson) {
  ensureRoutesMapInitialized();
  if (routesRouteLayer) {
    routesMap.removeLayer(routesRouteLayer);
  }
  routesRouteLayer = L.geoJSON(routeGeojson, {
    style: { color: '#0a7ea4', weight: 5 },
  }).addTo(routesMap);
  routesMap.fitBounds(routesRouteLayer.getBounds(), { padding: [20, 20] });
}

function renderHistory(routes) {
  historyListEl.innerHTML = '';
  if (!routes || routes.length === 0) {
    historyEmptyEl.hidden = false;
    return;
  }
  historyEmptyEl.hidden = true;

  const targetModeLabel = (mode) => {
    if (mode === 'hours') return 'Hours';
    if (mode === 'minutes') return 'Minutes';
    if (mode === 'kilometers') return 'Kilometers';
    if (mode === 'steps') return 'Steps';
    return mode;
  };

  routes.forEach((route) => {
    const li = document.createElement('li');
    li.className = 'history-item';
    const routeLabel = route.route_name ? route.route_name : `Route ${route.id}`;
    li.innerHTML = `
      <p><strong>${routeLabel}</strong></p>
      <p><strong>Walking</strong> | ${targetModeLabel(route.target_mode)}: ${route.target_value}</p>
      <p>${route.distance_km} km | ${route.duration_min} min | ${route.steps} steps</p>
      <p>${new Date(route.created_at + 'Z').toLocaleString()}</p>
    `;

    const selectBtn = document.createElement('button');
    selectBtn.type = 'button';
    selectBtn.textContent = 'Select';
    selectBtn.addEventListener('click', () => {
      setActiveTab('routes');
      renderRouteOnRoutesMap(route.route_geojson);
      routeCoords = extractRouteCoordinates(route.route_geojson);
      buildRouteDistanceCache();
      plannedDurationMin = Number(route.duration_min) || 0;
      currentRouteId = Number(route.id) || null;
      if (routeProgressMarker && routesMap) {
        routesMap.removeLayer(routeProgressMarker);
        routeProgressMarker = null;
      }
      walkTimerEl.hidden = false;
      routeProgressEl.hidden = false;
      renderSameRouteSessions();
      resetWalkTimer();
      setStatus('Route selected. Click Start in Walk Timer to begin session.');
    });

    const renameBtn = document.createElement('button');
    renameBtn.type = 'button';
    renameBtn.className = 'ghost small';
    renameBtn.textContent = 'Rename';
    renameBtn.addEventListener('click', async () => {
      const next = window.prompt('Route name', route.route_name || '');
      if (next === null) {
        return;
      }
      try {
        const response = await fetch(`/api/me/routes/${route.id}/name`, {
          method: 'PATCH',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ route_name: next.trim() || null }),
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || 'Rename failed');
        }
        await loadHistory();
      } catch (error) {
        setStatus(`Error: ${error.message}`, true);
      }
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'ghost small';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
      const ok = window.confirm('Delete this route?');
      if (!ok) {
        return;
      }
      try {
        const response = await fetch(`/api/me/routes/${route.id}`, {
          method: 'DELETE',
          credentials: 'same-origin',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || 'Delete failed');
        }
        await Promise.all([loadHistory(), loadWalkAnalytics()]);
        setStatus('Route deleted.');
      } catch (error) {
        setStatus(`Error: ${error.message}`, true);
      }
    });

    const actions = document.createElement('div');
    actions.className = 'history-actions';
    actions.appendChild(selectBtn);
    actions.appendChild(renameBtn);
    actions.appendChild(deleteBtn);

    li.appendChild(actions);
    historyListEl.appendChild(li);
  });
}

async function loadHistory() {
  const response = await fetch('/api/me/routes', { credentials: 'same-origin' });
  if (!response.ok) {
    renderHistory([]);
    return;
  }
  const data = await response.json();
  renderHistory(data.routes || []);
}

function clearSessionDetails() {
  if (sessionsRouteLayer && sessionsMap) {
    sessionsMap.removeLayer(sessionsRouteLayer);
    sessionsRouteLayer = null;
  }
  sessionStatsEl.hidden = true;
  ssTimeEl.textContent = '00:00:00';
  ssKmEl.textContent = '0.00';
  ssStepsEl.textContent = '0';
  ssStartedEl.textContent = '-';
  ssEndedEl.textContent = '-';
}

function renderSessionDetails(session) {
  setActiveTab('sessions');
  ensureSessionsMapInitialized();
  sessionsMap.invalidateSize();
  clearSessionDetails();

  if (session.route_geojson) {
    sessionsRouteLayer = L.geoJSON(session.route_geojson, {
      style: { color: '#0a7ea4', weight: 5 },
    }).addTo(sessionsMap);
    sessionsMap.fitBounds(sessionsRouteLayer.getBounds(), { padding: [20, 20] });
  } else {
    setStatus('This session has no route geometry to display.', true);
  }

  sessionStatsEl.hidden = false;
  ssTimeEl.textContent = formatDuration((Number(session.elapsed_seconds) || 0) * 1000);
  ssKmEl.textContent = Number(session.distance_km || 0).toFixed(2);
  ssStepsEl.textContent = `${session.steps || 0}`;
  ssStartedEl.textContent = session.started_at ? new Date(`${session.started_at}Z`).toLocaleString() : '-';
  ssEndedEl.textContent = new Date(`${session.ended_at}Z`).toLocaleString();
}

function renderSameRouteSessions() {
  if (!sameRouteSessionsListEl || !sameRouteSessionsEmptyEl) {
    return;
  }

  sameRouteSessionsListEl.innerHTML = '';
  if (!currentRouteId) {
    sameRouteSessionsEmptyEl.hidden = false;
    sameRouteSessionsEmptyEl.textContent = 'Select a route to view past sessions.';
    return;
  }

  const routeSessions = allWalkSessions.filter(
    (session) => Number(session.route_session_id || 0) === Number(currentRouteId),
  );

  if (routeSessions.length === 0) {
    sameRouteSessionsEmptyEl.hidden = false;
    sameRouteSessionsEmptyEl.textContent = 'No past sessions for this route yet.';
    return;
  }

  sameRouteSessionsEmptyEl.hidden = true;
  routeSessions.forEach((session) => {
    const ended = new Date(`${session.ended_at}Z`);
    const li = document.createElement('li');
    li.className = 'history-item';
    li.innerHTML = `
      <p><strong>${session.route_name || `Route ${session.route_session_id || '-'}`}</strong></p>
      <p>${Number(session.distance_km || 0).toFixed(2)} km | ${formatDuration((Number(session.elapsed_seconds) || 0) * 1000)} | ${session.steps || 0} steps</p>
      <p>Ended: ${ended.toLocaleString()}</p>
    `;
    sameRouteSessionsListEl.appendChild(li);
  });
}

function renderSessions(sessions) {
  allWalkSessions = Array.isArray(sessions) ? sessions : [];
  sessionsListEl.innerHTML = '';
  if (!sessions || sessions.length === 0) {
    sessionsEmptyEl.hidden = false;
    clearSessionDetails();
    renderSameRouteSessions();
    return;
  }
  sessionsEmptyEl.hidden = true;

  let lastDateLabel = '';
  sessions.forEach((session) => {
    const ended = new Date(`${session.ended_at}Z`);
    const dateLabel = ended.toLocaleDateString();
    if (dateLabel !== lastDateLabel) {
      const divider = document.createElement('li');
      divider.className = 'session-date-divider';
      divider.textContent = dateLabel;
      sessionsListEl.appendChild(divider);
      lastDateLabel = dateLabel;
    }

    const li = document.createElement('li');
    li.className = 'history-item';
    li.innerHTML = `
      <p><strong>${session.route_name || `Route ${session.route_session_id || '-'}`}</strong></p>
      <p>${Number(session.distance_km || 0).toFixed(2)} km | ${formatDuration((Number(session.elapsed_seconds) || 0) * 1000)} | ${session.steps || 0} steps</p>
      <p>Ended: ${ended.toLocaleString()}</p>
    `;

    const showBtn = document.createElement('button');
    showBtn.type = 'button';
    showBtn.className = 'small';
    showBtn.textContent = 'Show';
    showBtn.addEventListener('click', async () => {
      try {
        const response = await fetch(`/api/me/walk-sessions/${session.id}`, { credentials: 'same-origin' });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || 'Could not load session');
        }
        renderSessionDetails(data.session);
      } catch (error) {
        setStatus(`Error: ${error.message}`, true);
      }
    });

    const deleteBtn = document.createElement('button');
    deleteBtn.type = 'button';
    deleteBtn.className = 'ghost small';
    deleteBtn.textContent = 'Delete';
    deleteBtn.addEventListener('click', async () => {
      const ok = window.confirm('Delete this session?');
      if (!ok) {
        return;
      }
      try {
        const response = await fetch(`/api/me/walk-sessions/${session.id}`, {
          method: 'DELETE',
          credentials: 'same-origin',
        });
        const data = await response.json().catch(() => ({}));
        if (!response.ok) {
          throw new Error(data.detail || 'Could not delete session');
        }
        await Promise.all([loadSessions(), loadWalkAnalytics()]);
        setStatus('Session deleted.');
      } catch (error) {
        setStatus(`Error: ${error.message}`, true);
      }
    });

    const actions = document.createElement('div');
    actions.className = 'history-actions';
    actions.appendChild(showBtn);
    actions.appendChild(deleteBtn);
    li.appendChild(actions);
    sessionsListEl.appendChild(li);
  });
  renderSameRouteSessions();
}

async function loadSessions() {
  const response = await fetch('/api/me/walk-sessions', { credentials: 'same-origin' });
  if (!response.ok) {
    renderSessions([]);
    return;
  }
  const data = await response.json().catch(() => ({}));
  renderSessions(data.sessions || []);
}

async function loadAuthState() {
  const response = await fetch('/api/auth/me', { credentials: 'same-origin' });
  const data = await response.json();

  if (!data.authenticated) {
    currentUser = null;
    showWelcome();
    return;
  }

  currentUser = data.user;
  showApp();
  await Promise.all([loadHistory(), loadSessions(), loadWalkAnalytics()]);
}

function renderWalkAnalytics(data) {
  currentAnalyticsOverview = data;
  if (!analyticsOverviewEl) {
    return;
  }

  analyticsOffsets = {
    day: Number(data?.day?.offset || 0),
    week: Number(data?.week?.offset || 0),
    month: Number(data?.month?.offset || 0),
  };

  analyticsOverviewEl.innerHTML = '';
  if (currentSummaryPeriod === 'week') {
    analyticsOverviewEl.appendChild(renderAnalyticsOverviewCard('week', 'Week', data.week || {}));
  } else if (currentSummaryPeriod === 'month') {
    analyticsOverviewEl.appendChild(renderAnalyticsOverviewCard('month', 'Month', data.month || {}));
  } else {
    analyticsOverviewEl.appendChild(renderAnalyticsOverviewCard('day', 'Day', data.day || {}));
  }
  updateSummaryToggleButtons();
  renderAnalyticsCharts(data);
}

async function loadWalkAnalytics() {
  if (!currentUser) {
    return;
  }
  const params = new URLSearchParams({
    day_offset: String(analyticsOffsets.day || 0),
    week_offset: String(analyticsOffsets.week || 0),
    month_offset: String(analyticsOffsets.month || 0),
  });
  const response = await fetch(`/api/me/walk-analytics-overview?${params.toString()}`, {
    credentials: 'same-origin',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'Failed to load analytics');
  }
  renderWalkAnalytics(data);
}

async function authAction(action) {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;

  if (!email || !password) {
    setAuthMessage('Please enter email and password.', true);
    return;
  }

  const response = await fetch(`/api/auth/${action}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ email, password }),
  });
  const data = await response.json().catch(() => ({}));

  if (!response.ok) {
    throw new Error(data.detail || `${action} failed (HTTP ${response.status})`);
  }

  if (data.user) {
    currentUser = data.user;
    showApp();
    await loadHistory();
    return;
  }

  await loadAuthState();
}

async function resetPasswordAction() {
  const email = document.getElementById('auth-email').value.trim();
  const password = document.getElementById('auth-password').value;

  if (!email || !password) {
    setAuthMessage('Please enter email and new password.', true);
    return;
  }

  const response = await fetch('/api/auth/reset-password', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    credentials: 'same-origin',
    body: JSON.stringify({ email, password }),
  });

  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data.detail || 'Password reset failed');
  }

  setAuthMessage('Password reset successful. You can now log in.', false);
}

form.addEventListener('submit', async (event) => {
  event.preventDefault();
  try {
    await generateRouteNow();
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
});

saveRouteBtn.addEventListener('click', async () => {
  if (!generatedRoute) {
    setStatus('Generate a route first.', true);
    return;
  }
  try {
    const response = await fetch('/api/me/routes/save', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'same-origin',
      body: JSON.stringify({
        ...generatedRoute,
        route_name: routeNameEl.value.trim() || null,
      }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(data.detail || 'Could not save route');
    }
    generatedRoute = null;
    generatedActionsEl.hidden = true;
    await loadHistory();
    setStatus(`Route saved as ${routeNameEl.value.trim() || `Route ${data.id}`}.`);
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
});

newRouteBtn.addEventListener('click', async () => {
  const previousGeojson = generatedRoute?.route_geojson || routeLayer?.toGeoJSON?.() || null;
  try {
    await generateRouteNow(previousGeojson);
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
});

registerBtn.addEventListener('click', async () => {
  try {
    await authAction('register');
  } catch (error) {
    setAuthMessage(`Error: ${error.message}`, true);
  }
});

loginBtn.addEventListener('click', async () => {
  try {
    await authAction('login');
  } catch (error) {
    setAuthMessage(`Error: ${error.message}`, true);
  }
});

resetBtn?.addEventListener('click', async () => {
  try {
    await resetPasswordAction();
  } catch (error) {
    setAuthMessage(`Error: ${error.message}`, true);
  }
});

logoutBtn.addEventListener('click', async () => {
  try {
    await fetch('/api/auth/logout', {
      method: 'POST',
      credentials: 'same-origin',
    });
    currentUser = null;
    renderHistory([]);
    showWelcome();
  } catch (error) {
    setStatus(`Error: ${error.message}`, true);
  }
});


if (tabGenerateBtn && tabGenerateEl && tabRoutesEl && tabSessionsEl && tabAnalyticsEl) {
  tabGenerateBtn.addEventListener('click', () => setActiveTab('generate'));
  tabRoutesBtn.addEventListener('click', () => setActiveTab('routes'));
  tabSessionsBtn.addEventListener('click', () => setActiveTab('sessions'));
  tabAnalyticsBtn.addEventListener('click', () => setActiveTab('analytics'));
}

if (analyticsMetricSelectEl) {
  analyticsMetricSelectEl.addEventListener('change', () => {
    if (currentAnalyticsOverview) {
      renderAnalyticsCharts(currentAnalyticsOverview);
    }
  });
}

if (summaryDailyBtn) {
  summaryDailyBtn.addEventListener('click', () => {
    currentSummaryPeriod = 'day';
    if (currentAnalyticsOverview) {
      renderWalkAnalytics(currentAnalyticsOverview);
    }
  });
}

if (summaryWeeklyBtn) {
  summaryWeeklyBtn.addEventListener('click', () => {
    currentSummaryPeriod = 'week';
    if (currentAnalyticsOverview) {
      renderWalkAnalytics(currentAnalyticsOverview);
    }
  });
}

if (summaryMonthlyBtn) {
  summaryMonthlyBtn.addEventListener('click', () => {
    currentSummaryPeriod = 'month';
    if (currentAnalyticsOverview) {
      renderWalkAnalytics(currentAnalyticsOverview);
    }
  });
}

if (analyticsOverviewEl) {
  analyticsOverviewEl.addEventListener('click', async (event) => {
    const btn = event.target.closest('.analytics-shift-btn');
    if (!btn) {
      return;
    }
    const period = btn.dataset.period;
    const delta = Number(btn.dataset.delta || 0);
    if (!period || !Object.prototype.hasOwnProperty.call(analyticsOffsets, period) || Number.isNaN(delta)) {
      return;
    }
    const nextOffset = Math.max(0, Number(analyticsOffsets[period]) + delta);
    if (nextOffset === analyticsOffsets[period]) {
      return;
    }
    analyticsOffsets[period] = nextOffset;
    try {
      await loadWalkAnalytics();
    } catch (error) {
      analyticsOffsets[period] = Math.max(0, analyticsOffsets[period] - delta);
      setStatus(`Error: ${error.message}`, true);
    }
  });
}

timerStartBtn.addEventListener('click', () => {
  startWalkTimer();
});

timerPauseBtn.addEventListener('click', () => {
  pauseWalkTimer();
});

timerEndBtn.addEventListener('click', () => {
  endWalkTimer();
});

loadAuthState();
