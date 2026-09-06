# GeoJSON-Share-Links — verbindliche Spezifikation

Status: **Spezifikation, nicht implementiert und strikt deaktiviert**

Diese Spezifikation beschreibt die spätere, optionale Freigabe gefilterter
GeoJSON-Daten. Sie aktiviert keine Route, erzeugt keine Tokens und
veröffentlicht keine Standortdaten. Abweichungen von den hier festgelegten
Defaults benötigen eine bewusste Sicherheitsentscheidung und eine
Dokumentationsänderung.

## Sicherheitsziele

- Standortdaten nur nach ausdrücklicher Admin-Aktion freigeben.
- Freigaben zeitlich und inhaltlich begrenzen.
- Tokens bei Verlust schnell widerrufen können.
- Keine Geheimnisse oder vollständigen Tokens in Logs, Datenbank oder
  Fehlermeldungen speichern.
- Der Download darf keine neue Autorisierung aus URL-Parametern oder
  Clientdaten ableiten.
- Ein Share darf weder den Live-Datenbestand noch spätere Datenänderungen
  unbeabsichtigt freigeben.

## Sichere Defaults

| Eigenschaft | Verbindlicher Default |
|---|---|
| Feature | aus (`GEOJSON_SHARING_ENABLED=false`) |
| Share-Erstellung | nur Admins mit gültiger Dashboard-Session |
| Abruf | Bearer-Link; kein zusätzlicher Login erforderlich |
| Erreichbarkeit | zunächst nur über die konfigurierte Receiver-Origin; keine öffentliche Aktivierung |
| Token | 32 zufällige Bytes, URL-safe kodiert; mindestens 256 Bit Entropie |
| Speicherung | ausschließlich SHA-256-Hash des Tokens |
| Gültigkeit | 24 Stunden ab Erstellung |
| Abrufe | maximal 10 erfolgreiche Downloads |
| Widerruf | jederzeit durch Admin; Widerruf wirkt sofort |
| Inhalt | unveränderlicher Snapshot zum Erstellungszeitpunkt |
| Punktlimit | maximal 100.000 Punkte |
| Dateilimit | maximal 50 MiB erzeugte GeoJSON-Datei |
| Metadaten | nur Koordinaten und ausdrücklich freigegebene, nicht geheime Zeit-/Qualitätsdaten |
| Caching | `Cache-Control: no-store, private` |
| Referrer | `Referrer-Policy: no-referrer` |
| Indexierung | `X-Robots-Tag: noindex, nofollow, noarchive` |
| Rate-Limit | 10 fehlgeschlagene Tokenprüfungen pro IP und 15 Minuten |
| Aufbewahrung | Snapshot und Share-Datensatz werden nach Ablauf/Widerruf innerhalb von 24 Stunden gelöscht |

Ein Share wird nicht automatisch verlängert. Ein erneuter Zugriff erzeugt
keine neue Gültigkeit.

## Nicht verhandelbare Datenregeln

Ein Share enthält standardmäßig:

- `FeatureCollection`
- gültige `Point`-Geometrien mit `[longitude, latitude]`
- optional `point_timestamp_utc`, wenn der Ersteller dies ausdrücklich
  aktiviert
- optional `horizontal_accuracy_m`, wenn der Ersteller dies ausdrücklich
  aktiviert

Standardmäßig nicht enthalten:

- Request-ID
- Session-ID
- Benutzername
- interne Quellen-/Debuginformationen
- Bearer-Tokens oder Auth-Cookies
- Rohpayloads

Der Snapshot muss vor der Token-Erstellung serverseitig gegen die zulässigen
Filter und Limits geprüft werden. Der Client darf weder Scope noch Exportpfad
vorgeben.

## Vorgesehene Datenstruktur

Die genaue Implementierung bleibt offen, die Sicherheitsfelder sind jedoch
verbindlich:

```text
geojson_shares
- id
- token_hash
- created_by_user_id
- scope_json
- snapshot_path
- point_count
- byte_count
- created_at
- expires_at
- revoked_at
- max_downloads
- download_count
- last_download_at
```

`token_hash` ist eindeutig indiziert. `snapshot_path` liegt außerhalb des
Static-Webroots und enthält keine vom Nutzer kontrollierten Pfadbestandteile.
Downloadzähler und Limitprüfung müssen atomar erfolgen, damit parallele
Abrufe das Limit nicht umgehen.

## Vorgesehene, aktuell nicht registrierte Endpunkte

Diese Pfade sind nur der spätere Vertrag; sie existieren derzeit nicht:

```text
POST   /api/admin/geojson-shares
GET    /api/admin/geojson-shares
DELETE /api/admin/geojson-shares/{share_id}
GET    /share/geojson/{opaque_token}
```

Die Admin-Endpunkte benötigen die zentrale Dashboard-Session und die Rolle
`admin`. Der Abruf prüft ausschließlich den serverseitig gespeicherten
Token-Hash, Ablauf, Widerruf, Abruflimit und Snapshotstatus.

Der Token wird nach erfolgreicher Erstellung genau einmal an den Admin
zurückgegeben. Listen-, Detail- und Audit-Endpunkte geben niemals den
Tokenwert oder eine rekonstruierbare URL zurück.

## Protokoll- und Headerregeln

Der Token darf nicht in normalen Request-Logs erscheinen. Der Webserver bzw.
Proxy muss den Tokenpfad redigieren oder durch die Share-ID ersetzen.

Ein erfolgreicher Download setzt mindestens:

```http
Content-Type: application/geo+json
Content-Disposition: attachment; filename="lh2gpx-share.geojson"
Cache-Control: no-store, private
Referrer-Policy: no-referrer
X-Robots-Tag: noindex, nofollow, noarchive
X-Content-Type-Options: nosniff
```

Der Dateiname wird nicht aus dem Token oder ungeprüften Eingaben gebildet.

## Fehlerverhalten

Ungültige, abgelaufene, widerrufene oder ausgeschöpfte Shares liefern dieselbe
neutrale Antwort, vorzugsweise `404`, damit kein Tokenstatus nach außen
unterschieden werden kann. Fehlermeldungen dürfen keine Tokenfragmente,
Dateipfade, Filterdetails oder Standortdaten enthalten.

## Testmatrix vor einer Aktivierung

### Konfiguration und Aktivierung

| Test | Erwartung |
|---|---|
| Default ohne Konfiguration | Keine Share-Route registriert oder erreichbar |
| `GEOJSON_SHARING_ENABLED=false` | Erstellen und Abruf nicht verfügbar |
| ungültiger Aktivierungswert | Sicherer Zustand: deaktiviert oder Startfehler, niemals implizit aktiv |
| Feature-Flag nach Neustart | Zustand bleibt deterministisch |
| Logs/Health/API-Dokumentation | Keine versehentliche öffentliche Share-Route behauptet |

### Berechtigung

| Test | Erwartung |
|---|---|
| nicht angemeldet erstellt Share | `401`/Redirect, kein Datensatz |
| normaler Nutzer erstellt Share | `403`, kein Datensatz |
| Admin erstellt Share | genau ein Datensatz, Scope serverseitig geprüft |
| Client manipuliert Scope | Manipulation wird ignoriert oder abgelehnt |
| Admin widerruft fremden Share | nur gemäß definierter Admin-Berechtigung; Audit-Ereignis |

### Token und Lebenszyklus

| Test | Erwartung |
|---|---|
| Tokenentropie | mindestens 256 Bit Zufall |
| Token in Datenbank | nur Hash, nie Klartext |
| Token in Logs/Fehlern | nicht vorhanden |
| gültiger Token | genau passender Snapshot wird geliefert |
| falscher Token | neutrale Fehlerantwort |
| abgelaufener Token | neutral abgelehnt |
| widerrufener Token | sofort neutral abgelehnt |
| mehr als 10 erfolgreiche Abrufe | weitere Abrufe atomar abgelehnt |
| parallele Abrufe am Limit | Limit wird nicht überschritten |
| erneuter Zugriff | Ablaufzeit wird nicht verlängert |

### Scope, Inhalt und Grenzen

| Test | Erwartung |
|---|---|
| Session-/Zeitraum-/BBox-Filter | nur der freigegebene Snapshot enthalten |
| 100.001 Punkte | Erstellung abgelehnt oder sicher begrenzt |
| Datei über 50 MiB | Snapshot wird nicht freigegeben und bereinigt |
| ungültige GPS-Geometrie | ungültige Features werden verworfen oder Export abgelehnt |
| interne Metadaten | nicht im GeoJSON enthalten |
| nachträgliche Datenbankänderung | bestehender Snapshot bleibt unverändert |
| Snapshotfehler/fehlende Datei | neutraler Fehler, keine Pfadinformation |

### HTTP- und Datenschutzverhalten

| Test | Erwartung |
|---|---|
| Response-Header | `no-store`, `no-referrer`, `noindex`, `nosniff` gesetzt |
| Browser-/Proxy-Cache | keine wiederverwendbare Cache-Antwort |
| Referer an externe Ressource | kein Token oder Standort-Scope geleakt |
| Tokenpfad in Access-Log | redigiert |
| Content-Disposition | fester sicherer Dateiname |
| CORS | keine unnötige Freigabe fremder Origins |
| Rate-Limit | Fehlversuche begrenzt und ohne Status-Leak |

### Aufbewahrung und Betrieb

| Test | Erwartung |
|---|---|
| Ablaufbereinigung | Snapshot und Metadaten werden innerhalb von 24 Stunden entfernt |
| Widerrufsbereinigung | Datei wird nicht weiter ausgeliefert |
| Neustart während Download | kein beschädigter oder unautorisierter Fallback |
| Datenbank-Lock | kein doppelter Downloadzähler, kein ungeschützter Fallback |
| Backup/Restore | Token-Hashes und Widerrufsstatus bleiben konsistent |
| Audit | Erstellung, Abruf, Widerruf und Ablauf ohne Tokenwert nachvollziehbar |

## Aktivierungskriterien

Eine spätere Aktivierung ist erst zulässig, wenn:

1. die oben genannten Defaults ausdrücklich bestätigt oder dokumentiert
   geändert wurden;
2. alle Testgruppen bestanden sind;
3. Access-Log-Redaktion geprüft wurde;
4. Snapshot-, Ablauf- und Bereinigungsjobs produktiv getestet wurden;
5. ein Admin-Recovery- und Widerrufsprozess vorhanden ist;
6. eine explizite Aktivierungsänderung von `false` vorliegt.

