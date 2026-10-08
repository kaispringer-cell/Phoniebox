"""Trusted updater shipped with the desktop app. Runs on the Pi as root.

Only application files and explicit SQL migrations are applied. No Rust build,
password reset, nginx rewrite, service-unit replacement or automatic reboot.
"""

import argparse
import fcntl
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import signal
import sqlite3
import subprocess
import tarfile
import time
import urllib.request
import uuid


class UpdateError(Exception):
    pass


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r'\d+\.\d+\.\d+', value):
        raise UpdateError('Ungültige Paketversion.')
    return tuple(map(int, value.split('.')))


def relative(value):
    if not isinstance(value, str):
        raise UpdateError('Ungültiger Dateiname im Update.')
    path = PurePosixPath(value)
    if path.is_absolute() or '..' in path.parts or not path.parts or str(path) != value:
        raise UpdateError('Unzulässiger Dateipfad im Update.')
    return path


def unpack(archive, destination):
    """No tar extraction primitives: only explicitly listed regular files are copied."""
    with tarfile.open(archive, 'r:gz') as tar:
        members = tar.getmembers()
        if len(members) > 3000 or sum(m.size for m in members) > 128 * 1024 * 1024:
            raise UpdateError('Update-Paket ist zu groß.')
        by_name = {}
        for m in members:
            path = relative(m.name)
            if path.parts[0] != 'phoniebox' or not (m.isfile() or m.isdir()) or m.name in by_name:
                raise UpdateError('Ungültiger Archivinhalt; nur reguläre Projektdateien sind erlaubt.')
            by_name[m.name] = m
        member = by_name.get('phoniebox/release.json')
        if not member or not member.isfile() or member.size > 65536:
            raise UpdateError('release.json fehlt oder ist zu groß.')
        try:
            manifest = json.load(tar.extractfile(member))
        except (ValueError, TypeError):
            raise UpdateError('Ungültige release.json.') from None
        if not isinstance(manifest, dict):
            raise UpdateError('Ungültige release.json.')
        version_tuple(manifest.get('version'))
        if manifest.get('format') != 1:
            raise UpdateError('Dieses Paket benötigt einen neueren Desktop-Installer.')
        schema = manifest.get('database_schema')
        if type(schema) is not int or not 1 <= schema <= 1000:
            raise UpdateError('Ungültige Datenbankversion.')
        packages = manifest.get('packages', [])
        if not isinstance(packages, list) or any(
            not isinstance(p, str) or not re.fullmatch(r'[a-z0-9][a-z0-9+.-]{0,99}', p) for p in packages
        ):
            raise UpdateError('Ungültige Paketabhängigkeiten.')
        files = manifest.get('files')
        if (
            not isinstance(files, list)
            or not files
            or any(not isinstance(f, str) for f in files)
            or len(files) != len(set(files))
        ):
            raise UpdateError('Dateiliste fehlt oder enthält Duplikate.')
        if not {'app.py', 'run.py', 'storage.py', 'VERSION'}.issubset(files):
            raise UpdateError('Unvollständiges Programm-Update.')
        migrations = manifest.get('migrations', [])
        if not isinstance(migrations, list):
            raise UpdateError('Ungültige Migrationen.')
        for migration in migrations:
            if (
                not isinstance(migration, dict)
                or type(migration.get('to')) is not int
                or migration.get('file') not in files
            ):
                raise UpdateError('Ungültiger Datenbank-Migrationsschritt.')
        for name in files:
            path = relative(name)
            m = by_name.get('phoniebox/' + str(path))
            if not m or not m.isfile():
                raise UpdateError('Programmdatei fehlt: ' + str(path))
            target = destination / str(path)
            target.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
            with tar.extractfile(m) as source, target.open('wb') as dest:
                shutil.copyfileobj(source, dest)
            target.chmod(0o644)
            if target.suffix == '.py':
                try:
                    compile(target.read_bytes(), str(path), 'exec')
                except SyntaxError:
                    raise UpdateError('Python-Syntaxfehler im Update: ' + str(path)) from None
        if (destination / 'VERSION').read_text().strip() != manifest['version']:
            raise UpdateError('Versionsdateien stimmen nicht überein.')
        (destination / 'release.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
        (destination / 'release.json').chmod(0o644)
        for directory in destination.rglob('*'):
            if directory.is_dir():
                directory.chmod(0o755)
        destination.chmod(0o755)
        return manifest


def size_of(path):
    return sum(p.stat().st_size for p in path.rglob('*') if p.is_file() and not p.is_symlink())


def current_schema(database):
    with sqlite3.connect('file:' + str(database) + '?mode=ro', uri=True) as db:
        schema = db.execute('PRAGMA user_version').fetchone()[0]
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    if schema == 0 and {'settings', 'secrets', 'cards'}.issubset(tables):
        return 1
    if schema < 1:
        raise UpdateError('Unbekanntes Datenbankschema; Update abgebrochen.')
    return schema


def migration_plan(manifest, current):
    target = manifest['database_schema']
    if current > target:
        raise UpdateError('Dieses Update ist älter als die vorhandene Datenbank.')
    steps = []
    for number in range(current + 1, target + 1):
        found = [m for m in manifest.get('migrations', []) if m['to'] == number]
        if len(found) != 1:
            raise UpdateError('Passende Datenbankmigration fehlt für Version ' + str(number))
        steps.append(found[0])
    return steps


class Updater:
    def __init__(
        self,
        app=Path('/opt/phoniebox'),
        data=Path('/var/lib/phoniebox'),
        backups=Path('/var/backups/phoniebox'),
        run=subprocess.run,
        sleep=time.sleep,
    ):
        self.app, self.data, self.backups = Path(app), Path(data), Path(backups)
        self.run, self.sleep = run, sleep

    def service(self, action):
        result = self.run(['systemctl', action, 'phoniebox'], capture_output=True, text=True, timeout=45)
        if result.returncode:
            raise UpdateError('Phoniebox-Dienst konnte nicht ' + action + ' ausführen.')

    def dependencies(self, packages):
        missing = []
        for package in packages:
            r = self.run(['dpkg-query', '-W', '-f=${Status}', package], capture_output=True, text=True, timeout=15)
            if r.returncode or r.stdout.strip() != 'install ok installed':
                missing.append(package)
        if missing:
            env = dict(os.environ, DEBIAN_FRONTEND='noninteractive', APT_LISTCHANGES_FRONTEND='none')
            for args in (
                ['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'update'],
                ['apt-get', '-o', 'DPkg::Lock::Timeout=180', 'install', '-y'] + missing,
            ):
                if self.run(args, env=env, timeout=1800).returncode:
                    raise UpdateError('Neue Paketabhängigkeiten konnten nicht installiert werden.')

    def healthy(self, version):
        for _ in range(20):
            try:
                with urllib.request.urlopen('http://127.0.0.1:8888/health', timeout=3) as response:
                    health = json.load(response)
                if health.get('ok') and health.get('version') == version:
                    return True
            except (OSError, ValueError):
                pass
            self.sleep(1)
        return False

    def apply(self, archive):
        if not self.app.is_dir() or self.app.is_symlink() or not (self.data / 'phoniebox.sqlite3').is_file():
            raise UpdateError('Vorhandene Phoniebox-Installation nicht gefunden.')
        if self.data.is_symlink() or (self.data / 'phoniebox.sqlite3').is_symlink():
            raise UpdateError('Unerwarteter Datenpfad.')
        tag = time.strftime('%Y%m%d-%H%M%S') + '-' + uuid.uuid4().hex[:8]
        stage = self.app.parent / ('.phoniebox-stage-' + tag)
        previous = self.app.parent / ('.phoniebox-previous-' + tag)
        backup = self.backups / tag
        stage.mkdir(mode=0o755)
        stopped = False
        switched = False
        data_may_change = False
        try:
            manifest = unpack(archive, stage)
            current = (self.app / 'VERSION').read_text().strip() if (self.app / 'VERSION').exists() else '0.0.0'
            if version_tuple(manifest['version']) <= version_tuple(current):
                raise UpdateError('Paket ist nicht neuer als die installierte Version ' + current + '.')
            schema = current_schema(self.data / 'phoniebox.sqlite3')
            steps = migration_plan(manifest, schema)
            required = 2 * (size_of(self.app) + size_of(self.data) + size_of(stage)) + 100 * 1024 * 1024
            if shutil.disk_usage(self.app.parent).free < required:
                raise UpdateError('Zu wenig Speicher für Update und vollständige Sicherung.')
            self.dependencies(manifest.get('packages', []))
            print('Abhängigkeiten geprüft. Musik wird für das Update kurz angehalten.', flush=True)
            self.service('stop')
            stopped = True
            self.backups.mkdir(mode=0o700, parents=True, exist_ok=True)
            self.backups.chmod(0o700)
            backup.mkdir(mode=0o700)
            shutil.copytree(self.app, backup / 'app', symlinks=True)
            shutil.copytree(self.data, backup / 'data', symlinks=True)
            data_owner = self.data.stat()
            (backup / 'info.json').write_text(
                json.dumps(
                    {'from': current, 'to': manifest['version'], 'uid': data_owner.st_uid, 'gid': data_owner.st_gid}
                )
            )
            print('Sicherung angelegt: ' + str(backup), flush=True)
            self.app.rename(previous)
            try:
                stage.rename(self.app)
            except BaseException:
                previous.rename(self.app)
                raise
            switched = True
            data_may_change = True
            with sqlite3.connect(self.data / 'phoniebox.sqlite3') as db:
                for step in steps:
                    sql = (self.app / step['file']).read_text()
                    db.executescript(
                        'BEGIN IMMEDIATE;\n' + sql + '\nPRAGMA user_version=' + str(step['to']) + ';\nCOMMIT;'
                    )
                db.execute('PRAGMA user_version=' + str(manifest['database_schema']))
            self.service('start')
            if not self.healthy(manifest['version']):
                raise UpdateError('Die neue Weboberfläche besteht den Funktionstest nicht.')
            stopped = False  # Commit: later cleanup/output errors must not roll back success.
            shutil.rmtree(previous, ignore_errors=True)
            print('PHONIEBOX_UPDATE_OK:' + manifest['version'], flush=True)
            return manifest['version'], backup
        except BaseException:
            if stopped:
                try:
                    if switched:
                        self.service('stop')
                        shutil.rmtree(self.app)
                        previous.rename(self.app)
                    if data_may_change:
                        shutil.rmtree(self.data)
                        shutil.copytree(backup / 'data', self.data, symlinks=True)
                        for path in [self.data, *self.data.rglob('*')]:
                            os.chown(path, data_owner.st_uid, data_owner.st_gid, follow_symlinks=False)
                    self.service('start')
                    print('Vorheriger Programmstand wiederhergestellt und Dienst gestartet.', flush=True)
                except Exception:
                    print('Automatische Wiederherstellung fehlgeschlagen. Sicherung: ' + str(backup), flush=True)
            raise
        finally:
            if stage.exists():
                shutil.rmtree(stage)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('package', type=Path)
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Update benötigt sudo-Rechte.')
    os.umask(0o077)

    def interrupted(*_):
        raise UpdateError('Update unterbrochen; Wiederherstellung wird versucht.')

    for sig in (signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, interrupted)
    try:
        with open('/run/lock/phoniebox-update.lock', 'w') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            Updater().apply(args.package)
    except Exception as e:
        # No raw tokens, database rows, SQL text or tracebacks in logs.
        print(str(e) if isinstance(e, UpdateError) else 'Update abgebrochen: ' + type(e).__name__, flush=True)
        raise SystemExit(1)
