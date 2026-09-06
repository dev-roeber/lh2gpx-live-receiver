#!/usr/bin/env python3
"""Validate an LH2GPX backup archive without contacting any service.

The validator only reads the archive and its checksum. SQLite content is
copied into a temporary directory for read-only integrity checks; no
production path is opened for writing.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


ALLOWED_FILES = {
    "manifest.json",
    "data/receiver.sqlite3",
    "data/raw-payloads.ndjson",
    "data/live-location.ndjson",
}
REQUIRED_FILES = {"manifest.json", "data/receiver.sqlite3"}
REQUIRED_TABLES = {"gps_points", "external_points", "dawarich_sync_state"}


def fail(message: str) -> "NoReturn":
    print(f"FEHLER: {message}", file=sys.stderr)
    raise SystemExit(1)


def checksum_path(archive: Path, supplied: Path | None) -> Path:
    path = supplied or archive.with_name(archive.name + ".sha256")
    if not path.is_file():
        fail(f"SHA-256-Datei fehlt: {path}")
    return path


def verify_checksum(archive: Path, checksum: Path) -> None:
    lines = checksum.read_text(encoding="utf-8").splitlines()
    if len(lines) != 1:
        fail("SHA-256-Datei muss genau eine Zeile enthalten")
    fields = lines[0].split(maxsplit=1)
    if len(fields) != 2 or len(fields[0]) != 64:
        fail("ungültiges SHA-256-Format")
    expected, filename = fields
    if filename.lstrip(" *") != archive.name:
        fail("SHA-256-Datei gehört nicht zum angegebenen Archiv")
    actual = hashlib.sha256()
    with archive.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            actual.update(chunk)
    if actual.hexdigest() != expected.lower():
        fail("SHA-256-Prüfung fehlgeschlagen")


def safe_members(archive: Path) -> dict[str, tarfile.TarInfo]:
    try:
        tar = tarfile.open(archive, mode="r:gz")
    except (tarfile.TarError, OSError) as exc:
        fail(f"Archiv kann nicht gelesen werden: {exc}")

    members: dict[str, tarfile.TarInfo] = {}
    with tar:
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                fail(f"unsicherer Archivpfad: {member.name}")
            if member.name in members:
                fail(f"doppelter Archivpfad: {member.name}")
            if member.name not in ALLOWED_FILES and member.name != "data":
                fail(f"unerwarteter Archivinhalt: {member.name}")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                fail(f"nicht erlaubter Archivtyp: {member.name}")
            members[member.name] = member
    missing = REQUIRED_FILES - members.keys()
    if missing:
        fail(f"Pflichtdateien fehlen: {', '.join(sorted(missing))}")
    return members


def extract_regular_files(archive: Path, members: dict[str, tarfile.TarInfo], target: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as tar:
        for name, member in members.items():
            if not member.isfile():
                continue
            destination = target / name
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                fail(f"Archivdatei kann nicht gelesen werden: {name}")
            with source, destination.open("wb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)


def validate_manifest(path: Path, members: dict[str, tarfile.TarInfo]) -> None:
    try:
        manifest = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"Manifest ist ungültig: {exc}")
    if manifest.get("format") != "lh2gpx-local-snapshot-v1":
        fail("unbekanntes Manifestformat")
    if manifest.get("contains_application_secrets") is not False:
        fail("Manifest bestätigt nicht, dass keine Application-Secrets enthalten sind")
    declared = {
        item.get("path"): item.get("bytes")
        for item in manifest.get("included_files", [])
        if isinstance(item, dict)
    }
    actual_files = {name for name, member in members.items() if member.isfile() and name != "manifest.json"}
    if set(declared) != actual_files:
        fail("Manifest-Dateiliste stimmt nicht mit dem Archiv überein")
    for name, size in declared.items():
        if not isinstance(size, int) or size < 0 or path.parent.joinpath(name).stat().st_size != size:
            fail(f"Manifest-Größe stimmt nicht: {name}")


def validate_sqlite(path: Path) -> tuple[int, int, int | None]:
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        with connection:
            quick = connection.execute("PRAGMA quick_check").fetchone()[0]
            if quick != "ok":
                fail(f"SQLite quick_check fehlgeschlagen: {quick}")
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                )
            }
            missing = REQUIRED_TABLES - tables
            if missing:
                fail(f"SQLite-Pflichttabellen fehlen: {', '.join(sorted(missing))}")
            gps_count = connection.execute("SELECT count(*) FROM gps_points").fetchone()[0]
            external_count = connection.execute("SELECT count(*) FROM external_points").fetchone()[0]
            cursor_row = connection.execute(
                "SELECT last_event_id FROM dawarich_sync_state WHERE provider='dawarich'"
            ).fetchone()
            cursor = int(cursor_row[0]) if cursor_row and cursor_row[0] is not None else None
        connection.close()
        return gps_count, external_count, cursor
    except sqlite3.Error as exc:
        fail(f"SQLite-Prüfung fehlgeschlagen: {exc}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-Validierung eines LH2GPX-Backups")
    parser.add_argument("archive", type=Path)
    parser.add_argument("--checksum", type=Path, help="optionale SHA-256-Datei")
    args = parser.parse_args()

    archive = args.archive.resolve(strict=True)
    if not archive.is_file():
        fail("Archiv ist keine reguläre Datei")
    checksum = checksum_path(archive, args.checksum.resolve() if args.checksum else None)
    verify_checksum(archive, checksum)
    members = safe_members(archive)

    with tempfile.TemporaryDirectory(prefix="lh2gpx-validate-") as temporary:
        root = Path(temporary)
        extract_regular_files(archive, members, root)
        validate_manifest(root / "manifest.json", members)
        gps_count, external_count, cursor = validate_sqlite(root / "data/receiver.sqlite3")

    print("OK: SHA-256, TAR-Inhalt, Manifest und SQLite-Read-only-Prüfung erfolgreich")
    print(f"SQLite gps_points={gps_count}, external_points={external_count}, sync_cursor={cursor}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
