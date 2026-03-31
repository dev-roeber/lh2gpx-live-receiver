# App-Store / Privacy Notes

Diese Notizen betreffen nur den Receiver. App- und Wrapper-Dateien wurden in diesem Schritt bewusst nicht geaendert.

## Receiver-Sicht auf den Datenfluss

Wenn ein Client den optionalen Upload aktiviert, koennen beim Receiver ankommen:

- Latitude
- Longitude
- Zeitstempel des Punktes
- `sentAt`
- `sessionID`
- `source`
- `captureMode`
- `horizontalAccuracyM`
- technische Request-Metadaten wie User-Agent, Remote-IP und Forwarded-IP

## Speicherverhalten

- Requests und Punkte werden serverseitig gespeichert
- auf Wunsch wird zusaetzlich ein Rohpayload-Audit als NDJSON gefuehrt
- diese Daten sind sensible Standortdaten und entsprechend zu schuetzen

## Wichtige Receiver-Grenzen

- dieses Repo liefert keine verpflichtende Online-Vorgabe fuer die Produkt-App
- es enthaelt keinen versionierten Bearer-Token
- es enthaelt keine versionierte produktive Servervorgabe

## Folgearbeit ausserhalb dieses Scopes

Spaeter separat pruefen:

- App-Disclosure fuer optionalen Standort-Upload
- Review-Wording fuer App Store Connect
- appseitige Privacy-Texte
- Entfernen appseitiger Test-Defaults, falls dort noch vorhanden
