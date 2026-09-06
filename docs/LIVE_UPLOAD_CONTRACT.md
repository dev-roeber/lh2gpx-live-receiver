# Live-Upload-Contract (v1-Entwurf)

Status: **v1 entschieden (Phase 0), Implementierung steht noch aus.**
Beide offenen Designfragen (`echoRequestId`, Idempotenz-Aufbewahrung)
sind geklärt. Ersetzt keine bestehende Route; dokumentiert erstmals
verbindlich, was bisher nur implizit im Code (`app/models.py`,
`app/main.py`) und in der iOS-App feststand.

## Warum dieses Dokument

Bisher gab es **keinen** dokumentierten Contract zwischen App und Receiver
für den Live-Location-Upload — nur zwei unabhängig gewachsene
Implementierungen, die zufällig kompatibel sind. Dieses Dokument plus
`openapi.yaml` wird die einzige Wahrheitsquelle (Leitprinzip 1,
Contract-First). Jede Änderung läuft ab jetzt über eine PR gegen
`openapi.yaml`, nie über stillschweigende Feldänderungen in Client oder
Server.

## Scope v1

Enthalten:
- `POST /live-location` (Ingest, mit neuer Idempotenz)
- `GET /events/map` (SSE, einziger Live-Push-Kanal)
- `GET /healthz`, `GET /readyz`

Bewusst **nicht** enthalten (Foundation-Entscheidung, siehe
`docs/OPEN_ITEMS.md`):
- GeoJSON-Share-Links — bleibt deaktiviert, bis die dort gelisteten
  Produktfragen beantwortet sind.
- Web-Push/VAPID — kein erkannter Bedarf, zurückgestellt.
- `/ws/map` — wird ersatzlos gestrichen (verifiziert unauthentifiziert,
  `app/main.py:811-821`).

## `POST /live-location`

Kompatibel zum heutigen `LiveLocationRequest` (`app/models.py:20`), plus
eine neu eingeführte Idempotenz:

| Feld | Typ | Pflicht | Änderung ggü. Ist-Zustand |
|---|---|---|---|
| `source` | string, non-blank | ja | unverändert |
| `sessionID` | UUID | ja | unverändert |
| `requestID` | UUID | **neu, ja** | client-generiert, pro Upload-Versuch stabil (auch bei Retry gleich) |
| `captureMode` | string, non-blank | ja | unverändert |
| `sentAt` | datetime (ISO-8601, tz-aware) | ja | unverändert |
| `points[]` | Liste, min. 1 | ja | unverändert (siehe unten) |

`points[]`-Element (= heutiges `LiveLocationPoint`, unverändert):
`latitude` (-90..90), `longitude` (-180..180), `timestamp` (tz-aware),
`horizontalAccuracyM` (>=0).

**Idempotenz-Semantik**: Der Server dedupliziert auf `(sessionID,
requestID)`. Ein wiederholter Request mit identischem Schlüsselpaar
liefert denselben `202`-Body wie beim ersten Erfolg, ohne die Punkte
erneut zu schreiben. Das behebt den dokumentierten Mangel "kein echter
Retry/Backoff bei Server-Outage" auf App-Seite (Phase 2) — der Client
darf beim Wiederanlauf blind erneut senden.

**Aufbewahrung der Idempotenz-Tabelle**: **entschieden — 7 Tage
rollierend.** Ein Housekeeping-Job löscht `(sessionID, requestID)`-
Einträge älter als 7 Tage; das deckt jeden realistischen
Offline-Backoff-Zeitraum ab, ohne die Tabelle unbegrenzt wachsen zu
lassen.

**Auth**: unverändert Bearer-Token (`require_bearer_token`) + Rate-Limit
(`apply_rate_limit`).

**Response** (`202 Accepted`, `Cache-Control: no-store`): **entschieden
— beide IDs werden zurückgegeben**, damit App- und Server-Logs
korrelierbar sind. `requestId` bleibt wie heute serverseitig vergeben,
`echoRequestId` spiegelt das vom Client gesendete `requestID` und ist
ab v1 Pflichtfeld.
```json
{
  "status": "accepted",
  "requestId": "<server-request-id>",
  "echoRequestId": "<client-requestID>",
  "...": "…bestehende storage_summary-Felder unverändert"
}
```

**Server-seitige Nebeneffekte** (nicht Teil des Contracts, aber
dokumentiert, da sie sich mit dem Rewrite ändern):
- Geofencing wird ab Phase 1 direkt im Ingest-Pfad ausgewertet
  (`GeofenceEngine.evaluate`, bisher nicht angeschlossen).
- Live-Push geht nur noch über SSE (`sse_manager.publish`), nicht mehr
  zusätzlich über den WebSocket-Manager.

## `GET /events/map` (SSE)

Unverändert admin-geschützt (`require_admin_access`), unterstützt
`Last-Event-ID` für History-Replay. Event-Typen v1:

| `type` | Payload | Auslöser |
|---|---|---|
| `new_location` | `{ "sessionId": "<uuid>" }` | erfolgreicher `/live-location`-Ingest (unverändert) |
| `geofence_transition` | `{ "geofenceId", "subjectKey", "transition": "enter"\|"exit", "pointTimestampUtc", "latitude", "longitude" }` | **neu in Phase 1** — 1:1 aus `GeofenceEvent` (`app/geofencing.py:66`), sobald scharf verdrahtet |

`/ws/map` entfällt ersatzlos — kein Ersatz-Contract nötig, da SSE
denselben Zweck bereits erfüllt und korrekt authentifiziert ist.

## Offene Punkte für die finale Abstimmung

Keine mehr offen — beide Punkte aus dem Entwurf (`echoRequestId` im
Response-Body, 7-Tage-Aufbewahrung der Idempotenz-Tabelle) sind
entschieden und oben eingearbeitet.

## Nächster Schritt

Aus diesem Dokument wird `openapi.yaml` generiert/gepflegt (siehe
Datei im selben Verzeichnis). Nach Freigabe: `swift-openapi-generator`
gegen `openapi.yaml` laufen lassen und den erzeugten Swift-Client als
Kompilier-Test werten (Phase-0-Abnahmekriterium).
