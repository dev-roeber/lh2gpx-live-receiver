# LH2GPX Receiver – Vollständige Bedienungsanleitung

## 📖 Für Endnutzer

Dieses Handbuch führt dich durch alle Funktionen der Webseite.

---

## 🔐 1. Anmeldung (Login)

### Anmeldung durchführen

1. Öffne die **Login-Seite** des Receivers
2. Gib ein:
   - **Server-URL**: Die Adresse deines Receivers (z.B. `https://receiver.example.com/live-location`)
   - **Authentifizierungs-Token**: Dein geheimes Token aus der App
3. Klick **Anmelden**

### Token-Hilfe

- **Token ist nicht sichtbar?** → Klick auf das **👁️-Symbol**, um es anzuzeigen
- **Token verloren?** → Gib es in deiner LocationHistory2GPX-App ein und kopiere es
- **Hinweis:** Der Token wird in deinem Browser gespeichert (Session-Cookie, 7 Tage)

### Systemprüfung

- Klick auf **Systemprüfung (Readyz-Check)**, um zu überprüfen, ob der Server bereit ist

---

## 📊 2. Übersicht (Dashboard)

**Zugang:** Nach dem Login oder **Übersicht → Übersicht**

Hier siehst du auf einen Blick:

### Receiver Tile
| Feld | Bedeutung |
|------|-----------|
| **Zustand** | Health Status (OK, WARNING, ERROR) |
| **Bereitschaft** | Ist der Receiver einsatzbereit? |
| **Letzter Ingest** | Wann kam der letzte GPS-Punkt an? |
| **Erfolgsquote** | % erfolgreich hochgeladener Punkte |

### Sicherheit Tile
| Feld | Bedeutung |
|------|-----------|
| **Ingest-Auth** | Ist Token-Authentifizierung aktiv? |
| **Admin-Zugriff** | Bist du angemeldet? |
| **Letzte Fehlerkategorie** | Welcher Fehler ist zuletzt aufgetreten? |

### Speicher Tile
| Feld | Bedeutung |
|------|-----------|
| **Verfügbar** | Wie viel Speicherplatz ist frei? |
| **Verwendet** | Wie viel Speicherplatz nutzen die Daten? |
| **Lesbar** | Kann der Receiver auf den Speicher zugreifen? |

### Weitere Tiles
- **Uploads** — Heute, 24h, letzte 7 Tage
- **Punkte** — Heute, Woche, Monat
- **Performance** — Durchsnittsantwortzeit, Requests/Minute

---

## 🟢 3. Receiver-Status (Live-Status)

**Zugang:** **Übersicht → Receiver-Status**

Detaillierte Prüfung des Receiver-Zustands:

### Service
- **Receiver**: Läuft der Service? (aktiv/inaktiv)
- **Verfügbarkeit**: Wie lange läuft der Service schon?

### Zustand (Health)
- **Lebendigkeit**: Antwortet der Service auf Liveness-Checks?

### Bereitschaft (Readiness)
- **Speicher bereit**: Kann der Service auf den Speicher schreiben?
- **Meldung**: Details zur Bereitschaft (z.B. "Speicher schreibbar")

### Ingest-Auth
- **Status**: Token-Authentifizierung aktiv?
- **Token gesetzt**: Ist ein Token in der Konfiguration definiert?
- **Bearer-Token**: Funktioniert die Token-Validierung?

---

## 📈 4. Aktivität (Activity)

**Zugang:** **Übersicht → Aktivität**

Sieh deine Uploads grafisch:

### Metrik-Karten oben
- **Requests heute** — Anzahl heute (lokales Datum)
- **Requests 24h** — Letzte 24 Stunden
- **Punkte heute** — GPS-Punkte heute
- **Punkte 7d** — Letzte 7 Tage

### Diagramme
- **Punkte pro Tag** — Trend der letzten Tage
- **Requests pro Tag** — Trend der Requests

### Tabellen
- **Letzte 10 GPS-Punkte** — Mit Zeit, Ort, Genauigkeit
- **Session-Aktivität** — Aktive Sessions mit Punkt-Count

### Verteilungen
- **Quellen-Verteilung** — Woher kommen die Punkte? (iOS, Android, etc.)
- **Erfassungsmodus-Verteilung** — Wie wurden sie erfasst? (automatisch, manuell, etc.)

---

## 📍 5. Punkte (Points)

**Zugang:** **Daten → Punkte**

Alle deine GPS-Punkte durchsuchen:

### Tabelle
| Spalte | Bedeutung |
|--------|-----------|
| **Zeit** | UTC + lokale Zeit |
| **Ort** | Latitude, Longitude |
| **Genauigkeit** | Radius der Unsicherheit (Meter) |
| **Quelle** | iOS, Android, Web, etc. |
| **Session** | Welche Session gehört dieser Punkt? |

### Filter & Sortierung
- **Quelle**: Filtere nach iOS/Android/etc.
- **Session**: Nur Punkte aus einer bestimmten Session
- **Datum**: Punkte von einem bestimmten Tag
- **Seite**: Blätter durch mehrere Seiten

### Aktionen
- **Detail**: Klick auf einen Punkt, um mehr Infos zu sehen

---

## 📍 6. Punkt-Details

**Zugang:** **Daten → Punkte** → Auf einen Punkt klicken

Alle Informationen zu einem einzelnen Punkt:

| Feld | Bedeutung |
|------|-----------|
| **Punkt-ID** | Eindeutige ID (gekürzt angezeigt) |
| **Zeitstempel UTC** | Wann wurde der Punkt erfasst? |
| **Zeitstempel Lokal** | In deiner Zeitzone |
| **Breitengrad / Längengrad** | GPS-Koordinaten |
| **Genauigkeit** | Wie genau ist der Punkt? (Meter) |
| **Höhe** | Höhenmeter über Meeresspiegel |
| **Quelle** | Woher kommt der Punkt? |
| **Erfassungsmodus** | Automatisch oder manuell? |
| **Session-ID** | Zu welcher Session gehört er? |

---

## 📤 7. Requests

**Zugang:** **Daten → Requests**

Alle HTTP-Uploads deiner App:

### Tabelle
| Spalte | Bedeutung |
|--------|-----------|
| **Request-ID** | Eindeutige ID |
| **Punkte** | Wie viele GPS-Punkte in diesem Request? |
| **Status** | HTTP-Status (202 = OK, 401 = Auth-Fehler) |
| **Zeit** | Wann wurde der Request empfangen? |
| **Quelle** | iOS, Android, etc. |

### Filter
- **Status**: Nur erfolgreiche (202) oder fehlerhafte zeigen
- **Quelle**: Nach Quellgeräte filtern
- **Datum**: Nach Datum filtern

### Aktionen
- **Detail**: Klick auf einen Request, um Details zu sehen

---

## 📤 8. Request-Details

**Zugang:** **Daten → Requests** → Auf einen Request klicken

Detaillierte Informationen:

| Feld | Bedeutung |
|------|-----------|
| **Request-ID** | Eindeutige ID |
| **HTTP-Status** | 202 = erfolgreich, 401 = Auth-Fehler, 429 = zu häufig |
| **Empfangen** | Zeitstempel des Empfangs (UTC + lokal) |
| **Punkte** | Wie viele Punkte in diesem Request? |
| **Quellgeräte** | Von welcher App/Version? |
| **Fehler** | Falls vorhanden: Welcher Fehler ist aufgetreten? |

---

## 👤 9. Sessions

**Zugang:** **Daten → Sessions**

Deine Aufzeichnungssitzungen:

### Tabelle
| Spalte | Bedeutung |
|--------|-----------|
| **Session-ID** | Eindeutige Session-ID |
| **Punkte** | Wie viele Punkte in dieser Session? |
| **Requests** | Wie viele Uploads? |
| **Zeitraum** | Von wann bis wann? |

### Filter
- **Datum**: Sessions von einem bestimmten Tag
- **Dauer**: Sessions mit min. X Punkten

### Aktionen
- **Detail**: Klick auf eine Session, um alle Punkte zu sehen

---

## 👤 10. Session-Details

**Zugang:** **Daten → Sessions** → Auf eine Session klicken

Alle Punkte einer Session:

| Info | Bedeutung |
|------|-----------|
| **Session-ID** | Eindeutige ID |
| **Erstellt** | Wann wurde die Session gestartet? |
| **Letzter Punkt** | Wann kam der letzte Punkt? |
| **Dauer** | Wie lange dauerte die Session? |
| **Punkte-Tabelle** | Alle GPS-Punkte in dieser Session |

---

## 💾 11. Exporte

**Zugang:** **Daten → Exporte**

Deine GPS-Daten exportieren:

### Exportformular
1. **Dateiname**: Gib einen Namen ein (z.B. "Mein-Urlaub-2026")
2. **Format**: GPX (Standard für Maps-Apps)
3. **Filter** (optional):
   - **Von Datum**: Startdatum
   - **Bis Datum**: Enddatum
   - **Session**: Nur aus einer bestimmten Session
   - **Quelle**: Nur von iOS/Android/etc.
4. Klick **Exportieren**

### Export-Liste
- **Letzte Exporte** zeigen bereits erstellte Dateien
- **Download**: Klick auf einen Export, um ihn herunterzuladen
- **Größe**: Wie groß ist die GPX-Datei?
- **Punkte**: Wie viele Punkte sind darin?

### GPX-Datei verwenden
- Öffne sie in **Google Maps**, **Komoot**, **Garmin Connect**, etc.
- Importiere sie in andere Mapping-Apps

---

## 🔒 12. Sicherheit

**Zugang:** **Betrieb & Sicherheit → Sicherheit**

Alle Sicherheitseinstellungen:

### Auth-Status
| Feld | Bedeutung |
|------|-----------|
| **Ingest-Auth** | Ist Bearer-Token-Authentifizierung aktiv? |
| **Token gesetzt** | Ist ein Token konfiguriert? |
| **Proxy-Header** | Werden X-Forwarded-* Header berücksichtigt? |

### Admin-Zugriff
- **Du bist angemeldet**: Grüner Haken
- **Session gültig**: Für weitere 7 Tage

### Empfehlungen
- Ändere dein Token regelmäßig
- Nutze nur HTTPS (nicht HTTP)
- Teile dein Token nicht!

---

## 💾 13. Speicher

**Zugang:** **Betrieb & Sicherheit → Speicher**

Speicherplatz-Überwachung:

### Speicher-Tiles
| Feld | Bedeutung |
|------|-----------|
| **Gesamt** | Gesamtspeicher des Servers |
| **Verfügbar** | Freier Speicherplatz |
| **Verwendet** | Speicher der Receiver-Daten |
| **Prozent** | % Auslastung |

### Datenbank-Größe
- **SQLite-Datei**: Größe der Datenbank
- **Kompression**: Wie viel Speicher wird durch Kompression gespart?

### Warnung
- ⚠️ **Zu wenig Speicher**: Exporte können blockiert werden
- ✅ **Speicher schreibbar**: Neue Punkte können gespeichert werden

---

## ⚙️ 14. Konfiguration

**Zugang:** **Betrieb & Sicherheit → Konfiguration**

Aktuelle Einstellungen des Receivers:

### Netzwerk
- **Öffentlicher Hostname**: Wie ist der Server erreichbar?
- **Port**: Auf welchem Port läuft der Service?

### Authentifizierung
- **Token gesetzt**: Ist eines konfiguriert?
- **Token-Länge**: Wie lang ist dein Token?

### Logging
- **Log-Level**: DEBUG, INFO, WARNING, ERROR

### Speicher
- **Pfad**: Wo werden Daten gespeichert?
- **Zeitzone**: Lokale Zeitzone

### Performance
- **Rate Limit**: Wie viele Requests pro Minute?

> 💡 **Hinweis:** Viele Einstellungen erfordern Neustart des Servers (nicht von hier aus möglich)

---

## 🖥️ 15. System

**Zugang:** **Betrieb & Sicherheit → System**

System-Informationen:

### Service-Info
- **Version**: Receiver-Version
- **Uptime**: Wie lange läuft der Service?
- **Prozessor**: CPU-Auslastung
- **Speicher**: RAM-Nutzung (lokal)

### Datenbank
- **Größe**: SQLite-Datei-Größe
- **Rekorde**: Anzahl Punkte, Sessions, Requests
- **Letzte Bereinigung**: Wann wurde aufgeräumt?

### Netzwerk
- **Eingehende Daten**: Bytes von Clients
- **Ausgehende Daten**: Bytes zu Clients

---

## 🔧 16. Fehlerbehebung

**Zugang:** **Hilfe → Fehlerbehebung**

Lösungen zu häufigen Problemen:

### Problem: "Token ungültig"
- ✅ Überprüfe, dass dein Token korrekt kopiert ist
- ✅ Keine Leerzeichen am Anfang/Ende
- ✅ Sieh in der App nach, welcher Token dort eingestellt ist

### Problem: "Punkte werden nicht gespeichert"
- ✅ Ist die Erfolgsquote > 0 %?
- ✅ Gibt es Fehler in der Aktivität?
- ✅ Überprüfe unter **Sicherheit**, ob Ingest-Auth aktiv ist

### Problem: "Speicher voll"
- ✅ Exportiere und lösche alte Daten
- ✅ Siehe unter **Speicher**, wie viel Platz verfügbar ist
- ✅ Kontaktiere deinen Administrator

### Problem: "Webseite lädt nicht"
- ✅ Überprüfe die Verbindung zum Server
- ✅ Versuche einen anderen Browser
- ✅ Öffne Developer Tools (F12) und sieh in der Konsole nach Fehlern

---

## 🗂️ 17. Offene Punkte

**Zugang:** **Hilfe → Offene Punkte**

Bekannte Limitierungen und geplante Features:

- 🔜 Echtzeit-Benachrichtigungen
- 🔜 Daten-Import aus anderen Quellen
- 🔜 Backup & Restore
- ℹ️ Maximale Dateigröße: ~500 MB pro Export

---

## 🗺️ Abmelden

Oben links in der Sidebar:
- Klick auf **Abmelden**
- Deine Session wird beendet
- Du kannst dich später neu anmelden

---

## 💡 Tipps & Tricks

### Schnellere Navigation
- Nutze die **Sidebar** auf der linken Seite
- Die aktuelle Seite ist **fett** hervorgehoben

### Export-Planung
- **Täglich**: Exportiere einmal täglich als Backup
- **Wöchentlich**: Größerer Export für längere Trips
- **Nach Events**: Exportiere nach besonderen Reisen

### Performance
- Zu viele Punkte? Filtern nach Session oder Datum
- Exporte brauchen Zeit? Nutze längere Zeitfenster

### Fehler beheben
- Aktivere **Readyz-Check** unter Sicherheit
- Überprüfe **System-Info** auf Ressourcen-Probleme
- Lies **Fehlerbehebung**, wenn etwas nicht funktioniert

---

## 🆘 Noch Fragen?

- Sieh die **Fehlerbehebung** an
- Kontaktiere deinen Administrator
