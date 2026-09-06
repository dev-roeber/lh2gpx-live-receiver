# Passkey/WebAuthn: Entscheidungs- und Migrationsdokumentation

Status: **Entscheidung dokumentiert, nicht implementiert**

Diese Datei beschreibt die spätere Erweiterung der zentralen Authentifizierung für Dashboard, ytdl-webui und LH2GPX. Sie aktiviert keine WebAuthn-Zeremonie, ändert keine Abhängigkeiten und erzeugt keine Credentials.

## 1. Bestehende Architektur und Ziel

Die zentrale Authentifizierung liegt in `YT-DL-CLI/webui/auth_shared.py`:

- `users.json` enthält Benutzer, Argon2-Passworthashes, Rollen und stabile `user_id`.
- `~/services/auth/sessions.db` enthält prozessübergreifende Sessions.
- Der gemeinsame Cookie heißt `ytdl_session` und hat eine gleitende Laufzeit von 14 Tagen.
- Rollen sind derzeit `user` und `admin`.
- Dashboard, ytdl-webui und LH2GPX akzeptieren dieselbe Session.
- LH2GPX besitzt im Produktionsbetrieb keine eigene Loginmaske.

WebAuthn wird daher ausschließlich zentral am Dashboard-Login ergänzt. Nach einer erfolgreichen Passkey-Prüfung wird weiterhin genau eine normale `ytdl_session` erzeugt; nachgelagerte Dienste bleiben unverändert.

Ziel ist ein zusätzlicher phishing-resistenter Loginweg. Der Passwortlogin bleibt während der Migration und als Recovery-Weg erhalten. Ein Passkey-only-Betrieb ist nicht Bestandteil dieser Entscheidung.

## 2. RP-ID und Origin

### Produktionsprüfung am 2026-09-06

Read-only verifiziert:

- `dashboard.service`, `ytdl-webui.service` und
  `lh2gpx-live-receiver.service` sind aktiv.
- Dashboard-Health ist lokal unter `/api/health` erreichbar; die Loginseite
  ist unter `/login` erreichbar.
- Die Receiver-Karte ist lokal unter `/dashboard/map` erreichbar.
- Dashboard und ytdl verwenden byte-identische produktive Kopien von
  `auth_shared.py`.
- In den geprüften systemd-Units und der Receiver-Umgebung sind keine
  Passkey-/WebAuthn-Aktivierungswerte gesetzt.
- Es wurde keine WebAuthn-Abhängigkeit, Ceremony oder Credential-Datenbank
  durch diese Prüfung angelegt.

Der lokale Dashboard-Health-Aufruf ohne Session wird erwartungsgemäß durch
die Auth-Schicht geschützt; der explizit ausgenommene API-Pfad ist
`/api/health`. Der Receiver-Health-/Map-Pfad hat davon getrennte Regeln.

### Produktion

- RP-ID: `devroeber.tail71a8bc.ts.net`
- kanonischer Origin: `https://devroeber.tail71a8bc.ts.net`
- RP-ID enthält weder Schema, Pfad noch Port.

Die Zeremonien finden ausschließlich am zentralen HTTPS-Dashboard-Origin statt. ytdl und LH2GPX liegen zwar auf Pfaden bzw. Proxy-Routen desselben Hosts, führen aber keine eigenen WebAuthn-Zeremonien aus.

Nicht zulässig als Produktions-RP-ID:

- `ts.net`
- `localhost`
- `100.113.100.41`
- öffentliche IPv4-/IPv6-Adressen
- ein Hostname mit Schema, Port oder Pfad

Lokale Entwicklung verwendet getrennte Test-Credentials:

- Origin: `http://localhost:<port>`
- RP-ID: `localhost`
- Testpasskeys dürfen nie als Produktions-Credentials übernommen werden.

WebAuthn verlangt HTTPS (mit der definierten localhost-Ausnahme). Die RP-ID muss dem effektiven Domainnamen des Origins entsprechen oder ein zulässiger registrierbarer Suffix sein. Sie enthält kein Schema und keinen Port. [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/)

### Origin-Prüfung

Der Server muss bei Registration und Assertion zusätzlich zur RP-ID den erwarteten Origin exakt prüfen:

```text
https://devroeber.tail71a8bc.ts.net
```

Forwarded-/Proxy-Header dürfen diesen Wert nur über den vertrauenswürdigen zentralen Proxy liefern. Öffentliche Client-Header dürfen nicht unkritisch als Origin-Konfiguration verwendet werden.

## 3. Credential-Speicherung

WebAuthn-Daten gehören in die gemeinsame `sessions.db`, nicht in die LH2GPX-SQLite und nicht in `users.json`.

Vorgesehene Struktur:

```sql
passkey_credentials (
    credential_id BLOB PRIMARY KEY,
    user_id TEXT NOT NULL,
    public_key_cose BLOB NOT NULL,
    sign_count INTEGER NOT NULL DEFAULT 0,
    transports_json TEXT,
    user_verified INTEGER NOT NULL DEFAULT 0,
    backup_eligible INTEGER NOT NULL DEFAULT 0,
    backed_up INTEGER NOT NULL DEFAULT 0,
    label TEXT NOT NULL,
    created_at REAL NOT NULL,
    last_used_at REAL,
    revoked_at REAL
)
```

Anforderungen:

- Nur der öffentlichen Schlüssel wird gespeichert; private Schlüssel verlassen den Authenticator nicht.
- Credential-ID, Challenge und Assertion werden nicht geloggt.
- Mehrere Credentials pro Benutzer müssen möglich sein.
- Stabile `user_id` statt Benutzername als Zuordnung verwenden.
- `revoked_at` ermöglicht Widerruf und Audit, ohne sofortige physische Löschung.
- `sign_count`, User-Verification und Backup-Status gemäß geprüfter Bibliothek auswerten.
- Backup Eligibility/State ist Diagnoseinformation, kein alleiniger Admin-Vertrauensnachweis.

Challenges gehören in einen kurzlebigen, prozessübergreifend konsistenten Store. Jeder Challenge ist an Benutzer, Operation, Origin/RP-ID und Erstellungszeit gebunden, einmalig verwendbar und nach Ablauf ungültig.

## 4. Geplanter Ablauf

### Registration

1. Angemeldeter Benutzer öffnet die zentrale Passkey-Verwaltung.
2. Server erzeugt einen kryptografisch zufälligen, kurzlebigen Challenge.
3. Browser führt `navigator.credentials.create()` mit fester RP-ID aus.
4. Server prüft Challenge, Origin, RP-ID-Hash, Benutzerbindung und Credential-Daten.
5. Nur der öffentliche Schlüssel wird in `sessions.db` gespeichert.
6. Credential wird der stabilen `user_id` zugeordnet.

Empfohlen: discoverable/resident credential, User Verification `required`, `excludeCredentials` für bereits registrierte Credentials. Attestation zunächst `none` oder `indirect`, sofern kein Geräteinventar benötigt wird.

### Login

1. Dashboard stellt einen neuen Challenge bereit.
2. Browser führt `navigator.credentials.get()` aus.
3. Server validiert Challenge, Origin, RP-ID, User Handle, Credential-ID und Signatur.
4. Server aktualisiert Signaturzähler und letzte Nutzung.
5. Auth-Modul erzeugt eine neue `ytdl_session` mit der bestehenden Rolle.
6. Dashboard, ytdl-webui und LH2GPX nutzen diese Session wie bisher.

Die Serverprüfung darf nicht nur auf Benutzername oder Clientdaten vertrauen. WebAuthn bindet die Assertion an Origin und RP-ID; beides muss serverseitig geprüft werden. [MDN Passkeys](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)

## 5. Recovery und Rollback

### Nutzer-Recovery

- Passwortlogin bleibt verfügbar.
- Jeder Benutzer soll mindestens zwei unabhängige Passkeys registrieren.
- Nutzer können einzelne verlorene oder kompromittierte Credentials widerrufen.
- Credential-Label und letzte Nutzung sind sichtbar; Schlüsselmaterial nicht.

### Admin-Recovery

- Mindestens ein getesteter Admin-Passwort-Break-Glass-Weg bleibt erhalten.
- Ein zweiter Admin soll Credentials eines anderen Admins widerrufen können.
- Das letzte Admin-Credential darf nicht ohne vorhandenen Passwort-/Offline-Recovery-Weg gelöscht werden.
- Passwortänderung widerruft weiterhin Sessions, löscht aber nicht automatisch Passkeys.
- Bei Kompromittierung: Credential widerrufen, Sessions des Benutzers widerrufen, neues Credential registrieren und Audit prüfen.

Vor einem Passkey-only-Betrieb müssen getestet sein:

- lokaler Betreiberzugriff auf den Server
- Backup und Restore von `sessions.db`
- kontrolliertes Credential-Revoke
- Wiederherstellung eines Admin-Zugangs
- Rollback auf den vorherigen Auth-Code
- Recovery auf einem zweiten Gerät

Passkeys dürfen nicht die einzige Recovery-Möglichkeit werden, solange dieser Ablauf nicht reproduzierbar getestet ist. [MDN: Umgang mit verlorenen Passkeys](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)

## 6. Sicherheitsanforderungen

- Registration, Login und Challenge-Ausgabe nur über HTTPS.
- Schreibende Credential-Routen mit Origin-Allowlist und CSRF-Schutz.
- Challenges zufällig, kurzlebig und einmalig.
- Separate Rate-Limits für Challenge, Registration und Assertion.
- `ytdl_session` bleibt `HttpOnly`, `SameSite=Lax` und unter HTTPS `Secure`.
- Nach WebAuthn-Erfolg neue Session-ID erzeugen; keine Session vor der Prüfung übernehmen.
- Rollenprüfung bleibt nach der Session-Prüfung unverändert.
- Keine WebAuthn-Daten in Logs, URLs oder normalen Fehlerantworten.

## 7. Geräte- und Browser-Testmatrix

Alle Tests laufen am kanonischen öffentlichen HTTPS-Origin, nicht nur auf localhost.

| Gerät/Browser | Registration | Login | Recovery | Erwartung |
|---|---:|---:|---:|---|
| iPhone Safari, aktuelles iOS | ✓ | ✓ | ✓ | Face ID/Passkey; exakter Produktions-Origin |
| iPhone Home-Screen-PWA | ✓ | ✓ | ✓ | PWA-Verhalten, gleiche RP-ID |
| Android Chrome | ✓ | ✓ | ✓ | Gerätesperre/Passkey-Provider |
| macOS Safari | ✓ | ✓ | ✓ | iCloud-Keychain oder Hardware-Key |
| macOS Chrome | ✓ | ✓ | ✓ | Auswahl und Cross-Device-Flow |
| Windows Chrome/Edge | ✓ | ✓ | ✓ | Windows Hello und FIDO2-Key |
| Linux Firefox/Chromium | ✓ | ✓ | ✓ | Hardware-Key/System-Provider |
| USB/NFC-FIDO2-Key | ✓ | ✓ | ✓ | Admin-Recovery-Credential |
| Tailscale-/lokale HTTP-Adresse | nein | nein | n/a | Produktions-Credential darf dort nicht funktionieren |

Pro Testfall:

1. Falscher Origin wird abgewiesen.
2. Falsche RP-ID wird abgewiesen.
3. Abgelaufener oder wiederverwendeter Challenge wird abgewiesen.
4. Unbekannte oder widerrufene Credential-ID wird abgewiesen.
5. Assertion für einen anderen Benutzer wird abgewiesen.
6. Passwort- und Passkey-Login erzeugen dieselbe Sessionform und korrekte Rolle.
7. LH2GPX akzeptiert die resultierende Session.
8. Session-Widerruf beendet Zugriff in Dashboard, ytdl und LH2GPX.
9. Browser-Neustart, PWA-Modus und Netzwerkwechsel hinterlassen keinen hängenden Challenge.

Auf iOS 16.4+ muss das Webapp-Push-/PWA-Verhalten getrennt betrachtet werden: Web Push ist dort an eine Home-Screen-Web-App gebunden. Das betrifft nicht die WebAuthn-Login-Zeremonie, ist aber für spätere PWA-Tests relevant. [WebKit Web Push auf iOS/iPadOS](https://webkit.org/blog/13878/web-push-for-web-apps-on-ios-and-ipados/)

## 8. Migrationsphasen

### Phase 0 — Vorbereitung

- RP-ID und Origin unveränderlich festlegen.
- Backup-/Restore-Test der gemeinsamen Session-Datenbank.
- Geeignete, zum Implementierungszeitpunkt gepflegte WebAuthn-Bibliothek prüfen.
- Keine Dependency installieren und kein Feature-Flag aktivieren.

### Phase 1 — Datenmodell und Verwaltung

- Credential- und Challenge-Speicher idempotent migrieren.
- Admin-Verwaltung für Label, letzte Nutzung und Widerruf.
- Passwortlogin unverändert lassen.
- Unit-/Integrationstests ohne echte Zeremonie ergänzen.

### Phase 2 — kontrollierter Testmodus

- Feature-Flag bleibt standardmäßig `false`.
- Nur ausgewählte Testkonten freischalten.
- Geräte-Matrix und Recovery vollständig testen.
- Keine automatische Credential-Erstellung.

### Phase 3 — zusätzlicher Loginweg

- Passkey-Schaltfläche feature-flagged aktivieren.
- Bei Fehlern sauber auf Passwortlogin zurückfallen.
- Gemeinsame `ytdl_session` erzeugen.
- Dashboard, ytdl-webui und LH2GPX gemeinsam prüfen.
- Rollback durch Deaktivieren des Flags testen.

### Phase 4 — kontrollierte Erweiterung

- Nutzer schrittweise freischalten.
- Für Admins mindestens zwei Credentials verlangen.
- Verwaiste und widerrufene Credentials pflegen.
- Erst danach über eine Reduktion der Passwortabhängigkeit entscheiden.

## 9. Nicht Teil dieses Dokuments

- keine WebAuthn-Zeremonien oder Browser-API-Aufrufe
- keine neue Dependency
- keine Änderung an `users.json`, `sessions.db` oder `ytdl_session`
- kein Push, Geofencing oder Share-Link
- keine Änderung der produktiven RP-ID

## Quellen

- [W3C WebAuthn Level 3](https://www.w3.org/TR/webauthn-3/)
- [MDN Web Authentication API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Authentication_API)
- [MDN Passkeys](https://developer.mozilla.org/en-US/docs/Web/Security/Authentication/Passkeys)
- [MDN Authenticator Data](https://developer.mozilla.org/docs/Web/API/Web_Authentication_API/Authenticator_data)
