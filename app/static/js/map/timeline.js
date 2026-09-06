// Timeline/Replay: Datensatz-Aufbau, Scrubber, Play/Pause, Geschwindigkeits-
// stufen, Marker-/Aktivitätsstreifen und die zugehörige DOM-Verdrahtung.
// Importiert renderMapPayload/renderLog/updateStatistics/updateMapOverlayLayout
// aus layers.js (zyklische, aber rein funktionsbasierte Abhängigkeit - siehe
// Kommentar in layers.js).
import { state, timelinePreviewCache } from './state.js';
import { escapeHtml, storageSet, fetchWithRetry, supportsAbortController } from '../map-page-utils.js';
import { buildCurrentFilters, updateMap } from './network.js';
import { renderMapPayload, renderLog, updateStatistics, updateMapOverlayLayout } from './layers.js';

  export function updateTimelineToggleButton() {
    const button = document.getElementById('mtc-btn');
    if (!button) return;
    button.style.opacity = state.timelineVisible ? '1' : '0.72';
    button.title = state.timelineVisible ? 'Timeline ausblenden' : 'Timeline einblenden';
    button.setAttribute('aria-pressed', String(state.timelineVisible));
  }


  export function applyTimelineVisibilityState() {
    const container = document.getElementById('map-timeline-container');
    const button = document.getElementById('mtc-btn');
    const hasTimelineData = state.timelinePoints.length > 1 && (state.timelineMaxTs - state.timelineMinTs) >= 1000;
    if (button) {
      button.disabled = !hasTimelineData;
      button.style.cursor = hasTimelineData ? 'pointer' : 'default';
      button.style.opacity = hasTimelineData ? (state.timelineVisible ? '1' : '0.72') : '0.5';
    }
    if (container) {
      container.style.display = hasTimelineData && state.timelineVisible ? 'block' : 'none';
    }
    if ((!hasTimelineData || !state.timelineVisible) && state.timelineIsPlaying) {
      state.timelineIsPlaying = false;
      clearTimeout(state.timelinePlayTimer);
      const playButton = document.getElementById('timeline-play-btn');
      if (playButton) {
        playButton.textContent = '▶';
        playButton.setAttribute('aria-pressed', 'false');
        playButton.setAttribute('aria-label', 'Wiedergabe starten');
      }
    }
    updateMapOverlayLayout();
    updateTimelineToggleButton();
    updateTimelineModeLabel();
  }


  export function updateTimelineModeLabel(labelOverride = null) {
    const label = document.getElementById('timeline-mode-label');
    const sourceLabel = document.getElementById('timeline-source-label');
    if (!label || !sourceLabel) return;
    let text = labelOverride;
    let color = '#0A84FF';
    if (!text) {
      if (state.timelineIsPlaying) {
        text = `Playback ${state.timelinePlaybackRate}x${state.timelineReplayLive ? ' Live' : ''}`;
        color = '#BF5AF2';
      } else if (state.timelinePreviewActive) {
        text = 'Vorschau';
        color = '#FF9F0A';
      } else {
        text = 'Live';
        color = '#30D158';
      }
    }
    label.textContent = text;
    label.style.color = color;
    label.style.background = `color-mix(in srgb, ${color} 14%, transparent)`;
    label.style.borderColor = `color-mix(in srgb, ${color} 28%, transparent)`;
    sourceLabel.textContent = state.timelineSourceSummaryText || (state.timelineSourceMode === 'filter' ? 'Aktueller Filter' : 'Sichtbarer Bereich');
  }


  export function cancelTimelinePreviewRequests() {
    state.timelinePreviewToken += 1;
    if (state.timelinePreviewController && typeof state.timelinePreviewController.abort === 'function') {
      state.timelinePreviewController.abort();
    }
    state.timelinePreviewController = null;
  }


  export function normalizeTimelinePoint(point) {
    return {
      id: point.id,
      lat: point.lat != null ? point.lat : point.latitude,
      lon: point.lon != null ? point.lon : point.longitude,
      timestampUtc: point.timestampUtc || point.point_timestamp_utc,
      point_timestamp_utc: point.point_timestamp_utc || point.timestampUtc,
      timestampLocal: point.timestampLocal || point.point_timestamp_local || point.point_timestamp_utc,
      accuracyM: point.accuracyM != null ? point.accuracyM : point.horizontal_accuracy_m,
      source: point.source,
      session_id: point.session_id || point.sessionId,
      captureMode: point.captureMode || point.capture_mode,
      isLatest: !!point.isLatest
    };
  }


  export function haversineMeters(a, b) {
    const toRad = deg => deg * (Math.PI / 180);
    const radius = 6371000;
    const dLat = toRad(b.lat - a.lat);
    const dLon = toRad(b.lon - a.lon);
    const lat1 = toRad(a.lat);
    const lat2 = toRad(b.lat);
    const root = Math.sin(dLat / 2) ** 2 + Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLon / 2) ** 2;
    return 2 * radius * Math.asin(Math.sqrt(root));
  }


  export function buildClientTimelineMarkers(points) {
    const markers = [];
    let previousDay = null;
    for (let index = 0; index < points.length; index += 1) {
      const point = points[index];
      const day = String(point.timestampLocal || point.timestampUtc || '').slice(0, 10);
      if (day && day !== previousDay) {
        markers.push({ type: 'day', timestampUtc: point.timestampUtc, label: day });
      }
      previousDay = day;
    }
    let anchorIndex = 0;
    while (anchorIndex < points.length) {
      const anchor = points[anchorIndex];
      let cursor = anchorIndex + 1;
      while (cursor < points.length && haversineMeters(anchor, points[cursor]) <= state.STOP_RADIUS_M) cursor += 1;
      if (cursor - anchorIndex > 1) {
        const startTs = new Date(anchor.timestampUtc).getTime();
        const endTs = new Date(points[cursor - 1].timestampUtc).getTime();
        const durationMin = Math.round((endTs - startTs) / 60000);
        if (durationMin >= state.STOP_MIN_DUR) {
          markers.push({ type: 'stop', timestampUtc: anchor.timestampUtc, label: `Stop ${durationMin} min`, durationMin });
        }
      }
      anchorIndex = Math.max(cursor, anchorIndex + 1);
    }
    return markers;
  }


  export function buildTimelineQueryKey() {
    const params = buildCurrentFilters();
    params.delete('zoom');
    params.delete('log_limit');
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
    params.delete('latest_known_ts');
    if (state.timelineSourceMode !== 'viewport') params.delete('bbox');
    return JSON.stringify({
      mode: state.timelineSourceMode,
      query: params.toString(),
    });
  }


  export function buildTimelineFetchUrl() {
    const params = buildCurrentFilters();
    params.delete('zoom');
    params.delete('log_limit');
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
    params.delete('latest_known_ts');
    if (state.timelineSourceMode !== 'viewport') params.delete('bbox');
    params.set('limit', String(Math.max(2000, state.MAP_MAX_POINTS)));
    return `/api/timeline?${params.toString()}`;
  }


  export function buildTimelinePreviewUrl(selectedTs) {
    const params = buildCurrentFilters();
    params.delete('latest_known_ts');
    params.set('include_heatmap', 'false');
    params.set('include_speed', 'false');
    params.set('include_stops', 'false');
    params.set('include_daytrack', 'false');
    params.set('include_snap', 'false');
    if (state.timelineSourceMode === 'filter') params.delete('bbox');
    params.set('date_to', new Date(selectedTs).toISOString());
    return `/api/timeline-preview?${params.toString()}`;
  }


  export function buildTimelineMarkerStrip() {
    const strip = document.getElementById('timeline-marker-strip');
    if (!strip) return;
    if (!state.timelineMarkers.length || state.timelineMaxTs <= state.timelineMinTs) {
      strip.innerHTML = '';
      return;
    }
    strip.innerHTML = state.timelineMarkers.map(marker => {
      const ts = new Date(marker.timestampUtc).getTime();
      const ratio = Math.max(0, Math.min(1, (ts - state.timelineMinTs) / Math.max(1, (state.timelineMaxTs - state.timelineMinTs))));
      const color = marker.type === 'stop' ? 'rgba(191,90,242,0.95)' : 'rgba(255,214,10,0.95)';
      const title = `${marker.type === 'stop' ? 'Stop' : 'Tag'} · ${marker.label}`;
      return `<span title="${escapeHtml(title)}" style="position:absolute;left:calc(${(ratio * 100).toFixed(3)}% - 1px);top:0;width:2px;height:10px;border-radius:999px;background:${color};opacity:0.92;"></span>`;
    }).join('');
  }


  export function buildTimelineActivityStrip() {
    const strip = document.getElementById('timeline-activity-strip');
    if (!strip) return;
    if (state.timelinePoints.length < 2 || state.timelineMaxTs <= state.timelineMinTs) {
      strip.innerHTML = '';
      state.timelineActivityNodes = [];
      state.timelineActivityBucketCount = 0;
      return;
    }
    const bucketCount = Math.max(24, Math.min(60, Math.round((document.getElementById('map-timeline-card')?.clientWidth || 320) / 8)));
    if (state.timelineActivityBucketCount !== bucketCount || state.timelineActivityNodes.length !== bucketCount) {
      strip.innerHTML = '';
      state.timelineActivityNodes = [];
      state.timelineActivityBucketCount = bucketCount;
      for (let index = 0; index < bucketCount; index += 1) {
        const node = document.createElement('span');
        node.style.flex = '1';
        node.style.borderRadius = '999px';
        strip.appendChild(node);
        state.timelineActivityNodes.push(node);
      }
    }
    const buckets = new Array(bucketCount).fill(0);
    state.timelinePoints.forEach(point => {
      const ts = new Date(point.timestampUtc || point.point_timestamp_utc).getTime();
      const ratio = Math.max(0, Math.min(0.9999, (ts - state.timelineMinTs) / Math.max(1, (state.timelineMaxTs - state.timelineMinTs))));
      buckets[Math.min(bucketCount - 1, Math.floor(ratio * bucketCount))] += 1;
    });
    const maxBucket = Math.max(...buckets, 1);
    buckets.forEach((count, index) => {
      const height = Math.max(3, Math.round((count / maxBucket) * 18));
      const ts = state.timelineMinTs + ((index + 0.5) / bucketCount) * (state.timelineMaxTs - state.timelineMinTs);
      const active = state.timelineSelectedTs && ts <= state.timelineSelectedTs;
      const node = state.timelineActivityNodes[index];
      if (!node) return;
      node.style.height = `${height}px`;
      node.style.background = active ? 'rgba(48,209,88,0.95)' : 'rgba(255,255,255,0.16)';
    });
  }


  export function findTimelineIndexAtOrBefore(targetTs) {
    if (!state.timelinePoints.length) return -1;
    let low = 0;
    let high = state.timelinePoints.length - 1;
    let best = -1;
    while (low <= high) {
      const mid = Math.floor((low + high) / 2);
      const ts = new Date(state.timelinePoints[mid].timestampUtc || state.timelinePoints[mid].point_timestamp_utc).getTime();
      if (ts <= targetTs) {
        best = mid;
        low = mid + 1;
      } else {
        high = mid - 1;
      }
    }
    return best < 0 ? 0 : best;
  }


  export function getTimelinePointTs(index) {
    if (index < 0 || index >= state.timelinePoints.length) return null;
    return new Date(state.timelinePoints[index].timestampUtc || state.timelinePoints[index].point_timestamp_utc).getTime();
  }


  export function getNextTimelineTimestamp(currentTs, direction = 1) {
    if (!state.timelinePoints.length) return null;
    const mode = String(state.timelineStepMode || 'points:1');
    if (mode.startsWith('points:')) {
      const stepPoints = Math.max(1, parseInt(mode.split(':')[1], 10) || 1);
      const currentIndex = findTimelineIndexAtOrBefore(currentTs);
      const nextIndex = Math.max(0, Math.min(state.timelinePoints.length - 1, currentIndex + (stepPoints * direction)));
      return getTimelinePointTs(nextIndex);
    }
    if (mode.startsWith('seconds:')) {
      const seconds = Math.max(1, parseInt(mode.split(':')[1], 10) || 30);
      const targetTs = currentTs + (seconds * 1000 * direction);
      return Math.max(state.timelineMinTs, Math.min(state.timelineMaxTs, targetTs));
    }
    return null;
  }


  export function applyTimelineAutoFollow(latestPoint) {
    if (!state.timelineAutoFollow || !latestPoint || !state.map) return;
    state.suppressedViewportRefreshes += 1;
    state.map.easeTo({ center: [latestPoint.lon, latestPoint.lat], duration: 280, essential: true });
  }


  export function buildLocalTimelinePreviewPayload(selectedTs) {
    if (!state.lastMapPayload) return null;
    const cutoff = Number.isFinite(selectedTs) ? selectedTs : state.timelineMaxTs;
    const sourcePoints = (state.timelinePoints || []).filter(point => new Date(point.timestampUtc || point.point_timestamp_utc || 0).getTime() <= cutoff);
    const previewPoints = sourcePoints
      .slice()
      .sort((a, b) => String(b.timestampUtc || b.point_timestamp_utc || '').localeCompare(String(a.timestampUtc || a.point_timestamp_utc || '')))
      .map(point => Object.assign({}, point, { isLatest: false }));
    const latestPoint = previewPoints.length ? Object.assign({}, previewPoints[0], { isLatest: true }) : null;
    const filteredLog = (state.lastMapPayload.logItems || [])
      .filter(item => new Date(item.timestampUtc || item.timestampLocal || 0).getTime() <= cutoff)
      .sort((a, b) => String(b.timestampUtc || b.timestampLocal || '').localeCompare(String(a.timestampUtc || a.timestampLocal || '')));
    const avgAccuracy = previewPoints.length
      ? previewPoints.reduce((sum, point) => sum + (Number(point.accuracyM) || 0), 0) / previewPoints.length
      : 0;
    const firstTs = previewPoints.length ? new Date(previewPoints[previewPoints.length - 1].timestampUtc || previewPoints[previewPoints.length - 1].point_timestamp_utc || 0).getTime() : 0;
    const lastTs = previewPoints.length ? new Date(previewPoints[0].timestampUtc || previewPoints[0].point_timestamp_utc || 0).getTime() : 0;
    const durationSeconds = previewPoints.length > 1 ? Math.max(0, Math.round((lastTs - firstTs) / 1000)) : 0;
    const pointsPerMinute = durationSeconds > 0 ? (previewPoints.length / (durationSeconds / 60)) : previewPoints.length;
    return {
      processing: state.lastMapPayload.processing || null,
      meta: Object.assign({}, state.lastMapPayload.meta || {}, { visiblePoints: previewPoints.length }),
      stats: Object.assign({}, state.lastMapPayload.stats || {}, {
        avgAccuracyM: avgAccuracy,
        pointsPerMinute,
        sessionDurationSeconds: durationSeconds
      }),
      layers: Object.assign({}, state.lastMapPayload.layers || {}, {
        points: previewPoints,
        latestPoint,
        heatmap: [],
        polylines: [],
        accuracy: [],
        speed: [],
        stops: [],
        daytracks: [],
        snap: []
      }),
      logItems: filteredLog
    };
  }


  export async function loadTimelinePreview(selectedTs) {
    if (!state.timelinePreviewActive || !state.lastMapPayload) return;
    const cacheKey = `${buildCurrentFilters().toString()}::${Math.floor(selectedTs / 1000)}`;
    if (timelinePreviewCache.has(cacheKey)) {
      const cached = timelinePreviewCache.get(cacheKey);
      renderMapPayload(cached, { skipFocus: true, skipTimeline: true });
      renderLog(cached.logItems || []);
      updateStatistics(cached.stats || {}, cached.meta || {});
      applyTimelineAutoFollow(cached.layers && cached.layers.latestPoint ? cached.layers.latestPoint : null);
      return;
    }
    const token = ++state.timelinePreviewToken;
    if (state.timelinePreviewController && typeof state.timelinePreviewController.abort === 'function') state.timelinePreviewController.abort();
    state.timelinePreviewController = supportsAbortController ? new AbortController() : null;
    try {
      const response = await fetchWithRetry(buildTimelinePreviewUrl(selectedTs), {
        credentials: 'same-origin',
        signal: state.timelinePreviewController ? state.timelinePreviewController.signal : undefined,
      });
      if (!response.ok) throw new Error(`Timeline preview HTTP ${response.status}`);
      const payload = await response.json();
      if (token !== state.timelinePreviewToken) return;
      timelinePreviewCache.set(cacheKey, payload);
      if (timelinePreviewCache.size > 24) timelinePreviewCache.delete(timelinePreviewCache.keys().next().value);
      renderMapPayload(payload, { skipFocus: true, skipTimeline: true });
      renderLog(payload.logItems || []);
      updateStatistics(payload.stats || {}, payload.meta || {});
      applyTimelineAutoFollow(payload.layers && payload.layers.latestPoint ? payload.layers.latestPoint : null);
    } catch (error) {
      if (error.name === 'AbortError') return;
      console.warn('Timeline-Vorschau nutzt lokalen Fallback:', error);
      const fallback = buildLocalTimelinePreviewPayload(selectedTs);
      if (fallback) {
        renderMapPayload(fallback, { skipFocus: true, skipTimeline: true });
        renderLog(fallback.logItems || []);
        updateStatistics(fallback.stats || {}, fallback.meta || {});
        applyTimelineAutoFollow(fallback.layers && fallback.layers.latestPoint ? fallback.layers.latestPoint : null);
      }
    }
  }


  export async function ensureTimelineDataset(viewportPoints) {
    if (state.timelineSourceMode !== 'filter') {
      state.timelineSourcePoints = (viewportPoints || []).map(normalizeTimelinePoint);
      state.timelineMarkers = buildClientTimelineMarkers(state.timelineSourcePoints);
      state.timelineSourceSummaryText = 'Sichtbarer Bereich';
      state.timelineLoadedQueryKey = null;
      return state.timelineSourcePoints;
    }
    const queryKey = buildTimelineQueryKey();
    if (state.timelineLoadedQueryKey === queryKey && state.timelineSourcePoints.length) return state.timelineSourcePoints;
    updateTimelineModeLabel('Laden');
    const token = ++state.timelineFetchToken;
    const response = await fetchWithRetry(buildTimelineFetchUrl(), { credentials: 'same-origin' });
    if (!response.ok) throw new Error(`Timeline HTTP ${response.status}`);
    const payload = await response.json();
    if (token !== state.timelineFetchToken) return state.timelineSourcePoints;
    const items = payload && payload.timeline && payload.timeline.items ? payload.timeline.items : [];
    state.timelineMarkers = payload && payload.timeline && Array.isArray(payload.timeline.markers) ? payload.timeline.markers : [];
    state.timelineSourcePoints = items.map(normalizeTimelinePoint);
    if (payload && payload.timeline && payload.timeline.meta) {
      const meta = payload.timeline.meta;
      if (meta.minTimestampUtc) state.timelineMinTs = new Date(meta.minTimestampUtc).getTime();
      if (meta.maxTimestampUtc) state.timelineMaxTs = new Date(meta.maxTimestampUtc).getTime();
      state.timelineSourceSummaryText = meta.truncated
        ? `Aktueller Filter · ${meta.sampledCount}/${meta.rawCount}`
        : 'Aktueller Filter';
    }
    state.timelineLoadedQueryKey = queryKey;
    return state.timelineSourcePoints;
  }


  export function resetTimelineToLive() {
    const slider = document.getElementById('map-timeline-slider');
    if (!slider) return;
    cancelTimelinePreviewRequests();
    slider.value = slider.max;
    state.timelineSelectedTs = state.timelineMaxTs || null;
    storageSet('map-timeline-selected-ts', state.timelineSelectedTs ? String(state.timelineSelectedTs) : '');
    applyTimelineFilter(state.timelineMaxTs || 0);
  }


  export function applyTimelineDataset(points) {
    if (!points || points.length < 2) {
      cancelTimelinePreviewRequests();
      state.timelinePreviewActive = false;
      state.timelinePoints = [];
      state.timelineMinTs = 0;
      state.timelineMaxTs = 0;
      state.timelineMarkers = [];
      state.timelineSourceSummaryText = null;
      applyTimelineVisibilityState();
      return;
    }
    
    // Zeitlich sortieren für den Slider
    state.timelinePoints = (points || []).slice().sort((a, b) => new Date(a.timestampUtc || a.point_timestamp_utc).getTime() - new Date(b.timestampUtc || b.point_timestamp_utc).getTime());
    state.timelineMinTs = new Date(state.timelinePoints[0].timestampUtc || state.timelinePoints[0].point_timestamp_utc).getTime();
    state.timelineMaxTs = new Date(state.timelinePoints[state.timelinePoints.length - 1].timestampUtc || state.timelinePoints[state.timelinePoints.length - 1].point_timestamp_utc).getTime();
    
    if (state.timelineMaxTs - state.timelineMinTs < 1000) { // Zu kurzer Zeitraum
      cancelTimelinePreviewRequests();
      state.timelinePreviewActive = false;
      state.timelinePoints = [];
      state.timelineMinTs = 0;
      state.timelineMaxTs = 0;
      state.timelineMarkers = [];
      state.timelineSourceSummaryText = null;
      applyTimelineVisibilityState();
      return;
    }

    applyTimelineVisibilityState();
    buildTimelineMarkerStrip();
    buildTimelineActivityStrip();
    document.getElementById('timeline-start-label').textContent = new Date(state.timelineMinTs).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' });
    document.getElementById('timeline-end-label').textContent = new Date(state.timelineMaxTs).toLocaleString('de-DE', { hour: '2-digit', minute: '2-digit' });
    
    const slider = document.getElementById('map-timeline-slider');
    if (state.timelineSelectedTs && state.timelineSelectedTs >= state.timelineMinTs && state.timelineSelectedTs <= state.timelineMaxTs) {
      const pctFromTs = (state.timelineSelectedTs - state.timelineMinTs) / Math.max(1, (state.timelineMaxTs - state.timelineMinTs));
      slider.value = String(Math.max(0, Math.min(parseInt(slider.max, 10), Math.round(pctFromTs * parseInt(slider.max, 10)))));
    } else {
      slider.value = slider.max;
      state.timelineSelectedTs = state.timelineMaxTs;
    }
    const pct = parseInt(slider.value, 10) / parseInt(slider.max, 10);
    const targetTs = state.timelineMinTs + (state.timelineMaxTs - state.timelineMinTs) * (Number.isFinite(pct) ? pct : 1);
    applyTimelineFilter(targetTs);
  }


  export function updateTimeline(points) {
    ensureTimelineDataset(points)
      .then(applyTimelineDataset)
      .catch(error => {
        console.warn('Timeline-Daten konnten nicht geladen werden:', error);
        state.timelineSourceMode = 'viewport';
        storageSet('map-timeline-source', 'viewport');
        state.timelineSourcePoints = (points || []).map(normalizeTimelinePoint);
        state.timelineMarkers = buildClientTimelineMarkers(state.timelineSourcePoints);
        state.timelineSourceSummaryText = 'Sichtbarer Bereich';
        applyTimelineDataset(state.timelineSourcePoints);
      });
  }


  export function applyTimelineFilter(selectedTs) {
    if (!state.map || !state.map.isStyleLoaded()) return;
    
    const date = new Date(selectedTs);
    state.timelineSelectedTs = Number.isFinite(selectedTs) ? Math.round(selectedTs) : null;
    storageSet('map-timeline-selected-ts', state.timelineSelectedTs ? String(state.timelineSelectedTs) : '');
    const timeText = date.toLocaleTimeString('de-DE', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const dateText = date.toLocaleDateString('de-DE', { day: '2-digit', month: 'short', year: '2-digit' });
    document.getElementById('timeline-current-time').textContent = timeText;
    document.getElementById('timeline-current-date').textContent = dateText;
    document.getElementById('map-timeline-slider')?.setAttribute('aria-valuetext', `${dateText} ${timeText}`);

    const count = state.timelinePoints.filter(p => new Date(p.timestampUtc || p.point_timestamp_utc).getTime() <= selectedTs).length;
    document.getElementById('timeline-info-points').textContent = `${count.toLocaleString('de-DE')} Punkte`;
    buildTimelineActivityStrip();
    state.timelinePreviewActive = selectedTs < state.timelineMaxTs;
    if (!state.lastMapPayload || !state.timelinePreviewActive) {
      cancelTimelinePreviewRequests();
      if (state.lastMapPayload) {
        renderMapPayload(state.lastMapPayload, { skipTimeline: true });
        renderLog(state.lastMapPayload.logItems || []);
        updateStatistics(state.lastMapPayload.stats || {}, state.lastMapPayload.meta || {});
      }
      applyTimelineVisibilityState();
      return;
    }
    loadTimelinePreview(selectedTs);
    applyTimelineVisibilityState();
  }


  export function toggleTimelinePlay() {
    state.timelineIsPlaying = !state.timelineIsPlaying;
    const btn = document.getElementById('timeline-play-btn');
    btn.textContent = state.timelineIsPlaying ? '⏸' : '▶';
    btn.setAttribute('aria-pressed', String(state.timelineIsPlaying));
    btn.setAttribute('aria-label', state.timelineIsPlaying ? 'Wiedergabe pausieren' : 'Wiedergabe starten');

    if (state.timelineIsPlaying) {
      if (!state.timelineVisible) {
        state.timelineVisible = true;
        storageSet('map-timeline-visible', '1');
        applyTimelineVisibilityState();
      }
      const slider = document.getElementById('map-timeline-slider');
      if (parseInt(slider.value) >= parseInt(slider.max)) slider.value = 0;
      
      const step = () => {
        if (!state.timelineIsPlaying) return;
        const currentPct = parseInt(slider.value, 10) / parseInt(slider.max, 10);
        const currentTs = state.timelineMinTs + (state.timelineMaxTs - state.timelineMinTs) * currentPct;
        const nextTs = getNextTimelineTimestamp(currentTs, 1);
        if (nextTs !== null && nextTs < state.timelineMaxTs) {
          const nextPct = (nextTs - state.timelineMinTs) / Math.max(1, (state.timelineMaxTs - state.timelineMinTs));
          slider.value = String(Math.max(0, Math.min(parseInt(slider.max, 10), Math.round(nextPct * parseInt(slider.max, 10)))));
          slider.dispatchEvent(new Event('input'));
          state.timelinePlayTimer = setTimeout(step, Math.max(40, Math.round(140 / Math.max(0.5, state.timelinePlaybackRate))));
        } else if (state.timelineReplayLive) {
          slider.value = slider.max;
          slider.dispatchEvent(new Event('input'));
          state.timelinePlayTimer = setTimeout(step, Math.max(120, Math.round(400 / Math.max(0.5, state.timelinePlaybackRate))));
        } else {
          toggleTimelinePlay();
        }
      };
      step();
    } else {
      clearTimeout(state.timelinePlayTimer);
    }
    updateTimelineModeLabel();
  }


  document.addEventListener('DOMContentLoaded', () => {
    const slider = document.getElementById('map-timeline-slider');
    slider.oninput = (e) => {
      const pct = e.target.value / e.target.max;
      const targetTs = state.timelineMinTs + (state.timelineMaxTs - state.timelineMinTs) * pct;
      applyTimelineFilter(targetTs);
    };
    document.getElementById('timeline-play-btn').onclick = toggleTimelinePlay;
    document.getElementById('timeline-start-btn').onclick = () => {
      if (!state.timelinePoints.length) return;
      slider.value = '0';
      slider.dispatchEvent(new Event('input'));
    };
    document.getElementById('timeline-end-btn').onclick = resetTimelineToLive;
    document.getElementById('timeline-prev-btn').onclick = () => {
      if (!state.timelinePoints.length) return;
      slider.value = String(Math.max(0, parseInt(slider.value, 10) - Math.max(1, Math.round(8 * state.timelinePlaybackRate))));
      slider.dispatchEvent(new Event('input'));
    };
    document.getElementById('timeline-next-btn').onclick = () => {
      if (!state.timelinePoints.length) return;
      slider.value = String(Math.min(parseInt(slider.max, 10), parseInt(slider.value, 10) + Math.max(1, Math.round(8 * state.timelinePlaybackRate))));
      slider.dispatchEvent(new Event('input'));
    };
    document.getElementById('timeline-live-btn').onclick = resetTimelineToLive;
    const speedSelect = document.getElementById('timeline-speed-select');
    speedSelect.value = String(state.timelinePlaybackRate);
    speedSelect.onchange = (event) => {
      state.timelinePlaybackRate = parseFloat(event.target.value) || 1;
      storageSet('map-timeline-speed', String(state.timelinePlaybackRate));
      updateTimelineModeLabel();
    };
    const stepSelect = document.getElementById('timeline-step-select');
    stepSelect.value = state.timelineStepMode;
    stepSelect.onchange = (event) => {
      state.timelineStepMode = String(event.target.value || 'points:1');
      storageSet('map-timeline-step', state.timelineStepMode);
    };
    const replayToggle = document.getElementById('timeline-replay-live-toggle');
    replayToggle.checked = state.timelineReplayLive;
    replayToggle.onchange = (event) => {
      state.timelineReplayLive = !!event.target.checked;
      storageSet('map-timeline-replay-live', state.timelineReplayLive ? '1' : '0');
    };
    const autoFollowToggle = document.getElementById('timeline-autofollow-toggle');
    autoFollowToggle.checked = state.timelineAutoFollow;
    autoFollowToggle.onchange = (event) => {
      state.timelineAutoFollow = !!event.target.checked;
      storageSet('map-timeline-autofollow', state.timelineAutoFollow ? '1' : '0');
    };
    const sourceSelect = document.getElementById('timeline-source-select');
    sourceSelect.value = state.timelineSourceMode;
    sourceSelect.onchange = (event) => {
      cancelTimelinePreviewRequests();
      state.timelineSourceMode = event.target.value === 'filter' ? 'filter' : 'viewport';
      storageSet('map-timeline-source', state.timelineSourceMode);
      state.timelineLoadedQueryKey = null;
      state.timelineSourcePoints = [];
      state.timelineMarkers = [];
      state.timelineSourceSummaryText = null;
      if (state.lastMapPayload && state.lastMapPayload.layers) updateTimeline(state.lastMapPayload.layers.points || []);
      else applyTimelineVisibilityState();
    };
    const retryButton = document.getElementById('map-loading-retry');
    if (retryButton) {
      retryButton.onclick = () => {
        state.isManualRefresh = true;
        state.lastETag = null;
        updateMap();
      };
    }
    updateTimelineModeLabel();
    updateTimelineToggleButton();
  });

