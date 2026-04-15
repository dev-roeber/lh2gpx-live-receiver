/**
 * MapController - Hochmoderne Kartenanwendung
 * Modular, testbar, error-safe
 */

class APIClient {
  static async fetchPoints(range, sessionId, pageSize) {
    const retryConfig = [
      { delay: 1000, attempt: 1 },
      { delay: 3000, attempt: 2 },
      { delay: 10000, attempt: 3 }
    ];

    for (const config of retryConfig) {
      try {
        let url = `/api/points?page_size=${pageSize}`;
        if (sessionId) url += `&session_id=${sessionId}`;

        if (range !== 'all') {
          const mins = { '5m': 5, '15m': 15, '30m': 30, '1h': 60, '3h': 180, '6h': 360, '12h': 720, '24h': 1440, '7d': 10080 }[range];
          const from = new Date(Date.now() - mins * 60000).toISOString();
          url += `&date_from=${from.split('T')[0]}&time_from=${from.split('T')[1].substring(0, 8)}`;
        }

        const res = await fetch(url, { credentials: 'same-origin', timeout: 5000 });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return await res.json();
      } catch (e) {
        if (config.attempt < 3) {
          console.warn(`API retry ${config.attempt}:`, e.message);
          await new Promise(r => setTimeout(r, config.delay));
        } else {
          throw e;
        }
      }
    }
  }
}

class PollingManager {
  constructor(callback) {
    this.callback = callback;
    this.interval = null;
    this.pollingInterval = parseInt(localStorage.getItem('map-polling-interval')) || 5000;
  }

  start() {
    this.interval = setInterval(() => this.callback(), this.pollingInterval);
    this.callback();
  }

  stop() {
    if (this.interval) clearInterval(this.interval);
  }

  updateInterval(newInterval) {
    this.pollingInterval = newInterval;
    localStorage.setItem('map-polling-interval', newInterval);
    this.stop();
    this.start();
  }
}

class MapRenderer {
  constructor(containerId) {
    this.map = L.map(containerId).setView([52.52, 13.405], 10);
    this.pathLayer = L.featureGroup().addTo(this.map);
    this.markerClusterGroup = L.markerClusterGroup().addTo(this.map);
    this.darkMode = localStorage.getItem('map-dark-mode') === 'true' || false;
    this.tileLayer = this.createTileLayer();
    L.control.scale().addTo(this.map);
    setTimeout(() => this.map.invalidateSize(), 600);
  }

  createTileLayer() {
    const osmUrl = this.darkMode
      ? 'https://tiles.stadiamaps.com/tiles/stamen_tonerqant/{z}/{x}/{y}.png'
      : 'https://tile.openstreetmap.org/{z}/{x}/{y}.png';
    return L.tileLayer(osmUrl, { maxZoom: 19, attribution: '© OpenStreetMap' }).addTo(this.map);
  }

  toggleDarkMode() {
    this.darkMode = !this.darkMode;
    localStorage.setItem('map-dark-mode', this.darkMode);
    this.map.removeLayer(this.tileLayer);
    this.tileLayer = this.createTileLayer();
  }

  updateMap(points, autoCenter) {
    this.pathLayer.clearLayers();
    this.markerClusterGroup.clearLayers();

    if (!points || points.length === 0) return;

    const coords = points.map(p => [p.latitude, p.longitude]);
    L.polyline(coords, {color: '#3b82f6', weight: 5, opacity: 0.6}).addTo(this.pathLayer);

    const last = points[0];
    L.circleMarker([last.latitude, last.longitude], {
      radius: 10, color: '#fff', fillColor: '#3b82f6', fillOpacity: 1, weight: 3
    }).addTo(this.pathLayer).bindPopup(`<b>Letzte Position</b><br>${last.point_timestamp_local}<br>Genauigkeit: ${last.horizontal_accuracy_m}m`);

    if (points.length > 50) {
      points.forEach(p => {
        const marker = L.circleMarker([p.latitude, p.longitude], {
          radius: 5, color: '#3b82f6', fillOpacity: 0.7, weight: 1
        });
        this.markerClusterGroup.addLayer(marker);
      });
    }

    if (autoCenter) {
      this.map.setView([last.latitude, last.longitude], 18, {animate: true});
    }
  }
}

class LogManager {
  constructor(tableBodyId) {
    this.tbody = document.getElementById(tableBodyId);
    this.knownIds = new Set();
    this.maxLines = 1000;
  }

  addPoints(points, logLimit) {
    points.forEach(p => {
      if (!this.knownIds.has(p.id)) {
        // Sliding window: remove oldest if max reached
        if (this.knownIds.size >= this.maxLines) {
          const firstRow = this.tbody.lastChild;
          if (firstRow) this.tbody.removeChild(firstRow);
          this.knownIds.delete([...this.knownIds][0]);
        }

        this.knownIds.add(p.id);
        const row = document.createElement('tr');
        row.style.borderBottom = '1px solid #1e293b';
        row.dataset.lat = p.latitude.toFixed(5);
        row.dataset.lon = p.longitude.toFixed(5);
        row.dataset.time = p.point_timestamp_local;

        const ts = p.point_timestamp_utc.split('T');
        row.innerHTML = `
          <td style="padding: 12px 16px; color: #94a3b8;">${ts[0]}</td>
          <td style="padding: 12px 16px; font-weight: 600;">${ts[1].substring(0, 8)}</td>
          <td style="padding: 12px 16px; color: #3b82f6; cursor: pointer;" onclick="navigator.clipboard.writeText('${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}')">${p.latitude.toFixed(5)}, ${p.longitude.toFixed(5)}</td>
          <td style="padding: 12px 16px; color: #64748b;">${p.horizontal_accuracy_m}m</td>
        `;
        this.tbody.insertBefore(row, this.tbody.firstChild);
      }
    });

    while (this.tbody.children.length > logLimit) {
      this.tbody.removeChild(this.tbody.lastChild);
    }
  }

  filterBySearch(query) {
    const rows = this.tbody.querySelectorAll('tr');
    rows.forEach(row => {
      if (!query) {
        row.style.display = '';
        return;
      }
      const match = (row.dataset.lat?.includes(query) ||
                    row.dataset.lon?.includes(query) ||
                    row.dataset.time?.includes(query));
      row.style.display = match ? '' : 'none';
    });
  }
}

// Global instances
let renderer, poller, logger;

window.initMap = function() {
  renderer = new MapRenderer('map-container');
  logger = new LogManager('live-log-body');

  poller = new PollingManager(updateMapData);
  poller.start();

  // Event Listeners
  document.getElementById('polling-interval').onchange = (e) => poller.updateInterval(parseInt(e.target.value));
  document.getElementById('dark-mode-btn').onclick = () => renderer.toggleDarkMode();
  document.getElementById('refresh-map-btn').onclick = updateMapData;
  document.getElementById('time-range-select').onchange = debounce(updateMapData, 300);
  document.getElementById('session-select').onchange = debounce(updateMapData, 300);
  document.getElementById('log-search').oninput = (e) => logger.filterBySearch(e.target.value.toLowerCase());
};

async function updateMapData() {
  const range = document.getElementById('time-range-select').value;
  const sessionId = document.getElementById('session-select').value;
  const logLimit = parseInt(document.getElementById('log-limit').value) || 50;
  const autoCenter = document.getElementById('auto-center-toggle').checked;
  const apiStatus = document.getElementById('api-status');
  const stats = document.getElementById('map-stats-text');

  try {
    apiStatus.textContent = '● LADEN...';
    apiStatus.style.color = '#f59e0b';

    const pageSize = Math.min(logLimit * 2, 250);
    const data = await APIClient.fetchPoints(range, sessionId, pageSize);
    const points = data.points.items;

    renderer.updateMap(points, autoCenter);
    logger.addPoints(points, logLimit);

    stats.innerText = `${data.points.total} Punkte gefunden (${points.length} angezeigt).`;
    apiStatus.textContent = '● ONLINE';
    apiStatus.style.color = '#10b981';
  } catch (e) {
    console.error('Error:', e);
    stats.innerText = 'Fehler beim Laden der Kartendaten.';
    stats.style.color = 'var(--c-crit)';
    apiStatus.textContent = '● FEHLER';
    apiStatus.style.color = '#ef4444';
  } finally {
    document.getElementById('btn-text').style.display = 'inline';
    document.getElementById('btn-spinner').style.display = 'none';
  }
}

function debounce(fn, ms) {
  let timeout;
  return function(...args) {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn.apply(this, args), ms);
  };
}

// Heat Map Feature (TIER 3)
class HeatMapManager {
  constructor(map) {
    this.map = map;
    this.heatLayer = null;
  }

  update(points) {
    if (this.heatLayer) this.map.removeLayer(this.heatLayer);
    
    if (points && points.length > 10) {
      const heatPoints = points.map(p => [p.latitude, p.longitude, 0.5]);
      this.heatLayer = L.heatLayer(heatPoints, { radius: 25, blur: 15, maxZoom: 17 }).addTo(this.map);
    }
  }

  clear() {
    if (this.heatLayer) {
      this.map.removeLayer(this.heatLayer);
      this.heatLayer = null;
    }
  }
}
