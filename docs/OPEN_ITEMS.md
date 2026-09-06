# Open Items / Deferred Work

Diese Datei beschreibt den **aktuellen** Restbestand nach dem inzwischen deutlich erweiterten Karten-, Timeline- und Backend-Ausbau.

## Bereits umgesetzt

- serverseitig vorbereitete Karten-Layer über `/api/map-data`
- globaler Karten-Metapfad `/api/map-meta`
- dedizierte Timeline-Endpunkte:
  - `/api/timeline`
  - `/api/timeline-preview`
- Hybrid-Live-Pfad:
  - WebSocket-Hinweise
  - Polling
  - Delta-/Noop-Refresh
- ingest-nahe Vorberechnung für:
  - `point_rollups`
  - `timeline_day_markers`
- räumliche Beschleunigung über:
  - `gps_points_rtree`
  - tile-basierte Prefilter

## Aktuell noch offen

## Tokenisierte GeoJSON-Share-Links — strikt deaktiviert

Im aktuellen Stand existiert **keine Share-Link-Route**, kein Share-Token,
keine Share-Datenbanktabelle und kein öffentlich erreichbarer GeoJSON-Link.
Der vorhandene GeoJSON-Export bleibt ausschließlich über die geschützte
Operator-API verfügbar. Diese Sperre ist beabsichtigt und darf nicht durch
eine einfache URL- oder Frontend-Erweiterung umgangen werden.

Eine spätere Umsetzung darf erst beginnen, wenn diese Produktentscheidungen
explizit festgelegt sind:

- Wer darf Shares erstellen: ausschließlich Admins oder alle angemeldeten
  Nutzer?
- Wer darf sie abrufen: jeder mit dem Link, nur angemeldete Nutzer oder eine
  bestimmte Rolle?
- Welche maximale Gültigkeit gilt (empfohlen: endlich, z. B. 24 Stunden)?
- Sind unbegrenzt viele Abrufe erlaubt oder gilt ein Download-/Abruflimit?
- Können Shares jederzeit widerrufen werden?
- Ist der Inhalt ein unveränderlicher Snapshot oder eine dynamische
  Datenbankabfrage?
- Welche Filter/Scopes dürfen geteilt werden (Session, Zeitraum, BBox,
  Layer)?
- Welche maximale Punktzahl und Dateigröße gilt?
- Welche Standort-Metadaten werden entfernt oder anonymisiert?
- Soll der Share nur im Tailnet oder über die öffentliche HTTPS-Adresse
  funktionieren?

Sicherheitsinvarianten für die spätere Umsetzung:

- Feature standardmäßig aus; keine Route aktivieren, solange die Freigabe
  nicht bewusst erfolgt.
- Opaque Token mit mindestens 256 Bit Zufall; nur ein Hash des Tokens darf
  persistent gespeichert werden.
- Ablauf, Widerruf, Scope und Abruflimit müssen serverseitig bei jedem Abruf
  geprüft werden.
- Tokenwerte dürfen weder geloggt noch in Fehlermeldungen, Responses oder
  Analytics erscheinen.
- Exportdateien gehören außerhalb des Static-Webroots und müssen mit
  `Cache-Control: no-store` sowie `Referrer-Policy: no-referrer` ausgeliefert
  werden.
- Ein Share muss auf eine konkrete Datenmenge begrenzt sein; unlimitierte
  dynamische Exporte sind nicht zulässig.
- Erstellung, Abruf, Widerruf und Ablauf sollen ohne Tokenwert auditierbar
  sein.

Bis zur Festlegung dieser Punkte bleibt der Status: **nicht implementiert,
nicht aktiviert, keine Standortdaten veröffentlicht**.

- noch feinere echte Teil-Deltas für weitere Kontextlayer
  - besonders:
    - Stops
    - Daytracks
    - Snap

- noch stärkere ingest-nahe Vorberechnung
  - z. B. vorberechnete:
    - vereinfachte Tracks
    - Stop-Artefakte
    - Daytrack-Artefakte
    - Snap-Ergebnisse

- weitere Spatial-Modernisierung über `SQLite + RTree + Tile-Prefilter` hinaus
  - z. B.:
    - SpatiaLite
    - tile-/bucket-orientierte Voraggregation
    - später ggf. PostGIS

- weitere Modularisierung von `map.html`
  - Transport-/Delta-State
  - Timeline
  - Lade-/Progress-Logik
  - Renderer
  - UI/Controls

- Snap weiter aus dem heißen Live-/Renderpfad herausziehen

- Doku-/Audit-Nachzug künftig laufend aktuell halten

## Produktionshinweis

- Der produktive Receiver läuft per User-systemd auf `127.0.0.1:8082`; der öffentliche Zugriff erfolgt über den zentralen Dashboard-Proxy.
- WebSocket-Live-Updates benötigen die in `requirements.txt` deklarierte `websockets`-Abhängigkeit. Ohne diese Abhängigkeit fällt die Oberfläche auf Polling zurück.
- Die zentrale Dashboard-Session (`ytdl_session`) ist im Produktionsbetrieb die einzige Anmeldung; eine separate Receiver-Admin-Anmeldung ist kein offener Punkt.

## Bewusst nicht Teil dieses Repos

- Änderungen an iOS-App oder Wrapper-Repos
- App-Store-Artefakte
- Produktvorgaben für App-Defaults außerhalb dieses Repos
