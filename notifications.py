"""Current problems of the box as short messages for the Android app's notifications.

The app polls GET /api/notifications. Each entry has a stable id, so the app notifies
once when a problem appears and removes the notification when it disappears. Every
value here comes from state the hardware threads already keep; no request runs
bluetoothctl or touches Spotify.
"""

import threading
import time

# A problem must persist this long before it is reported, so a speaker that drops for
# a moment and the reconnect worker brings back does not buzz the phone.
GRACE = 30


class Notices:
    def __init__(self, store, hardware, clock=time.time):
        self.store, self.hw, self.clock = store, hardware, clock
        self.lock = threading.Lock()
        self.first_seen = {}

    def problems(self):
        """All problems that hold right now, without grace period: [(id, title, text)]."""
        found = []
        bluetooth = self.hw.bluetooth.connected is False
        if bluetooth:
            found.append((
                'bluetooth',
                'Bluetooth nicht verbunden',
                self.hw.bluetooth.message or 'Der gespeicherte Lautsprecher ist nicht verbunden.',
            ))
        player = self.hw.player_status
        if player.startswith('Audioausgang') and not bluetooth:
            found.append(('audio', 'Audioausgang nicht erreichbar', player))
        elif player.startswith('Audio/Player-Start fehlgeschlagen'):
            found.append(('player', 'Player startet nicht', player))
        reader = self.hw.reader_status
        if not reader.startswith(('Verbunden', 'Reader wird gestartet')):
            found.append(('reader', 'NFC-Reader nicht bereit', reader))
        if not self.store.secret('tokens'):
            found.append(('spotify', 'Spotify nicht verbunden', 'Spotify im Desktop-Installer oder in der Weboberfläche verbinden.'))
        return found

    def current(self):
        """Problems that have held for at least GRACE seconds, oldest first."""
        now = self.clock()
        found = self.problems()
        with self.lock:
            ids = {id for id, _, _ in found}
            for id in list(self.first_seen):
                if id not in ids:
                    del self.first_seen[id]
            result = []
            for id, title, text in found:
                since = self.first_seen.setdefault(id, now)
                if now - since >= GRACE:
                    result.append(dict(id=id, title=title, text=text, since=int(since)))
        return sorted(result, key=lambda n: n['since'])
