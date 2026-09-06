// Kleine, zustandslose Hilfsfunktionen für die Kartenansicht.
// Absichtlich als Namespace statt als globale Einzel-Funktion exportiert,
// damit map-page.js und spätere Map-Module keine Namen überschreiben.
(function exposeMapPageUtils(global) {
  'use strict';

  function getRelativeTime(timestamp) {
    const diffMs = Date.now() - new Date(timestamp).getTime();
    if (diffMs < 1000) return 'jetzt';
    if (diffMs < 60000) return `vor ${Math.floor(diffMs / 1000)}s`;
    if (diffMs < 3600000) return `vor ${Math.floor(diffMs / 60000)}m`;
    if (diffMs < 86400000) return `vor ${Math.floor(diffMs / 3600000)}h`;
    return `vor ${Math.floor(diffMs / 86400000)}d`;
  }

  global.LH2GPXMapUtils = Object.freeze({ getRelativeTime });
}(window));
