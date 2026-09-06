// Geteilter, veränderlicher Zustand der Kartenseite.
//
// Alle Module (network.js, layers.js, timeline.js, app.js) teilen sich genau
// dieses eine `state`-Objekt. Da ES-Module reine Bindings (let/const) nicht
// gegenseitig neu zuweisen können, werden ehemalige globale `let`-Variablen
// aus map-page.js hier als Properties eines einzigen Objekts geführt und
// überall als `state.NAME` gelesen/geschrieben - exakt wie zuvor als
// Closure-Variable, nur explizit statt implizit geteilt.
import { storageGet, storageSet } from '../map-page-utils.js';

export const {
  configSummary: MAP_CONFIG,
  querySessionId: QUERY_SESSION_ID,
  queryImportSession: QUERY_IMPORT_SESSION,
} = window.MAP_BOOTSTRAP || {};

export const RANGE_MINUTES = {
  '2m': 2, '5m': 5, '10m': 10, '15m': 15, '30m': 30, '45m': 45,
  '1h': 60, '2h': 120, '4h': 240, '6h': 360, '8h': 480, '12h': 720, '18h': 1080, '24h': 1440,
  '2d': 2880, '3d': 4320, '5d': 7200, '7d': 10080, '14d': 20160, '30d': 43200
};

export const SOURCE_IDS = {
  POINTS: 'src-points',
  LATEST: 'src-latest',
  LINES: 'src-lines',
  ACCURACY: 'src-accuracy',
  SPEED: 'src-speed',
  STOPS: 'src-stops',
  DAYTRACKS: 'src-daytracks',
  SNAP: 'src-snap',
  HEATMAP: 'src-heatmap'
};

export const layerDataLoaded = {
  heatmap: false,
  points: false,
  polyline: false,
  accuracy: false,
  labels: false,
  speed: false,
  stops: false,
  daytrack: false,
  snap: false
};

export const timelinePreviewCache = new Map();

// Server-seitiges Hard-Limit für Punkte pro Seite, unabhängig von MAP_CONFIG.
export const MAP_PAGE_SIZE_SAFE_MAX = 20000;

// Historische Konstante, aktuell ungenutzt (kein Verweis mehr im Code) - hier
// bewahrt, damit sie nicht stillschweigend verschwindet.
export const CLUSTER_THRESHOLD = 50;

const ROUTE_DEFAULTS_VERSION = '2';
if (storageGet('map-route-defaults-version') !== ROUTE_DEFAULTS_VERSION) {
  if (!storageGet('map-route-time-gap') || storageGet('map-route-time-gap') === '5') {
    storageSet('map-route-time-gap', '15');
  }
  if (!storageGet('map-route-dist-gap') || storageGet('map-route-dist-gap') === '300') {
    storageSet('map-route-dist-gap', '1200');
  }
  storageSet('map-route-defaults-version', ROUTE_DEFAULTS_VERSION);
}

export const state = {
  pointDetailsRestoreFocus: null,
  mobileModalIsolation: null,
  isInitialLoad: true,
  db: null,
  localMirrorAvailable: false,
  localMirrorPruneInFlight: false,
  localMirrorClearInFlight: false,
  POLLING_INTERVAL: parseInt(storageGet('map-polling-interval'), 10) || 30000,
  TIME_RANGE: storageGet('map-time-range', '1h') || '1h',
  FIT_BOUNDS_MODE: storageGet('map-fit-bounds-mode', 'global') || 'global',
  MAP_MAX_POINTS: parseInt(storageGet('map-max-points'), 10) || MAP_CONFIG.pointsPageSizeMax || 2000,
  LOG_LIMIT: parseInt(storageGet('map-log-limit'), 10) || 100,
  ROUTE_TIME_GAP: parseInt(storageGet('map-route-time-gap'), 10) || 15,
  ROUTE_DIST_GAP: parseInt(storageGet('map-route-dist-gap'), 10) || 1200,
  STOP_MIN_DUR: parseInt(storageGet('map-stop-min-dur'), 10) || 5,
  STOP_RADIUS_M: parseInt(storageGet('map-stop-radius'), 10) || 100,
  map: undefined,
  mapReady: false,
  mapInitFailed: false,
  mapInitInProgress: false,
  darkMode: storageGet('map-dark-mode') === 'true' || false,
  cssFsActive: false,
  filtersExpanded: false,
  filterRestoreFocus: null,
  currentFetchController: null,
  currentMetaFetchController: null,
  lastETag: null,
  lastMetaEtag: null,
  updateTimer: null,
  barTickTimer: null,
  lastRefreshTime: null,
  nextRefreshTime: null,
  lastFetchedBbox: null,
  lastFetchedZoom: null,
  isManualRefresh: false,
  mapUpdateInFlight: false,
  pendingMapRefresh: false,
  suppressedViewportRefreshes: 0,
  currentLogItems: [],
  lastMapPayload: null,
  lastMetaPayload: null,
  lastMetaQueryKey: null,
  lastMetaFetchedAtMs: 0,
  lastMapBaseQueryKey: null,
  lastVisiblePointTsUtc: null,
  loadingOverlayTimer: null,
  loadingOverlayShown: false,
  loadingSyncPillTimer: null,
  loadingStartedAtMs: 0,
  persistentRuntimeWarnings: [],
  mapRuntimeWarnings: [],
  legendVisible: storageGet('map-legend-visible', '1') !== '0',
  initialGlobalLatestFocusDone: false,
  forceGlobalLatestFocus: false,
  suppressMapFocusUntil: 0,
  heatmapActive: false,
  pointsActive: true,
  polylineActive: true,
  accuracyActive: false,
  labelsActive: false,
  speedActive: false,
  stopsActive: false,
  daytrackActive: false,
  snapActive: false,
  mapToastTimer: null,
  pitch3DActive: storageGet('map-pitch-3d') === '1',
  timelinePoints: [],
  timelineMinTs: 0,
  timelineMaxTs: 0,
  timelineIsPlaying: false,
  timelinePlayTimer: null,
  timelinePreviewActive: false,
  timelineVisible: storageGet('map-timeline-visible', '1') !== '0',
  timelinePlaybackRate: parseFloat(storageGet('map-timeline-speed', '1')) || 1,
  timelineStepMode: storageGet('map-timeline-step', 'points:1') || 'points:1',
  timelineReplayLive: storageGet('map-timeline-replay-live', '1') !== '0',
  timelineAutoFollow: storageGet('map-timeline-autofollow', '1') !== '0',
  timelineSourceMode: storageGet('map-timeline-source', 'viewport') || 'viewport',
  timelineSelectedTs: parseInt(storageGet('map-timeline-selected-ts', ''), 10) || null,
  timelineLoadedQueryKey: null,
  timelineSourcePoints: [],
  timelineMarkers: [],
  timelineSourceSummaryText: null,
  timelineFetchToken: 0,
  timelinePreviewToken: 0,
  timelinePreviewController: null,
  timelineActivityNodes: [],
  timelineActivityBucketCount: 0,
  socket: null,
  socketReconnectTimer: null,
  socketReconnectAttempt: 0,
  socketReconnectScheduled: false,
  sseSource: null,
  sseReconnectTimer: null,
  sseReconnectAttempt: 0,
  sseReconnectScheduled: false,
  liveTransport: 'polling',
};
