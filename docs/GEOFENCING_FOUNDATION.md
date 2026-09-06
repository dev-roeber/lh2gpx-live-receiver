# Geofencing-Grundlage

## Aktivierungsstatus

Die Geofencing-Grundlage ist vorbereitet, aber nicht aktiv. Die SQL-Datei
`sql/geofencing_v1.sql` wird von `app/storage.py` nicht automatisch geladen.
Es wurden keine Produktivdatenbanken geändert, keine API-Routen ergänzt und
kein Dienst neugestartet.

Der aktuelle Stand enthält ausdrücklich:

- kein Geofence-Management in der Weboberfläche
- keinen Erkennungs-Worker
- keine Push-Nachrichten oder Push-Subscriptions
- keine automatische Rückverfolgung/Backfill-Auswertung
- keine automatische Löschung von Geofences oder Übergängen

## Modell

### `geofences`

Speichert die Definition einer Zone:

- stabile textuelle `geofence_id`
- Name mit Längenbegrenzung
- `circle` oder `polygon`
- `enabled`, standardmäßig `0` (deaktiviert)
- Kreiszentrum und Radius oder ein Polygon-GeoJSON
- UTC-Erstellungs- und Änderungszeit

Kreise erlauben nur Koordinaten innerhalb der WGS84-Grenzen und einen Radius
größer als null bis maximal 1.000 km. Polygone werden zunächst als nichtleeres
GeoJSON-Dokument gespeichert; eine spätere Anwendungsschicht muss zusätzlich
RFC-7946-Geometrie, Ring-Schließung, Vertex-Limit und gültige WGS84-
Koordinaten prüfen, bevor eine Zone aktiviert werden darf.

### `geofence_subject_state`

Hält den zuletzt bekannten Innen-/Außenstatus eines logischen Subjekts pro Zone.
`subject_key` ist absichtlich nicht an `gps_points.id` gebunden. Dadurch kann
derselbe Mechanismus Receiver-Punkte und Dawarich-Punkte mit unterschiedlichen
Quellschlüsseln verarbeiten.

### `geofence_transitions`

Ist ein idempotentes Erkennungsprotokoll für `enter` und `exit`. Der eindeutige
Schlüssel verhindert doppelte Übergänge, wenn ein Punkt oder ein Sync-Event
mehrfach verarbeitet wird. Die Tabelle ist kein Benachrichtigungs- oder
Push-Queue-System.

## Sichere Aktivierungsvoraussetzungen

Vor einer späteren Aktivierung sind mindestens erforderlich:

1. Backup und Integritätsprüfung der Receiver-SQLite.
2. Explizite Feature-Flag mit Default `false`.
3. Separater Operator-Workflow zum Anlegen, Prüfen, Aktivieren und Deaktivieren
   von Zonen; neue Zonen bleiben standardmäßig deaktiviert.
4. Serverseitige Validierung jeder Kreis-/Polygon-Geometrie, unabhängig von
   Browserdaten.
5. Verarbeitung nur neuer Punkte als Standard; historische Backfills erst nach
   einer separaten Vorschau und ausdrücklicher Bestätigung.
6. Atomare Aktualisierung von `geofence_subject_state` und
   `geofence_transitions` in einer SQLite-Transaktion.
7. Festgelegte Datenschutz-, Aufbewahrungs- und Exportregeln. Bis dahin werden
   Übergänge nicht automatisch gelöscht.
8. Erst danach eine separat geplante Benachrichtigungsschicht mit Einwilligung,
   Authentifizierung und Rate-Limits. Diese Migration enthält keinerlei Push-
   oder Zustellungsdaten.

Die Migration darf erst in `app/storage.py` integriert werden, wenn diese
Voraussetzungen und ein Restore-/Rollback-Test abgeschlossen sind.
