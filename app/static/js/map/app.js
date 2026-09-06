// Bootstrap/Einstiegspunkt der Kartenseite: verdrahtet beim Laden alle
// Event-Handler (Buttons, Checkboxen, Tastatur/Fokus, Fullscreen, mobiles
// Filter-Panel inkl. ARIA-Synchronisation) und initialisiert MapLibre.
//
// Wichtig: In einem <script type="module"> sind Top-Level-Deklarationen NICHT
// automatisch auf `window` sichtbar (anders als im vorherigen klassischen
// <script>). Für inline onclick="..."-Attribute in map.html (toggleFilterPanel,
// toggleLocationMenu, locateBrowserPosition, focusLatestPoint) müssen die
// jeweiligen Funktionen daher explizit auf window gehängt werden - siehe
// Fußzeile dieser Datei bzw. network.js für focusLatestPoint.
import {
  state, MAP_CONFIG, QUERY_SESSION_ID, QUERY_IMPORT_SESSION, MAP_PAGE_SIZE_SAFE_MAX,
  SOURCE_IDS, layerDataLoaded,
} from './state.js';
import { storageGet, storageSet, scheduleTask } from '../map-page-utils.js';
import {
  updateMap, debouncedMapRefresh, clampMapMaxPoints, clampLogLimit, scheduleNextMapUpdate,
  exportGeoJSON, clearLocalMirror, updateLocalMirrorStatus, focusInitialGlobalLatestPoint,
  tickRefreshBar, isFatalMapError, showMapRecovery, showToast, setWebSocketStatus, initSSE, closeSSE,
} from './network.js';
import {
  updateLayerVisibility, updateLegend, updateLegendPlacement, updateLegendToggleButton,
  updateMapOverlayLayout, isWebglSupported, setupMapLayers, renderLog,
} from './layers.js';
import {
  applyTimelineVisibilityState, updateTimelineToggleButton, updateTimelineModeLabel,
} from './timeline.js';

const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
const supportsNativeFullscreen = !!document.documentElement.requestFullscreen;
const supportsResizeObserver = typeof window.ResizeObserver === 'function';

  export function clearMobileModalIsolation() {
    if (!state.mobileModalIsolation) return;
    for (const [element, state] of state.mobileModalIsolation.regions) {
      if (state.hadInert) {
        element.setAttribute('inert', '');
        if ('inert' in element) element.inert = true;
      } else {
        element.removeAttribute('inert');
        if ('inert' in element) element.inert = false;
      }
      if (state.ariaHidden === null) element.removeAttribute('aria-hidden');
      else element.setAttribute('aria-hidden', state.ariaHidden);
    }
    state.mobileModalIsolation = null;
  }

  // Keep the open mobile surface and its optional backdrop interactive while
  // making every other visible document region unavailable to assistive tech
  // and keyboard navigation.  Walking around ancestors is important here:
  // both surfaces live inside the map page and must not make their own parent
  // inert by accident.

  export function isolateMobileModal(modal, extras = []) {
    clearMobileModalIsolation();
    if (!modal || !isMobileFilter() || modal.hidden) return;

    const keep = [modal, ...extras].filter(Boolean);
    const regions = new Map();
    const visit = (element) => {
      if (!(element instanceof Element) || keep.includes(element)) return;
      const containsKeptElement = keep.some((kept) => element.contains(kept));
      if (!containsKeptElement) {
        regions.set(element, {
          hadInert: element.hasAttribute('inert'),
          ariaHidden: element.getAttribute('aria-hidden'),
        });
        element.setAttribute('inert', '');
        if ('inert' in element) element.inert = true;
        element.setAttribute('aria-hidden', 'true');
        return;
      }
      Array.from(element.children).forEach(visit);
    };

    Array.from(document.body.children).forEach(visit);
    state.mobileModalIsolation = { regions };
  }


  window.showPointDetails = function showPointDetails(properties, lngLat) {
    const panel = document.getElementById('point-detail-panel');
    if (!panel) return false;

    if (!panel.hidden && document.activeElement && panel.contains(document.activeElement)) {
      state.pointDetailsRestoreFocus = null;
    } else if (document.activeElement && typeof document.activeElement.focus === 'function') {
      state.pointDetailsRestoreFocus = document.activeElement;
    }

    const props = properties && typeof properties === 'object' ? properties : {};
    const value = (key) => {
      const item = props[key];
      return item === null || item === undefined ? '' : String(item);
    };
    const setText = (id, text, fallback = '—') => {
      const element = document.getElementById(id);
      if (element) element.textContent = text || fallback;
    };

    const timestamp = value('timestamp') || value('point_timestamp') || value('timestampLocal');
    const accuracyNumber = Number(props.accuracy ?? props.accuracyM);
    const accuracy = Number.isFinite(accuracyNumber) ? `±${Math.round(accuracyNumber)} m` : '';
    const lng = lngLat && typeof lngLat === 'object' ? Number(lngLat.lng) : Number(lngLat?.[0]);
    const lat = lngLat && typeof lngLat === 'object' ? Number(lngLat.lat) : Number(lngLat?.[1]);
    const coordinates = Number.isFinite(lat) && Number.isFinite(lng)
      ? `${lat.toFixed(6)}, ${lng.toFixed(6)}`
      : '';

    setText('point-detail-time', timestamp);
    setText('point-detail-accuracy', accuracy);
    setText('point-detail-coordinates', coordinates);
    panel.hidden = false;
    panel.setAttribute('aria-hidden', 'false');
    panel.setAttribute('aria-modal', String(isMobileFilter()));
    if (isMobileFilter()) isolateMobileModal(panel);

    const closeButton = document.getElementById('point-detail-close');
    if (closeButton) closeButton.focus({ preventScroll: true });
    return true;
  };


  export function closePointDetails() {
    const panel = document.getElementById('point-detail-panel');
    if (!panel) return;
    panel.hidden = true;
    panel.setAttribute('aria-hidden', 'true');
    panel.setAttribute('aria-modal', 'false');
    clearMobileModalIsolation();
    const restore = state.pointDetailsRestoreFocus;
    state.pointDetailsRestoreFocus = null;
    if (restore && document.contains(restore) && typeof restore.focus === 'function') {
      restore.focus({ preventScroll: true });
    }
  }


  export function getFocusableElements(container) {
    if (!container) return [];
    return Array.from(container.querySelectorAll(
      'a[href], area[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    )).filter(element => !element.hidden && element.getAttribute('aria-hidden') !== 'true');
  }


  export function isMobileFilter() {
    return window.matchMedia ? window.matchMedia('(max-width: 767px)').matches : window.innerWidth <= 767;
  }


  export function focusModalPanel(event, panel) {
    if (!panel || !isMobileFilter()) return;
    const focusable = getFocusableElements(panel);
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.key === 'Tab' && event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (event.key === 'Tab' && !event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }


  export function focusFilterPanel(event) {
    const panel = document.getElementById('map-filter-panel');
    if (!panel || !state.filtersExpanded) return;
    focusModalPanel(event, panel);
  }



  export function toggleLocationMenu(forceState) {
    const menu = document.getElementById('location-selection-menu');
    if (!menu) return;
    const nextState = typeof forceState === 'boolean' ? forceState : (menu.style.display === 'none' || menu.style.display === '');
    menu.style.display = nextState ? 'flex' : 'none';
    const btn = document.getElementById('browser-location-btn');
    if (btn) btn.setAttribute('aria-expanded', String(nextState));
  }


  export function toggleQuickCtrl(forceState) {
    const ctrl = document.getElementById('map-quick-ctrl');
    if (!ctrl) return;
    const nextState = typeof forceState === 'boolean' ? forceState : !ctrl.classList.contains('mqc-open');
    ctrl.classList.toggle('mqc-open', nextState);
    const btn = document.getElementById('mqc-btn');
    if (btn) btn.setAttribute('aria-expanded', String(nextState));
  }


  export function toggleFilterPanel(show) {
    const panel = document.getElementById('map-filter-panel');
    const button = document.getElementById('fp-show-btn');
    const backdrop = document.getElementById('fp-backdrop');
    if (!panel || !button || !backdrop) return;
    if (show && !state.filtersExpanded && document.activeElement && typeof document.activeElement.focus === 'function') {
      state.filterRestoreFocus = document.activeElement;
    }
    panel.classList.toggle('fp-open', show);
    backdrop.classList.toggle('fp-open', show);
    state.filtersExpanded = show;
    button.dataset.open = show ? '1' : '0';
    button.textContent = show ? '✕ Filter' : '☰ Filter';
    button.setAttribute('aria-expanded', String(show));
    panel.setAttribute('aria-hidden', String(!show));
    panel.setAttribute('aria-modal', String(show && isMobileFilter()));
    backdrop.setAttribute('aria-hidden', String(!show));
    if (show && isMobileFilter()) isolateMobileModal(panel, [backdrop]);
    else clearMobileModalIsolation();
    storageSet('map-fp-hidden', show ? '0' : '1');
    if (state.map) setTimeout(() => state.map.resize(), 250);
    if (show && isMobileFilter()) {
      setTimeout(() => {
        const closeButton = document.getElementById('fp-hide-btn');
        (closeButton || panel).focus({ preventScroll: true });
      }, 0);
    } else if (!show) {
      const restore = state.filterRestoreFocus;
      state.filterRestoreFocus = null;
      if (restore && document.contains(restore) && typeof restore.focus === 'function') {
        restore.focus({ preventScroll: true });
      }
    }
  }


  export function setDropdown(id, active) {
    const element = document.getElementById(id);
    element.disabled = !active;
    element.classList.toggle('fp-inactive', !active);
  }


  export function setupMobileFilterToggle() {
    const toggleBtn = document.getElementById('map-filter-toggle-btn');
    const filterPanel = document.querySelector('.map-filter-panel');
    if (!toggleBtn || !filterPanel) return;
    const isMobile = window.innerWidth <= 767;
    if (isMobile) {
      toggleBtn.style.display = 'block';
      if (toggleBtn.dataset.init !== '1') {
        toggleBtn.dataset.init = '1';
        filterPanel.classList.add('collapsed');
        state.filtersExpanded = false;
      }
    } else {
      toggleBtn.style.display = 'none';
      filterPanel.classList.remove('collapsed');
      state.filtersExpanded = true;
      toggleBtn.dataset.init = '0';
      filterPanel.setAttribute('aria-modal', 'false');
      clearMobileModalIsolation();
    }
  }


  export function applyFullscreenLayout(active) {
    const wrap = document.getElementById('map-wrap');
    const container = document.getElementById('map-container');
    if (!wrap || !container) return;
    if (active) {
      wrap.style.position = 'fixed';
      wrap.style.top = '0';
      wrap.style.left = '0';
      wrap.style.width = '100vw';
      wrap.style.height = '100dvh';
      wrap.style.zIndex = '9999';
      wrap.style.margin = '0';
      wrap.style.background = '#000';
      wrap.style.overflow = 'hidden';
      container.style.width = '100%';
      container.style.height = '100%';
      container.style.borderRadius = '0';
      container.style.margin = '0';
      document.getElementById('fullscreen-btn').innerHTML = '✕ <span>Vollbild</span>';
      document.getElementById('fullscreen-btn').title = 'Vollbild beenden';
      document.getElementById('fullscreen-btn').setAttribute('aria-pressed', 'true');
    } else {
      wrap.style.position = 'relative';
      wrap.style.top = '';
      wrap.style.left = '';
      wrap.style.width = '';
      wrap.style.height = '';
      wrap.style.zIndex = '';
      wrap.style.margin = '';
      wrap.style.background = '';
      wrap.style.overflow = '';
      container.style.width = '';
      container.style.height = '';
      container.style.borderRadius = '';
      container.style.margin = '';
      document.getElementById('fullscreen-btn').innerHTML = '⛶ <span>Vollbild</span>';
      document.getElementById('fullscreen-btn').title = 'Vollbild';
      document.getElementById('fullscreen-btn').setAttribute('aria-pressed', 'false');
    }
    if (state.map) state.map.resize();
    updateLegendPlacement();
  }


  export function activateCssFullscreen() {
    if (!state.cssFsActive) {
      state.cssFsActive = true;
      applyFullscreenLayout(true);
      return;
    }
    state.cssFsActive = false;
    applyFullscreenLayout(false);
  }


  export function toggleFullscreen() {
    const wrap = document.getElementById('map-wrap');
    if (!isIOS && supportsNativeFullscreen) {
      if (!document.fullscreenElement) {
        wrap.requestFullscreen().catch(() => activateCssFullscreen());
      } else {
        document.exitFullscreen();
      }
      return;
    }
    activateCssFullscreen();
  }


  export function showIOSBanner() {
    if (!isIOS || window.navigator.standalone || sessionStorage.getItem('ios-banner-dismissed')) return;
    const banner = document.createElement('div');
    banner.id = 'ios-home-banner';
    banner.style.cssText = 'position:fixed; bottom:24px; left:50%; transform:translateX(-50%); background:#1C1C1E; border:1px solid rgba(255,255,255,0.12); border-radius:16px; padding:14px 16px; z-index:10000; display:flex; align-items:flex-start; gap:12px; max-width:calc(100vw - 32px); box-shadow:0 8px 32px rgba(0,0,0,0.6); font-family:-apple-system,system-ui,sans-serif;';
    banner.innerHTML = '<div style="font-size:1.6rem;flex-shrink:0;margin-top:2px;">⊕</div><div style="flex:1;min-width:0;"><div style="font-size:0.85rem;font-weight:700;color:#fff;margin-bottom:3px;">Zum Home-Bildschirm hinzufügen</div><div style="font-size:0.75rem;color:rgba(255,255,255,0.55);line-height:1.4;">Tippe auf <strong style="color:#fff;">Teilen ↑</strong> und dann <strong style="color:#fff;">„Zum Home-Bildschirm"</strong> — danach steht echter Vollbild zur Verfügung.</div></div><button style="background:none;border:none;color:rgba(255,255,255,0.4);font-size:1.1rem;cursor:pointer;flex-shrink:0;padding:0;line-height:1;">✕</button>';
    banner.querySelector('button').onclick = () => {
      banner.remove();
      sessionStorage.setItem('ios-banner-dismissed', '1');
    };
    document.body.appendChild(banner);
  }


  export function resetBrowserLocationButton() {
    const button = document.getElementById('browser-location-btn');
    if (!button) return;
    button.innerHTML = '◎ <span>Standort</span>';
    button.disabled = false;
    button.title = 'Aktuellen Browser-Standort abrufen';
  }


  export function locateBrowserPosition() {
    const button = document.getElementById('browser-location-btn');
    if (!button) return;
    if (!navigator.geolocation) {
      showToast('Der Browser unterstützt keine Standortabfrage.', 'error');
      return;
    }

    if (!confirm('Darf dein aktueller Standort präzise abgerufen werden? (Dies kann einige Sekunden dauern)')) {
      return;
    }

    button.disabled = true;
    button.innerHTML = '⌛ <span>Standort</span>';
    button.title = 'Präziser Standort wird abgerufen…';
    
    navigator.geolocation.getCurrentPosition(
      (position) => {
        const lat = position.coords.latitude;
        const lon = position.coords.longitude;
        const accuracy = Math.max(0, Math.round(position.coords.accuracy || 0));
        
        state.map.getSource(SOURCE_IDS.LATEST).setData({
          type: 'FeatureCollection',
          features: [{ 
            type: 'Feature', 
            geometry: { type: 'Point', coordinates: [lon, lat] }, 
            properties: { isLatest: true, isBrowser: true, accuracy: accuracy } 
          }]
        });

        state.map.flyTo({ center: [lon, lat], zoom: 17, speed: 1.2, essential: true });
        resetBrowserLocationButton();
      },
      (error) => {
        resetBrowserLocationButton();
        let msg = 'Standortabfrage fehlgeschlagen.';
        if (error.code === 1) msg = 'Standortfreigabe im Browser verweigert.';
        else if (error.code === 3) msg = 'Zeitüberschreitung (bitte erneut versuchen).';
        showToast(msg, 'error');
      },
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
  }


  export function initMap() {
    if (state.mapInitInProgress) return;
    state.mapInitInProgress = true;
    state.mapReady = false;
    state.mapInitFailed = false;
    const recovery = document.getElementById('map-init-recovery');
    if (recovery) recovery.hidden = true;
    try {
      initSSE();
    
    state.MAP_MAX_POINTS = clampMapMaxPoints(state.MAP_MAX_POINTS);
    
    const style = {
      version: 8,
      sources: {
        'osm': {
          type: 'raster',
          tiles: [
            state.darkMode 
              ? 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
              : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png'
          ],
          tileSize: 256,
          attribution: state.darkMode ? '&copy; OpenStreetMap Contributors &middot; &copy; CARTO' : '&copy; OpenStreetMap Contributors'
        }
      },
      layers: [{ id: 'osm', type: 'raster', source: 'osm' }]
    };

      if (typeof window.maplibregl === 'undefined' || typeof window.maplibregl.Map !== 'function') {
        throw new Error('MapLibre konnte nicht geladen werden.');
      }
      if (!isWebglSupported()) {
        throw new Error('WebGL wird auf diesem Browser/Gerät nicht unterstützt.');
      }

    const mapOptions = {
      container: 'map-container',
      style: style,
      center: [13.405, 52.52],
      zoom: 10,
      pitch: state.pitch3DActive ? 45 : 0,
      hash: false,
      antialias: !isIOS
    };

      try {
        state.map = new maplibregl.Map(mapOptions);
      } catch (error) {
        if (!isIOS) throw error;
        console.warn('MapLibre iOS-Fallback aktiv:', error);
        state.map = new maplibregl.Map(Object.assign({}, mapOptions, { pitch: 0, antialias: false }));
        state.pitch3DActive = false;
        storageSet('map-pitch-3d', '0');
        document.getElementById('pitch-toggle-btn')?.setAttribute('aria-pressed', 'false');
      }

      state.map.on('error', (event) => {
        if (isFatalMapError(event)) showMapRecovery(event.error, state.mapReady ? 'Karten-Rendering' : 'Karteninitialisierung');
      });

    state.map.addControl(new maplibregl.NavigationControl({ visualizePitch: true }), 'top-left');
    state.map.addControl(new maplibregl.ScaleControl({ maxWidth: 80, unit: 'metric' }));

    function forceMapResize() {
      if (!state.map || typeof state.map.resize !== 'function') return;
      requestAnimationFrame(() => {
        state.map.resize();
        updateMapOverlayLayout();
        setTimeout(() => state.map.resize(), 250);
      });
    }

    state.map.on('load', () => {
      try {
      if (state.mapInitFailed) return;
      // Sources initialisieren
      Object.keys(SOURCE_IDS).map(key => SOURCE_IDS[key]).forEach(id => {
        const sourceOptions = { type: 'geojson', data: { type: 'FeatureCollection', features: [] } };
        // OPTIMIZATION: Enable clustering for the points layer
        if (id === SOURCE_IDS.POINTS) {
          Object.assign(sourceOptions, {
            cluster: true,
            clusterMaxZoom: 13,
            clusterRadius: 50
          });
        }
        state.map.addSource(id, sourceOptions);
      });
      // Layer initialisieren (Reihenfolge ist wichtig für Z-Index)
      setupMapLayers();
      forceMapResize();
      
      document.getElementById('pitch-toggle-btn')?.setAttribute('aria-pressed', String(state.pitch3DActive));
      document.getElementById('dark-mode-btn')?.setAttribute('aria-pressed', String(state.darkMode));
      updateLegend();
      updateLegendPlacement();
      updateLegendToggleButton();
      updateTimelineToggleButton();
      updateTimelineModeLabel();
      applyTimelineVisibilityState();
      updateMapOverlayLayout();
      if (state.isInitialLoad) {
        state.isInitialLoad = false;
        scheduleTask(() => focusInitialGlobalLatestPoint());
      }
        state.mapReady = true;
        state.mapInitInProgress = false;
        if (recovery) recovery.hidden = true;
        updateMap();
      } catch (error) {
        state.mapInitInProgress = false;
        showMapRecovery(error, 'Karteninitialisierung');
      }
    });

    document.getElementById('map-max-points').max = String(Math.max(1, Math.min(MAP_CONFIG.pointsPageSizeMax || 2000, MAP_PAGE_SIZE_SAFE_MAX)));
    document.getElementById('map-max-points').value = state.MAP_MAX_POINTS;
    document.getElementById('log-limit').value = clampLogLimit(state.LOG_LIMIT);
    document.getElementById('route-time-gap').value = state.ROUTE_TIME_GAP;
    document.getElementById('route-dist-gap').value = state.ROUTE_DIST_GAP;
    document.getElementById('stop-min-duration').value = state.STOP_MIN_DUR;
    document.getElementById('stop-radius').value = state.STOP_RADIUS_M;
    document.getElementById('polling-interval').value = String(state.POLLING_INTERVAL);
    document.getElementById('fit-bounds-mode').value = state.FIT_BOUNDS_MODE;
    document.getElementById('time-range-select').value = state.TIME_RANGE;

    // Apply Deep-Link Filters from Query Params
    if (QUERY_SESSION_ID) {
      document.getElementById('session-filter-toggle').checked = true;
      const select = document.getElementById('session-select-dropdown');
      select.disabled = false;
      select.value = QUERY_SESSION_ID;
      // Ensure import filter is off
      document.getElementById('import-filter-toggle').checked = false;
      document.getElementById('import-select-dropdown').disabled = true;
      document.getElementById('import-select-dropdown').value = '';
    } else if (QUERY_IMPORT_SESSION) {
      document.getElementById('import-filter-toggle').checked = true;
      const select = document.getElementById('import-select-dropdown');
      select.disabled = false;
      select.value = QUERY_IMPORT_SESSION;
      // Ensure session filter is off
      document.getElementById('session-filter-toggle').checked = false;
      document.getElementById('session-select-dropdown').disabled = true;
      document.getElementById('session-select-dropdown').value = '';
    }

    if (supportsResizeObserver) {
      const resizeObserver = new ResizeObserver(() => forceMapResize());
      resizeObserver.observe(document.getElementById('map-container'));
    } else {
      window.addEventListener('resize', forceMapResize);
    }
    window.addEventListener('orientationchange', () => setTimeout(forceMapResize, 350));
    if (window.visualViewport && typeof window.visualViewport.addEventListener === 'function') {
      window.visualViewport.addEventListener('resize', forceMapResize);
    }

    state.map.on('moveend', () => {
      if (state.suppressedViewportRefreshes > 0) {
        state.suppressedViewportRefreshes -= 1;
        return;
      }
      debouncedMapRefresh();
    });

    state.barTickTimer = setInterval(tickRefreshBar, 1000);
    } catch (error) {
      state.mapInitInProgress = false;
      showMapRecovery(error, 'Karteninitialisierung');
    }
  }


  document.addEventListener('click', (event) => {
    const pointPanel = document.getElementById('point-detail-panel');
    if (pointPanel && event.target === pointPanel) closePointDetails();
    if (event.target.closest?.('#point-detail-close')) closePointDetails();

    const locMenu = document.getElementById('location-selection-menu');
    if (locMenu && !locMenu.contains(event.target)) toggleLocationMenu(false);

    const ctrl = document.getElementById('map-layer-ctrl');
    if (ctrl && !ctrl.contains(event.target)) {
      ctrl.classList.remove('mlc-open');
      document.getElementById('mlc-btn')?.setAttribute('aria-expanded', 'false');
    }
    const quickCtrl = document.getElementById('map-quick-ctrl');
    if (quickCtrl && !quickCtrl.contains(event.target)) {
      quickCtrl.classList.remove('mqc-open');
      document.getElementById('mqc-btn')?.setAttribute('aria-expanded', 'false');
    }
  });


  document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && state.cssFsActive) activateCssFullscreen();
    const filterPanel = document.getElementById('map-filter-panel');
    if (filterPanel && state.filtersExpanded && isMobileFilter()) {
      if (event.key === 'Escape') {
        event.preventDefault();
        toggleFilterPanel(false);
        return;
      }
      focusFilterPanel(event);
    }
    const pointPanel = document.getElementById('point-detail-panel');
    if (pointPanel && !pointPanel.hidden && isMobileFilter()) {
      if (event.key === 'Escape') {
        event.preventDefault();
        closePointDetails();
        return;
      }
      focusModalPanel(event, pointPanel);
    }
    if (event.key === 'Escape') {
      closePointDetails();
      const fpBtn = document.getElementById('fp-show-btn');
      if (fpBtn && fpBtn.dataset.open === '1') toggleFilterPanel(false);
    }
  });


  document.addEventListener('fullscreenchange', () => {
    if (state.cssFsActive) return;
    const active = !!document.fullscreenElement;
    applyFullscreenLayout(active);
  });

  document.getElementById('mqc-btn').onclick = () => toggleQuickCtrl();
  document.getElementById('mtc-btn').onclick = () => {
    state.timelineVisible = !state.timelineVisible;
    storageSet('map-timeline-visible', state.timelineVisible ? '1' : '0');
    applyTimelineVisibilityState();
  };
  document.getElementById('refresh-map-btn').onclick = () => {
    state.isManualRefresh = true;
    state.forceGlobalLatestFocus = true;
    state.lastETag = null;
    clearTimeout(state.updateTimer);
    document.getElementById('btn-text').style.display = 'none';
    document.getElementById('btn-spinner').style.display = 'inline';
    if (state.currentFetchController) state.currentFetchController.abort();
    updateMap();
  };
  document.getElementById('time-range-select').onchange = (event) => {
    state.TIME_RANGE = event.target.value;
    storageSet('map-time-range', state.TIME_RANGE);
    debouncedMapRefresh();
  };
  document.getElementById('polling-interval').onchange = (event) => {
    state.POLLING_INTERVAL = parseInt(event.target.value, 10) || 5000;
    storageSet('map-polling-interval', String(state.POLLING_INTERVAL));
    scheduleNextMapUpdate(state.POLLING_INTERVAL);
    tickRefreshBar();
  };
  document.getElementById('fit-bounds-mode').onchange = (event) => {
    state.FIT_BOUNDS_MODE = event.target.value === 'visible' ? 'visible' : 'global';
    storageSet('map-fit-bounds-mode', state.FIT_BOUNDS_MODE);
    if (document.getElementById('fit-bounds-toggle').checked) debouncedMapRefresh();
  };
  document.getElementById('map-max-points').onchange = (event) => {
    state.MAP_MAX_POINTS = clampMapMaxPoints(event.target.value);
    event.target.value = state.MAP_MAX_POINTS;
    document.getElementById('log-limit').value = clampLogLimit(document.getElementById('log-limit').value);
    storageSet('map-max-points', String(state.MAP_MAX_POINTS));
    debouncedMapRefresh();
  };
  document.getElementById('route-time-gap').onchange = (event) => {
    state.ROUTE_TIME_GAP = parseInt(event.target.value, 10) || 5;
    storageSet('map-route-time-gap', String(state.ROUTE_TIME_GAP));
    debouncedMapRefresh();
  };
  document.getElementById('route-dist-gap').onchange = (event) => {
    state.ROUTE_DIST_GAP = parseInt(event.target.value, 10) || 300;
    storageSet('map-route-dist-gap', String(state.ROUTE_DIST_GAP));
    debouncedMapRefresh();
  };
  document.getElementById('stop-min-duration').onchange = (event) => {
    state.STOP_MIN_DUR = parseInt(event.target.value, 10) || 5;
    storageSet('map-stop-min-dur', String(state.STOP_MIN_DUR));
    if (state.stopsActive) debouncedMapRefresh();
  };
  document.getElementById('stop-radius').onchange = (event) => {
    state.STOP_RADIUS_M = parseInt(event.target.value, 10) || 100;
    storageSet('map-stop-radius', String(state.STOP_RADIUS_M));
    if (state.stopsActive) debouncedMapRefresh();
  };
  document.getElementById('log-limit').onchange = (event) => {
    state.LOG_LIMIT = clampLogLimit(event.target.value);
    event.target.value = state.LOG_LIMIT;
    storageSet('map-log-limit', String(state.LOG_LIMIT));
    debouncedMapRefresh();
  };
  document.getElementById('log-search').oninput = () => renderLog(state.currentLogItems);
  document.getElementById('dark-mode-btn').onclick = () => {
    state.darkMode = !state.darkMode;
    storageSet('map-dark-mode', String(state.darkMode));
    document.getElementById('dark-mode-btn').innerHTML = `${state.darkMode ? '☀️' : '🌙'} <span>Dark</span>`;
    document.getElementById('dark-mode-btn').title = state.darkMode ? 'Helle Karte' : 'Dunkle Karte';
    document.getElementById('dark-mode-btn').setAttribute('aria-pressed', String(state.darkMode));

    const nextTileUrl = state.darkMode
      ? 'https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'
      : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
      
    const osmSource = state.map.getSource('osm');
    if (osmSource) {
      osmSource.setTiles([nextTileUrl]);
    }
  };
  document.getElementById('legend-toggle-btn').onclick = () => {
    state.legendVisible = !state.legendVisible;
    storageSet('map-legend-visible', state.legendVisible ? '1' : '0');
    updateLegend();
  };
  document.getElementById('browser-location-btn').onclick = (event) => {
    event.stopPropagation();
    toggleLocationMenu();
  };
  document.getElementById('pitch-toggle-btn').onclick = () => {
    state.pitch3DActive = !state.pitch3DActive;
    storageSet('map-pitch-3d', state.pitch3DActive ? '1' : '0');
    document.getElementById('pitch-toggle-btn').setAttribute('aria-pressed', String(state.pitch3DActive));
    state.map.easeTo({ pitch: state.pitch3DActive ? 45 : 0, duration: 800 });
  };
  document.getElementById('fullscreen-btn').onclick = toggleFullscreen;
  document.getElementById('export-geojson-btn').onclick = exportGeoJSON;
  document.getElementById('local-mirror-clear-btn').onclick = clearLocalMirror;
  document.getElementById('fit-bounds-toggle').onchange = (event) => {
    if (event.target.checked) document.getElementById('auto-center-toggle').checked = false;
    updateMap();
  };
  document.getElementById('auto-center-toggle').onchange = (event) => {
    if (event.target.checked) document.getElementById('fit-bounds-toggle').checked = false;
  };

  document.getElementById('heatmap-toggle').onchange = (event) => { state.heatmapActive = event.target.checked; updateLegend(); if (state.heatmapActive && !layerDataLoaded.heatmap) debouncedMapRefresh(); else updateLayerVisibility('heatmap', state.heatmapActive); };
  document.getElementById('points-toggle').onchange = (event) => { state.pointsActive = event.target.checked; updateLegend(); if (state.pointsActive && !layerDataLoaded.points) debouncedMapRefresh(); else updateLayerVisibility('points', state.pointsActive); };
  document.getElementById('polyline-toggle').onchange = (event) => { state.polylineActive = event.target.checked; updateLegend(); if (state.polylineActive && !layerDataLoaded.polyline) debouncedMapRefresh(); else updateLayerVisibility('polyline', state.polylineActive); };
  document.getElementById('accuracy-toggle').onchange = (event) => { state.accuracyActive = event.target.checked; updateLegend(); if (state.accuracyActive && !layerDataLoaded.accuracy) debouncedMapRefresh(); else updateLayerVisibility('accuracy', state.accuracyActive); };
  document.getElementById('labels-toggle').onchange = (event) => { state.labelsActive = event.target.checked; updateLegend(); if (state.labelsActive && !layerDataLoaded.labels) debouncedMapRefresh(); else updateLayerVisibility('labels', state.labelsActive); };
  document.getElementById('speed-toggle').onchange = (event) => { state.speedActive = event.target.checked; updateLegend(); if (state.speedActive && !layerDataLoaded.speed) debouncedMapRefresh(); else updateLayerVisibility('speed', state.speedActive); };
  document.getElementById('stops-toggle').onchange = (event) => {
    state.stopsActive = event.target.checked;
    document.getElementById('stops-config').style.display = state.stopsActive ? '' : 'none';
    event.target.setAttribute('aria-expanded', String(state.stopsActive));
    updateLegend();
    if (state.stopsActive && !layerDataLoaded.stops) debouncedMapRefresh();
    else updateLayerVisibility('stops', state.stopsActive);
  };
  document.getElementById('daytrack-toggle').onchange = (event) => { state.daytrackActive = event.target.checked; updateLegend(); if (state.daytrackActive && !layerDataLoaded.daytrack) debouncedMapRefresh(); else updateLayerVisibility('daytrack', state.daytrackActive); };
  document.getElementById('snap-toggle').onchange = (event) => { state.snapActive = event.target.checked; updateLegend(); if (state.snapActive && !layerDataLoaded.snap) debouncedMapRefresh(); else updateLayerVisibility('snap', state.snapActive); };

  document.getElementById('session-filter-toggle').onchange = (event) => {
    setDropdown('session-select-dropdown', event.target.checked);
    if (event.target.checked) {
      document.getElementById('import-filter-toggle').checked = false;
      setDropdown('import-select-dropdown', false);
      document.getElementById('import-select-dropdown').value = '';
    } else {
      document.getElementById('session-select-dropdown').value = '';
    }
    debouncedMapRefresh();
  };
  document.getElementById('session-select-dropdown').onchange = debouncedMapRefresh;
  document.getElementById('import-filter-toggle').onchange = (event) => {
    setDropdown('import-select-dropdown', event.target.checked);
    if (event.target.checked) {
      document.getElementById('session-filter-toggle').checked = false;
      setDropdown('session-select-dropdown', false);
      document.getElementById('session-select-dropdown').value = '';
    } else {
      document.getElementById('import-select-dropdown').value = '';
    }
    debouncedMapRefresh();
  };
  document.getElementById('import-select-dropdown').onchange = debouncedMapRefresh;


  (() => {
    const toggleBtn = document.getElementById('map-filter-toggle-btn');
    const filterPanel = document.querySelector('.map-filter-panel');
    toggleBtn.onclick = () => {
      state.filtersExpanded = !state.filtersExpanded;
      filterPanel.classList.toggle('collapsed', !state.filtersExpanded);
      toggleBtn.textContent = state.filtersExpanded ? 'Filteroptionen ▲' : 'Filteroptionen ▼';
      toggleBtn.setAttribute('aria-expanded', String(state.filtersExpanded));
    };
  })();


  document.addEventListener('DOMContentLoaded', () => {
    toggleFilterPanel(storageGet('map-fp-hidden', '0') !== '1');
    setupMobileFilterToggle();
    showIOSBanner();
    const toastClose = document.getElementById('map-toast-close');
    if (toastClose) toastClose.onclick = () => {
      clearTimeout(state.mapToastTimer);
      const toast = document.getElementById('map-toast');
      if (toast) toast.hidden = true;
    };
    const mapRecoveryRetry = document.getElementById('map-init-recovery-retry');
    if (mapRecoveryRetry) {
      mapRecoveryRetry.addEventListener('click', () => {
        mapRecoveryRetry.disabled = true;
        mapRecoveryRetry.textContent = 'Wird erneut versucht…';
        if (state.barTickTimer) {
          clearInterval(state.barTickTimer);
          state.barTickTimer = null;
        }
        if (state.socket) {
          const failedSocket = state.socket;
          state.socket = null;
          failedSocket.close(1000, 'Karteninitialisierung wird wiederholt');
        }
        if (state.socketReconnectTimer) {
          clearTimeout(state.socketReconnectTimer);
          state.socketReconnectTimer = null;
          state.socketReconnectScheduled = false;
        }
        try { state.map?.remove?.(); } catch (error) { console.warn('Fehler beim Zurücksetzen der Karte:', error); }
        state.map = null;
        setTimeout(() => {
          mapRecoveryRetry.disabled = false;
          mapRecoveryRetry.textContent = 'Erneut versuchen';
          initMap();
        }, 0);
      });
    }
    const filterBackdrop = document.getElementById('fp-backdrop');
    if (filterBackdrop) {
      filterBackdrop.addEventListener('keydown', (event) => {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          toggleFilterPanel(false);
        }
      });
    }
    initMap();
    void updateLocalMirrorStatus();

    document.addEventListener('visibilitychange', () => {
      if (document.hidden) {
        clearTimeout(state.updateTimer);
        state.updateTimer = null;
        state.nextRefreshTime = 0;
        if (state.socketReconnectTimer) {
          clearTimeout(state.socketReconnectTimer);
          state.socketReconnectTimer = null;
          state.socketReconnectScheduled = false;
        }
        if (state.socket) {
          const pausedSocket = state.socket;
          state.socket = null;
          pausedSocket.close(1000, 'Tab verborgen');
        }
        closeSSE();
        state.liveTransport = 'polling';
        setWebSocketStatus('pausiert – Tab verborgen', 'info', 60000);
        return;
      }
      setWebSocketStatus('aktualisiere nach Rückkehr…', 'info', 5000);
      initSSE();
      updateMap();
    });
  });

  window.addEventListener('resize', setupMobileFilterToggle);

  window.addEventListener('resize', () => {
    const filterPanel = document.getElementById('map-filter-panel');
    const pointPanel = document.getElementById('point-detail-panel');
    if (isMobileFilter()) {
      if (filterPanel && state.filtersExpanded) isolateMobileModal(filterPanel, [document.getElementById('fp-backdrop')]);
      else if (pointPanel && !pointPanel.hidden) isolateMobileModal(pointPanel);
    } else {
      clearMobileModalIsolation();
      if (filterPanel) filterPanel.setAttribute('aria-modal', 'false');
      if (pointPanel) pointPanel.setAttribute('aria-modal', 'false');
    }
  });

// Inline onclick="..."-Attribute in map.html rufen diese Funktionen im
// globalen Scope auf; ohne diese Zuweisungen wären sie als Modul-Bindings
// nicht erreichbar (siehe Kommentar am Dateianfang).
window.toggleFilterPanel = toggleFilterPanel;
window.toggleLocationMenu = toggleLocationMenu;
window.locateBrowserPosition = locateBrowserPosition;
