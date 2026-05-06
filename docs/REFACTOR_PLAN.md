# Refactor Plan

## Ziel

Das Repo soll von einer stark dateizentrierten Struktur in eine klar geschnittene Service- und UI-Architektur ueberfuehrt werden, ohne den produktiven Ingest-, Import- und Kartenpfad zu destabilisieren.

## Prioritaeten

### P0

1. `app/main.py` in fachliche Schnittstellen zerlegen
2. Auth-/Session-Logik aus dem Hauptmodul herausziehen
3. `app/templates/map.html` in modulare Frontend-Dateien aufteilen
4. `app/storage.py` in Migrations-, Ingest-, Query- und Rollup-Teile zerlegen

### P1

1. CSS auf ein konsistentes responsives Design-System zurueckfuehren
2. Konfigurationsmodell fuer ENV und persistente Overrides explizit machen
3. Import-Parser als Registry-System umstellen
4. Jinja-Templates ueber Includes/Macros entduplizieren

### P2

1. DX-Skripte und lokales Startmodell vereinheitlichen
2. Systemtests fuer Login, Session, Hot-Reload und WebSocket-Auth ausbauen
3. Query- und Kartenpfade staerker instrumentieren

## Zielstruktur

```text
app/
  auth.py
  cache.py
  config.py
  models.py
  schemas/
    api.py
    map.py
  routers/
    dashboard.py
    ingest.py
    imports.py
    map_api.py
    system.py
  services/
    imports.py
    map_payloads.py
    settings.py
  storage/
    __init__.py
    ingest.py
    migrations.py
    queries_points.py
    queries_requests.py
    rollups.py
  static/
    css/
      app.css
      dashboard.css
      map.css
    js/
      base.js
      map/
        app.js
        layers.js
        network.js
        state.js
        timeline.js
  templates/
    includes/
    macros/
```

## Phasen

### Phase 1: Hauptmodul entlasten

- Auth-/Session-Funktionen in `app/auth.py`
- spaeter Cache-Helfer in `app/cache.py`
- danach Router in `app/routers/*`

### Phase 2: Karten-Frontend modularisieren

- `map.html` auf Shell + Initialdaten reduzieren
- Kartenlogik in `static/js/map/*`
- Inline-Styles in `static/css/map.css`

### Phase 3: Storage entkoppeln

- Migrationslogik separieren
- Ingest- und Query-Pfade trennen
- Rollup- und Rebuild-Logik separat machen

### Phase 4: Oberflaeche konsolidieren

- `style.css`, `desktop.css`, `mobile.css` zu einem System zusammenfuehren
- Design-Token behalten, Stilbrueche entfernen

## Guardrails

- Kein funktionaler Umbau ohne Testabdeckung fuer den betroffenen Pfad
- Jede Phase soll fuer sich deploybar bleiben
- Public API-Verhalten nur absichtlich aendern
- Ingest-, Readiness- und Kartenpfade nach jedem P0-Schritt mit Tests absichern
