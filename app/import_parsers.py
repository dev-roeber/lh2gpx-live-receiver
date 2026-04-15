"""Parsers for GPS import formats: JSON (Google Timeline), GPX, KML, KMZ, GeoJSON, CSV, ZIP."""
from __future__ import annotations

import csv
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from typing import Any


class ImportError(ValueError):
    pass


def parse_file(filename: str, data: bytes) -> list[dict[str, Any]]:
    name = filename.lower()
    if name.endswith(".zip"):
        return _parse_zip(data)
    if name.endswith(".kmz"):
        return _parse_kmz(data)
    if name.endswith(".gpx"):
        return _parse_gpx(data)
    if name.endswith(".kml"):
        return _parse_kml(data)
    if name.endswith(".geojson") or name.endswith(".geo.json"):
        return _parse_geojson(data)
    if name.endswith(".json"):
        return _parse_json(data)
    if name.endswith(".csv"):
        return _parse_csv(data)
    raise ImportError(f"Unbekanntes Dateiformat: {filename}")


# ── Helpers ──────────────────────────────────────────────────

def _pt(lat: float, lon: float, ts: datetime, accuracy: float = 0.0, mode: str | None = None) -> dict[str, Any]:
    if not (-90 <= lat <= 90 and -180 <= lon <= 180):
        raise ValueError(f"Koordinaten außerhalb des gültigen Bereichs: {lat}, {lon}")
    return {"latitude": lat, "longitude": lon,
            "timestamp_utc": ts.astimezone(timezone.utc),
            "accuracy_m": max(0.0, float(accuracy or 0)),
            "capture_mode": mode}


def _parse_ts(value: str) -> datetime:
    """Parse ISO 8601 / RFC 3339 / epoch-ms / epoch-s strings."""
    value = value.strip().rstrip("Z")
    # Unix timestamp in ms (Google Maps legacy)
    if value.lstrip("+-").isdigit():
        ms = int(value)
        sec = ms / 1000 if abs(ms) > 1e10 else ms
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    # ISO mit oder ohne Z / Offset
    for fmt in (
        "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S.%f",   "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",       "%Y-%m-%d",
    ):
        try:
            dt = datetime.strptime(value, fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except ValueError:
            continue
    raise ValueError(f"Unbekanntes Zeitformat: {value!r}")


def _e7_to_deg(val: Any) -> float:
    f = float(val)
    return f / 1e7 if abs(f) > 180 else f


def _parse_geo_uri(s: str) -> tuple[float, float] | None:
    """Extrahiert lat/lon aus 'geo:lat,lon' oder 'geo:lat,lon?...' Strings."""
    if not isinstance(s, str) or not s.startswith("geo:"):
        return None
    try:
        coords = s[4:].split("?")[0]
        lat_s, lon_s = coords.split(",", 1)
        return float(lat_s), float(lon_s)
    except Exception:
        return None


# ── JSON (Google Maps Timeline, diverse Formate) ─────────────

def _parse_json(data: bytes) -> list[dict[str, Any]]:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        raise ImportError(f"Ungültiges JSON: {e}")

    points: list[dict[str, Any]] = []

    # Root-Level: Liste oder Objekt mit locations / timelineObjects / features
    if isinstance(obj, list):
        locations = obj
    elif isinstance(obj, dict):
        locations = (obj.get("locations")
                     or obj.get("timelineObjects")
                     or obj.get("features")
                     or [obj])  # einzelnes Objekt
    else:
        raise ImportError("JSON-Format nicht erkannt.")

    for item in locations:
        if not isinstance(item, dict):
            continue

        # ── Google Locations: latitudeE7/longitudeE7 oder latE7/lngE7 ──
        lat_raw = item.get("latitudeE7") or item.get("latE7")
        lon_raw = item.get("longitudeE7") or item.get("lngE7") or item.get("lonE7")
        if lat_raw is not None and lon_raw is not None:
            try:
                lat = _e7_to_deg(lat_raw)
                lon = _e7_to_deg(lon_raw)
                ts_raw = (item.get("timestamp") or item.get("timestampMs")
                          or item.get("time") or item.get("datetime") or "")
                ts = _parse_ts(str(ts_raw)) if ts_raw else datetime.now(timezone.utc)
                acc = float(item.get("accuracy") or item.get("horizontalAccuracy") or 0)
                points.append(_pt(lat, lon, ts, acc, "google_timeline"))
            except Exception:
                pass
            continue

        # ── Google Timeline: lat/lon als float direkt ──
        if "latitude" in item and "longitude" in item:
            try:
                lat = _e7_to_deg(item["latitude"])
                lon = _e7_to_deg(item["longitude"])
                ts_raw = item.get("timestamp") or item.get("time") or item.get("datetime") or ""
                ts = _parse_ts(str(ts_raw)) if ts_raw else datetime.now(timezone.utc)
                acc = float(item.get("accuracy") or item.get("horizontalAccuracy") or 0)
                points.append(_pt(lat, lon, ts, acc, "json_point"))
            except Exception:
                pass
            continue

        # ── timelineObjects: placeVisit ──
        if "placeVisit" in item:
            pv = item["placeVisit"]
            loc = pv.get("location", {})
            lat_raw = loc.get("latitudeE7") or loc.get("latE7")
            lon_raw = loc.get("longitudeE7") or loc.get("lngE7") or loc.get("lonE7")
            if lat_raw is None:
                lat_raw = loc.get("latitude")
                lon_raw = loc.get("longitude")
            if lat_raw is not None and lon_raw is not None:
                try:
                    lat = _e7_to_deg(lat_raw)
                    lon = _e7_to_deg(lon_raw)
                    ts_raw = pv.get("duration", {}).get("startTimestamp", "")
                    ts = _parse_ts(ts_raw) if ts_raw else datetime.now(timezone.utc)
                    points.append(_pt(lat, lon, ts, 0, "place_visit"))
                except Exception:
                    pass
            continue

        # ── timelineObjects: activitySegment ──
        if "activitySegment" in item:
            seg = item["activitySegment"]
            dur = seg.get("duration", {})
            for loc_key, ts_key in (("startLocation", "startTimestamp"), ("endLocation", "endTimestamp")):
                loc = seg.get(loc_key, {})
                if not loc:
                    continue
                try:
                    lat_raw = loc.get("latitudeE7") or loc.get("latE7") or loc.get("latitude")
                    lon_raw = loc.get("longitudeE7") or loc.get("lngE7") or loc.get("lonE7") or loc.get("longitude")
                    if lat_raw is None or lon_raw is None:
                        continue
                    lat = _e7_to_deg(lat_raw)
                    lon = _e7_to_deg(lon_raw)
                    ts_raw = dur.get(ts_key, "")
                    ts = _parse_ts(ts_raw) if ts_raw else datetime.now(timezone.utc)
                    points.append(_pt(lat, lon, ts, 0, "activity_segment"))
                except Exception:
                    pass
            continue

        # ── Google Timeline 2024+: visit ──
        if "visit" in item:
            vis = item["visit"]
            geo_uri = (vis.get("topCandidate", {}).get("placeLocation")
                       or vis.get("placeLocation"))
            coords = _parse_geo_uri(geo_uri) if geo_uri else None
            if coords:
                try:
                    ts_raw = item.get("startTime") or item.get("endTime") or ""
                    ts = _parse_ts(ts_raw) if ts_raw else datetime.now(timezone.utc)
                    points.append(_pt(coords[0], coords[1], ts, 0, "google_visit"))
                except Exception:
                    pass
            continue

        # ── Google Timeline 2024+: activity ──
        if "activity" in item:
            act = item["activity"]
            for geo_key, ts_key in (("start", "startTime"), ("end", "endTime")):
                geo_uri = act.get(geo_key)
                coords = _parse_geo_uri(geo_uri) if geo_uri else None
                if not coords:
                    continue
                try:
                    ts_raw = item.get(ts_key) or item.get("startTime") or ""
                    ts = _parse_ts(ts_raw) if ts_raw else datetime.now(timezone.utc)
                    points.append(_pt(coords[0], coords[1], ts, 0, "google_activity"))
                except Exception:
                    pass
            continue

        # ── Google Timeline 2024+: timelinePath ──
        if "timelinePath" in item:
            path = item["timelinePath"]
            ts_raw = item.get("startTime") or ""
            try:
                base_ts = _parse_ts(ts_raw) if ts_raw else datetime.now(timezone.utc)
            except Exception:
                base_ts = datetime.now(timezone.utc)
            for step in path:
                geo_uri = step.get("point")
                coords = _parse_geo_uri(geo_uri) if geo_uri else None
                if not coords:
                    continue
                try:
                    offset_min = int(step.get("durationMinutesOffsetFromStartTime", 0))
                    ts = base_ts + timedelta(minutes=offset_min)
                    points.append(_pt(coords[0], coords[1], ts, 0, "google_path"))
                except Exception:
                    continue
            continue

        # ── GeoJSON Feature eingebettet in JSON ──
        if item.get("type") == "Feature":
            geom = item.get("geometry", {})
            if geom.get("type") == "Point":
                try:
                    coords = geom["coordinates"]
                    lon, lat = float(coords[0]), float(coords[1])
                    props = item.get("properties", {}) or {}
                    ts_raw = props.get("time") or props.get("timestamp") or ""
                    ts = _parse_ts(str(ts_raw)) if ts_raw else datetime.now(timezone.utc)
                    points.append(_pt(lat, lon, ts, float(props.get("accuracy", 0)), "geojson_feature"))
                except Exception:
                    pass
            continue

    if not points:
        raise ImportError(
            "Keine GPS-Punkte im JSON gefunden. "
            "Unterstützt: Google Maps Timeline 2024+ (visit/activity/timelinePath), "
            "Records.json (latitudeE7), Timeline-Objekte (placeVisit/activitySegment), "
            "GeoJSON-Features sowie JSON-Arrays mit latitude/longitude."
        )
    return points


# ── GPX ──────────────────────────────────────────────────────

def _parse_gpx(data: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError(f"Ungültiges GPX-XML: {e}")

    # Namespace aus Root-Tag extrahieren
    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    prefix = f"{{{ns}}}" if ns else ""

    points = []
    for tag in ("trkpt", "wpt", "rtept"):
        for el in root.iter(f"{prefix}{tag}"):
            try:
                lat = float(el.attrib["lat"])
                lon = float(el.attrib["lon"])
                time_el = el.find(f"{prefix}time")
                if time_el is None or not (time_el.text or "").strip():
                    # Waypoints ohne Zeit: aktuellen Zeitstempel verwenden
                    ts = datetime.now(timezone.utc)
                else:
                    ts = _parse_ts(time_el.text.strip())
                hdop_el = el.find(f"{prefix}hdop")
                acc = float(hdop_el.text) * 5 if hdop_el is not None and hdop_el.text else 0
                points.append(_pt(lat, lon, ts, acc, "gpx"))
            except Exception:
                continue

    if not points:
        raise ImportError(
            "Keine Trackpunkte im GPX gefunden. "
            "Erwartet werden <trkpt>, <wpt> oder <rtept> Elemente mit lat/lon-Attributen."
        )
    return points


# ── KML ──────────────────────────────────────────────────────

def _parse_kml(data: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError(f"Ungültiges KML-XML: {e}")

    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    prefix = f"{{{ns}}}" if ns else ""
    now = datetime.now(timezone.utc)
    points = []

    for pm in root.iter(f"{prefix}Placemark"):
        pt_el = pm.find(f".//{prefix}Point/{prefix}coordinates")
        if pt_el is None or not (pt_el.text or "").strip():
            continue
        try:
            parts = pt_el.text.strip().split(",")
            lon, lat = float(parts[0]), float(parts[1])
            ts_el = (pm.find(f".//{prefix}when")
                     or pm.find(f".//{prefix}TimeStamp/{prefix}when"))
            ts = _parse_ts(ts_el.text.strip()) if ts_el is not None and ts_el.text else now
            points.append(_pt(lat, lon, ts, 0, "kml_placemark"))
        except Exception:
            continue

    # LineString-Koordinaten
    for coord_el in root.iter(f"{prefix}coordinates"):
        text = (coord_el.text or "").strip()
        tuples = [t.strip() for t in text.split() if t.strip() and "," in t]
        if len(tuples) < 2:
            continue
        for t in tuples:
            try:
                parts = t.split(",")
                lon, lat = float(parts[0]), float(parts[1])
                points.append(_pt(lat, lon, now, 0, "kml_linestring"))
            except Exception:
                continue

    if not points:
        raise ImportError("Keine Koordinaten im KML gefunden.")
    return points


# ── KMZ ──────────────────────────────────────────────────────

def _parse_kmz(data: bytes) -> list[dict[str, Any]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as zf:
            kml_names = [n for n in zf.namelist() if n.lower().endswith(".kml")]
            if not kml_names:
                raise ImportError("Keine KML-Datei im KMZ-Archiv gefunden.")
            return _parse_kml(zf.read(kml_names[0]))
    except zipfile.BadZipFile:
        raise ImportError("KMZ-Datei konnte nicht geöffnet werden.")


# ── GeoJSON ───────────────────────────────────────────────────

def _parse_geojson(data: bytes) -> list[dict[str, Any]]:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        raise ImportError(f"Ungültiges GeoJSON: {e}")

    features: list[dict] = []
    t = obj.get("type", "")
    if t == "FeatureCollection":
        features = obj.get("features", [])
    elif t == "Feature":
        features = [obj]
    elif t in ("Point", "LineString", "MultiLineString"):
        features = [{"type": "Feature", "geometry": obj, "properties": {}}]
    else:
        raise ImportError(f"GeoJSON type nicht erkannt: {t!r}")

    now = datetime.now(timezone.utc)
    points = []
    for feat in features:
        geom = feat.get("geometry") or {}
        props = feat.get("properties") or {}
        ts_raw = (props.get("time") or props.get("timestamp")
                  or props.get("when") or props.get("datetime") or "")
        try:
            ts = _parse_ts(str(ts_raw)) if ts_raw else now
        except Exception:
            ts = now
        acc = float(props.get("accuracy") or props.get("horizontal_accuracy") or 0)

        if geom.get("type") == "Point":
            try:
                c = geom["coordinates"]
                points.append(_pt(float(c[1]), float(c[0]), ts, acc, "geojson"))
            except Exception:
                pass
        elif geom.get("type") == "LineString":
            for c in geom.get("coordinates", []):
                try:
                    points.append(_pt(float(c[1]), float(c[0]), ts, 0, "geojson_line"))
                except Exception:
                    pass
        elif geom.get("type") == "MultiLineString":
            for segment in geom.get("coordinates", []):
                for c in segment:
                    try:
                        points.append(_pt(float(c[1]), float(c[0]), ts, 0, "geojson_line"))
                    except Exception:
                        pass

    if not points:
        raise ImportError("Keine GPS-Punkte im GeoJSON gefunden.")
    return points


# ── CSV ───────────────────────────────────────────────────────

_LAT_COLS = ("latitude", "lat", "breitengrad", "y", "latitude_deg", "lat_deg")
_LON_COLS = ("longitude", "lon", "lng", "längengrad", "x", "longitude_deg", "lon_deg", "long")
_TS_COLS  = ("timestamp", "time", "datetime", "date", "zeit", "zeitstempel",
              "point_timestamp_utc", "point_timestamp_local", "created_at", "recorded_at", "utc")
_ACC_COLS = ("accuracy", "accuracy_m", "horizontal_accuracy_m", "genauigkeit", "hdop")

def _col(header: list[str], candidates: tuple[str, ...]) -> int | None:
    h = [c.lower().strip() for c in header]
    for c in candidates:
        if c in h:
            return h.index(c)
    return None

def _parse_csv(data: bytes) -> list[dict[str, Any]]:
    # Encoding-Erkennung: UTF-8-BOM, UTF-8, Latin-1
    for enc in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            text = data.decode(enc)
            break
        except Exception:
            continue
    else:
        text = data.decode("utf-8", errors="replace")

    sample = text[:8192]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel  # type: ignore[assignment]

    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header:
        raise ImportError("CSV leer oder kein Header gefunden.")

    lat_i = _col(header, _LAT_COLS)
    lon_i = _col(header, _LON_COLS)
    if lat_i is None or lon_i is None:
        raise ImportError(
            f"CSV: Keine Lat/Lon-Spalten erkannt. Gefundene Spalten: {header}. "
            "Erwartet werden Spalten wie latitude/longitude, lat/lon oder y/x."
        )

    ts_i  = _col(header, _TS_COLS)
    acc_i = _col(header, _ACC_COLS)
    now = datetime.now(timezone.utc)
    points = []

    for row in reader:
        if not row or all(not c.strip() for c in row):
            continue
        try:
            lat = float(row[lat_i].strip())
            lon = float(row[lon_i].strip())
            ts_val = row[ts_i].strip() if ts_i is not None and ts_i < len(row) else ""
            ts = _parse_ts(ts_val) if ts_val else now
            acc_val = row[acc_i].strip() if acc_i is not None and acc_i < len(row) else ""
            acc = float(acc_val) if acc_val else 0.0
            points.append(_pt(lat, lon, ts, acc, "csv"))
        except Exception:
            continue

    if not points:
        raise ImportError("CSV: Keine gültigen GPS-Punkte gefunden (Koordinaten außerhalb des Bereichs oder ungültige Werte).")
    return points


# ── ZIP (Google Takeout und andere Archive) ───────────────────

_SUPPORTED_EXT = (".json", ".gpx", ".kml", ".geojson", ".csv")

def _parse_zip(data: bytes) -> list[dict[str, Any]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ImportError("ZIP-Datei konnte nicht geöffnet werden.")

    names = sorted(
        [n for n in zf.namelist()
         if any(n.lower().endswith(ext) for ext in _SUPPORTED_EXT)
         and not n.startswith("__MACOSX")
         and not n.split("/")[-1].startswith(".")],
        key=lambda n: (
            # Records.json und Semantic Location History zuerst
            0 if "records" in n.lower() or "location" in n.lower() else
            1 if n.lower().endswith(".gpx") else 2
        )
    )

    if not names:
        raise ImportError(
            "ZIP enthält keine unterstützten Dateien "
            f"({', '.join(_SUPPORTED_EXT)}). "
            "Inhalt: " + ", ".join(zf.namelist()[:10])
        )

    all_points: list[dict[str, Any]] = []
    errors: list[str] = []
    for name in names:
        try:
            file_data = zf.read(name)
            pts = parse_file(name.split("/")[-1], file_data)
            all_points.extend(pts)
        except ImportError as e:
            errors.append(f"{name.split('/')[-1]}: {e}")
        except Exception as e:
            errors.append(f"{name.split('/')[-1]}: {type(e).__name__}: {e}")

    if not all_points:
        detail = "; ".join(errors[:5]) if errors else "Keine verwertbaren GPS-Daten"
        raise ImportError(f"ZIP: {detail}")
    return all_points
