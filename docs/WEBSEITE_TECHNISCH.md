# LH2GPX Receiver – Technische Dokumentation der Webseite

## 📖 Für Entwickler & Betreuer

Diese Dokumentation erklärt die technischen Aspekte jeder Seite.

---

## 🏗️ Allgemeine Architektur

### Frontend
- **Template Engine**: Jinja2
- **Styling**: CSS in `/app/static/style.css`
- **Responsive**: Mobile-friendly (Flexbox/Grid)
- **Sprache**: Deutsch

### Backend Routes
```python
# app/main.py

@app.get("/login")                          # Login-Seite
@app.post("/login")                         # Login verarbeiten
@app.get("/logout")                         # Logout
@app.get("/dashboard")                      # Übersicht
@app.get("/dashboard/live-status")         # Receiver-Status
@app.get("/dashboard/activity")            # Aktivitäts-Diagramme
@app.get("/dashboard/points")              # Punkte-Tabelle
@app.get("/dashboard/points/<id>")         # Punkt-Detail
@app.get("/dashboard/requests")            # Requests-Tabelle
@app.get("/dashboard/requests/<id>")       # Request-Detail
@app.get("/dashboard/sessions")            # Sessions-Tabelle
@app.get("/dashboard/sessions/<id>")       # Session-Detail
@app.get("/dashboard/exports")             # Exports-Manager
@app.get("/dashboard/storage")             # Speicher-Überwachung
@app.get("/dashboard/config")              # Konfiguration (Read-only)
@app.get("/dashboard/security")            # Sicherheitsstatus
@app.get("/dashboard/system")              # System-Infos
@app.get("/dashboard/troubleshooting")     # Fehlerbehebung
@app.get("/dashboard/open-items")          # Offene Punkte
```

### Template Kontext
Jede Dashboard-Route ruft `_base_template_context()` auf:

```python
_base_template_context(
    request,
    active_nav="dashboard",
    page_title="Übersicht",
    page_kicker="LH2GPX Receiver",
    page_description="Aktuelle Statusübersicht",
    snapshot=dashboard_snapshot,  # alle Daten
    page_header_actions=[...]     # optionale Buttons
)
```

**Kontext-Variablen** (in Jinja2 verfügbar):
- `snapshot` — Dashboard-Snapshot (Daten)
- `receiver_summary` — Status Summary
- `config_summary` — Konfiguration (masked)
- `config_explanations` — Erklärungen
- `nav_groups` — Navigation Menu
- `app_version` — Version

---

## 🔐 1. Login-Seite

### Route: `/login` (GET/POST)

```python
@app.get("/login")
async def login_page(request: Request) -> TemplateResponse:
    # Wenn bereits angemeldet → /dashboard redirect
    return templates.TemplateResponse("login.html", {...})

@app.post("/login")
async def login_form(request: Request, ...) -> Response:
    # Validiere Token
    # Setze Session-Cookie
    # Redirect zu /dashboard
```

### Template: `app/templates/login.html`

**HTML-Struktur:**
```html
<div class="login-wrap">
  <div class="login-brand">LL Logo + Name</div>
  <div class="login-card">
    <h2>Anmeldung</h2>
    <form method="post">
      <input type="url" name="server_url">
      <input type="password" name="bearer_token" id="bearer_token">
      <button type="button" onclick="toggleBearerVisibility()">👁️</button>
    </form>
  </div>
</div>
```

**JavaScript:**
```javascript
function toggleBearerVisibility() {
  const input = document.getElementById('bearer_token');
  input.type = input.type === 'password' ? 'text' : 'password';
}
```

**Cookie:**
- Name: `lh2gpx_session`
- Maxage: 7 Tage (604800 Sekunden)
- HttpOnly: Ja (Sicherheit)

### Validation
- **Bearer Token**: Muss mit env `BEARER_TOKEN` übereinstimmen
- **Server URL**: Optional (wird von Form gesendet oder aus Session gelesen)

---

## 📊 2. Dashboard (Übersicht)

### Route: `/dashboard` (GET)

```python
@app.get("/dashboard")
async def dashboard(request: Request) -> TemplateResponse:
    snapshot = _dashboard_snapshot(request)  # Alle Metriken
    context = _base_template_context(
        request,
        active_nav="dashboard",
        page_title="Übersicht",
        snapshot=snapshot
    )
    return templates.TemplateResponse("dashboard.html", context)
```

### Data Flow

```
Dashboard
├── Receiver Tile
│   ├── Zustand (health_status)
│   ├── Bereitschaft (readiness_status)
│   ├── Letzter Ingest (snapshot.totals.lastSuccessAt)
│   └── Erfolgsquote (snapshot.totals.successRate)
├── Sicherheit Tile
│   ├── Ingest-Auth (authStatus)
│   ├── Admin-Zugriff (adminStatus)
│   └── Letzte Fehlerkategorie
├── Speicher Tile
│   ├── Verfügbar (snapshot.storage.available)
│   ├── Verwendet (snapshot.storage.used)
│   └── Lesbar (snapshot.storage.readiness.writable)
└── Upload-Metriken
    ├── Requests heute
    ├── Punkte heute
    └── Performance-Stats
```

### Template: `app/templates/dashboard.html`

**CSS-Klassen:**
- `.tile` — Einzelne Kachel
- `.tile-grid.six-up` — 6 Spalten Layout
- `.status-badge.ok` / `.status-badge.crit` — Status-Indikator
- `.tile-metric-label` / `.tile-metric-value` — Metrik-Paare

**Daten-Quellen:**
- `snapshot.totals` — Aggregierte Statistiken
- `receiver_summary` — Berechnete Status
- `snapshot.storage` — Speicher-Infos
- `snapshot.status` — Aktueller HTTP-Status

---

## 🟢 3. Receiver-Status (Live-Status)

### Route: `/dashboard/live-status` (GET)

```python
@app.get("/dashboard/live-status")
async def live_status(request: Request) -> TemplateResponse:
    snapshot = _dashboard_snapshot(request)
    context = _base_template_context(
        request,
        active_nav="live_status",
        page_title="Receiver-Status",
        snapshot=snapshot
    )
    return templates.TemplateResponse("live_status.html", context)
```

### Template: `app/templates/live_status.html`

**Tiles:**

| Tile | Quelle | Berechnung |
|------|--------|-----------|
| Service | `receiver_summary.serviceStatus` | "OK" wenn app.state.started_at_utc existiert |
| Verfügbarkeit | `receiver_summary.uptime` | `now - started_at_utc` |
| Zustand (Health) | `receiver_summary.healthStatus` | HTTP GET `/health` Status |
| Lebendigkeit | `receiver_summary.healthStatus` | Alias für Health |
| Bereitschaft | `receiver_summary.readinessStatus` | HTTP GET `/readyz` Status |
| Speicher bereit | `snapshot.storage.readiness.writable` | Boolean |
| Ingest-Auth | `receiver_summary.authStatus` | "aktiv" wenn `config.bearer_token` gesetzt |

**Status-Mapping:**
```python
healthStatus = "ok" | "warn" | "crit"
readinessStatus = "ok" | "warn" | "crit"
authStatus = "aktiv" | "inaktiv"
adminStatus = "angemeldet" | "nicht angemeldet"
```

---

## 📈 4. Aktivität (Activity)

### Route: `/dashboard/activity` (GET)

```python
@app.get("/dashboard/activity")
async def activity(request: Request) -> TemplateResponse:
    snapshot = _dashboard_snapshot(request)
    # Snapshot enthält bereits:
    # - snapshot.lists.pointsPerDay
    # - snapshot.lists.requestsPerDay
    # - snapshot.lists.recentPoints
    # - snapshot.lists.recentSessions
    # - snapshot.lists.sourceDistribution
    # - snapshot.lists.captureModeDistribution
```

### Template: `app/templates/activity.html`

**Diagramme (Bar Charts):**

```html
<div class="bar-list">
  {% for item in snapshot.lists.pointsPerDay %}
  <div class="bar-row">
    <span>{{ item.period_label }}</span>  <!-- "Mo", "Di", etc. -->
    <div class="bar">
      <div style="width: {{ percentage }}%"></div>  <!-- Bar-Breite -->
    </div>
    <strong>{{ item.value }}</strong>  <!-- Punkt-Anzahl -->
  </div>
  {% endfor %}
</div>
```

**Daten-Struktur:**
```python
snapshot.lists = {
    "pointsPerDay": [
        {"period_label": "Mo", "value": 150},
        {"period_label": "Di", "value": 230},
        ...
    ],
    "sourceDistribution": [
        {"label": "iOS", "value": 1000},
        {"label": "Android", "value": 500},
    ],
    "captureModeDistribution": [
        {"label": "automatic", "value": 1200},
        {"label": "manual", "value": 300},
    ]
}
```

---

## 📍 5. Punkte (Points)

### Route: `/dashboard/points` (GET)

```python
@app.get("/dashboard/points")
async def points(
    request: Request,
    page: int = Query(1),
    limit: int = Query(50),
    source: Optional[str] = Query(None),
    session_id: Optional[str] = Query(None),
) -> TemplateResponse:
    filters = PointFilters(
        source=source,
        session_id=session_id,
        offset=(page - 1) * limit,
        limit=limit,
    )
    points_list = storage.get_points(filters)  # DB Query
    # Pagination berechnen
```

### Template: `app/templates/points.html`

**Tabelle:**
```html
<table>
  <thead>
    <tr>
      <th>Zeit</th>
      <th>Lokal</th>
      <th>Genauigkeit</th>
      <th>Quelle</th>
      <th>Session</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for point in points_list %}
    <tr>
      <td>{{ format_timestamp(point.point_timestamp_utc).relative }}</td>
      <td>{{ point.point_timestamp_local }}</td>
      <td>{{ point.horizontal_accuracy_m }} m</td>
      <td>{{ point.source }}</td>
      <td><a href="/dashboard/sessions/{{ point.session_id }}">{{ short_id(point.session_id) }}</a></td>
      <td><a href="/dashboard/points/{{ point.id }}">Detail</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

**Filter-Form:**
```python
# Query-Parameter
source = request.query_params.get("source")  # "LocationHistory2GPX-iOS"
session_id = request.query_params.get("session_id")  # UUID
page = request.query_params.get("page", 1)

# Pagination UI
# Seite 1, 2, 3, ... mit Links zu /dashboard/points?page=2
```

**Pagination:**
```python
total_count = storage.count_points(filters)
total_pages = (total_count + limit - 1) // limit
```

---

## 📍 6. Punkt-Details

### Route: `/dashboard/points/<id>` (GET)

```python
@app.get("/dashboard/points/{point_id}")
async def point_detail(request: Request, point_id: int) -> TemplateResponse:
    point = storage.get_point(point_id)
    if not point:
        raise HTTPException(status_code=404, detail="Punkt nicht gefunden")
    # Template zeigt alle Felder
```

### Template: `app/templates/point_detail.html`

**Struktur:**
```html
<div class="detail-card">
  <h3>Punkt {{ short_id(point.id) }}</h3>
  <table>
    <tr><td>Punkt-ID</td><td>{{ point.id }}</td></tr>
    <tr><td>Zeitstempel UTC</td><td>{{ format_timestamp(point.point_timestamp_utc).utc }}</td></tr>
    <tr><td>Zeitstempel Lokal</td><td>{{ point.point_timestamp_local }}</td></tr>
    <tr><td>Breitengrad</td><td>{{ point.latitude }}</td></tr>
    <tr><td>Längengrad</td><td>{{ point.longitude }}</td></tr>
    <tr><td>Genauigkeit</td><td>{{ point.horizontal_accuracy_m }} m</td></tr>
    <tr><td>Höhe</td><td>{{ point.altitude_m }} m</td></tr>
    <tr><td>Quelle</td><td>{{ point.source }}</td></tr>
    <tr><td>Erfassungsmodus</td><td>{{ point.capture_mode }}</td></tr>
    <tr><td>Session-ID</td><td><a href="/dashboard/sessions/{{ point.session_id }}">{{ point.session_id }}</a></td></tr>
  </table>
</div>
```

---

## 📤 7. Requests

### Route: `/dashboard/requests` (GET)

```python
@app.get("/dashboard/requests")
async def requests(
    request: Request,
    page: int = Query(1),
    limit: int = Query(50),
    status: Optional[int] = Query(None),  # 202, 401, 429, etc.
) -> TemplateResponse:
    filters = RequestFilters(
        status_code=status,
        offset=(page - 1) * limit,
        limit=limit,
    )
    requests_list = storage.get_requests(filters)
```

### Template: `app/templates/requests.html`

**Tabelle:**
```html
<table>
  <thead>
    <tr>
      <th>Request-ID</th>
      <th>Punkte</th>
      <th>Status</th>
      <th>Zeit</th>
      <th>Quelle</th>
      <th></th>
    </tr>
  </thead>
  <tbody>
    {% for req in requests_list %}
    <tr>
      <td>{{ short_id(req.request_id) }}</td>
      <td>{{ req.points_count }}</td>
      <td><span class="status-badge {{ 'ok' if req.http_status == 202 else 'error' }}">{{ req.http_status }}</span></td>
      <td>{{ format_timestamp(req.received_at_utc).relative }}</td>
      <td>{{ req.source }}</td>
      <td><a href="/dashboard/requests/{{ req.request_id }}">Detail</a></td>
    </tr>
    {% endfor %}
  </tbody>
</table>
```

---

## 📤 8. Request-Details

### Route: `/dashboard/requests/<id>` (GET)

```python
@app.get("/dashboard/requests/{request_id}")
async def request_detail(request: Request, request_id: str) -> TemplateResponse:
    req = storage.get_request(request_id)
    # UUID Format
```

### Template: `app/templates/request_detail.html`

**Anzeige:**
- Request-Metadaten
- HTTP-Status
- Fehler (falls vorhanden)
- Punkte in diesem Request

---

## 👤 9. Sessions

### Route: `/dashboard/sessions` (GET)

```python
@app.get("/dashboard/sessions")
async def sessions(request: Request, page: int = Query(1)) -> TemplateResponse:
    session_list = storage.get_sessions(
        offset=(page - 1) * 50,
        limit=50,
    )
```

### Template: `app/templates/sessions.html`

**Tabelle:**
| Spalte | Quelle |
|--------|--------|
| Session-ID | `session.session_id` |
| Punkte | `session.points_count` |
| Requests | `session.requests_count` |
| Zeitraum | `format_timestamp(session.first_point_ts) - format_timestamp(session.last_point_ts)` |

---

## 👤 10. Session-Details

### Route: `/dashboard/sessions/<id>` (GET)

```python
@app.get("/dashboard/sessions/{session_id}")
async def session_detail(request: Request, session_id: str) -> TemplateResponse:
    session = storage.get_session(session_id)
    points_in_session = storage.get_points(
        PointFilters(session_id=session_id)
    )
```

### Template: `app/templates/session_detail.html`

**Info:**
- Session-ID, Erstellt, Letzter Punkt, Dauer
- Tabelle aller Punkte in dieser Session

---

## 💾 11. Exporte

### Route: `/dashboard/exports` (GET/POST)

```python
@app.get("/dashboard/exports")
async def exports(request: Request) -> TemplateResponse:
    # Zeige Export-Form + Liste vorheriger Exporte

@app.post("/dashboard/exports")
async def create_export(
    request: Request,
    filename: str = Form(...),
    format: str = Form("gpx"),
    from_date: Optional[str] = Form(None),
    to_date: Optional[str] = Form(None),
    session_id: Optional[str] = Form(None),
) -> Response:
    # Erstelle GPX-Datei
    # Speichere in /tmp oder Stream direkt
```

### Template: `app/templates/exports.html`

**Export-Generierung:**
1. Form ausfüllen (Datum, Session, etc.)
2. Backend erstellt GPX-Datei
3. Download-Link wird angezeigt
4. Alte Exporte in Liste

**GPX-Format:**
```xml
<?xml version="1.0"?>
<gpx version="1.1">
  <metadata>
    <name>My Track</name>
    <time>2026-04-13T...</time>
  </metadata>
  <trk>
    <trkseg>
      <trkpt lat="52.52" lon="13.40">
        <ele>35</ele>
        <time>2026-04-13T...</time>
      </trkpt>
      ...
    </trkseg>
  </trk>
</gpx>
```

---

## 🔒 12. Sicherheit

### Route: `/dashboard/security` (GET)

```python
@app.get("/dashboard/security")
async def security(request: Request) -> TemplateResponse:
    auth_status = "aktiv" if config.bearer_token else "inaktiv"
    admin_status = "angemeldet" if _is_authenticated(request) else "nicht angemeldet"
    proxy_header = "berücksichtigt" if config.trust_proxy_headers else "ignoriert"
```

### Template: `app/templates/security.html`

**Status-Kacheln:**
- Ingest-Auth: Token aktiv? ✅/❌
- Bearer-Token: Gesetzt? ✅/❌
- Proxy-Header: Berücksichtigt? ✅/❌

**Empfehlungen:**
- Token regelmäßig ändern
- Nur HTTPS verwenden
- Starkes Token nutzen

---

## 💾 13. Speicher

### Route: `/dashboard/storage` (GET)

```python
@app.get("/dashboard/storage")
async def storage(request: Request) -> TemplateResponse:
    readiness = storage.readiness()
    space_total = os.statvfs("/").f_blocks * os.statvfs("/").f_frsize
    space_used = snapshot.storage.used
    db_size = os.path.getsize(storage_path)
```

### Template: `app/templates/storage.html`

**Metriken:**
- Gesamt-Speicher
- Verfügbar (Free)
- Verwendet (SQLite DB Größe)
- Prozent-Auslastung
- Warnung wenn < 10 % verfügbar

---

## ⚙️ 14. Konfiguration

### Route: `/dashboard/config` (GET)

```python
@app.get("/dashboard/config")
async def config_page(request: Request) -> TemplateResponse:
    config = settings.masked_config_summary()
    explanations = _config_explanations()
```

### Template: `app/templates/config.html`

**Angezeigt (maskiert):**
- Hostname
- Port
- Timezone
- Token-Status (nur "gesetzt" oder "nicht gesetzt", nicht der Token selbst!)
- Log-Level
- Rate Limit

**Nicht angezeigt (Sicherheit):**
- Der tatsächliche Bearer-Token
- Datenbank-Pfade
- Interne IP-Adressen

---

## 🖥️ 15. System

### Route: `/dashboard/system` (GET)

```python
@app.get("/dashboard/system")
async def system(request: Request) -> TemplateResponse:
    uptime = now - app.state.started_at_utc
    db_stats = {
        "points_count": storage.count_points(),
        "requests_count": storage.count_requests(),
        "sessions_count": storage.count_sessions(),
    }
    cpu_percent = psutil.cpu_percent()
    memory_info = psutil.virtual_memory()
```

### Template: `app/templates/system.html`

**Angezeigt:**
- Version
- Uptime
- CPU-Auslastung
- RAM-Nutzung
- Datenbank-Statistiken

---

## 🔧 16. Fehlerbehebung

### Route: `/dashboard/troubleshooting` (GET)

```python
@app.get("/dashboard/troubleshooting")
async def troubleshooting(request: Request) -> TemplateResponse:
    # Read docs/TROUBLESHOOTING.md oder aus DB
    tips = [...]
```

### Template: `app/templates/troubleshooting.html`

**Inhalte:**
- FAQ mit häufigen Problemen
- Lösungsschritte
- Links zu Sicherheit, Storage, etc.

---

## 🗂️ 17. Offene Punkte

### Route: `/dashboard/open-items` (GET)

```python
@app.get("/dashboard/open-items")
async def open_items(request: Request) -> TemplateResponse:
    # Read docs/OPEN_ITEMS.md
    items = [...]
```

### Template: `app/templates/open_items.html`

**Inhalte:**
- Bekannte Limitierungen
- Geplante Features
- Workarounds

---

## 🚨 Error-Handling

### Exception Handler in main.py

```python
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException) -> Response:
    if "/dashboard" in str(request.url.path):
        # HTML-Fehlerseite für Dashboard
        return templates.TemplateResponse(
            "error.html",
            {"request": request, "status_code": exc.status_code, "detail": exc.detail},
            status_code=exc.status_code,
        )
    else:
        # JSON-Fehler für API
        return JSONResponse(...)

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception) -> Response:
    # Gleich wie HTTPException
```

### error.html Template

```html
<div class="error-page">
  <h1>Hoppla, hier stimmt etwas nicht</h1>
  <p>Statuscode: {{ status_code }}</p>
  <p>{{ detail }}</p>
  <p><a href="/dashboard">Zurück zum Dashboard</a></p>
</div>
```

---

## 📱 Template-Basis (base.html)

### Header
```html
<header class="global-header">
  <div class="gh-brand">LL Logo</div>
  <div class="gh-strip">
    Host: {{ config_summary.publicHostname }}
    Status: {{ snapshot.status.lastHttpStatus }}
    Uptime: {{ format_duration(snapshot.system.uptimeSeconds) }}
  </div>
</header>
```

### Sidebar
```html
<aside class="sidebar">
  <nav>
    {% for group in nav_groups %}
    <div class="sidebar-section">
      <h4>{{ group.title }}</h4>  <!-- "Übersicht", "Daten", etc. -->
      <ul>
        {% for item in group.items %}
        <li><a href="{{ item.href }}" class="{% if active_nav == item.key %}active{% endif %}">
          {{ item.label }}
        </a></li>
        {% endfor %}
      </ul>
    </div>
    {% endfor %}
  </nav>
</aside>
```

### Main Content
```html
<main class="page-shell">
  {% block content %}
  {# Page-spezifischer Inhalt #}
  {% endblock %}
  
  <footer class="context-footer">
    Region: {{ config_summary.localTimezone }}
    Version: {{ app_version }}
    Storage: {{ 'Writable' if snapshot.storage.readiness.writable else 'ReadOnly' }}
  </footer>
</main>
```

---

## 🎯 Template-Helper (Jinja2)

### Globale Filter/Funktionen (in main.py registriert)

```python
templates.env.globals.update(
    format_timestamp=_timestamp_summary,        # UTC + relative Zeit
    relative_time=_relative_time,               # "vor 5 Min."
    format_duration=_format_duration,           # "1h 23m"
    format_bytes=_format_bytes,                 # "512 MB"
    format_percent=_format_percent,             # "42.5%"
    status_tone=_status_tone,                   # CSS-Klasse für Status
    short_id=short_id,                          # Kürze auf 8 Zeichen
)
```

### Beispiel-Nutzung in Templates

```html
<!-- Format Timestamp -->
<td>{{ format_timestamp(point.point_timestamp_utc).relative }}</td>
<!-- Output: "vor 3 Stunden" -->

<!-- Format Bytes -->
<td>{{ format_bytes(snapshot.storage.used) }}</td>
<!-- Output: "1.2 GB" -->

<!-- Short ID -->
<td>{{ short_id(point.id) }}</td>
<!-- Output: "abc12345…" -->

<!-- Status Tone -->
<span class="{{ status_tone(receiver_summary.healthStatus) }}">{{ status }}</span>
<!-- Output: class="ok" oder "warn" oder "crit" -->
```

---

## 🔐 Authentication

### Session-Cookie
```python
response.set_cookie(
    key="lh2gpx_session",
    value=session_id,
    max_age=7 * 24 * 3600,  # 7 Tage
    httponly=True,
    secure=True,  # HTTPS nur
    samesite="strict"
)
```

### Middleware-Check
```python
def _require_admin_access(request: Request) -> None:
    if request.cookies.get("lh2gpx_session") not in request.app.state.admin_sessions:
        raise _LoginRequired()
```

---

## 🧪 Testing

### Test-Command
```bash
pytest tests/test_app.py::test_dashboard_navigation_pages_render -v
```

### Was wird getestet?
- Alle /dashboard/* Routes geben 200 zurück
- Templates rendern ohne Fehler
- Kein Token in Logs
- config_summary ist gemarskt
- Alle required Kontext-Variablen vorhanden

---

## 📊 Performance-Tipps

### Query-Optimierung
- Punkte/Requests: Mit LIMIT pageinieren, nicht alles laden
- Sessions: Mit Index auf `session_id`
- Storage.get_dashboard_snapshot(): Cache für 5-10 Sekunden

### Template-Rendering
- Jinja2 kompiliert zu Python-Code
- Große Loops (1000+ Items) → Pageinierung
- Keine N+1 Queries in Templates

### Netzwerk
- CSS/JS werden mit Flask StaticFiles served
- Responsive Design: Mobile-first
- SVG-Icons für Branding

---

## 🔍 Debugging

### Browser Developer Tools
- F12 → Network Tab → Sieh GraphQL/API-Requests
- F12 → Console → JavaScript-Fehler
- F12 → Application → Cookies sehen (lh2gpx_session)

### Server Logs
```bash
LOG_LEVEL=DEBUG uvicorn app.main:create_app --reload
```

### Flask/Jinja2 Debug
```python
# In main.py
if LOG_LEVEL == "DEBUG":
    app.config["PROPAGATE_EXCEPTIONS"] = True
```

---

## 📝 Weitere Ressourcen

- **API Docs**: `docs/API.md`
- **ARCHITECTURE**: `docs/ARCHITECTURE.md`
- **SECURITY**: `docs/SECURITY.md`
