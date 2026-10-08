"""SQLite settings and encrypted credentials; never expose secret values to templates."""

import json
import os
import sqlite3
from pathlib import Path
from contextlib import contextmanager
from cryptography.fernet import Fernet

DEFAULTS = dict(
    name='NFC Phoniebox',
    audio='plughw:0,0',
    mixer_card='0',
    mixer_control='PCM',
    volume=35,
    client_id='',
    repeat_card='pause',
)


class Store:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(self.directory, 0o700)
        key = self.directory / 'secret.key'
        if not key.exists() and (self.directory / 'phoniebox.sqlite3').exists():
            raise RuntimeError(
                'Verschlüsselungsschlüssel fehlt. Datenbank und secret.key gemeinsam aus Sicherung wiederherstellen.'
            )
        try:
            with key.open('xb') as f:
                os.chmod(key, 0o600)
                f.write(Fernet.generate_key())
        except FileExistsError:
            pass
        self.cipher = Fernet(key.read_bytes())
        self.path = self.directory / 'phoniebox.sqlite3'
        with self.connect() as db:
            db.executescript('''
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value BLOB NOT NULL);
                CREATE TABLE IF NOT EXISTS cards (
                    uid TEXT PRIMARY KEY, name TEXT NOT NULL, uri TEXT NOT NULL);
            ''')
        os.chmod(self.path, 0o600)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def get(self, key, default=None):
        with self.connect() as db:
            row = db.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
        return json.loads(row[0]) if row else DEFAULTS.get(key, default)

    def put(self, **values):
        with self.connect() as db:
            db.executemany(
                'INSERT OR REPLACE INTO settings VALUES (?,?)', [(k, json.dumps(v)) for k, v in values.items()]
            )

    def secret(self, key):
        with self.connect() as db:
            row = db.execute('SELECT value FROM secrets WHERE key=?', (key,)).fetchone()
        return json.loads(self.cipher.decrypt(row[0])) if row else None

    def set_secret(self, key, value):
        with self.connect() as db:
            if value is None:
                db.execute('DELETE FROM secrets WHERE key=?', (key,))
            else:
                db.execute(
                    'INSERT OR REPLACE INTO secrets VALUES (?,?)',
                    (key, self.cipher.encrypt(json.dumps(value).encode())),
                )

    @staticmethod
    def card_details(row):
        card = dict(row)
        card.update(action='music', value=10, station='')
        if card['uri'].startswith('phoniebox:'):
            _, action, value = card['uri'].split(':')
            if action == 'radio':
                card.update(action=action, station=value, uri='')
            else:
                card.update(action=action, value=int(value), uri='')
        return card

    def cards(self):
        with self.connect() as db:
            return [self.card_details(r) for r in db.execute('SELECT * FROM cards ORDER BY name,uid')]

    def card(self, uid):
        with self.connect() as db:
            r = db.execute('SELECT * FROM cards WHERE uid=?', (uid,)).fetchone()
        return self.card_details(r) if r else None

    def save_card(self, uid, name, uri):
        with self.connect() as db:
            db.execute('INSERT OR REPLACE INTO cards VALUES (?,?,?)', (uid, name, uri))

    def delete_card(self, uid):
        with self.connect() as db:
            db.execute('DELETE FROM cards WHERE uid=?', (uid,))
