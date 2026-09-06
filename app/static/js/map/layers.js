// Karten-/Layer-Rendering: MapLibre-Layer anlegen, GeoJSON-Quellen befüllen,
// Legende/Sichtbarkeit pro Layer, Heatmap/Track/Stop-Visualisierung sowie das
// Zusammenführen von Voll- und Delta-Updates. Ruft für die Timeline-Anzeige
// gezielt in timeline.js hinein (zyklische, aber rein funktionsbasierte
// Abhängigkeit - unproblematisch in ES-Modulen, da nur innerhalb von
// Funktionsrümpfen referenziert, nie beim Modul-Import selbst ausgewertet).
import { state, SOURCE_IDS, layerDataLoaded } from './state.js';
import { formatDuration, formatEta } from '../map-page-utils.js';
import { clampLogLimit } from './network.js';
import { updateTimeline, applyTimelineFilter } from './timeline.js';

  export function updateLayerVisibility(layerKey, active) {
    if (!state.map) return;
    const layerMappings = {
      heatmap: ['layer-heatmap'],
      points: ['layer-points', 'layer-points-clusters', 'layer-points-cluster-count', 'layer-latest'],
      polyline: ['layer-lines-casing', 'layer-lines'],
      labels: ['layer-line-labels'],
      accuracy: ['layer-accuracy-fill', 'layer-accuracy'],
      speed: ['layer-speed'],
      stops: ['layer-stops', 'layer-stops-labels'],
      daytrack: ['layer-daytracks'],
      snap: ['layer-snap']
    };
    const ids = layerMappings[layerKey] || [];
    ids.forEach(id => {
      if (state.map.getLayer(id)) {
        state.map.setLayoutProperty(id, 'visibility', active ? 'visible' : 'none');
      }
    });
  }


  export function updateMapOverlayLayout() {
    const wrap = document.getElementById('map-wrap');
    const loadingCard = document.getElementById('map-loading-card');

    const timeline = document.getElementById('map-timeline-container');
    if (!wrap || !loadingCard || !timeline) return;
    const width = wrap.clientWidth || 0;
    const height = wrap.clientHeight || 0;
    const compact = width < 560 || height < 430;
    const overlayGap = width < 420 ? 8 : width < 768 ? 10 : 12;
    const loadingWidth = compact ? Math.max(210, Math.min(width - overlayGap * 2, 260)) : Math.max(260, Math.min(width * 0.34, 340));
    const timelineWidth = compact ? Math.max(220, width - overlayGap * 2) : Math.max(300, Math.min(width * 0.72, 560));
    const timelineBottom = compact ? 10 : 18;
    const menuOffset = 0;
    wrap.style.setProperty('--map-overlay-gap', `${overlayGap}px`);
    wrap.style.setProperty('--map-loading-width', `${Math.max(180, loadingWidth)}px`);
    wrap.style.setProperty('--map-timeline-width', `${Math.max(220, timelineWidth)}px`);
    wrap.style.setProperty('--map-timeline-bottom', `${timelineBottom}px`);
    wrap.style.setProperty('--map-loading-menu-offset', `${menuOffset}px`);
    wrap.dataset.overlayCompact = compact ? '1' : '0';
    wrap.dataset.timelineMini = width < 520 || height < 410 ? '1' : '0';
  }


  export function updateLegendPlacement() {
    const legend = document.getElementById('map-legend');
    const legendAnchor = document.getElementById('map-legend-anchor');
    const mapWrap = document.getElementById('map-wrap');
    if (!legend) return;
    const fullscreenActive = state.cssFsActive || !!document.fullscreenElement;
    if (fullscreenActive) {
      if (mapWrap && legend.parentElement !== mapWrap) {
        mapWrap.appendChild(legend);
      }
      legend.style.position = 'absolute';
      legend.style.left = '12px';
      legend.style.right = '12px';
      legend.style.bottom = '18px';
      legend.style.zIndex = '690';
      legend.style.padding = '12px 14px';
      legend.style.border = '1px solid var(--separator)';
      legend.style.borderRadius = '12px';
      legend.style.background = 'color-mix(in srgb, var(--surface-1) 88%, transparent)';
      legend.style.backdropFilter = 'blur(10px)';
      legend.style.boxShadow = '0 10px 30px rgba(0,0,0,0.22)';
      legend.style.marginTop = '0';
    } else {
      if (legendAnchor && legendAnchor.parentNode && legend.parentElement !== legendAnchor.parentElement) {
        legendAnchor.parentNode.insertBefore(legend, legendAnchor.nextSibling);
      }
      legend.style.position = 'static';
      legend.style.left = '';
      legend.style.right = '';
      legend.style.bottom = '';
      legend.style.zIndex = '';
      legend.style.padding = '';
      legend.style.border = '';
      legend.style.borderRadius = '';
      legend.style.background = '';
      legend.style.backdropFilter = '';
      legend.style.boxShadow = '';
      legend.style.marginTop = '14px';
    }
  }


  export function renderProcessingStatus(processing) {
    const statusLabel = document.getElementById('processing-status-label');
    const detail = document.getElementById('processing-status-detail');
    const remaining = document.getElementById('processing-remaining');
    const eta = document.getElementById('processing-eta');
    if (!processing || processing.allProcessed) {
      statusLabel.textContent = 'vollständig';
      statusLabel.style.color = 'var(--mint)';
      detail.textContent = 'Alle verfügbaren Serverdaten verarbeitet';
      remaining.textContent = '0 Punkte';
      eta.textContent = '0s';
      return;
    }

    statusLabel.textContent = processing.statusLabel || 'Verarbeitung läuft';
    statusLabel.style.color = 'var(--orange)';
    const parts = [];
    if (processing.activeTasks) parts.push(`${processing.activeTasks} Task${processing.activeTasks !== 1 ? 's' : ''}`);
    if (processing.knownTotalPoints) {
      parts.push(`${(processing.processedPoints || 0).toLocaleString('de-DE')} / ${processing.knownTotalPoints.toLocaleString('de-DE')} Punkte`);
    }
    if (processing.unknownTasks) {
      parts.push(`${processing.unknownTasks} Task${processing.unknownTasks !== 1 ? 's' : ''} noch in Analyse`);
    }
    detail.textContent = parts.join(' · ') || 'Server analysiert/verarbeitet noch Daten';
    remaining.textContent = processing.unknownTasks
      ? `${(processing.remainingPoints || 0).toLocaleString('de-DE')} Punkte + Analyse offen`
      : `${(processing.remainingPoints || 0).toLocaleString('de-DE')} Punkte`;
    eta.textContent = processing.unknownTasks && !processing.etaSeconds
      ? 'nach Analyse verfügbar'
      : formatEta(processing.etaSeconds);
  }


  export function updateLegendToggleButton() {
    const button = document.getElementById('legend-toggle-btn');
    if (!button) return;
    button.style.opacity = state.legendVisible ? '1' : '0.72';
    button.title = state.legendVisible ? 'Legende ausblenden' : 'Legende einblenden';
    button.setAttribute('aria-pressed', String(state.legendVisible));
  }


  export function updateLegend() {
    document.getElementById('legend-points').style.display = state.pointsActive ? '' : 'none';
    document.getElementById('legend-lines').style.display = state.polylineActive ? '' : 'none';
    document.getElementById('legend-heatmap').style.display = state.heatmapActive ? '' : 'none';
    document.getElementById('legend-accuracy').style.display = state.accuracyActive ? '' : 'none';
    document.getElementById('legend-labels').style.display = state.labelsActive ? '' : 'none';
    document.getElementById('legend-speed').style.display = state.speedActive ? '' : 'none';
    document.getElementById('legend-stops').style.display = state.stopsActive ? '' : 'none';
    document.getElementById('legend-daytrack').style.display = state.daytrackActive ? '' : 'none';
    document.getElementById('legend-snap').style.display = state.snapActive ? '' : 'none';
    const anyActive = state.heatmapActive || state.pointsActive || state.polylineActive || state.accuracyActive || state.labelsActive || state.speedActive || state.stopsActive || state.daytrackActive || state.snapActive;
    document.getElementById('map-legend').style.display = state.legendVisible && anyActive ? 'flex' : 'none';
    updateLegendPlacement();
    updateLegendToggleButton();
  }


  export function setToggleAvailability(toggleId, available, unavailableTitle = 'Funktion derzeit nicht verfügbar') {
    const toggle = document.getElementById(toggleId);
    if (!toggle) return;
    toggle.disabled = !available;
    if (!available) {
      toggle.checked = false;
      toggle.title = unavailableTitle;
    } else {
      toggle.title = '';
    }
  }


  export function isWebglSupported() {
    if (!window.WebGLRenderingContext) return false;
    const canvas = document.createElement('canvas');
    try {
      const context = canvas.getContext('webgl2') || canvas.getContext('webgl');
      return !!(context && typeof context.getParameter === 'function');
    } catch (error) {
      return false;
    }
  }


  export function setLayerToggle(toggleId, active) {
    const toggle = document.getElementById(toggleId);
    if (toggle) toggle.checked = active;
  }


  export function rememberLayerWarning(message) {
    if (state.mapRuntimeWarnings.indexOf(message) === -1) state.mapRuntimeWarnings.push(message);
  }


  export function rememberPersistentWarning(message) {
    if (state.persistentRuntimeWarnings.indexOf(message) === -1) state.persistentRuntimeWarnings.push(message);
  }


  export function runLayerStage(name, fn) {
    try {
      fn();
    } catch (error) {
      console.error(`Layer render failed: ${name}`, error);
      rememberLayerWarning(`${name} deaktiviert`);
      if (name === 'Heatmap') {
        state.heatmapActive = false;
        setLayerToggle('heatmap-toggle', false);
        setToggleAvailability('heatmap-toggle', false, 'Heatmap-Layer fehlgeschlagen');
        updateLegend();
      }
    }
  }


  export function collectVisibleBoundsPoints(layers) {
    const points = [];
    if (state.pointsActive) {
      (layers.points || []).forEach(p => points.push([p.lat, p.lon]));
      if (layers.latestPoint) points.push([layers.latestPoint.lat, layers.latestPoint.lon]);
    }
    if (state.polylineActive) {
      (layers.polylines || []).forEach(s => s.coords.forEach(c => points.push(c)));
    }
    if (state.accuracyActive) (layers.accuracy || []).forEach(p => points.push([p.lat, p.lon]));
    if (state.speedActive) (layers.speed || []).forEach(s => s.coords.forEach(c => points.push(c)));
    if (state.stopsActive) (layers.stops || []).forEach(p => points.push([p.lat, p.lon]));
    if (state.daytrackActive) (layers.daytracks || []).forEach(d => d.segments.forEach(seg => seg.forEach(c => points.push(c))));
    if (state.snapActive) (layers.snap || []).forEach(s => s.coords.forEach(c => points.push(c)));
    return points;
  }


  export function applyMapFocus(layers) {
    if (Date.now() < state.suppressMapFocusUntil) return;
    const latest = layers.latestPoint;
    const autoCenter = document.getElementById('auto-center-toggle').checked;
    const fitBounds = document.getElementById('fit-bounds-toggle').checked;

    if (fitBounds) {
      const useGlobalBounds = state.FIT_BOUNDS_MODE === 'global';
      const metaBounds = useGlobalBounds && state.lastMetaPayload && state.lastMetaPayload.meta ? state.lastMetaPayload.meta.boundingBox : null;
      
      if (metaBounds && useGlobalBounds) {
        state.suppressedViewportRefreshes += 1;
        state.map.fitBounds([
          [metaBounds.minLongitude, metaBounds.minLatitude],
          [metaBounds.maxLongitude, metaBounds.maxLatitude]
        ], { padding: 50, linear: false });
      } else {
        const bounds = new maplibregl.LngLatBounds();
        const pts = collectVisibleBoundsPoints(layers);
        if (pts.length) {
          pts.forEach(p => bounds.extend([p[1], p[0]]));
          state.suppressedViewportRefreshes += 1;
          state.map.fitBounds(bounds, { padding: 50, linear: false });
        }
      }
    } else if (autoCenter && latest) {
      state.suppressedViewportRefreshes += 1;
      state.map.panTo([latest.lon, latest.lat]);
    }
  }


  export function renderMapPayload(data, options = {}) {
    state.mapRuntimeWarnings = state.persistentRuntimeWarnings.slice();
    clearRenderedLayers();
    renderProcessingStatus(data.processing || null);
    const layers = data.layers || {};
    const meta = data.meta || {};
    
    // Track which layers were actually provided with data from the backend
    if (meta.loadedLayers) {
      meta.loadedLayers.forEach(layer => {
        if (layerDataLoaded.hasOwnProperty(layer)) {
          layerDataLoaded[layer] = true;
        }
      });
    }

    runLayerStage('Heatmap', () => renderHeatmap(layers.heatmap || []));
    runLayerStage('Punkte', () => renderPoints(layers.points || [], layers.latestPoint || null));
    runLayerStage('Linien', () => renderPolylines(layers.polylines || []));
    runLayerStage('Radius', () => renderAccuracy(layers.accuracy || []));
    runLayerStage('Tempo', () => renderSpeed(layers.speed || []));
    runLayerStage('Stops', () => renderStops(layers.stops || []));
    runLayerStage('Tage', () => renderDaytracks(layers.daytracks || []));
    runLayerStage('Snap', () => renderSnap(layers.snap || []));
    
    // Ensure visibility matches toggles
    updateLayerVisibility('heatmap', state.heatmapActive);
    updateLayerVisibility('points', state.pointsActive);
    updateLayerVisibility('polyline', state.polylineActive);
    updateLayerVisibility('labels', state.labelsActive);
    updateLayerVisibility('accuracy', state.accuracyActive);
    updateLayerVisibility('speed', state.speedActive);
    updateLayerVisibility('stops', state.stopsActive);
    updateLayerVisibility('daytrack', state.daytrackActive);
    updateLayerVisibility('snap', state.snapActive);

    if (!options.skipFocus) applyMapFocus(layers);
    if (!options.skipTimeline) updateTimeline(layers.points || []);
  }


  export function clearRenderedLayers() {
    Object.keys(SOURCE_IDS).map(key => SOURCE_IDS[key]).forEach(id => {
      const src = state.map.getSource(id);
      if (src) src.setData({ type: 'FeatureCollection', features: [] });
    });
  }


  export function buildCirclePolygon(lon, lat, radiusMeters, steps = 48) {
    const safeRadius = Math.max(0, Number(radiusMeters) || 0);
    if (!safeRadius) return [];
    const coords = [];
    const latRad = lat * (Math.PI / 180);
    const metersPerDegLat = 111320;
    const metersPerDegLon = Math.max(111320 * Math.cos(latRad), 0.000001);
    for (let i = 0; i <= steps; i += 1) {
      const angle = (i / steps) * Math.PI * 2;
      coords.push([
        lon + (Math.cos(angle) * safeRadius) / metersPerDegLon,
        lat + (Math.sin(angle) * safeRadius) / metersPerDegLat,
      ]);
    }
    return coords;
  }

  // Backend data is normally well-formed, but a single bad point must not
  // make MapLibre reject the complete source update. Coordinates in the
  // layer payloads are [latitude, longitude]; GeoJSON uses [longitude,
  // latitude]. Keep the conversion in one place so every render path applies
  // the same finite/range checks.

  export function isCoordinateValue(value) {
    return (typeof value === 'number' || typeof value === 'string')
      && (typeof value !== 'string' || value.trim() !== '');
  }


  export function validGeometryPoint(lat, lon) {
    if (!isCoordinateValue(lat) || !isCoordinateValue(lon)) return null;
    const latitude = Number(lat);
    const longitude = Number(lon);
    if (!Number.isFinite(latitude) || !Number.isFinite(longitude)
      || latitude < -90 || latitude > 90
      || longitude < -180 || longitude > 180) return null;
    return [longitude, latitude];
  }


  export function validGeometryPair(pair) {
    return Array.isArray(pair) && pair.length >= 2
      ? validGeometryPoint(pair[0], pair[1])
      : null;
  }


  export function validLineCoordinates(coords) {
    if (!Array.isArray(coords)) return null;
    const valid = coords.map(validGeometryPair).filter(Boolean);
    return valid.length >= 2 ? valid : null;
  }


  export function renderPoints(points, latestPoint) {
    const validPoints = points.filter(p => Number.isFinite(Number(p.lat)) && Number.isFinite(Number(p.lon))
      && Number(p.lat) >= -90 && Number(p.lat) <= 90
      && Number(p.lon) >= -180 && Number(p.lon) <= 180);
    const features = validPoints.map(p => ({
      type: 'Feature',
      geometry: { type: 'Point', coordinates: [Number(p.lon), Number(p.lat)] },
      properties: { timestamp: p.timestampLocal || p.timestampUtc, accuracy: p.accuracyM, isLatest: !!p.isLatest }
    }));
    state.map.getSource(SOURCE_IDS.POINTS).setData({ type: 'FeatureCollection', features: features.filter(f => !f.properties.isLatest) });
    
    if (latestPoint && Number.isFinite(Number(latestPoint.lat)) && Number.isFinite(Number(latestPoint.lon))
      && Number(latestPoint.lat) >= -90 && Number(latestPoint.lat) <= 90
      && Number(latestPoint.lon) >= -180 && Number(latestPoint.lon) <= 180) {
      state.map.getSource(SOURCE_IDS.LATEST).setData({
        type: 'FeatureCollection',
        features: [{ type: 'Feature', geometry: { type: 'Point', coordinates: [Number(latestPoint.lon), Number(latestPoint.lat)] }, properties: { isLatest: true } }]
      });
    } else {
      state.map.getSource(SOURCE_IDS.LATEST).setData({ type: 'FeatureCollection', features: [] });
    }
  }


  export function renderHeatmap(entries) {
    const features = (Array.isArray(entries) ? entries : []).map(e => {
      const coordinates = Array.isArray(e) ? validGeometryPoint(e[0], e[1]) : null;
      if (!coordinates) return null;
      return {
      type: 'Feature',
      geometry: { type: 'Point', coordinates },
      properties: { weight: e[2] || 0.5 }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.HEATMAP).setData({ type: 'FeatureCollection', features });
  }


  export function renderPolylines(segments) {
    const features = (Array.isArray(segments) ? segments : []).map(s => {
      const coordinates = s && validLineCoordinates(s.coords);
      if (!coordinates) return null;
      return {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates },
        properties: { color: s.color, label: `${s.startLabel} - ${s.endLabel}` }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.LINES).setData({ type: 'FeatureCollection', features });
  }


  export function renderAccuracy(entries) {
    const features = (Array.isArray(entries) ? entries : []).map(e => {
      const point = e && validGeometryPoint(e.lat, e.lon);
      const radius = e ? Number(e.radius) : NaN;
      if (!point || !Number.isFinite(radius) || radius <= 0) return null;
      const coordinates = buildCirclePolygon(point[0], point[1], radius);
      if (coordinates.length < 4) return null;
      return {
        type: 'Feature',
        geometry: { type: 'Polygon', coordinates: [coordinates] },
        properties: { radius_m: e.radius }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.ACCURACY).setData({ type: 'FeatureCollection', features });
  }


  export function renderSpeed(entries) {
    const features = (Array.isArray(entries) ? entries : []).map(e => {
      const coordinates = e && validLineCoordinates(e.coords);
      if (!coordinates) return null;
      return {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates },
        properties: { color: e.color, kmh: e.kmh }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.SPEED).setData({ type: 'FeatureCollection', features });
  }


  export function renderStops(entries) {
    const features = (Array.isArray(entries) ? entries : []).map(e => {
      const coordinates = e && validGeometryPoint(e.lat, e.lon);
      if (!coordinates) return null;
      return {
        type: 'Feature',
        geometry: { type: 'Point', coordinates },
        properties: { label: `⏱ ${e.durationMin}min`, duration: e.durationMin }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.STOPS).setData({ type: 'FeatureCollection', features });
  }


  export function renderDaytracks(entries) {
    const features = [];
    (Array.isArray(entries) ? entries : []).forEach(d => {
       (d && Array.isArray(d.segments) ? d.segments : []).forEach(coords => {
         const validCoordinates = validLineCoordinates(coords);
         if (!validCoordinates) return;
         features.push({
           type: 'Feature',
           geometry: { type: 'LineString', coordinates: validCoordinates },
           properties: { color: d.color, day: d.day }
         });
       });
    });
    state.map.getSource(SOURCE_IDS.DAYTRACKS).setData({ type: 'FeatureCollection', features });
  }


  export function renderSnap(entries) {
    const features = (Array.isArray(entries) ? entries : []).map(e => {
      const coordinates = e && validLineCoordinates(e.coords);
      if (!coordinates) return null;
      return {
        type: 'Feature',
        geometry: { type: 'LineString', coordinates },
        properties: { }
      };
    }).filter(Boolean);
    state.map.getSource(SOURCE_IDS.SNAP).setData({ type: 'FeatureCollection', features });
  }


  export function mergePointItems(existing, appended, latestPoint) {
    const merged = new Map((existing || []).map(item => [item.id, Object.assign({}, item, { isLatest: false })]));
    (appended || []).forEach(item => merged.set(item.id, Object.assign({}, item, { isLatest: false })));
    const latestId = latestPoint && latestPoint.id != null ? latestPoint.id : null;
    const result = Array.from(merged.values()).sort((a, b) => String(b.timestampUtc || '').localeCompare(String(a.timestampUtc || '')));
    if (latestId !== null) result.forEach(item => { item.isLatest = item.id === latestId; });
    return result;
  }


  export function mergeLogItems(existing, appended) {
    const merged = new Map((existing || []).map(item => [item.id, item]));
    (appended || []).forEach(item => merged.set(item.id, item));
    return Array.from(merged.values()).sort((a, b) => String(b.timestampLocal || '').localeCompare(String(a.timestampLocal || '')));
  }


  export function mergeLayerEntries(existing, appended, keyBuilder) {
    const merged = new Map();
    (existing || []).forEach(item => merged.set(keyBuilder(item), item));
    (appended || []).forEach(item => merged.set(keyBuilder(item), item));
    return Array.from(merged.values());
  }

  // Delta updates only replace properties on the payload and its layers. Keep
  // unchanged, potentially large arrays structurally shared instead of
  // recursively cloning the complete payload on every update.

  export function createDeltaPayloadBase(previous) {
    const layers = previous && previous.layers && typeof previous.layers === 'object'
      ? previous.layers
      : {};
    return Object.assign({}, previous, { layers: Object.assign({}, layers) });
  }


  export function updateStatistics(stats, meta) {
    document.getElementById('stat-points-per-min').innerText = (stats.pointsPerMinute || 0).toFixed(1);
    document.getElementById('stat-avg-accuracy').innerText = stats.avgAccuracyM ? `${Math.round(stats.avgAccuracyM)}m` : '-';
    document.getElementById('stat-visible-points').innerText = (meta.visiblePoints || 0).toLocaleString('de-DE');
    document.getElementById('stat-total-points').innerText = (meta.totalPoints || 0).toLocaleString('de-DE');
    document.getElementById('stat-session-duration').innerText = formatDuration(stats.sessionDurationSeconds || 0);
    document.getElementById('stat-zoom-level').innerText = state.map ? Math.round(state.map.getZoom()) : '-';
  }


  export function renderLog(items) {
    state.currentLogItems = items || [];
    const body = document.getElementById('live-log-body');
    body.innerHTML = '';
    const limit = clampLogLimit(document.getElementById('log-limit').value);
    const query = document.getElementById('log-search').value.toLowerCase().trim();
    const filtered = state.currentLogItems.filter(item => {
      if (!query) return true;
      const haystack = `${item.lat.toFixed(5)} ${item.lon.toFixed(5)} ${item.timestampLocal} ${item.requestId}`.toLowerCase();
      return haystack.indexOf(query) !== -1;
    }).slice(0, limit);

    if (!filtered.length) {
      body.innerHTML = '<tr><td colspan="6" style="text-align: center; padding: 60px; color: var(--text-3); font-size: 0.95rem;">Keine Punkte im aktuellen Filter.</td></tr>';
      return;
    }

    filtered.forEach(item => {
      const row = document.createElement('tr');
      row.style.borderBottom = '1px solid var(--surface-2)';
      const coordText = `${item.lat.toFixed(5)}, ${item.lon.toFixed(5)}`;
      const timeText = new Date(item.timestampLocal).toLocaleTimeString('de-DE', { timeZone: 'Europe/Berlin', hour: '2-digit', minute: '2-digit', second: '2-digit' });
      const timeCell = document.createElement('td');
      timeCell.style.cssText = 'padding: 14px 10px; color: var(--text-2); font-size: 0.9rem;';
      const relativeSpan = document.createElement('span');
      relativeSpan.style.color = 'var(--text-3)';
      relativeSpan.textContent = window.LH2GPXMapUtils.getRelativeTime(item.timestampLocal);
      timeCell.append(relativeSpan, ` • ${timeText}`);

      const coordCell = document.createElement('td');
      coordCell.style.cssText = 'padding: 14px 10px; color: var(--blue); cursor: pointer; user-select: none; border-radius: 4px; font-weight: 500;';
      coordCell.title = 'Klicken zum Kopieren';
      coordCell.setAttribute('role', 'button');
      coordCell.setAttribute('tabindex', '0');
      coordCell.setAttribute('aria-label', `Koordinaten ${coordText} kopieren`);
      coordCell.setAttribute('aria-keyshortcuts', 'Enter Space');
      coordCell.textContent = coordText;

      const accuracyCell = document.createElement('td');
      accuracyCell.className = 'log-col-accuracy';
      accuracyCell.style.cssText = 'padding: 14px 10px; color: var(--mint); font-weight: 500;';
      accuracyCell.textContent = `${item.accuracyM}m`;

      const sourceCell = document.createElement('td');
      sourceCell.style.cssText = 'padding: 14px 10px; color: var(--orange); font-size: 0.9rem;';
      sourceCell.textContent = item.source || 'N/A';

      const modeCell = document.createElement('td');
      modeCell.className = 'log-col-mode';
      modeCell.style.cssText = 'padding: 14px 10px; color: var(--teal); font-size: 0.85rem;';
      modeCell.textContent = item.captureMode || 'N/A';

      const requestCell = document.createElement('td');
      requestCell.className = 'log-col-request-id';
      requestCell.style.cssText = 'padding: 14px 10px; color: var(--text-3); font-size: 0.8rem; font-family: monospace;';
      requestCell.title = item.requestId || 'N/A';
      requestCell.textContent = (item.requestId || 'N/A').substring(0, 12);

      row.append(timeCell, coordCell, accuracyCell, sourceCell, modeCell, requestCell);
      const copyCoordinates = async (event) => {
        event.stopPropagation();
        try {
          await navigator.clipboard.writeText(coordText);
          const original = coordCell.style.backgroundColor;
          coordCell.style.backgroundColor = 'rgba(16, 185, 129, 0.3)';
          setTimeout(() => { coordCell.style.backgroundColor = original; }, 300);
        } catch (error) {
          console.warn('Clipboard write failed', error);
          window.prompt('Koordinaten kopieren:', coordText);
        }
      };
      coordCell.onclick = copyCoordinates;
      coordCell.onkeydown = (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          copyCoordinates(event);
        }
      };
      body.appendChild(row);
    });
  }


  export function applyMapDelta(payload) {
    if (!state.lastMapPayload || !payload || !payload.delta) {
      renderMapPayload(payload);
      return;
    }
    state.mapRuntimeWarnings = state.persistentRuntimeWarnings.slice();
    renderProcessingStatus(payload.processing || null);
    const merged = createDeltaPayloadBase(state.lastMapPayload);
    merged.meta = payload.meta || merged.meta;
    merged.stats = payload.stats || merged.stats;
    merged.processing = payload.processing || merged.processing;
    const delta = payload.delta || {};
    merged.layers.latestPoint = delta.latestPoint || merged.layers.latestPoint || null;

    if (Array.isArray(delta.appendPoints)) {
      merged.layers.points = mergePointItems(merged.layers.points || [], delta.appendPoints, merged.layers.latestPoint);
      renderPoints(merged.layers.points, merged.layers.latestPoint);
    }
    if ('replaceHeatmap' in delta) {
      merged.layers.heatmap = delta.replaceHeatmap || [];
      renderHeatmap(merged.layers.heatmap);
    }
    if ('replacePolylines' in delta) {
      merged.layers.polylines = delta.replacePolylines || [];
      renderPolylines(merged.layers.polylines);
    } else if (Array.isArray(delta.appendPolylines)) {
      merged.layers.polylines = mergeLayerEntries(
        merged.layers.polylines || [],
        delta.appendPolylines,
        item => JSON.stringify(item.coords || [])
      );
      renderPolylines(merged.layers.polylines);
    }
    if ('replaceAccuracy' in delta) {
      merged.layers.accuracy = delta.replaceAccuracy || [];
      renderAccuracy(merged.layers.accuracy);
    }
    if ('replaceSpeed' in delta) {
      merged.layers.speed = delta.replaceSpeed || [];
      renderSpeed(merged.layers.speed);
    } else if (Array.isArray(delta.appendSpeed)) {
      merged.layers.speed = mergeLayerEntries(
        merged.layers.speed || [],
        delta.appendSpeed,
        item => JSON.stringify(item.coords || [])
      );
      renderSpeed(merged.layers.speed);
    }
    if ('replaceStops' in delta) {
      merged.layers.stops = delta.replaceStops || [];
    } else if (Array.isArray(delta.upsertStops)) {
      merged.layers.stops = mergeLayerEntries(
        merged.layers.stops || [],
        delta.upsertStops,
        item => `${item.startTimeUtc || ''}:${item.endTimeUtc || ''}`
      );
    }
    if ('replaceStops' in delta || Array.isArray(delta.upsertStops)) {
      renderStops(merged.layers.stops);
    }
    if ('replaceDaytracks' in delta) {
      merged.layers.daytracks = delta.replaceDaytracks || [];
    } else if (Array.isArray(delta.upsertDaytracks)) {
      merged.layers.daytracks = mergeLayerEntries(
        merged.layers.daytracks || [],
        delta.upsertDaytracks,
        item => String(item.day || '')
      );
    }
    if ('replaceDaytracks' in delta || Array.isArray(delta.upsertDaytracks)) {
      renderDaytracks(merged.layers.daytracks);
    }
    if ('replaceSnap' in delta) {
      merged.layers.snap = delta.replaceSnap || [];
    } else if (Array.isArray(delta.appendSnap)) {
      merged.layers.snap = mergeLayerEntries(
        merged.layers.snap || [],
        delta.appendSnap,
        item => JSON.stringify(item.coords || [])
      );
    }
    if ('replaceSnap' in delta || Array.isArray(delta.appendSnap)) {
      renderSnap(merged.layers.snap);
    }
    if (Array.isArray(delta.appendLogItems)) {
      merged.logItems = mergeLogItems(merged.logItems || state.currentLogItems || [], delta.appendLogItems);
      renderLog(merged.logItems || []);
    }

    state.lastMapPayload = merged;
    if (state.timelinePreviewActive) {
      const slider = document.getElementById('map-timeline-slider');
      const pct = slider ? (parseInt(slider.value, 10) / parseInt(slider.max, 10)) : 1;
      const targetTs = state.timelineMinTs + (state.timelineMaxTs - state.timelineMinTs) * (Number.isFinite(pct) ? pct : 1);
      applyTimelineFilter(targetTs);
    } else {
      updateStatistics(merged.stats || {}, merged.meta || {});
      applyMapFocus(merged.layers || {});
    }
  }


  export function setupMapLayers() {
    // Heatmap Layer (Ganz unten)
    state.map.addLayer({
      id: 'layer-heatmap', type: 'heatmap', source: SOURCE_IDS.HEATMAP,
      paint: {
        'heatmap-weight': ['interpolate', ['linear'], ['get', 'weight'], 0, 0, 1, 1],
        'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 0, 1, 19, 3],
        'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(0,100,255,0)', 0.2, '#0A84FF', 0.4, '#30D158', 0.6, '#FF9F0A', 0.8, '#FF453A', 1, '#FFD60A'],
        'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 0, 2, 19, 20],
        'heatmap-opacity': 0.8
      }
    });

    // Polylines
    state.map.addLayer({
      id: 'layer-lines-casing', type: 'line', source: SOURCE_IDS.LINES,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 8, 'line-opacity': 0.15 }
    });
    state.map.addLayer({
      id: 'layer-lines', type: 'line', source: SOURCE_IDS.LINES,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 2.5, 'line-opacity': 0.9 }
    });
    state.map.addLayer({
      id: 'layer-line-labels', type: 'symbol', source: SOURCE_IDS.LINES,
      filter: ['!=', ['get', 'label'], ' - '],
      layout: {
        'symbol-placement': 'line-center',
        'text-field': ['get', 'label'],
        'text-size': 11,
        'text-font': ['Open Sans Semibold', 'Arial Unicode MS Regular'],
        'text-offset': [0, -1.1],
        'text-allow-overlap': false,
      },
      paint: {
        'text-color': '#FFFFFF',
        'text-halo-color': 'rgba(0,0,0,0.65)',
        'text-halo-width': 1.2,
      }
    });

    // Accuracy Areas
    state.map.addLayer({
      id: 'layer-accuracy-fill', type: 'fill', source: SOURCE_IDS.ACCURACY,
      paint: { 'fill-color': '#0A84FF', 'fill-opacity': 0.08 }
    });
    state.map.addLayer({
      id: 'layer-accuracy', type: 'line', source: SOURCE_IDS.ACCURACY,
      paint: { 'line-color': '#0A84FF', 'line-opacity': 0.32, 'line-width': 1.5 }
    });

    // Points
    state.map.addLayer({
      id: 'layer-points', type: 'circle', source: SOURCE_IDS.POINTS,
      filter: ['!', ['has', 'point_count']],
      paint: { 'circle-radius': 4, 'circle-color': '#0A84FF', 'circle-stroke-width': 1, 'circle-stroke-color': '#fff', 'circle-opacity': 0.8 }
    });

    // OPTIMIZATION: Cluster Layer
    state.map.addLayer({
      id: 'layer-points-clusters', type: 'circle', source: SOURCE_IDS.POINTS,
      filter: ['has', 'point_count'],
      paint: {
        'circle-color': ['step', ['get', 'point_count'], '#51bbd6', 100, '#f1f075', 750, '#f28cb1'],
        'circle-radius': ['step', ['get', 'point_count'], 15, 100, 20, 750, 25],
        'circle-stroke-width': 1, 'circle-stroke-color': '#fff'
      }
    });

    state.map.addLayer({
      id: 'layer-points-cluster-count', type: 'symbol', source: SOURCE_IDS.POINTS,
      filter: ['has', 'point_count'],
      layout: {
        'text-field': '{point_count_abbreviated}',
        'text-font': ['Open Sans Semibold', 'Arial Unicode MS Regular'],
        'text-size': 12
      },
      paint: { 'text-color': '#ffffff' }
    });

    // Latest Point
    state.map.addLayer({
      id: 'layer-latest', type: 'circle', source: SOURCE_IDS.LATEST,
      paint: { 'circle-radius': 8, 'circle-color': '#30D158', 'circle-stroke-width': 2, 'circle-stroke-color': '#fff' }
    });
    state.map.addLayer({
      id: 'layer-speed', type: 'line', source: SOURCE_IDS.SPEED,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 4, 'line-opacity': 0.95 }
    });
    state.map.addLayer({
      id: 'layer-daytracks', type: 'line', source: SOURCE_IDS.DAYTRACKS,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': ['get', 'color'], 'line-width': 3.5, 'line-opacity': 0.9 }
    });
    state.map.addLayer({
      id: 'layer-snap', type: 'line', source: SOURCE_IDS.SNAP,
      layout: { 'line-join': 'round', 'line-cap': 'round' },
      paint: { 'line-color': '#30D158', 'line-width': 3, 'line-opacity': 0.9, 'line-dasharray': [1.2, 1.2] }
    });
    state.map.addLayer({
      id: 'layer-stops', type: 'circle', source: SOURCE_IDS.STOPS,
      paint: {
        'circle-radius': 7,
        'circle-color': '#BF5AF2',
        'circle-opacity': 0.2,
        'circle-stroke-width': 2,
        'circle-stroke-color': '#BF5AF2',
        'circle-stroke-opacity': 0.95
      }
    });
    state.map.addLayer({
      id: 'layer-stops-labels', type: 'symbol', source: SOURCE_IDS.STOPS,
      layout: {
        'text-field': ['get', 'label'],
        'text-size': 11,
        'text-font': ['Open Sans Semibold', 'Arial Unicode MS Regular'],
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
      },
      paint: {
        'text-color': '#FFFFFF',
        'text-halo-color': 'rgba(0,0,0,0.65)',
        'text-halo-width': 1.2,
      }
    });
    
    // Popups
    state.map.on('click', 'layer-points', (e) => {
      const p = e.features[0].properties;
      if (document.getElementById('point-detail-panel')) {
        window.showPointDetails(p, e.lngLat);
      }
      const content = document.createElement('div');
      const title = document.createElement('strong');
      title.textContent = 'GPS-Punkt';
      content.appendChild(title);
      content.appendChild(document.createElement('br'));
      const timestamp = document.createElement('span');
      timestamp.textContent = p.timestamp == null ? '' : String(p.timestamp);
      content.appendChild(timestamp);
      content.appendChild(document.createElement('br'));
      const accuracy = document.createElement('span');
      const accuracyValue = Number(p.accuracy);
      accuracy.textContent = `±${Number.isFinite(accuracyValue) ? Math.round(accuracyValue) : 0}m`;
      content.appendChild(accuracy);
      new maplibregl.Popup().setLngLat(e.lngLat).setDOMContent(content).addTo(state.map);
    });
    state.map.on('mouseenter', 'layer-points', () => state.map.getCanvas().style.cursor = 'pointer');
    state.map.on('mouseleave', 'layer-points', () => state.map.getCanvas().style.cursor = '');
  }
