// Netzwerk-/API-Layer der Kartenseite: alle fetch()-Aufrufe, WebSocket/SSE,
// Live-Transport-Fallback, Polling, Ladefortschritts-UI und der lokale
// Browser-Mirror (Dexie). Rendert empfangene Daten über layers.js.
import { state, MAP_CONFIG, RANGE_MINUTES, MAP_PAGE_SIZE_SAFE_MAX, timelinePreviewCache } from './state.js';
import {
  fetchWithRetry, storageGet, storageSet, scheduleTask, supportsAbortController, formatBytes, formatEta,
} from '../map-page-utils.js';
import { renderMapPayload, applyMapDelta, updateStatistics, renderLog, renderProcessingStatus } from './layers.js';

const supportsTextDecoder = typeof window.TextDecoder === 'function';
const supportsTextEncoder = typeof window.TextEncoder === 'function';

const FILTER_DEBOUNCE = 300;

  const LOCAL_MIRROR_MAX_POINTS = 50000;
  const LOCAL_MIRROR_MAX_AGE_MS = 14 * 24 * 60 * 60 * 1000;
  try {
    if (typeof window.Dexie === 'function' && typeof window.indexedDB !== 'undefined') {
      state.db = new Dexie('MapReceiverDB');
      state.db.version(1).stores({
        points: 'id, timestampUtc, sessionId'
      });
      // Version 2 mit zusammengesetztem Index für schnellere Filterung
      state.db.version(2).stores({
        points: 'id, timestampUtc, sessionId, [sessionId+timestampUtc]'
      });
      // Version 3 keeps the browser mirror bounded; old points are pruned
      // opportunistically after successful writes.
      state.db.version(3).stores({
        points: 'id, timestampUtc, sessionId, [sessionId+timestampUtc]'
      });
      state.localMirrorAvailable = true;
    }
  } catch (error) {
    console.warn('Lokaler Browser-Mirror deaktiviert:', error);
    state.db = null;
    state.localMirrorAvailable = false;
  }


  export async function pruneLocalMirror() {
    if (!state.localMirrorAvailable || !state.db || state.localMirrorPruneInFlight) return;
    state.localMirrorPruneInFlight = true;
    try {
      const cutoff = new Date(Date.now() - LOCAL_MIRROR_MAX_AGE_MS).toISOString();
      await state.db.points.where('timestampUtc').below(cutoff).delete();
      const overflowIds = await state.db.points.orderBy('timestampUtc').reverse()
        .offset(LOCAL_MIRROR_MAX_POINTS).primaryKeys();
      if (overflowIds.length) await state.db.points.bulkDelete(overflowIds);
    } catch (error) {
      console.warn('Lokaler Browser-Mirror konnte nicht bereinigt werden:', error);
    } finally {
      state.localMirrorPruneInFlight = false;
      void updateLocalMirrorStatus();
    }
  }


  export async function updateLocalMirrorStatus() {
    const countEl = document.getElementById('local-mirror-count');
    const storageEl = document.getElementById('local-mirror-storage');
    const statusEl = document.getElementById('local-mirror-status');
    const clearBtn = document.getElementById('local-mirror-clear-btn');
    if (!countEl || !statusEl || !clearBtn) return;
    const formatStorageBytes = (bytes) => {
      if (!Number.isFinite(bytes) || bytes < 0) return null;
      if (bytes < 1024) return `${Math.round(bytes)} B`;
      const units = ['KiB', 'MiB', 'GiB', 'TiB'];
      let value = bytes;
      let unit = 'B';
      for (const nextUnit of units) {
        value /= 1024;
        unit = nextUnit;
        if (value < 1024 || nextUnit === units[units.length - 1]) break;
      }
      return `${value.toLocaleString('de-DE', { maximumFractionDigits: value >= 100 ? 0 : 1 })} ${unit}`;
    };
    const updateStorageEstimate = async () => {
      if (!storageEl) return;
      try {
        const estimate = navigator.storage && typeof navigator.storage.estimate === 'function'
          ? await navigator.storage.estimate()
          : null;
        const used = formatStorageBytes(estimate && estimate.usage);
        const quota = formatStorageBytes(estimate && estimate.quota);
        storageEl.textContent = used && quota ? `Speicher: ~${used} / ~${quota}` : 'Speicher: nicht verfügbar';
      } catch (error) {
        storageEl.textContent = 'Speicher: nicht verfügbar';
        console.warn('Browser-Speicherbelegung konnte nicht gelesen werden:', error);
      }
    };
    if (!state.localMirrorAvailable || !state.db) {
      countEl.textContent = 'nicht verfügbar';
      if (storageEl) storageEl.textContent = 'Speicher: nicht verfügbar';
      statusEl.textContent = 'Lokaler Kartenspeicher ist in diesem Browser nicht verfügbar.';
      clearBtn.disabled = true;
      return;
    }
    try {
      const count = await state.db.points.count();
      countEl.textContent = count.toLocaleString('de-DE');
      statusEl.textContent = `${count.toLocaleString('de-DE')} Punkte lokal gespeichert (max. ${LOCAL_MIRROR_MAX_POINTS.toLocaleString('de-DE')}, 14 Tage).`;
      clearBtn.disabled = state.localMirrorClearInFlight || count === 0;
      void updateStorageEstimate();
    } catch (error) {
      countEl.textContent = 'unbekannt';
      if (storageEl) storageEl.textContent = 'Speicher: nicht verfügbar';
      statusEl.textContent = 'Status des lokalen Kartenspeichers konnte nicht gelesen werden.';
      clearBtn.disabled = true;
      console.warn('Status des lokalen Kartenspeichers konnte nicht gelesen werden:', error);
    }
  }


  export async function clearLocalMirror() {
    if (!state.localMirrorAvailable || !state.db || state.localMirrorClearInFlight) return;
    state.localMirrorClearInFlight = true;
    const clearBtn = document.getElementById('local-mirror-clear-btn');
    const statusEl = document.getElementById('local-mirror-status');
    if (clearBtn) {
      clearBtn.disabled = true;
      clearBtn.setAttribute('aria-busy', 'true');
    }
    if (statusEl) statusEl.textContent = 'Lokaler Kartenspeicher wird geleert…';
    try {
      await state.db.points.clear();
      timelinePreviewCache.clear();
      if (statusEl) statusEl.textContent = 'Lokaler Kartenspeicher wurde geleert.';
      showToast('Lokaler Kartenspeicher geleert.', 'success');
    } catch (error) {
      if (statusEl) statusEl.textContent = 'Lokaler Kartenspeicher konnte nicht geleert werden.';
      showToast('Lokaler Kartenspeicher konnte nicht geleert werden.', 'error');
      console.warn('Lokaler Kartenspeicher konnte nicht geleert werden:', error);
    } finally {
      state.localMirrorClearInFlight = false;
      if (clearBtn) clearBtn.removeAttribute('aria-busy');
      void updateLocalMirrorStatus();
    }
  }


  export async function savePointsLocally(points) {
    if (!state.localMirrorAvailable || !state.db || !points || !points.length) return;
    try {
      // Transformation für lokales Speicherformat falls nötig
      const toSave = points.map(p => ({
        id: p.id,
        lat: p.lat,
        lon: p.lon,
        timestampUtc: p.timestampUtc || p.point_timestamp_utc,
        timestampLocal: p.timestampLocal,
        accuracyM: p.accuracyM,
        source: p.source,
        sessionId: p.session_id || p.sessionId,
        cachedAt: Date.now()
      }));
      await state.db.points.bulkPut(toSave);
      void pruneLocalMirror();
      void updateLocalMirrorStatus();
    } catch (error) {
      console.warn('Fehler beim lokalen Speichern:', error);
    }
  }


  export async function getLocalPoints(filters) {
    if (!state.localMirrorAvailable || !state.db) return [];
    try {
      let collection;
      if (filters.session_id && filters.date_from) {
        collection = state.db.points.where('[sessionId+timestampUtc]').between([filters.session_id, filters.date_from], [filters.session_id, '\uffff']);
      } else if (filters.session_id) {
        collection = state.db.points.where('sessionId').equals(filters.session_id);
      } else if (filters.date_from) {
        collection = state.db.points.where('timestampUtc').aboveOrEqual(filters.date_from);
      } else {
        collection = state.db.points.toCollection();
      }

      let items = await collection.reverse().limit(10000).toArray();

      if (filters.date_to) items = items.filter(item => String(item.timestampUtc || '') <= filters.date_to);
      if (filters.bbox) {
        const parts = String(filters.bbox).split(',').map(Number);
        if (parts.length === 4 && parts.every(Number.isFinite)) {
          const [minLon, minLat, maxLon, maxLat] = parts;
          items = items.filter(item =>
            Number(item.lon) >= minLon &&
            Number(item.lon) <= maxLon &&
            Number(item.lat) >= minLat &&
            Number(item.lat) <= maxLat
          );
        }
      }
      return items.sort((a, b) => String(b.timestampUtc || '').localeCompare(String(a.timestampUtc || '')));
    } catch (error) {
      console.warn('Fehler beim Abrufen lokaler Daten:', error);
      return [];
    }
  }


  export function isShiftSignificant(newBbox, newZoom) {
    if (!state.lastFetchedBbox || state.lastFetchedZoom === null) return true;
    if (Math.abs(newZoom - state.lastFetchedZoom) > 0.7) return true;

    const b1 = state.lastFetchedBbox.split(',').map(Number);
    const b2 = newBbox.split(',').map(Number);
    const w1 = Math.abs(b1[2] - b1[0]);
    const h1 = Math.abs(b1[3] - b1[1]);
    const dx = Math.abs(b1[0] - b2[0]);
    const dy = Math.abs(b1[1] - b2[1]);

    return dx > w1 * 0.25 || dy > h1 * 0.25;
  }
  const LOADING_OVERLAY_DELAY_MS = 120;
  const LOADING_OVERLAY_PULSE_MS = 180;
  const META_REFRESH_MIN_MS = 30000;




  export async function focusLatestPoint() {
    let latest = (state.lastMapPayload && state.lastMapPayload.layers && state.lastMapPayload.layers.latestPoint)
      || (state.lastMapPayload && state.lastMapPayload.layers && state.lastMapPayload.layers.points && state.lastMapPayload.layers.points.find(p => p.isLatest));
    
    if (!latest) {
      try {
        const response = await fetchWithRetry('/api/points?page_size=1', { credentials: 'same-origin' });
        if (response.ok) {
          const data = await response.json();
          const point = data && data.points && data.points.items ? data.points.items[0] : null;
          if (point) latest = { lat: point.latitude, lon: point.longitude };
        }
      } catch (error) { console.error('Fokus-Fetch fehlgeschlagen:', error); }
    }

    if (latest && state.map) {
      state.map.flyTo({ center: [latest.lon, latest.lat], zoom: 17, speed: 1.2, essential: true });
    } else {
      showToast('Kein aktueller Punkt gefunden.', 'error');
    }
  }


  export async function focusInitialGlobalLatestPoint(fallback = null) {
    if ((!state.forceGlobalLatestFocus && state.initialGlobalLatestFocusDone) || !state.map) return;
    state.initialGlobalLatestFocusDone = true;
    state.forceGlobalLatestFocus = false;
    let latest = fallback;
    try {
      const response = await fetchWithRetry('/api/points?page_size=1', { credentials: 'same-origin' });
      if (response.ok) {
        const data = await response.json();
        const point = data && data.points && data.points.items ? data.points.items[0] : null;
        if (point) latest = { lat: point.latitude, lon: point.longitude };
      }
    } catch (error) {
      console.warn('Initialer Global-Fokus fehlgeschlagen:', error);
    }
    if (latest && state.map) {
      state.suppressedViewportRefreshes += 1;
      state.suppressMapFocusUntil = Date.now() + 2500;
      state.map.flyTo({ center: [latest.lon, latest.lat], zoom: 16, speed: 1.0, essential: true });
    }
  }


  export function debounce(fn, ms) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), ms);
    };
  }


  export function clampMapMaxPoints(value) {
    const serverMax = MAP_CONFIG.pointsPageSizeMax || 2000;
    const effectiveMax = Math.max(1, Math.min(serverMax, MAP_PAGE_SIZE_SAFE_MAX));
    return Math.max(1, Math.min(effectiveMax, parseInt(value || effectiveMax, 10) || effectiveMax));
  }


  export function clampLogLimit(value) {
    const effectiveMax = Math.max(1, state.MAP_MAX_POINTS);
    return Math.max(1, Math.min(effectiveMax, parseInt(value || effectiveMax, 10) || effectiveMax));
  }


  export function getRangeBucketMs() {
    const rangeMinutes = RANGE_MINUTES[state.TIME_RANGE] || 0;
    if (rangeMinutes <= 15) return 5000;
    if (rangeMinutes <= 180) return 15000;
    return 60000;
  }


  export function buildDateFromIso(nowMs = Date.now()) {
    const rangeMinutes = RANGE_MINUTES[state.TIME_RANGE];
    if (!rangeMinutes) return null;
    const bucketMs = getRangeBucketMs();
    const bucketedNowMs = Math.floor(nowMs / bucketMs) * bucketMs;
    return new Date(bucketedNowMs - rangeMinutes * 60000).toISOString();
  }


  export function scheduleNextMapUpdate(delay = state.POLLING_INTERVAL) {
    clearTimeout(state.updateTimer);
    if (state.liveTransport !== 'polling') {
      state.updateTimer = null;
      state.nextRefreshTime = 0;
      return;
    }
    if (document.hidden) {
      state.nextRefreshTime = 0;
      return;
    }
    if (!Number.isFinite(delay) || delay <= 0) return;
    state.nextRefreshTime = Date.now() + delay;
    state.updateTimer = setTimeout(() => {
      updateMap();
    }, delay);
  }


  export function getViewportBbox() {
    if (!state.map) return null;
    const bounds = state.map.getBounds();
    const southWest = bounds.getSouthWest();
    const northEast = bounds.getNorthEast();
    return `${southWest.lng.toFixed(6)},${southWest.lat.toFixed(6)},${northEast.lng.toFixed(6)},${northEast.lat.toFixed(6)}`;
  }


  export function normalizeMapZoom() {
    const currentZoom = state.map ? state.map.getZoom() : 10;
    const roundedZoom = Number.isFinite(currentZoom) ? Math.round(currentZoom) : 10;
    return Math.max(1, Math.min(22, roundedZoom));
  }


  export function buildCurrentFilters() {
    const sessionActive = document.getElementById('session-filter-toggle').checked;
    const importActive = document.getElementById('import-filter-toggle').checked;
    const sessionId = sessionActive
      ? document.getElementById('session-select-dropdown').value
      : importActive
        ? document.getElementById('import-select-dropdown').value
        : '';
    const params = new URLSearchParams();
    params.set('log_limit', String(clampLogLimit(document.getElementById('log-limit').value)));
    params.set('zoom', String(normalizeMapZoom()));
    params.set('route_time_gap_min', String(state.ROUTE_TIME_GAP));
    params.set('route_dist_gap_m', String(state.ROUTE_DIST_GAP));
    params.set('stop_min_duration_min', String(state.STOP_MIN_DUR));
    params.set('stop_radius_m', String(state.STOP_RADIUS_M));
    params.set('include_points', state.pointsActive ? 'true' : 'false');
    params.set('include_heatmap', state.heatmapActive ? 'true' : 'false');
    params.set('include_polyline', state.polylineActive ? 'true' : 'false');
    params.set('include_accuracy', state.accuracyActive ? 'true' : 'false');
    params.set('include_labels', state.labelsActive ? 'true' : 'false');
    params.set('include_speed', state.speedActive ? 'true' : 'false');
    params.set('include_stops', state.stopsActive ? 'true' : 'false');
    params.set('include_daytrack', state.daytrackActive ? 'true' : 'false');
    params.set('include_snap', state.snapActive ? 'true' : 'false');
    const bbox = getViewportBbox();
    if (bbox) {
      params.set('bbox', bbox);
    } else {
      params.set('page_size', clampMapMaxPoints(document.getElementById('map-max-points').value));
    }
    if (sessionId) params.set('session_id', sessionId);
    if (state.TIME_RANGE !== 'all') params.set('date_from', buildDateFromIso());
    return params;
  }


  export function buildCurrentFilterState() {
    const sessionActive = document.getElementById('session-filter-toggle').checked;
    const importActive = document.getElementById('import-filter-toggle').checked;
    const sessionId = sessionActive
      ? document.getElementById('session-select-dropdown').value
      : importActive
        ? document.getElementById('import-select-dropdown').value
        : '';
    return {
      session_id: sessionId || null,
      date_from: state.TIME_RANGE !== 'all' ? buildDateFromIso() : null,
      date_to: null,
      bbox: getViewportBbox()
    };
  }


  export function buildGeoJsonExportUrl() {
    const params = buildCurrentFilters();
    params.delete('zoom');
    params.delete('route_time_gap_min');
    params.delete('route_dist_gap_m');
    params.delete('stop_min_duration_min');
    params.delete('stop_radius_m');
    params.delete('include_points');
    params.delete('include_heatmap');
    params.delete('include_polyline');
    params.delete('include_accuracy');
    params.delete('include_labels');
    params.delete('include_speed');
    params.delete('include_stops');
    params.delete('include_daytrack');
    params.delete('include_snap');
    return `/api/points?${params.toString()}`;
  }


  export function buildMetaFilters() {
    const sessionActive = document.getElementById('session-filter-toggle').checked;
    const importActive = document.getElementById('import-filter-toggle').checked;
    const sessionId = sessionActive
      ? document.getElementById('session-select-dropdown').value
      : importActive
        ? document.getElementById('import-select-dropdown').value
        : '';
    const params = new URLSearchParams();
    if (sessionId) params.set('session_id', sessionId);
    if (state.TIME_RANGE !== 'all') params.set('date_from', buildDateFromIso());
    return params;
  }


  export async function updateMapMeta(options = {}) {
    const force = !!options.force;
    const params = buildMetaFilters();
    const queryKey = params.toString();
    const now = Date.now();
    if (
      !force &&
      state.lastMetaPayload &&
      state.lastMetaQueryKey === queryKey &&
      (now - state.lastMetaFetchedAtMs) < META_REFRESH_MIN_MS
    ) {
      renderProcessingStatus(state.lastMetaPayload.processing || null);
      return state.lastMetaPayload;
    }
    const url = `/api/map-meta?${params.toString()}`;
    const headers = state.lastMetaEtag ? { 'If-None-Match': state.lastMetaEtag } : {};
    if (state.currentMetaFetchController && typeof state.currentMetaFetchController.abort === 'function') state.currentMetaFetchController.abort();
    state.currentMetaFetchController = supportsAbortController ? new AbortController() : null;
    const fetchOptions = { credentials: 'same-origin', headers };
    if (state.currentMetaFetchController) fetchOptions.signal = state.currentMetaFetchController.signal;
    const response = await fetchWithRetry(url, fetchOptions);
    if (response.status === 304 && state.lastMetaPayload) {
      state.lastMetaQueryKey = queryKey;
      state.lastMetaFetchedAtMs = now;
      renderProcessingStatus(state.lastMetaPayload.processing || null);
      return state.lastMetaPayload;
    }
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.lastMetaEtag = response.headers.get('etag') || null;
    const payload = await response.json();
    state.lastMetaPayload = payload;
    state.lastMetaQueryKey = queryKey;
    state.lastMetaFetchedAtMs = now;
    renderProcessingStatus(payload.processing || null);
    return payload;
  }


  export async function exportGeoJSON() {
    try {
      const response = await fetchWithRetry(buildGeoJsonExportUrl(), { credentials: 'same-origin' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const payload = await response.json();
      const exportItems = payload && payload.points && payload.points.items ? payload.points.items : [];
      const features = exportItems.map(point => ({
        type: 'Feature',
        geometry: { type: 'Point', coordinates: [point.longitude, point.latitude] },
        properties: {
          id: point.id,
          request_id: point.request_id,
          received_at_utc: point.received_at_utc,
          sent_at_utc: point.sent_at_utc,
          point_timestamp_utc: point.point_timestamp_utc,
          point_timestamp_local: point.point_timestamp_local,
          point_date_local: point.point_date_local,
          point_time_local: point.point_time_local,
          horizontal_accuracy_m: point.horizontal_accuracy_m,
          session_id: point.session_id,
          source: point.source,
          capture_mode: point.capture_mode
        }
      }));
      const blob = new Blob([JSON.stringify({ type: 'FeatureCollection', features }, null, 2)], { type: 'application/geo+json' });
      const url = URL.createObjectURL(blob);
      const anchor = document.createElement('a');
      anchor.href = url;
      anchor.download = `lh2gpx-map-${new Date().toISOString().slice(0, 10)}.geojson`;
      document.body.appendChild(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(url);
      showToast(`${features.length.toLocaleString('de-DE')} Punkte exportiert.`, 'success', 3000);
    } catch (error) {
      if (error.name === 'AbortError') return;
      console.warn('GeoJSON-Export fehlgeschlagen:', error);
      showToast('GeoJSON-Export fehlgeschlagen. Bitte erneut versuchen.', 'error');
    }
  }


  export function updateTraffic(bytes, mbps) {
    document.getElementById('mbar-mbps').textContent = mbps.toFixed(2);
    const today = new Date().toISOString().slice(0, 10);
    const storedDate = storageGet('map-traffic-date');
    let dailyBytes = storedDate === today ? (parseInt(storageGet('map-traffic-bytes'), 10) || 0) : 0;
    dailyBytes += bytes;
    storageSet('map-traffic-date', today);
    storageSet('map-traffic-bytes', String(dailyBytes));
    const mb = dailyBytes / 1024 / 1024;
    document.getElementById('mbar-daily').textContent = mb >= 1 ? `${mb.toFixed(1)} MB` : `${(dailyBytes / 1024).toFixed(0)} KB`;
  }


  export function tickRefreshBar() {
    if (!state.lastRefreshTime) return;
    const now = Date.now();
    const agoSec = Math.round((now - state.lastRefreshTime) / 1000);
    const remMs = state.nextRefreshTime ? Math.max(0, state.nextRefreshTime - now) : null;
    const remSec = remMs !== null ? Math.ceil(remMs / 1000) : null;
    document.getElementById('mbar-ago').textContent = agoSec === 0 ? 'gerade eben' : `vor ${agoSec}s`;
    document.getElementById('mbar-next').textContent = remSec !== null ? (remSec <= 0 ? 'jetzt…' : `in ${remSec}s`) : '—';
    const pct = (remMs !== null && state.POLLING_INTERVAL > 0) ? Math.max(0, Math.min(100, 100 - (remMs / state.POLLING_INTERVAL * 100))) : 0;
    document.getElementById('mbar-progress').style.width = `${pct}%`;
  }


  export function getLoadingUi() {
    return {
      overlay: document.getElementById('map-loading-overlay'),
      card: document.getElementById('map-loading-card'),
      title: document.getElementById('map-loading-title'),
      stage: document.getElementById('map-loading-stage'),
      mode: document.getElementById('map-loading-mode'),
      subtext: document.getElementById('map-loading-subtext'),
      detail: document.getElementById('map-loading-detail'),
      eta: document.getElementById('map-loading-eta'),
      phases: document.getElementById('map-loading-phases'),
      retry: document.getElementById('map-loading-retry'),
      metricLabel: document.getElementById('map-loading-metric-label'),
      bytes: document.getElementById('map-loading-bytes'),
      percent: document.getElementById('map-loading-percent'),
      bar: document.getElementById('map-loading-bar'),
      progress: document.getElementById('map-loading-track'),
      syncPill: document.getElementById('map-sync-pill'),
      syncPillText: document.getElementById('map-sync-pill-text'),
    };
  }


  export function parseServerTimingHeader(value) {
    if (!value) return [];
    return value.split(',').map(part => part.trim()).filter(Boolean).map(entry => {
      const segments = entry.split(';').map(part => part.trim()).filter(Boolean);
      const name = segments.shift() || '';
      const meta = { name, dur: null, desc: null };
      segments.forEach(segment => {
        const [key, rawValue = ''] = segment.split('=');
        const parsedValue = rawValue.replace(/^"|"$/g, '');
        if (key === 'dur') meta.dur = Number(parsedValue) || 0;
        if (key === 'desc') meta.desc = parsedValue;
      });
      return meta;
    });
  }


  export function formatServerTimingDetail(entries) {
    if (!entries || !entries.length) return 'Serverphasen werden vorbereitet…';
    const detail = [];
    const total = entries.find(entry => entry.name === 'total');
    if (total && total.dur) detail.push(`gesamt ${Math.round(total.dur)} ms`);
    const relevant = [
      ['latest_check', 'delta'],
      ['summary', 'meta'],
      ['counts', 'query'],
      ['heatmap', 'heatmap'],
      ['track_context', 'kontext'],
      ['track_layers', 'layer'],
      ['payload', 'payload'],
      ['serialize', 'json'],
    ];
    relevant.forEach(([key, label]) => {
      const match = entries.find(entry => entry.name === key && entry.dur && entry.dur >= 1);
      if (match) detail.push(`${label} ${Math.round(match.dur)} ms`);
    });
    const cache = entries.find(entry => entry.name === 'cache' && entry.desc);
    if (cache) detail.push(`cache ${cache.desc}`);
    return detail.join(' · ') || 'Serverphasen werden vorbereitet…';
  }


  export function setLoadingDetail(text) {
    const ui = getLoadingUi();
    if (!ui.detail) return;
    ui.detail.textContent = text || 'Serverphasen werden vorbereitet…';
  }


  export function updateLoadingPhaseChips(stage, entries = []) {
    const ui = getLoadingUi();
    if (!ui.phases) return;
    const phaseStates = {
      counts: false,
      track_layers: false,
      serialize: false,
      download: stage === 'download' || stage === 'parse' || stage === 'render',
      render: stage === 'render',
    };
    entries.forEach(entry => {
      if (entry.name in phaseStates && entry.dur !== null) phaseStates[entry.name] = 'done';
    });
    if (stage === 'connect') phaseStates.counts = true;
    if (stage === 'parse') phaseStates.serialize = true;
    Array.from(ui.phases.querySelectorAll('span')).forEach(chip => {
      const key = chip.dataset.phase;
      chip.classList.remove('is-active', 'is-done');
      if (phaseStates[key] === 'done') chip.classList.add('is-done');
      else if (phaseStates[key] === true) chip.classList.add('is-active');
    });
  }


  export function updateLoadingEta(percentValue) {
    const ui = getLoadingUi();
    if (!ui.eta) return;
    const ratio = Math.max(0, Math.min(0.999, (Number(percentValue) || 0) / 100));
    if (!state.loadingStartedAtMs || ratio <= 0.05) {
      ui.eta.textContent = 'ETA wird berechnet…';
      return;
    }
    const elapsedSeconds = Math.max(0.05, (Date.now() - state.loadingStartedAtMs) / 1000);
    const etaSeconds = (elapsedSeconds * (1 - ratio)) / ratio;
    ui.eta.textContent = `noch ca. ${formatEta(etaSeconds)}`;
  }


  export function getServerPhaseDurations(entries) {
    if (!entries || !entries.length) return { total: 0, completed: 0 };
    const orderedKeys = ['latest_check', 'counts', 'heatmap', 'track_context', 'track_layers', 'payload', 'serialize'];
    let completed = 0;
    orderedKeys.forEach(key => {
      const match = entries.find(entry => entry.name === key && entry.dur && entry.dur >= 0);
      if (match) completed += match.dur;
    });
    const total = entries.find(entry => entry.name === 'total' && entry.dur && entry.dur >= 0);
    return { total: total ? total.dur : completed, completed };
  }


  export function computeLoadingPercent(stage, loadedBytes = null, totalBytes = null, serverTiming = []) {
    const { total, completed } = getServerPhaseDurations(serverTiming);
    const safeLoaded = Number.isFinite(Number(loadedBytes)) ? Math.max(0, Number(loadedBytes)) : 0;
    const safeTotal = Number.isFinite(Number(totalBytes)) && Number(totalBytes) > 0 ? Number(totalBytes) : null;
    const serverBase = total > 0 ? Math.max(6, Math.min(58, 6 + (completed / total) * 52)) : 12;
    if (stage === 'connect') return Math.round(Math.max(4, Math.min(18, serverBase * 0.35)));
    if (stage === 'download') {
      if (!safeTotal) return Math.round(Math.max(16, Math.min(72, serverBase + (safeLoaded > 0 ? 10 : 0))));
      const ratio = Math.max(0, Math.min(1, safeLoaded / safeTotal));
      return Math.round(Math.max(18, Math.min(84, serverBase + ratio * (84 - serverBase))));
    }
    if (stage === 'parse') return Math.round(Math.max(86, Math.min(93, serverBase + 28)));
    if (stage === 'render') return Math.round(Math.max(94, Math.min(99, serverBase + 40)));
    return 0;
  }


  export function setLoadingProgress(ui, percent) {
    const safePercent = Math.max(0, Math.min(100, Number(percent) || 0));
    const roundedPercent = Math.round(safePercent);
    if (ui.percent) ui.percent.textContent = `${roundedPercent}%`;
    if (ui.progress) ui.progress.setAttribute('aria-valuenow', String(roundedPercent));
    if (ui.bar) ui.bar.style.width = `${safePercent}%`;
    return roundedPercent;
  }


  export function setLoadingStage(stage, subtext = null, options = {}) {
    const ui = getLoadingUi();
    if (!ui.card || !ui.stage || !ui.title || !ui.subtext || !ui.metricLabel || !ui.bytes || !ui.percent) return;
    const { loadedBytes = null, totalBytes = null, serverTiming = [] } = options;
    const stageMap = {
      connect: { label: 'Verbinden', title: 'Synchronisierung läuft', subtext: 'Verbindung wird aufgebaut…', color: '#0A84FF', metric: 'Gesamt' },
      download: { label: 'Download', title: 'Kartendaten werden geladen', subtext: 'Antwort wird heruntergeladen…', color: '#30D158', metric: 'Gesamt' },
      parse: { label: 'Parse', title: 'Antwort wird verarbeitet', subtext: 'JSON wird dekodiert…', color: '#FF9F0A', metric: 'Gesamt' },
      render: { label: 'Render', title: 'Ansicht wird aktualisiert', subtext: 'Layer und UI werden gerendert…', color: '#BF5AF2', metric: 'Gesamt' },
      error: { label: 'Fehler', title: 'Aktualisierung fehlgeschlagen', subtext: 'Kartendaten konnten nicht geladen werden.', color: '#FF453A', metric: 'Status', progress: null },
    };
    const current = stageMap[stage] || stageMap.connect;
    ui.card.dataset.stage = stage;
    ui.title.textContent = current.title;
    ui.subtext.textContent = subtext || current.subtext;
    ui.stage.textContent = current.label;
    ui.metricLabel.textContent = current.metric;
    ui.stage.style.color = current.color;
    ui.stage.style.background = `color-mix(in srgb, ${current.color} 14%, transparent)`;
    ui.stage.style.borderColor = `color-mix(in srgb, ${current.color} 28%, transparent)`;
    if (stage !== 'error') {
      const percent = computeLoadingPercent(stage, loadedBytes, totalBytes, serverTiming);
      setLoadingProgress(ui, percent);
      updateLoadingEta(percent);
    }
    if (ui.retry) ui.retry.style.display = stage === 'error' ? 'inline-flex' : 'none';
    if (stage === 'parse') {
      ui.bytes.textContent = 'Download abgeschlossen';
    } else if (stage === 'render') {
      ui.bytes.textContent = 'Daten übernommen';
    } else if (stage === 'error') {
      ui.bytes.textContent = 'Aktualisierung abgebrochen';
      ui.percent.textContent = '—';
      if (ui.bar) ui.bar.style.width = '0%';
      if (ui.progress) ui.progress.removeAttribute('aria-valuenow');
      if (ui.eta) ui.eta.textContent = 'ETA nicht verfügbar';
    }
    updateLoadingPhaseChips(stage, serverTiming);
  }


  export function setLoadingMode(text, color = '#64D2FF') {
    const ui = getLoadingUi();
    if (!ui.mode) return;
    ui.mode.textContent = text;
    ui.mode.style.color = color;
    ui.mode.style.background = `color-mix(in srgb, ${color} 14%, transparent)`;
    ui.mode.style.borderColor = `color-mix(in srgb, ${color} 28%, transparent)`;
  }


  export function syncLoadingOverlayState() {
    const wrap = document.getElementById('map-wrap');
    const ui = getLoadingUi();
    if (!wrap || !ui.overlay || !ui.card) return;
    const active = state.loadingOverlayShown && ui.overlay.style.display !== 'none';
    wrap.dataset.loadingVisible = active ? '1' : '0';
    const offset = active ? Math.ceil(ui.card.offsetHeight + 14) : 0;
    wrap.style.setProperty('--map-loading-control-offset', `${offset}px`);
  }


  export function showSyncPill(text, mode = 'info', durationMs = LOADING_OVERLAY_PULSE_MS) {
    const ui = getLoadingUi();
    if (!ui.syncPill || !ui.syncPillText) return;
    clearTimeout(state.loadingSyncPillTimer);
    ui.syncPillText.textContent = text;
    ui.syncPill.dataset.mode = mode;
    ui.syncPill.classList.add('is-visible');
    state.loadingSyncPillTimer = setTimeout(() => {
      ui.syncPill.classList.remove('is-visible');
    }, durationMs);
  }


  export function showToast(message, mode = 'error', durationMs = 5000) {
    const toast = document.getElementById('map-toast');
    const text = document.getElementById('map-toast-text');
    if (!toast || !text) {
      showSyncPill(message, mode, durationMs);
      return;
    }
    clearTimeout(state.mapToastTimer);
    text.textContent = message;
    toast.dataset.mode = mode;
    toast.hidden = false;
    state.mapToastTimer = setTimeout(() => { toast.hidden = true; }, durationMs);
  }


  export function showMapRecovery(error, phase = 'Initialisierung') {
    if (state.mapInitFailed) return;
    state.mapInitFailed = true;
    state.mapInitInProgress = false;
    state.mapReady = false;
    const recovery = document.getElementById('map-init-recovery');
    const message = document.getElementById('map-init-recovery-message');
    const detail = error && error.message ? String(error.message) : '';
    if (message) {
      message.textContent = detail
        ? `${phase} fehlgeschlagen. ${detail} Bitte erneut versuchen.`
        : `${phase} fehlgeschlagen. Bitte erneut versuchen.`;
    }
    if (recovery) recovery.hidden = false;
    const overlay = document.getElementById('map-loading-overlay');
    if (overlay) overlay.style.display = 'none';
    const retry = document.getElementById('map-init-recovery-retry');
    if (retry) retry.focus({ preventScroll: true });
    console.error(`MapLibre ${phase} fehlgeschlagen:`, error);
  }


  export function isFatalMapError(event) {
    if (!event || !event.error) return false;
    if (!state.mapReady) return true;
    const text = String(event.error.message || event.error).toLowerCase();
    return /webgl|context|render|style|source|layer|shader/.test(text);
  }


  export function wait(ms) {
    return new Promise(resolve => setTimeout(resolve, ms));
  }


  export function updateLoadingOverlay(loadedBytes, totalBytes = null, serverTiming = []) {
    const ui = getLoadingUi();
    if (!ui.subtext || !ui.bytes || !ui.percent || !ui.bar || !ui.card) return;

    const loaded = Math.max(0, Number(loadedBytes) || 0);
    const total = totalBytes !== null && Number.isFinite(Number(totalBytes)) && Number(totalBytes) > 0 ? Number(totalBytes) : null;

    ui.bytes.textContent = total ? `${formatBytes(loaded)} / ${formatBytes(total)}` : `${formatBytes(loaded)} geladen`;

    if (total) {
      ui.card.dataset.indeterminate = '0';
      const overallPercent = computeLoadingPercent('download', loaded, total, serverTiming);
      setLoadingProgress(ui, overallPercent);
      setLoadingStage('download', loaded >= total ? 'Download abgeschlossen, Daten werden übernommen…' : 'Antwort wird heruntergeladen…', { loadedBytes: loaded, totalBytes: total, serverTiming });
      ui.bar.style.opacity = '1';
      ui.bar.style.background = 'linear-gradient(90deg,#0A84FF 0%,#30D158 55%,#64D2FF 100%)';
      ui.bar.style.backgroundPositionX = '0px';
      ui.bar.style.filter = 'none';
    } else {
      ui.card.dataset.indeterminate = loaded > 0 ? '1' : '0';
      const progress = computeLoadingPercent(loaded > 0 ? 'download' : 'connect', loaded, total, serverTiming);
      setLoadingProgress(ui, progress);
      setLoadingStage(loaded > 0 ? 'download' : 'connect', loaded > 0 ? 'Datenstrom aktiv…' : 'Verbindung wird aufgebaut…', { loadedBytes: loaded, totalBytes: total, serverTiming });
      ui.bar.style.opacity = loaded > 0 ? '0.9' : '1';
      ui.bar.style.background = 'linear-gradient(90deg,#0A84FF 0%,#30D158 55%,#64D2FF 100%)';
      ui.bar.style.backgroundPositionX = '0px';
      ui.bar.style.filter = 'none';
    }
    syncLoadingOverlayState();
  }


  export function showLoadingOverlay(immediate = false) {
    const ui = getLoadingUi();
    if (!ui.overlay) return;
    clearTimeout(state.loadingOverlayTimer);
    state.loadingStartedAtMs = Date.now();
    setLoadingDetail('Serverphasen werden vorbereitet…');
    if (ui.eta) ui.eta.textContent = 'ETA wird berechnet…';
    updateLoadingPhaseChips('connect', []);
    if (immediate) {
      ui.overlay.style.display = 'flex';
      state.loadingOverlayShown = true;
      syncLoadingOverlayState();
      return;
    }
    state.loadingOverlayTimer = setTimeout(() => {
      ui.overlay.style.display = 'flex';
      state.loadingOverlayShown = true;
      syncLoadingOverlayState();
    }, LOADING_OVERLAY_DELAY_MS);
  }


  export function hideLoadingOverlay() {
    const ui = getLoadingUi();
    clearTimeout(state.loadingOverlayTimer);
    state.loadingOverlayShown = false;
    state.loadingStartedAtMs = 0;
    if (ui.overlay) ui.overlay.style.display = 'none';
    syncLoadingOverlayState();
  }


  export async function readResponseTextWithProgress(response) {
    const totalBytes = parseInt(response.headers.get('content-length') || '', 10);
    const serverTiming = parseServerTimingHeader(response.headers.get('server-timing'));
    if (!response.body || !response.body.getReader) {
      const text = await response.text();
      const fallbackBytes = supportsTextEncoder ? new TextEncoder().encode(text).length : text.length;
      updateLoadingOverlay(fallbackBytes, Number.isFinite(totalBytes) ? totalBytes : fallbackBytes, serverTiming);
      return text;
    }
    const reader = response.body.getReader();
    const chunks = [];
    let loadedBytes = 0;
    updateLoadingOverlay(0, Number.isFinite(totalBytes) ? totalBytes : null, serverTiming);
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      if (value) {
        chunks.push(value);
        loadedBytes += value.byteLength;
        updateLoadingOverlay(loadedBytes, Number.isFinite(totalBytes) ? totalBytes : null, serverTiming);
      }
    }
    const merged = new Uint8Array(loadedBytes);
    let offset = 0;
    chunks.forEach(chunk => {
      merged.set(chunk, offset);
      offset += chunk.byteLength;
    });
    if (supportsTextDecoder) return new TextDecoder().decode(merged);
    let fallbackText = '';
    for (let i = 0; i < merged.length; i += 1) fallbackText += String.fromCharCode(merged[i]);
    try {
      return decodeURIComponent(escape(fallbackText));
    } catch (error) {
      return fallbackText;
    }
  }


  export async function updateMap() {
    if (document.hidden) return;
    if (state.mapUpdateInFlight) {
      state.pendingMapRefresh = true;
      return;
    }
    const statsText = document.getElementById('map-stats-text');
    const badge = document.getElementById('map-points-badge');
    const apiStatus = document.getElementById('api-status');
    const params = buildCurrentFilters();
    const baseQuery = params.toString();
    const currentBbox = getViewportBbox();
    const currentZoom = state.map ? state.map.getZoom() : 0;

    // OPTIMIZATION: Check if shift is significant
    if (!state.isManualRefresh && state.lastMapPayload && !isShiftSignificant(currentBbox, currentZoom) && state.lastMapBaseQueryKey === baseQuery) {
        console.log('Skipping map update: shift not significant');
        return;
    }

    // Lokale Daten abrufen für sofortige Anzeige (nur wenn kein Delta-Mode oder beim ersten Laden)
    if (!state.lastMapPayload) {
      const localPoints = await getLocalPoints(buildCurrentFilterState());
      if (localPoints.length > 0) {
        const fakePayload = { 
          layers: { points: localPoints, latestPoint: localPoints[0] },
          meta: { visiblePoints: localPoints.length, totalPoints: localPoints.length },
          stats: {} 
        };
        renderMapPayload(fakePayload);
        statsText.innerText = 'Lade lokale Daten…';
      }
    }

    if (!state.isManualRefresh && state.lastMapBaseQueryKey === baseQuery && state.lastVisiblePointTsUtc) {
      params.set('latest_known_ts', state.lastVisiblePointTsUtc);
    }
    const url = `/api/map-data?${params.toString()}`;
    const isInitialLoadRequest = !state.lastMapPayload;

    try {
      state.mapUpdateInFlight = true;
      state.pendingMapRefresh = false;
      const metaQueryKey = buildMetaFilters().toString();
      const shouldRefreshMeta =
        isInitialLoadRequest ||
        state.isManualRefresh ||
        !state.lastMetaPayload ||
        state.lastMetaQueryKey !== metaQueryKey ||
        (Date.now() - state.lastMetaFetchedAtMs) >= META_REFRESH_MIN_MS;
      if (shouldRefreshMeta) {
        updateMapMeta({ force: isInitialLoadRequest || state.isManualRefresh || state.lastMetaQueryKey !== metaQueryKey }).catch(error => {
          if (error.name !== 'AbortError') console.warn('Map meta update failed', error);
        });
      }
      apiStatus.textContent = '● LADEN';
      apiStatus.style.color = 'var(--orange)';
      setLoadingMode((!state.isManualRefresh && state.lastMapBaseQueryKey === baseQuery && state.lastVisiblePointTsUtc) ? 'Delta-Check' : 'Vollupdate');
      setLoadingStage('connect', 'Server prüft aktuelle Ansicht…');
      showLoadingOverlay(state.isManualRefresh || isInitialLoadRequest);
      updateLoadingOverlay(0, null);
      state.currentFetchController = supportsAbortController ? new AbortController() : null;
      const fetchStart = Date.now();
      const headers = state.lastETag && !state.isManualRefresh ? { 'If-None-Match': state.lastETag } : {};
      const fetchOptions = { credentials: 'same-origin', headers };
      if (state.currentFetchController) fetchOptions.signal = state.currentFetchController.signal;
      const response = await fetchWithRetry(url, fetchOptions);
      const fetchMs = Date.now() - fetchStart;
      const serverTiming = parseServerTimingHeader(response.headers.get('server-timing'));
      setLoadingDetail(formatServerTimingDetail(serverTiming));

      if (response.status === 304 && state.lastMapPayload) {
        if (state.loadingOverlayShown || state.isManualRefresh) {
          showLoadingOverlay(true);
          setLoadingMode('Delta-Noop', '#30D158');
          setLoadingStage('render', 'Keine Änderungen in der aktuellen Ansicht', { serverTiming });
          setLoadingDetail(`${formatServerTimingDetail(serverTiming)} · nichts neu im Viewport`);
          await wait(LOADING_OVERLAY_PULSE_MS);
        } else {
          showSyncPill('Keine Änderungen im Viewport', 'noop');
        }
        hideLoadingOverlay();
        apiStatus.textContent = '● ONLINE';
        apiStatus.style.color = 'var(--mint)';
        const deltaMode = response.headers.get('x-map-delta') === 'noop';
        document.getElementById('api-info-ms').textContent = deltaMode ? `${fetchMs} ms (delta)` : `${fetchMs} ms (cached)`;
        state.lastRefreshTime = Date.now();
        state.nextRefreshTime = Date.now() + state.POLLING_INTERVAL;
        state.isManualRefresh = false;
        renderProcessingStatus((state.lastMapPayload && state.lastMapPayload.processing) || (state.lastMetaPayload && state.lastMetaPayload.processing) || null);
        return;
      }

      if (!response.ok) {
        let errorDetail = '';
        try {
          const errorPayload = await response.json();
          if (errorPayload && errorPayload.detail) errorDetail = `: ${JSON.stringify(errorPayload.detail)}`;
        } catch (parseError) { errorDetail = ''; }
        throw new Error(`HTTP ${response.status}${errorDetail}`);
      }
      setLoadingMode(response.headers.get('x-map-delta') === 'noop' ? 'Delta-Noop' : 'Download');
      state.lastETag = response.headers.get('etag') || null;
      const text = await readResponseTextWithProgress(response);
      if (state.loadingOverlayShown) setLoadingStage('parse', null, { serverTiming });
      const payload = JSON.parse(text);
      setLoadingMode(payload.meta && payload.meta.deltaMode ? 'Delta-Update' : 'Vollupdate', payload.meta && payload.meta.deltaMode ? '#64D2FF' : '#64D2FF');
      if (state.loadingOverlayShown) setLoadingStage('render', null, { serverTiming });
      setLoadingDetail(formatServerTimingDetail(serverTiming));
      state.lastMapBaseQueryKey = baseQuery;
      state.lastVisiblePointTsUtc = payload && payload.meta ? payload.meta.latestVisiblePointTsUtc || null : null;
      state.lastFetchedBbox = currentBbox;
      state.lastFetchedZoom = currentZoom;
      state.isManualRefresh = false;
      state.lastRefreshTime = Date.now();
      state.nextRefreshTime = Date.now() + state.POLLING_INTERVAL;
      updateTraffic(text.length, fetchMs > 0 ? (text.length / 1024 / 1024) / (fetchMs / 1000) : 0);
      tickRefreshBar();

      // Neu empfangene Punkte lokal speichern
      if (payload.layers && payload.layers.points) await savePointsLocally(payload.layers.points);
      if (payload.delta && payload.delta.appendPoints) await savePointsLocally(payload.delta.appendPoints);

      if (payload.meta && payload.meta.deltaMode) applyMapDelta(payload);
      else {
        state.lastMapPayload = payload;
        renderMapPayload(payload);
      }
      updateStatistics(payload.stats || {}, payload.meta || {});
      if (!(payload.meta && payload.meta.deltaMode)) renderLog(payload.logItems || []);

      const visible = payload && payload.meta ? payload.meta.visiblePoints || 0 : 0;
      const total = state.lastMetaPayload && state.lastMetaPayload.meta && state.lastMetaPayload.meta.totalPoints != null
        ? state.lastMetaPayload.meta.totalPoints
        : payload && payload.meta && payload.meta.totalPoints != null
          ? payload.meta.totalPoints
          : 0;
      const viewportMode = !!(payload && payload.meta && payload.meta.bbox);
      const baseText = visible
        ? `${total.toLocaleString('de-DE')} Punkte gesamt · ${visible.toLocaleString('de-DE')} in der aktuellen Ansicht${viewportMode ? ' (viewport-basiert)' : ''}`
        : 'Keine Punkte im gewählten Zeitraum.';
      statsText.innerText = state.mapRuntimeWarnings.length ? `${baseText} · Hinweise: ${state.mapRuntimeWarnings.join(', ')}` : baseText;
      statsText.style.color = state.mapRuntimeWarnings.length ? 'var(--orange)' : 'var(--text-muted)';
      badge.textContent = `${visible.toLocaleString('de-DE')} geladen`;
      badge.style.display = visible ? 'inline' : 'none';
      document.getElementById('api-info-points').textContent = viewportMode
        ? `${visible.toLocaleString('de-DE')} / ${total.toLocaleString('de-DE')} sichtbar/gesamt · viewport`
        : `${visible.toLocaleString('de-DE')} / ${total.toLocaleString('de-DE')} sichtbar/gesamt · fallback`;
      document.getElementById('api-info-ms').textContent = `${fetchMs} ms`;
      document.getElementById('api-info-url').textContent = url.length > 48 ? `${url.slice(0, 48)}…` : url;
      apiStatus.textContent = '● ONLINE';
      apiStatus.style.color = 'var(--mint)';
      if (payload.meta && payload.meta.deltaMode && !state.loadingOverlayShown) showSyncPill('Delta aktualisiert', 'delta');
      hideLoadingOverlay();

    } catch (error) {
      if (error.name === 'AbortError') return;
      console.error('Map update error:', error);
      showLoadingOverlay(true);
      setLoadingMode('Fehler', '#FF453A');
      setLoadingStage('error', error.message ? `Kartendaten: ${error.message}` : 'Kartendaten konnten nicht geladen werden.');
      setLoadingDetail('Prüfe Netzwerk, Filter oder Serverantwort und versuche es erneut.');
      showSyncPill('Aktualisierung fehlgeschlagen', 'error', 1200);
      await wait(700);
      hideLoadingOverlay();

      statsText.innerText = `Fehler beim Laden der Kartendaten${error.message ? ` (${error.message})` : ''}.`;
      statsText.style.color = 'var(--c-crit)';
      apiStatus.textContent = '● FEHLER';
      apiStatus.style.color = '#ef4444';
    } finally {
      state.mapUpdateInFlight = false;
      state.currentFetchController = null;
      document.getElementById('btn-text').style.display = 'inline';
      document.getElementById('btn-spinner').style.display = 'none';
      if (state.pendingMapRefresh) {
        state.pendingMapRefresh = false;
        scheduleTask(() => updateMap());
      } else {
        scheduleNextMapUpdate(state.POLLING_INTERVAL);
      }
    }
  }


  export const debouncedMapRefresh = debounce(() => {
    state.lastETag = null;
    updateMap();
  }, FILTER_DEBOUNCE);


  // Phase 5: Timeline State


  const SOCKET_RECONNECT_BASE_MS = 1000;
  const SOCKET_RECONNECT_MAX_MS = 30000;


  export function setWebSocketStatus(text, mode = 'info', durationMs = 5000) {
    // Reuse the existing status pill; do not require template/CSS changes.
    showSyncPill(`Live: ${text}`, mode, durationMs);
  }


  export function stopPollingFallback() {
    clearTimeout(state.updateTimer);
    state.updateTimer = null;
    state.nextRefreshTime = 0;
  }


  export function startPollingFallback() {
    state.liveTransport = 'polling';
    scheduleNextMapUpdate(2000);
  }


  export function handleLiveEvent(event) {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch (error) {
      console.warn('Ungültige SSE-Nachricht ignoriert:', error);
      return;
    }
    if (!data || typeof data !== 'object' || Array.isArray(data)) return;
    if (event.type === 'resync_required') {
      invalidateMapClientCacheForStructuralChange();
      updateMapMeta({ force: true }).catch(() => {});
    } else if (event.type === 'import_completed' || event.type === 'session_deleted') {
      invalidateMapClientCacheForStructuralChange();
      updateMapMeta({ force: true }).catch(() => {});
    }
    debouncedMapRefresh();
  }


  export function scheduleSseReconnect() {
    if (state.sseReconnectScheduled || state.sseReconnectTimer || document.hidden) return;
    const exponentialDelay = Math.min(
      SOCKET_RECONNECT_MAX_MS,
      SOCKET_RECONNECT_BASE_MS * (2 ** Math.min(state.sseReconnectAttempt, 5))
    );
    const jitter = 0.75 + (Math.random() * 0.5);
    const delay = Math.round(exponentialDelay * jitter);
    state.sseReconnectAttempt += 1;
    state.sseReconnectScheduled = true;
    state.sseReconnectTimer = setTimeout(() => {
      state.sseReconnectTimer = null;
      state.sseReconnectScheduled = false;
      initSSE();
    }, delay);
  }


  export function closeSSE() {
    if (state.sseReconnectTimer) {
      clearTimeout(state.sseReconnectTimer);
      state.sseReconnectTimer = null;
    }
    state.sseReconnectScheduled = false;
    if (state.sseSource) {
      state.sseSource.close();
      state.sseSource = null;
    }
  }


  export function initSSE() {
    if (document.hidden || !('EventSource' in window)) {
      if (!('EventSource' in window)) {
        setWebSocketStatus('SSE nicht verfügbar – WebSocket', 'info', 5000);
        startPollingFallback();
      }
      initWebSocket();
      return;
    }
    if (state.sseSource) return;
    const source = new EventSource('/events/map');
    state.sseSource = source;
    setWebSocketStatus('SSE verbindet…', 'info', 3000);
    ['new_location', 'import_completed', 'session_deleted', 'resync_required'].forEach((eventName) => {
      source.addEventListener(eventName, handleLiveEvent);
    });
    source.onopen = () => {
      if (state.sseSource !== source) return;
      state.liveTransport = 'sse';
      state.sseReconnectAttempt = 0;
      setWebSocketStatus('SSE live', 'noop', 2500);
      stopPollingFallback();
      if (state.socket) {
        const fallbackSocket = state.socket;
        state.socket = null;
        fallbackSocket.close(1000, 'SSE aktiv');
      }
    };
    source.onerror = () => {
      if (state.sseSource !== source) return;
      state.sseSource = null;
      source.close();
      setWebSocketStatus('SSE getrennt – WebSocket-Fallback', 'error', 5000);
      startPollingFallback();
      initWebSocket();
      scheduleSseReconnect();
    };
  }


  export function scheduleWebSocketReconnect() {
    if (state.socketReconnectScheduled || state.socketReconnectTimer) return;
    if (document.hidden || state.sseSource) return;
    const exponentialDelay = Math.min(
      SOCKET_RECONNECT_MAX_MS,
      SOCKET_RECONNECT_BASE_MS * (2 ** Math.min(state.socketReconnectAttempt, 5))
    );
    // Jitter avoids synchronized reconnects after a server/network outage.
    const jitter = 0.75 + (Math.random() * 0.5);
    const delay = Math.round(exponentialDelay * jitter);
    state.socketReconnectAttempt += 1;
    state.socketReconnectScheduled = true;
    setWebSocketStatus(`getrennt – neuer Versuch in ${Math.ceil(delay / 1000)}s`, 'error', delay + 1000);
    state.socketReconnectTimer = setTimeout(() => {
      state.socketReconnectTimer = null;
      state.socketReconnectScheduled = false;
      initSSE();
    }, delay);
  }


  export function invalidateMapClientCacheForStructuralChange() {
    console.log('Strukturelle Änderung erkannt: Client-Caches werden invalidiert.');
    state.lastETag = null;
    state.lastMapBaseQueryKey = '';
    state.lastVisiblePointTsUtc = null;
    state.lastMetaEtag = null;
    state.lastMetaQueryKey = '';
    state.lastMetaFetchedAtMs = 0;
  }


  export function initWebSocket() {
    if (document.hidden) return;
    if (state.sseSource) return;
    if (!('WebSocket' in window)) {
      console.warn('WebSocket im Browser nicht verfügbar.');
      setWebSocketStatus('nicht verfügbar', 'error', 60000);
      startPollingFallback();
      return;
    }
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${protocol}//${window.location.host}/ws/map`;

    if (state.socket && (state.socket.readyState === WebSocket.OPEN || state.socket.readyState === WebSocket.CONNECTING)) return;
    const connection = new WebSocket(wsUrl);
    state.socket = connection;
    setWebSocketStatus('verbinde…', 'info', 3000);

    connection.onopen = () => {
      // A successful connection resets the backoff for the next outage.
      state.socketReconnectAttempt = 0;
      setWebSocketStatus('verbunden', 'noop', 2500);
      state.liveTransport = 'websocket';
      stopPollingFallback();
    };

    connection.onmessage = (event) => {
      let data;
      try {
        data = JSON.parse(event.data);
      } catch (error) {
        console.warn('Ungültige WebSocket-Nachricht ignoriert:', error);
        setWebSocketStatus('ungültige Nachricht ignoriert', 'error', 5000);
        return;
      }
      if (!data || typeof data !== 'object' || Array.isArray(data)) return;
      if (data.type === 'new_location' || data.type === 'import_completed' || data.type === 'session_deleted') {
        console.log(`Echtzeit-Update empfangen (${data.type})...`);
        
        if (data.type === 'import_completed' || data.type === 'session_deleted') {
          // Strukturelle Änderung -> Full Refresh erzwingen (kein Delta-Refresh)
          invalidateMapClientCacheForStructuralChange();
          updateMapMeta({ force: true }).catch(() => {});
        }
        
        debouncedMapRefresh();
      }
    };

    connection.onclose = () => {
      // Ignore close events from an obsolete connection.
      if (state.socket !== connection) return;
      state.socket = null;
      console.warn('WebSocket geschlossen. Reconnect wird geplant.');
      if (state.liveTransport === 'websocket') startPollingFallback();
      scheduleWebSocketReconnect();
    };

    connection.onerror = (err) => {
      console.error('WebSocket Fehler:', err);
      setWebSocketStatus('Verbindungsfehler', 'error', 5000);
      // onclose performs the single reconnect scheduling.
      if (connection.readyState === WebSocket.OPEN || connection.readyState === WebSocket.CONNECTING) {
        connection.close();
      }
    };
  }

// Für das inline onclick="focusLatestPoint(); ..." im Standort-Auswahlmenü
// (map.html) muss die Funktion global erreichbar sein - genau wie zuvor als
// klassische, nicht-modulare Top-Level-Funktion.
window.focusLatestPoint = focusLatestPoint;
