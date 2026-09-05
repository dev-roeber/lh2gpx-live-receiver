# Dawarich-Synchronisation

Der Receiver spiegelt Dawarichs `public.points`-Tabelle direkt aus PostgreSQL in seine lokale SQLite-Datenbank. Dawarich bleibt die führende Datenquelle.

## Architektur

- Dawarich-PostgreSQL/PostGIS: Quelle
- `receiver_sync_events`: dauerhaftes Änderungsprotokoll
- PostgreSQL-Trigger: erfasst Insert, Update und Delete
- `lh2gpx-dawarich-sync.service`: liest Events und aktualisiert den Receiver
- Receiver-SQLite: performanter Karten-/Timeline-Spiegel

`LISTEN/NOTIFY` dient als Wecksignal; der Sync-Cursor arbeitet ausschließlich mit der dauerhaften Event-Tabelle. Dadurch gehen Events bei einem Receiver-Neustart nicht verloren.

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

Die Vorlage liegt unter `systemd/user/lh2gpx-dawarich-sync.service`. Die produktive Kopie verwendet die lokale Service-Konfiguration. Die Dawarich-Credentials werden ausschließlich über `/home/sebastian/Secrets/dawarich.env` geladen und nicht versioniert.

## Datenkonsistenz

Dawarich-Punkte werden im Receiver mit `source=dawarich` und der Dawarich-Punkt-ID als externer ID gespeichert. Wiederholte Events sind idempotent. Wird ein Punkt in Dawarich gelöscht, wird er auch im Receiver gelöscht.

Der initiale Abgleich verarbeitet die vorhandenen Punkte batchweise. Danach werden Änderungen inkrementell verarbeitet. Bei einem beschädigten oder verlorenen Cursor kann ein vollständiger Abgleich durch Zurücksetzen des Sync-Status und Neustart des Dienstes durchgeführt werden.
