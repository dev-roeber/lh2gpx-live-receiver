# Dawarich-Synchronisation

Der Receiver spiegelt Dawarichs `public.points`-Tabelle direkt aus PostgreSQL in seine lokale SQLite-Datenbank. Dawarich bleibt die führende Datenquelle.

## Architektur

- Dawarich-PostgreSQL/PostGIS: Quelle
- `receiver_sync_events`: dauerhaftes Änderungsprotokoll
- PostgreSQL-Trigger: erfasst Insert, Update und Delete
- `lh2gpx-dawarich-sync.service`: liest Events und aktualisiert den Receiver
- Receiver-SQLite: performanter Karten-/Timeline-Spiegel

Der PostgreSQL-Trigger schreibt jede Änderung zuerst in die dauerhafte Event-Tabelle und sendet zusätzlich eine `NOTIFY`-Nachricht. Der produktive Worker verarbeitet den Cursor aus der Event-Tabelle und prüft diese derzeit im Abstand von einer Sekunde; dadurch bleiben Änderungen auch bei verpassten Benachrichtigungen oder einem Receiver-Neustart nachholbar.

## Betrieb

Der Datenbankport ist ausschließlich lokal verfügbar:

```text
127.0.0.1:5433 -> dawarich-db:5432
```

Service prüfen:

```bash
systemctl --user status lh2gpx-dawarich-sync.service
journalctl --user -u lh2gpx-dawarich-sync.service -f
```

Die Vorlage liegt unter `systemd/user/lh2gpx-dawarich-sync.service`. Die produktive Unit ist als `~/.config/systemd/user/lh2gpx-dawarich-sync.service` installiert und liest `/home/sebastian/Secrets/dawarich.env`; diese Datei ist nicht versioniert. Der verwendete PostgreSQL-Account `lh2gpx_sync` ist kein Superuser und darf weder Datenbanken noch Rollen anlegen. Die bestehende Secret-Datei enthält neben den Datenbankwerten weitere Dawarich-Betriebsgeheimnisse; eine weitere Aufteilung in eine dedizierte Sync-Secret-Datei ist ein offener Härtungsschritt.

## Datenkonsistenz

Dawarich-Punkte werden im Receiver mit `source=dawarich` und der Dawarich-Punkt-ID als externer ID gespeichert. Wiederholte Events sind idempotent. Wird ein Punkt in Dawarich gelöscht, wird er auch im Receiver gelöscht.

Der initiale Abgleich verarbeitet die vorhandenen Punkte batchweise. Danach werden Änderungen inkrementell verarbeitet. Bei einem beschädigten oder verlorenen Cursor kann ein vollständiger Abgleich durch Zurücksetzen des Sync-Status und Neustart des Dienstes durchgeführt werden. Ein verifizierter Produktionsabgleich spiegelte 486.210 Dawarich-Punkte; der zuletzt verifizierte Cursor stand danach auf Event-ID 72.325, ohne Fehler. Die Spiegelung verwendet eine eigene Zuordnungstabelle; eine relationale Foreign-Key-Verknüpfung zu `gps_points` ist derzeit nicht eingerichtet.

## Verifikation

```bash
systemctl --user is-active lh2gpx-dawarich-sync.service
journalctl --user -u lh2gpx-dawarich-sync.service --since today --no-pager
sqlite3 /home/sebastian/services/lh2gpx-live-receiver/data/receiver.sqlite3 \
  "select provider,last_event_id,last_success_at,last_error from dawarich_sync_state;"
```

Der Dawarich-PostgreSQL-Port ist auf dem Host nur an `127.0.0.1:5433` veröffentlicht und nicht als externer Web-Endpunkt gedacht.
