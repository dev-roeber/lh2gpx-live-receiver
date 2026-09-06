# Web-Push-/VAPID-Grundlage

Status: **vorbereitet, nicht aktiv**

Diese Grundlage enthält ausschließlich Konfigurations- und Datenmodell-
Vorbereitung. Es werden keine VAPID-Schlüssel erzeugt, keine Subscriptions
registriert und keine Push-Nachrichten versendet.

## Aktueller Sicherheitszustand

- `WEB_PUSH_ENABLED` ist standardmäßig `false`.
- `VAPID_PUBLIC_KEY` und `VAPID_PRIVATE_KEY_FILE` sind standardmäßig leer.
- `app/storage.py` importiert `sql/push_vapid_v1.sql` nicht automatisch.
- Es gibt noch keine Push-Routen, keinen Service-Worker-Push-Handler und
  keinen Versand-Worker.
- Bestehende Geofence-Daten lösen keine Push-Aktivität aus.

Die SQL-Datei darf erst nach einer separaten Prüfung von Einwilligung,
Authentifizierung, CSRF-Schutz, Schlüsselablage, Widerruf und Recovery
explizit angewendet werden.

## Konfiguration

Die vorgesehenen Variablen sind:

- `WEB_PUSH_ENABLED=false`
- `VAPID_PUBLIC_KEY=` — darf später öffentlich an den Browser geliefert werden
- `VAPID_PRIVATE_KEY_FILE=` — nur lokaler restriktiver Secret-Pfad; niemals
  committen, loggen oder als API-Wert ausgeben

Der Flag allein aktiviert absichtlich keine Funktion. Die endgültige
Implementierung muss zusätzlich vorhandene Schlüssel, HTTPS, Benutzer-
Einwilligung und eine gültige zentrale Dashboard-Session verlangen.

## Datenmodell

`sql/push_vapid_v1.sql` definiert:

- `push_subscriptions` für eine Subscription je Gerät/Benutzer
- `push_delivery_attempts` als spätere Zustellhistorie

Endpoint, `p256dh` und `auth` sind sensible Push-Zugangsdaten. Die bestehende
Dateischutz- und Backup-Strategie des Datenträgers muss sie einschließen. Die
Lieferhistorie enthält absichtlich keine vollständigen Nachrichtennutzdaten.

## Sichere Folgearbeit

1. Schlüssel außerhalb des Repositories erzeugen und restriktiv ablegen.
2. Challenge-/CSRF- und Origin-Schutz auf den Registrierungsrouten ergänzen.
3. Subscription an die zentrale `ytdl_session` und stabile `user_id` binden.
4. Nutzerseitige Einwilligung und Widerruf implementieren.
5. ungültige Push-Endpunkte bei HTTP 404/410 deaktivieren.
6. Safari/iOS-Home-Screen-, Android-Chrome- und Desktop-Tests durchführen.
7. erst danach den Feature-Flag kontrolliert aktivieren.

## Nicht enthalten

- VAPID-Schlüsselerzeugung
- Subscription-Registrierung oder -Löschung per API
- Push-Versand, Retry-Worker oder Notification-Queue
- Service-Worker-Änderungen
- Geofence-Aktivierung oder historische Auswertung
