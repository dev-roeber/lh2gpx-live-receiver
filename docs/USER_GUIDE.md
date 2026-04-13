# LH2GPX Receiver – Bedienungsanleitung für Endnutzer

## 🎯 Was ist das?

Der **LH2GPX Receiver** ist ein Empfänger, der GPS-Punkte von deiner **LocationHistory2GPX-App** entgegennimmt und speichert. Du kannst deine Live-Standorte hochladen und später as GPX-Dateien herunterladen.

---

## 🔐 Anmelden

1. Öffne das **Dashboard** im Browser
2. Gib die **Server-URL** ein (z.B. `https://mein-server.de/live-location`)
3. Gib dein **Authentifizierungs-Token** ein
4. Klick auf **Anmelden**

> 💡 **Tipp:** Dein Token findest du in der **Einstellung deiner LocationHistory2GPX-App**.

### Token-Passwort sichtbar machen?
Klick auf das **👁️-Symbol** neben dem Token-Feld, um es sichtbar zu machen.

---

## 📊 Dashboard überblicken

Das Dashboard zeigt dir auf einen Blick:

| Bereich | Bedeutung |
|---------|-----------|
| **Übersicht** | Receiver-Status, Aktivität, Erfolgsquote |
| **Daten** | Meine Requests, Sessions und Punkte |
| **Betrieb & Sicherheit** | Sicherheitsstatus, Speicher, Konfiguration |
| **Hilfe** | Fehlerbehebung und offene Punkte |

---

## 📍 Meine GPS-Punkte ansehen

### Einzelne Punkte
1. Geh zu **Daten → Punkte**
2. Sieh deine letzten GPS-Punkte mit:
   - Zeitstempel (UTC + lokal)
   - Genauigkeit in Metern
   - Session-Zuordnung

### Sessions
1. Geh zu **Daten → Sessions**
2. Sieh deine Aufzeichnungssitzungen mit:
   - Anzahl der Punkte
   - Anzahl der Requests
   - Letzter Punkt-Zeitstempel

---

## 💾 GPX-Datei exportieren

1. Geh zu **Daten → Exporte**
2. Wähle deine Filter (Datum, Session, etc.)
3. Klick auf **Exportieren**
4. Die GPX-Datei wird heruntergeladen und kannst in Maps-Apps (Google Maps, Garmin, etc.) öffnen

---

## 🔒 Sicherheit prüfen

Geh zu **Betrieb & Sicherheit → Sicherheit**, um zu sehen:
- ✅ Ist mein Authentifizierungs-Token aktiv?
- ✅ Bin ich angemeldet (Admin-Zugriff)?
- ✅ Wurden Proxy-Header berücksichtigt?

---

## 📈 Aktivität nachschauen

Geh zu **Übersicht → Aktivität**, um zu sehen:
- Punkte und Requests pro Tag
- Quellen (iOS, Android, etc.)
- Erfassungsmodi (automatisch, manuell, etc.)

---

## ❓ Häufige Fragen

### Mein Token funktioniert nicht
1. Überprüf, dass der Token korrekt kopiert ist (keine Leerzeichen!)
2. Sieh nach unter **Betrieb & Sicherheit → Sicherheit**, ob Ingest-Auth aktiv ist
3. Wenn nötig: Systemprüfung via **Readyz-Check** ausführen

### Ich sehe meine Punkte nicht
- Waren die Uploads erfolgreich? → **Übersicht → Activity**
- Überprüf unter **Übersicht → Receiver**, ob die Erfolgsquote > 0 % ist

### Wo finde ich meine Exporte?
- Alle Exporte werden unter **Daten → Exporte** aufgelistet
- Klick auf einen Export, um ihn herunterzuladen

---

## 🆘 Noch Fragen?

Geh zu **Hilfe → Fehlerbehebung**, um Lösungen zu häufigen Problemen zu finden.
