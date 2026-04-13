# App-Store / Privacy Notes

Diese Notizen betreffen nur den Receiver. App- und Wrapper-Dateien wurden in diesem Schritt bewusst nicht geändert.

## Receiver-Sicht auf den Datenfluss

Wenn ein Client den optionalen Upload aktiviert, können beim Receiver ankommen:

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
- auf Wunsch wird zusätzlich ein Rohpayload-Audit als NDJSON geführt
- diese Daten sind sensible Standortdaten und entsprechend zu schützen

## Wichtige Receiver-Grenzen

- dieses Repo liefert keine verpflichtende Online-Vorgabe für die Produkt-App
- es enthält keinen versionierten Bearer-Token
- es enthält keine versionierte produktive Servervorgabe

## Folgearbeit außerhalb dieses Scopes

Später separat prüfen:

- App-Disclosure für optionalen Standort-Upload
- Review-Wording für App Store Connect
- appseitige Privacy-Texte
- Entfernen appseitiger Test-Defaults, falls dort noch vorhanden

## Bewusst nicht Teil dieses Laufs

- keine Änderungen an App- oder Wrapper-Dateien
- keine Änderungen an App-Store-Artefakten
- keine Produktvorgabe für Hostname oder Bearer-Token

Dieser Receiver-Lauf bereitet die spätere Review-/Privacy-Arbeit nur dokumentarisch vor. Die eigentlichen App-/Wrapper-Anpassungen müssen später separat erfolgen.

Siehe auch: [OPEN_ITEMS.md](OPEN_ITEMS.md)
