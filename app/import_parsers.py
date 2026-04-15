"""Parsers for GPS import formats: JSON (Google Timeline), GPX, KML, KMZ, GeoJSON, CSV, ZIP."""
from __future__ import annotations

import csv
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
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
        raise ValueError("Koordinaten außerhalb des gültigen Bereichs")
    return {"latitude": lat, "longitude": lon,
            "timestamp_utc": ts.astimezone(timezone.utc),
            "accuracy_m": accuracy, "capture_mode": mode}


def _parse_ts(value: str) -> datetime:
    """Parse ISO 8601 / RFC 3339 / epoch-ms strings."""
    value = value.strip()
    # Unix timestamp in ms (Google Maps uses this)
    if value.lstrip("-").isdigit() and len(value) >= 10:
        ms = int(value)
        sec = ms / 1000 if ms > 1e10 else ms
        return datetime.fromtimestamp(sec, tz=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


# ── JSON (Google Maps Timeline Records.json) ─────────────────

def _parse_json(data: bytes) -> list[dict[str, Any]]:
    try:
        obj = json.loads(data)
    except json.JSONDecodeError as e:
        raise ImportError(f"Ungültiges JSON: {e}")

    # Google Takeout Records.json  {"locations": [...]}
    locations = obj if isinstance(obj, list) else obj.get("locations", obj.get("timelineObjects", []))

    points: list[dict[str, Any]] = []
    for loc in locations:
        # --- Locations array format ---
        if "latitudeE7" in loc:
            try:
                lat = loc["latitudeE7"] / 1e7
                lon = loc["longitudeE7"] / 1e7
                ts = _parse_ts(str(loc.get("timestamp") or loc.get("timestampMs", "")))
                acc = float(loc.get("accuracy", 0))
                points.append(_pt(lat, lon, ts, acc, "google_timeline"))
            except Exception:
                continue
        # --- timelineObjects: placeVisit / activitySegment ---
        elif "placeVisit" in loc:
            loc2 = loc["placeVisit"].get("location", {})
            try:
                lat = loc2["latitudeE7"] / 1e7
                lon = loc2["longitudeE7"] / 1e7
                ts_raw = loc["placeVisit"].get("duration", {}).get("startTimestamp", "")
                if not ts_raw:
                    continue
                ts = _parse_ts(ts_raw)
                points.append(_pt(lat, lon, ts, 0, "place_visit"))
            except Exception:
                continue
        elif "activitySegment" in loc:
            seg = loc["activitySegment"]
            for key in ("startLocation", "endLocation"):
                loc2 = seg.get(key, {})
                if not loc2:
                    continue
                try:
                    lat = loc2.get("latitudeE7", loc2.get("latitude", None))
                    lon = loc2.get("longitudeE7", loc2.get("longitude", None))
                    if lat is None or lon is None:
                        continue
                    if abs(lat) > 90:
                        lat /= 1e7
                        lon /= 1e7
                    ts_key = "startTimestamp" if key == "startLocation" else "endTimestamp"
                    ts = _parse_ts(seg.get("duration", {}).get(ts_key, ""))
                    points.append(_pt(lat, lon, ts, 0, "activity_segment"))
                except Exception:
                    continue

    if not points:
        raise ImportError("Keine GPS-Punkte im JSON gefunden.")
    return points


# ── GPX ──────────────────────────────────────────────────────

_GPX_NS = {"gpx": "http://www.topografix.com/GPX/1/1",
            "gpx10": "http://www.topografix.com/GPX/1/0"}

def _parse_gpx(data: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError(f"Ungültiges GPX-XML: {e}")

    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    prefix = f"{{{ns}}}" if ns else ""

    points = []
    for tag in ("trkpt", "wpt", "rtept"):
        for el in root.iter(f"{prefix}{tag}"):
            try:
                lat = float(el.attrib["lat"])
                lon = float(el.attrib["lon"])
                time_el = el.find(f"{prefix}time")
                if time_el is None or not time_el.text:
                    continue
                ts = _parse_ts(time_el.text)
                hdop_el = el.find(f"{prefix}hdop")
                acc = float(hdop_el.text) * 5 if hdop_el is not None and hdop_el.text else 0
                points.append(_pt(lat, lon, ts, acc, "gpx"))
            except Exception:
                continue

    if not points:
        raise ImportError("Keine Trackpunkte im GPX gefunden.")
    return points


# ── KML ──────────────────────────────────────────────────────

_KML_NS = "http://www.opengis.net/kml/2.2"

def _parse_kml(data: bytes) -> list[dict[str, Any]]:
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ImportError(f"Ungültiges KML-XML: {e}")

    ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
    prefix = f"{{{ns}}}" if ns else ""

    points = []
    now = datetime.now(timezone.utc)

    # Placemark Points
    for pm in root.iter(f"{prefix}Placemark"):
        pt_el = pm.find(f".//{prefix}Point/{prefix}coordinates")
        if pt_el is None or not pt_el.text:
            continue
        try:
            parts = pt_el.text.strip().split(",")
            lon, lat = float(parts[0]), float(parts[1])
            ts_el = pm.find(f".//{prefix}when") or pm.find(f".//{prefix}TimeStamp/{prefix}when")
            ts = _parse_ts(ts_el.text) if ts_el is not None and ts_el.text else now
            points.append(_pt(lat, lon, ts, 0, "kml_placemark"))
        except Exception:
            continue

    # LineString / MultiGeometry coordinates
    for coord_el in root.iter(f"{prefix}coordinates"):
        parent_tag = ""
        # skip Point coords already handled above
        text = coord_el.text or ""
        tuples = [t.strip() for t in text.strip().split() if t.strip()]
        if len(tuples) <= 1:
            continue
        # No timestamps in LineString — use equidistant dummy timestamps
        for i, t in enumerate(tuples):
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

    features = []
    if obj.get("type") == "FeatureCollection":
        features = obj.get("features", [])
    elif obj.get("type") == "Feature":
        features = [obj]
    elif obj.get("type") == "Point":
        features = [{"type": "Feature", "geometry": obj, "properties": {}}]

    points = []
    now = datetime.now(timezone.utc)
    for feat in features:
        geom = feat.get("geometry", {})
        if not geom:
            continue
        props = feat.get("properties", {}) or {}
        ts_raw = props.get("time") or props.get("timestamp") or props.get("when") or ""
        try:
            ts = _parse_ts(str(ts_raw)) if ts_raw else now
        except Exception:
            ts = now

        if geom["type"] == "Point":
            try:
                lon, lat = geom["coordinates"][0], geom["coordinates"][1]
                points.append(_pt(lat, lon, ts, float(props.get("accuracy", 0)), "geojson"))
            except Exception:
                continue
        elif geom["type"] in ("LineString", "MultiLineString"):
            coords_list = geom["coordinates"] if geom["type"] == "LineString" else [c for sub in geom["coordinates"] for c in sub]
            for c in coords_list:
                try:
                    points.append(_pt(c[1], c[0], ts, 0, "geojson_line"))
                except Exception:
                    continue

    if not points:
        raise ImportError("Keine GPS-Punkte im GeoJSON gefunden.")
    return points


# ── CSV ───────────────────────────────────────────────────────

_LAT_COLS  = ("latitude", "lat", "breitengrad", "y")
_LON_COLS  = ("longitude", "lon", "lng", "längengrad", "x")
_TS_COLS   = ("timestamp", "time", "datetime", "date", "zeit", "zeitstempel",
               "point_timestamp_utc", "point_timestamp_local")
_ACC_COLS  = ("accuracy", "accuracy_m", "horizontal_accuracy_m", "genauigkeit")

def _col(header: list[str], candidates: tuple[str, ...]) -> int | None:
    h = [c.lower().strip() for c in header]
    for c in candidates:
        if c in h:
            return h.index(c)
    return None

def _parse_csv(data: bytes) -> list[dict[str, Any]]:
    text = data.decode("utf-8-sig", errors="replace")
    dialect = csv.Sniffer().sniff(text[:4096], delimiters=",;\t")
    reader = csv.reader(io.StringIO(text), dialect)
    header = next(reader, None)
    if not header:
        raise ImportError("CSV leer oder kein Header gefunden.")

    lat_i = _col(header, _LAT_COLS)
    lon_i = _col(header, _LON_COLS)
    ts_i  = _col(header, _TS_COLS)
    acc_i = _col(header, _ACC_COLS)

    if lat_i is None or lon_i is None:
        raise ImportError("CSV: Keine Lat/Lon-Spalten erkannt. Erwartet: latitude/longitude, lat/lon oder y/x.")

    now = datetime.now(timezone.utc)
    points = []
    for row in reader:
        try:
            lat = float(row[lat_i])
            lon = float(row[lon_i])
            ts  = _parse_ts(row[ts_i]) if ts_i is not None and row[ts_i].strip() else now
            acc = float(row[acc_i]) if acc_i is not None and row[acc_i].strip() else 0.0
            points.append(_pt(lat, lon, ts, acc, "csv"))
        except Exception:
            continue

    if not points:
        raise ImportError("CSV: Keine gültigen GPS-Punkte gefunden.")
    return points


# ── ZIP (Google Takeout) ──────────────────────────────────────

_SUPPORTED_EXT = (".json", ".gpx", ".kml", ".geojson", ".csv")

def _parse_zip(data: bytes) -> list[dict[str, Any]]:
    try:
        zf = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise ImportError("ZIP-Datei konnte nicht geöffnet werden.")

    names = [n for n in zf.namelist()
             if any(n.lower().endswith(ext) for ext in _SUPPORTED_EXT)
             and not n.startswith("__MACOSX")]

    if not names:
        raise ImportError("ZIP enthält keine unterstützten Dateien (.json, .gpx, .kml, .geojson, .csv).")

    all_points: list[dict[str, Any]] = []
    errors: list[str] = []
    for name in names:
        try:
            file_data = zf.read(name)
            all_points.extend(parse_file(name.split("/")[-1], file_data))
        except ImportError as e:
            errors.append(f"{name}: {e}")
        except Exception as e:
            errors.append(f"{name}: {e}")

    if not all_points:
        detail = "; ".join(errors[:3]) if errors else "Keine verwertbaren GPS-Daten"
        raise ImportError(f"ZIP: {detail}")
    return all_points
