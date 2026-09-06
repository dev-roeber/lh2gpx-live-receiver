# Offsite-Backup-Checkliste: Storage Box und verschlüsselte Ziele

Diese Checkliste ist eine noch nicht aktivierte Betriebsanweisung. Sie
beschreibt Vorbereitung, Verifikation und Wiederherstellung, führt aber keine
Übertragung, Löschung oder Änderung am Produktivsystem aus.

## Sicherheits- und Zieldefinition

- [ ] Exakten Storage-Box-Account und Hostnamen dokumentieren; keine Zugangsdaten
      oder Schlüssel in Repository, README, Manifesten oder Logs ablegen.
- [ ] Einen dedizierten Storage-Box-Unteraccount nur für das Backup anlegen und
      ihn auf einen dedizierten Zielunterordner beschränken.
- [ ] Für automatisierte Abläufe SSH-Key-Authentifizierung verwenden; den
      privaten Schlüssel außerhalb des Repositories und mit restriktiven
      Dateirechten verwahren.
- [ ] Host-Key des Storage-Box-Hostnamens einmalig bewusst prüfen und danach
      per `known_hosts` pinnen. Keine pauschale Abschaltung der
      Host-Key-Prüfung verwenden.
- [ ] Einen exakten Zielpfad festlegen, zum Beispiel
      `backup/lh2gpx-receiver/`. Platzhalter erst nach Prüfung ersetzen.
- [ ] `/mnt/storagebox/YT-DL` nicht als aktive Datenbank oder Restore-Ziel
      verwenden. Ein Netzwerkdateisystem darf nur als Transport-/Ablageziel
      dienen; Restore erfolgt zunächst lokal in ein temporäres Verzeichnis.
- [ ] RPO/RTO festlegen: empfohlener Startwert Receiver/Dawarich: RPO 24 h,
      RTO 4 h; bei höherem Schutzbedarf ausdrücklich anpassen.

## Empfohlener verschlüsselter Aufbau

1. Lokales LH2GPX-Archiv zunächst mit dem vorhandenen Validator prüfen.
2. Für den Offsite-Bestand ein verschlüsseltes Repository verwenden, bevorzugt
   Restic über SFTP. Die Repository-Verschlüsselung ist unabhängig von der
   Transportverschlüsselung.
3. Repository-Passwort in einem Passwortmanager und zusätzlich als versiegelte
   Offline-Notfallkopie hinterlegen. Ohne dieses Passwort ist das Repository
   nicht wiederherstellbar.
4. Für Dawarich PostgreSQL zuerst einen konsistenten Custom-Format-Dump sowie
   einen separaten Rollen-/Globals-Dump erzeugen; danach Dump und Prüfsumme in
   dasselbe verschlüsselte Repository aufnehmen.
5. Dawarich-Dateibestände (`storage`, `public`, `watched`) getrennt vom
   Datenbankdump sichern. Redis, Photon und Tiles nur nach Inventarisierung
   aufnehmen, sofern sie nicht reproduzierbar oder geschäftskritisch sind.

Beispiel für die spätere, ausdrücklich manuell freizugebende Repository-
Initialisierung (noch nicht ausführen):

```bash
RESTIC_REPOSITORY='sftp:<subaccount>@<account>.your-storagebox.de:backup/lh2gpx-receiver' \
  restic init
```

Der Zielpfad ist relativ zum SFTP-Home. Ein absoluter Storage-Box-Pfad muss
entsprechend der tatsächlich verwendeten SFTP-Ansicht geprüft werden. Für
Storage Box sind SFTP/SSH, Rsync und Borg verfügbar; die konkrete
Protokollfreischaltung und der Port müssen im Hetzner-Konto geprüft werden.

## Vor jeder Aktivierung

- [ ] `restic`, `ssh` und `sftp` in einer festen, dokumentierten Version
      verfügbar; bei Borg entsprechend `borg` und kompatible Remote-Version.
- [ ] Lokales Backupziel mit Modus `0700`, Dateien mit `0600`.
- [ ] Ausreichend lokaler freier Speicher für SQLite-Snapshot, Dump,
      Verschlüsselungs-Repository und temporären Restore vorsehen.
- [ ] Backup-Quelle vollständig inventarisieren:
      `receiver.sqlite3`, optionale NDJSON-Rohdaten, Dawarich-PostgreSQL,
      Rollen/Globals, `storage`, `public`, `watched`, Service-/Container-
      Definitionen und Versionsinformationen.
- [ ] Ausschlüsse prüfen: `.env`, Session-Cookies, API-Keys, private Schlüssel,
      Passwortdateien und nicht benötigte Caches dürfen nicht unverschlüsselt
      oder versehentlich im Manifest landen.
- [ ] Einen Testlauf zunächst gegen ein lokales Test-Repository durchführen;
      kein Produktiv-Repository mit `init`, `backup`, `forget` oder `prune`
      ausprobieren.

## Nach einem Backup

- [ ] Exit-Code des Backup-Prozesses prüfen.
- [ ] Lokale SHA-256-Prüfsumme und Manifest prüfen.
- [ ] LH2GPX read-only validieren:

  ```bash
  scripts/validate-lh2gpx-backup.py \
    "$HOME/ki-backups/lh2gpx-live-receiver/lh2gpx-<timestamp>.tar.gz"
  scripts/test-lh2gpx-restore.py \
    "$HOME/ki-backups/lh2gpx-live-receiver/lh2gpx-<timestamp>.tar.gz"
  ```

- [ ] Für Restic zuerst Metadaten prüfen (`restic check`), regelmäßig zusätzlich
      einen vollständigen Datencheck (`restic check --read-data`) einplanen.
      Dieser liest das gesamte Repository und ist deshalb kein unbemerkter
      täglicher Job.
- [ ] Remote-Bestand read-only auflisten und die Anzahl/Größe der Snapshots
      dokumentieren; keine `--delete`, `forget` oder `prune`-Option verwenden.
- [ ] Ergebnis, Generation, Manifest-Hash und Restore-Stichprobe in einem
      Betriebsprotokoll ohne Secrets festhalten.

## Restore-Probe ohne Produktionsänderung

- [ ] Restore-Ziel neu und lokal anlegen, ausschließlich außerhalb von
      `/home/sebastian/services/`, `/mnt/storagebox/` und laufenden
      Container-/Datenbankpfaden, zum Beispiel `/tmp/lh2gpx-restore-<run>/`.
- [ ] Restore ohne `--delete` und ohne In-place-Ziel ausführen.
- [ ] LH2GPX-Archiv im temporären Ziel mit dem vorhandenen Restore-Test prüfen;
      SQLite nur über `mode=ro` öffnen und `PRAGMA quick_check` ausführen.
- [ ] Für Dawarich den Dump nur auflisten bzw. in eine temporäre PostgreSQL-
      Instanz mit separatem Datenverzeichnis einspielen; niemals gegen den
      produktiven Container verbinden.
- [ ] Tabellen, Zeilenanzahl, Zeitbereich, bekannte GPS-Stichproben,
      Dawarich-Sync-Outbox und LH2GPX-Sync-Cursor vergleichen.
- [ ] Anwendungstests nur gegen die temporären Ziele ausführen: Health/Ready,
      Kartenansicht, Export und ein inkrementeller Sync in eine Testdatenbank.
- [ ] Vor/nachher Produktionspfade per `stat` vergleichen; bei jeder Änderung
      den Test abbrechen und Ursache klären.
- [ ] Erst nach dokumentiertem Restore-Erfolg und expliziter Freigabe darf ein
      geplanter Produktionsrestore vorbereitet werden.

## Retention und Storage-Box-Snapshots

- [ ] Retention zunächst nur als Bericht ausführen; keine automatische Löschung
      aktivieren.
- [ ] Für den Start mindestens drei unabhängige Generationen behalten; als
      Arbeitswert 14 lokale Generationen und 30–90 Tage verschlüsselte Offsite-
      Generationen festlegen, bevor Speicherbedarf geprüft wurde.
- [ ] `forget`, `prune`, `--delete`, `rmdir` und Storage-Box-Snapshot-Restore
      erfordern eine separate, sichtbare Bestätigung und ein aktuelles
      überprüftes Backup.
- [ ] Storage-Box-Snapshots sind kein Ersatz für Verschlüsselung oder ein
      Restore-Test: Ein Snapshot kann spätere Änderungen und neue Daten bei
      einer Rücksetzung entfernen. Snapshot-Aufbewahrung und Zeitpunkt deshalb
      dokumentieren.

## Datenschutz und Notfallunterlagen

- [ ] Standortdaten als besonders schützenswert behandeln.
- [ ] Repository-Passwort, SSH-Key, Storage-Box-Account und Host-Key getrennt
      dokumentieren; niemals gemeinsam im selben unverschlüsselten Verzeichnis.
- [ ] Recovery-Unterlagen offline testen und mindestens einmal pro Quartal
      einen vollständigen temporären Restore durchführen.
- [ ] Bei Verlust des Repository-Passworts nicht von einer Wiederherstellung
      ausgehen; der verschlüsselte Bestand ist dann praktisch unbrauchbar.
- [ ] Keine Secrets in Tickets, Shell-History, Screenshots, Logs oder
      Chat-Nachrichten übernehmen.

## Nicht aktiviert / aktueller Befund

- [ ] Es wurde in diesem Arbeitsschritt kein Storage-Box-Ziel initialisiert.
- [ ] Es wurde keine Netzwerkübertragung ausgeführt.
- [ ] Es wurde keine Retention-Löschung ausgeführt.
- [ ] Es wurde kein systemd-Dienst geändert oder gestartet.
- [ ] Die lokale LH2GPX-Sicherung ist geprüft; ein verschlüsseltes Offsite-
      Repository und ein Dawarich-PostgreSQL-Dump bleiben bis zur expliziten
      Freigabe offen.

Referenzen: [Hetzner Storage Box – SSH/rsync/BorgBackup](https://docs.hetzner.com/storage/storage-box/access/access-ssh-rsync-borg/),
[Hetzner Storage Box – Zugriffsübersicht](https://docs.hetzner.com/storage/storage-box/access/access-overview/),
[Restic – SFTP-Repository](https://restic.readthedocs.io/en/stable/030_preparing_new_repo.html),
[Restic – Restore](https://restic.readthedocs.io/en/stable/050_restore.html),
[Restic – Check](https://restic.readthedocs.io/en/stable/077_troubleshooting.html).
