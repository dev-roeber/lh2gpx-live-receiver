# LH2GPX Receiver – Wartungsanleitung für Betreuer

## 📋 Überblick

Diese Anleitung ist für dich, wenn du den LH2GPX Receiver **betreibst, entwickelst oder debuggst**.

---

## 🚀 Schnelleinstieg

### Lokale Entwicklung starten

```bash
# 1. Repository klonen
git clone <repo-url>
cd lh2gpx-live-receiver

# 2. Virtuelle Umgebung + Dependencies
python3 -m venv venv
source venv/bin/activate
pip install -r requirements-dev.txt

# 3. Tests ausführen (sollten alle bestehen)
pytest tests/ -v

# 4. Server lokal starten
export BEARER_TOKEN="test-token"
uvicorn app.main:create_app --reload --host 0.0.0.0 --port 8000

# 5. Dashboard öffnen
# http://localhost:8000/login
```

---

## 📁 Projektstruktur

```
app/
  ├── main.py                 # FastAPI App, Routes, Error Handler
  ├── config.py              # Settings, Umgebungsvariablen
  ├── models.py              # Datenmodelle (LiveLocationRequest, etc.)
  ├── storage.py             # SQLite Storage Layer
  └── templates/             # Jinja2 HTML Templates (deutsch)
      ├── base.html          # Basis-Layout mit Navigation
      ├── login.html         # Login-Seite mit Token-Toggle
      ├── error.html         # Error-Fehlerseite
      ├── dashboard.html     # Übersicht Tiles
      ├── live_status.html   # Receiver-Status Seite
      └── ...                # weitere Dashboard-Seiten

tests/
  └── test_app.py            # 15 Unit-Tests

docs/
  ├── API.md                 # REST API Dokumentation
  ├── SECURITY.md            # Sicherheitskonzepte
  ├── DEPLOY_RUNBOOK.md      # Deployment-Schritte
  ├── USER_GUIDE.md          # Endnutzer-Anleitung
  └── MAINTAINER_GUIDE.md    # Diese Datei
```

---

## 🧪 Tests

Alle 15 Tests müssen **immer** bestehen:

```bash
# Alle Tests
pytest tests/ -v

# Einzelne Tests
pytest tests/test_app.py::test_dashboard_renders_operator_ui -v

# Mit Coverage
pytest tests/ --cov=app --cov-report=html
```

**Wichtige Tests:**
- `test_dashboard_navigation_pages_render` — Alle Dashboard-Seiten laden
- `test_config_summary_masks_secrets` — Keine Secrets in Templates
- `test_logs_do_not_include_bearer_token` — Token nicht in Logs

---

## 🌍 Umgebungsvariablen

```bash
# Erforderlich
export BEARER_TOKEN="dein-geheimes-token"

# Optional (Defaults am Ende)
export LOG_LEVEL="INFO"
export RATE_LIMIT_REQUESTS_PER_MINUTE="60"
export LOCAL_TIMEZONE="Europe/Berlin"
export PUBLIC_HOSTNAME="receiver.example.com"
export STORAGE_PATH="/tmp/lh2gpx"
```

Siehe `app/config.py` für vollständige Liste und Defaults.

---

## 🔧 Häufige Entwicklungs-Aufgaben

### Template ändern
1. Edit `app/templates/*.html`
2. Reload lädt Template automatisch neu (mit `--reload`)
3. Test: `pytest tests/test_app.py::test_dashboard_renders_operator_ui`

### Neue Route hinzufügen
1. In `app/main.py` unter dem entsprechenden `@app.get()` hinzufügen
2. Template erstellen (falls HTML-Response)
3. `_base_template_context()` prüfen — brauchst du `config_summary`?
4. Test schreiben in `tests/test_app.py`

### Error Handling erweitern
Exception Handler sind in `app/main.py` ab Zeile ~220:
- `@app.exception_handler(HTTPException)` — HTTP-Fehler (401, 404, etc.)
- `@app.exception_handler(Exception)` — Unerwartete Fehler

Dashboard-Routen bekommen HTML-Fehlerseiten, API-Routen JSON.

---

## 📊 Storage-Struktur

Daten werden in SQLite gespeichert (`/tmp/lh2gpx/receiver.sqlite3`):

```sql
-- 3 Haupttabellen:
CREATE TABLE requests (...)     -- HTTP POST Requests
CREATE TABLE sessions (...)     -- Unique Sessions (IDs)
CREATE TABLE points (...)       -- Individual GPS Points
```

Siehe `app/storage.py` für Queries und Schema.

---

## 🚢 Deployment

### Mit Docker
```bash
docker build -t lh2gpx-receiver .
docker run -e BEARER_TOKEN="xxx" -p 8000:8000 lh2gpx-receiver
```

### Mit Caddy (Reverse Proxy)
Siehe `Caddyfile` für SSL + Rate Limiting Setup.

### Via Docker Compose
```bash
docker-compose up -d
```

Siehe `compose.yaml` für Service-Konfiguration.

---

## 🔍 Debugging

### Server läuft aber Dashboard lädt nicht
1. Browser-Console öffnen (F12)
2. Netzwerk-Tab: Welche Requests schlagen fehl?
3. Server-Logs: `LOG_LEVEL=DEBUG` setzen

### Tests schlagen fehl
```bash
# Verbose Output
pytest tests/test_app.py -vv --tb=long

# Mit Logging
pytest tests/test_app.py -v -s
```

### Datenbank beschädigt?
```bash
rm /tmp/lh2gpx/receiver.sqlite3
# Server wird neue DB beim nächsten Start erstellen
```

---

## 📝 Lokalisierung & Übersetzung

Alle UI-Strings sind ins Deutsche übersetzt:

- Navigation: "Übersicht", "Daten", "Betrieb & Sicherheit", "Hilfe"
- Labels: "Genauigkeit", "Quelle", "Erfassungsmodus"
- Error Messages: "Hoppla, hier stimmt etwas nicht"

**Neue Strings hinzufügen?** Direkt in den entsprechenden Template schreiben — keine i18n-Komplexität (single language für jetzt).

---

## 🔐 Security Checklist

Vor jedem Deployment:
- [ ] `BEARER_TOKEN` ist stark (min. 32 Zeichen)
- [ ] `test_config_summary_masks_secrets` bestanden
- [ ] `test_logs_do_not_include_bearer_token` bestanden
- [ ] HTTPS ist aktiviert (via Caddy/Nginx)
- [ ] Rate Limiting ist konfiguriert
- [ ] Logs werden nicht öffentlich einsehbar

---

## 📦 Version & Releases

**Aktuelle Version:** `0.4.0` (in `app/main.py` als `APP_VERSION`)

Beim Release:
1. Update `APP_VERSION` in `app/main.py`
2. Update `CHANGELOG.md`
3. Git Tag: `git tag v0.4.0 && git push --tags`
4. Docker Image bauen & pushen

---

## 🛠️ Weitere Ressourcen

- **API Doku:** `docs/API.md`
- **Security:** `docs/SECURITY.md`
- **Deployment:** `docs/DEPLOY_RUNBOOK.md`
- **Architecture:** `docs/ARCHITECTURE.md`
- **Troubleshooting:** `docs/TROUBLESHOOTING.md`

---

## 💬 Git Workflow

```bash
# Feature Branch
git checkout -b feat/my-feature
# ... changes ...
git commit -m "Add my feature"
git push origin feat/my-feature

# PR erstellen, Review, Merge

# Main Branch
git checkout main
git pull
pytest tests/ -v  # Sicherstellen, dass alles läuft!
```

**Commits sollten sein:**
- Aussagekräftig ("Fix login button layout" statt "fix")
- Mit `Co-Authored-By` wenn mit KI geschrieben (Claude Haiku 4.5)

---

## 📞 Support

Wenn du stecken bleibst:
1. Sieh in `docs/TROUBLESHOOTING.md` nach
2. Überprüf `tests/test_app.py` — Tests sind oft die beste Dokumentation
3. Check Server-Logs: `LOG_LEVEL=DEBUG`
