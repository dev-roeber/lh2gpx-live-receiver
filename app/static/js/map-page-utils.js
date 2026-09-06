// Kleine, zustandslose Hilfsfunktionen für die Kartenansicht.
// Wird von app/static/js/map/*.js importiert. Absichtlich ohne Abhängigkeit
// auf state.js oder DOM-spezifische Kartenlogik, damit dieses Modul ein
// eigenständiges Blatt im Abhängigkeitsbaum bleibt.
'use strict';

export function getRelativeTime(timestamp) {
  const diffMs = Date.now() - new Date(timestamp).getTime();
  if (diffMs < 1000) return 'jetzt';
  if (diffMs < 60000) return `vor ${Math.floor(diffMs / 1000)}s`;
  if (diffMs < 3600000) return `vor ${Math.floor(diffMs / 60000)}m`;
  if (diffMs < 86400000) return `vor ${Math.floor(diffMs / 3600000)}h`;
  return `vor ${Math.floor(diffMs / 86400000)}d`;
}

export const supportsAbortController = typeof window.AbortController === 'function';

const FETCH_TIMEOUT_MS = 8000;
const FETCH_MAX_RETRIES = 2;
const FETCH_RETRY_STATUS = new Set([408, 425, 429, 500, 502, 503, 504]);

export function sleepWithSignal(ms, signal) {
  return new Promise((resolve, reject) => {
    if (signal && signal.aborted) {
      const error = new DOMException('The operation was aborted.', 'AbortError');
      reject(error);
      return;
    }
    let timer = setTimeout(() => {
      if (signal) signal.removeEventListener('abort', abort);
      resolve();
    }, ms);
    const abort = () => {
      clearTimeout(timer);
      timer = null;
      signal.removeEventListener('abort', abort);
      reject(new DOMException('The operation was aborted.', 'AbortError'));
    };
    if (signal) signal.addEventListener('abort', abort, { once: true });
  });
}

// All map GETs use one bounded request policy. The caller's signal remains
// authoritative, while every individual attempt gets its own timeout.
export async function fetchWithRetry(input, options = {}, config = {}) {
  const timeoutMs = Number.isFinite(config.timeoutMs) ? config.timeoutMs : FETCH_TIMEOUT_MS;
  const maxRetries = Number.isFinite(config.maxRetries) ? config.maxRetries : FETCH_MAX_RETRIES;
  const parentSignal = options.signal;

  for (let attempt = 0; attempt <= maxRetries; attempt += 1) {
    if (parentSignal && parentSignal.aborted) {
      throw new DOMException('The operation was aborted.', 'AbortError');
    }

    const controller = supportsAbortController ? new AbortController() : null;
    let timedOut = false;
    let timeoutId = null;
    const abortFromParent = () => controller?.abort();
    if (parentSignal && controller) parentSignal.addEventListener('abort', abortFromParent, { once: true });
    if (controller) {
      timeoutId = setTimeout(() => {
        timedOut = true;
        controller.abort();
      }, timeoutMs);
    }

    try {
      const attemptOptions = Object.assign({}, options);
      if (controller) attemptOptions.signal = controller.signal;
      const response = await fetch(input, attemptOptions);
      if (!FETCH_RETRY_STATUS.has(response.status) || attempt >= maxRetries) return response;
      try { await response.body?.cancel(); } catch (error) { /* response cleanup is best effort */ }
    } catch (error) {
      if (parentSignal?.aborted) throw new DOMException('The operation was aborted.', 'AbortError');
      const retryable = timedOut || error?.name === 'TypeError' || error?.name === 'NetworkError';
      if (!retryable || attempt >= maxRetries) {
        if (timedOut) {
          const timeoutError = new Error(`Zeitüberschreitung nach ${Math.round(timeoutMs / 1000)} s`);
          timeoutError.name = 'TimeoutError';
          throw timeoutError;
        }
        throw error;
      }
    } finally {
      if (timeoutId !== null) clearTimeout(timeoutId);
      if (parentSignal && controller) parentSignal.removeEventListener('abort', abortFromParent);
    }

    const backoffMs = Math.min(4000, 500 * (2 ** attempt)) + Math.round(Math.random() * 250);
    await sleepWithSignal(backoffMs, parentSignal);
  }
  throw new Error('Anfrage konnte nicht abgeschlossen werden.');
}

export function storageGet(key, fallback = null) {
  try {
    const value = window.localStorage ? window.localStorage.getItem(key) : null;
    return value === null ? fallback : value;
  } catch (error) {
    return fallback;
  }
}

export function storageSet(key, value) {
  try {
    if (window.localStorage) window.localStorage.setItem(key, value);
  } catch (error) {
    console.warn('localStorage write skipped:', key, error);
  }
}

export function scheduleTask(fn) {
  if (typeof window.queueMicrotask === 'function') {
    window.queueMicrotask(fn);
    return;
  }
  setTimeout(fn, 0);
}

export function formatDuration(seconds) {
  if (!seconds || seconds <= 0) return '-';
  const hours = Math.floor(seconds / 3600);
  const minutes = Math.floor((seconds % 3600) / 60);
  return hours > 0 ? `${hours}h ${minutes}m` : `${minutes}m`;
}

export function formatEta(seconds) {
  if (seconds === null || seconds === undefined) return 'wird berechnet';
  if (seconds <= 0) return '0s';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return formatDuration(seconds);
}

export function escapeHtml(value) {
  return String(value == null ? '' : value)
    .split('&').join('&amp;')
    .split('<').join('&lt;')
    .split('>').join('&gt;')
    .split('"').join('&quot;')
    .split("'").join('&#39;');
}

export function formatBytes(value) {
  const bytes = Number(value) || 0;
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(bytes < 10 * 1024 * 1024 ? 2 : 1)} MB`;
}

// Rückwärtskompatible globale Namespace-Brücke: falls andere Skripte oder die
// Browser-Konsole weiterhin darauf zugreifen.
window.LH2GPXMapUtils = Object.freeze({ getRelativeTime });
