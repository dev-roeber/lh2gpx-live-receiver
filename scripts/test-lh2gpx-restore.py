#!/usr/bin/env python3
"""Run an offline LH2GPX archive validation and temporary restore test.

The restore target is created below the operating system's temporary directory
and is removed automatically when the test exits. No production path is used
as a restore target and no service or database connection is opened.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path, PurePosixPath


ALLOWED = {
    "manifest.json",
    "data",
    "data/receiver.sqlite3",
    "data/raw-payloads.ndjson",
    "data/live-location.ndjson",
}


def fail(message: str) -> "NoReturn":
    print(f"FEHLER: {message}", file=sys.stderr)
    raise SystemExit(1)


def extract_safely(archive: Path, target: Path) -> None:
    with tarfile.open(archive, mode="r:gz") as tar:
        seen: set[str] = set()
        for member in tar.getmembers():
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts:
                fail(f"unsicherer Archivpfad: {member.name}")
            if member.name in seen:
                fail(f"doppelter Archivpfad: {member.name}")
            seen.add(member.name)
            if member.name not in ALLOWED:
                fail(f"unerwarteter Archivinhalt: {member.name}")
            if member.issym() or member.islnk() or not (member.isfile() or member.isdir()):
                fail(f"nicht erlaubter Archivtyp: {member.name}")
            if not member.isfile():
                continue
            destination = target / member.name
            destination.parent.mkdir(parents=True, exist_ok=True)
            source = tar.extractfile(member)
            if source is None:
                fail(f"Archivdatei kann nicht gelesen werden: {member.name}")
            with source, destination.open("xb") as output:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    output.write(chunk)


def check_restored_files(target: Path) -> tuple[int, int, int | None]:
    manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("contains_application_secrets") is not False:
        fail("Restore-Manifest bestätigt keinen secret-freien Archivinhalt")
    database = target / "data/receiver.sqlite3"
    import sqlite3

    connection = sqlite3.connect(f"file:{database}?mode=ro", uri=True)
    try:
        quick = connection.execute("PRAGMA quick_check").fetchone()[0]
        if quick != "ok":
            fail(f"Restore-SQLite quick_check fehlgeschlagen: {quick}")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        required = {"gps_points", "external_points", "dawarich_sync_state"}
        if not required.issubset(tables):
            fail("Restore-SQLite enthält nicht alle erwarteten Kern-Tabellen")
        gps = connection.execute("SELECT count(*) FROM gps_points").fetchone()[0]
        external = connection.execute("SELECT count(*) FROM external_points").fetchone()[0]
        row = connection.execute(
            "SELECT last_event_id FROM dawarich_sync_state WHERE provider='dawarich'"
        ).fetchone()
        cursor = int(row[0]) if row and row[0] is not None else None
        return gps, external, cursor
    finally:
        connection.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Offline-Restore-Test in temporärem Ziel")
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    archive = args.archive.resolve(strict=True)
    if not archive.is_file():
        fail("Archiv ist keine reguläre Datei")

    validator = Path(__file__).with_name("validate-lh2gpx-backup.py")
    subprocess.run([sys.executable, str(validator), str(archive)], check=True)

    with tempfile.TemporaryDirectory(prefix="lh2gpx-restore-test-") as temporary:
        target = Path(temporary)
        extract_safely(archive, target)
        gps, external, cursor = check_restored_files(target)
        print(f"Temporäres Restore-Ziel: {target}")
        print(f"Restore geprüft: gps_points={gps}, external_points={external}, sync_cursor={cursor}")

    print("OK: Restore-Test abgeschlossen; temporäres Ziel wurde automatisch entfernt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
