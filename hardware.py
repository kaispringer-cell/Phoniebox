"""Single-process hardware workers. Never run multiple web workers."""

import errno
import queue
from contextlib import closing
import select
import subprocess
import threading
import time
import bluetooth as bt
from configure_audio import device_reachable
from spotify import Problem

READER = '/dev/input/by-id/usb-413d_2107-event-kbd'


def reader_error(error, phase):
    reason = {
        errno.EACCES: 'Zugriff verweigert. Geräteberechtigungen prüfen.',
        errno.EPERM: 'Zugriff vom System verweigert. Dienstrechte prüfen.',
        errno.EBUSY: 'Reader von einem anderen Programm exklusiv belegt.',
        errno.ENOENT: 'Reader-Gerätepfad fehlt. USB-Verbindung prüfen.',
        errno.ENODEV: 'Reader wurde getrennt. USB-Verbindung prüfen.',
        errno.EIO: 'USB-Lesefehler. Reader neu verbinden.',
    }.get(error.errno, error.strerror or str(error))
    return f'NFC: {reason} Schritt: {phase}; Fehler {error.errno}.'



class DigitReader:
    """USB keyboard digits followed by ENTER, preserving leading zeroes."""

    def __init__(self):
        self.buffer = ''
        self.last = 0
        self.invalid = False

    def feed(self, key, now):
        if now - self.last > 2:
            self.buffer = ''
            self.invalid = False
        self.last = now
        if key in ('KEY_ENTER', 'KEY_KPENTER'):
            uid, self.buffer = self.buffer, ''
            invalid, self.invalid = self.invalid, False
            return uid if not invalid and 1 <= len(uid) <= 32 and uid.isdigit() else None
        digits = {**{f'KEY_{i}': str(i) for i in range(10)}, **{f'KEY_KP{i}': str(i) for i in range(10)}}
        if not self.invalid and key in digits and len(self.buffer) < 32:
            self.buffer += digits[key]
        else:
            self.buffer = ''
            self.invalid = True
        return None


class Hardware:
    def __init__(self, store, spotify):
        self.store, self.spotify = store, spotify
        self.stop = threading.Event()
        self.restart = threading.Event()
        self.bluetooth = bt.Reconnector(store, self.restart, self.stop)
        self.lock = threading.Lock()
        self.process = None
        self.reader_status = 'Reader wird gestartet'
        self.player_status = 'Player wird gestartet'
        self.message = ''
        self.last_music_uid = ''
        self.last_uid = ''
        self.scan_revision = 0
        self.learn_until = 0
        self.learned = ''
        self.last_scan = ('', 0)
        self.audio_lock = threading.RLock()
        self.local_audio = threading.Event()
        self.media = None
        self.jobs = queue.Queue(maxsize=1)

    def start(self):
        for fn in (self.player_loop, self.reader_loop, self.play_loop, self.bluetooth.loop):
            threading.Thread(target=fn, daemon=True).start()

    def close(self):
        if self.media:
            self.media.close()
        self.stop.set()
        self.restart.set()
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                self.process.kill()

    def learn(self):
        with self.lock:
            self.learn_until = time.monotonic() + 60
            self.learned = ''

    def cancel(self):
        with self.lock:
            self.learn_until = 0

    def scan(self, uid):
        now = time.monotonic()
        with self.lock:
            if now < self.learn_until:
                if uid != self.last_scan[0] or now - self.last_scan[1] >= 3:
                    self.scan_revision += 1
                self.last_uid = uid
                self.learned = uid
                self.last_scan = (uid, now)
                return
            if uid == self.last_scan[0] and now - self.last_scan[1] < 3:
                return
            self.last_scan = (uid, now)
            self.last_uid = uid
            self.scan_revision += 1
        card = self.store.card(uid)
        if not card:
            self.message = f'Unbekannte Karte: {uid}. Unter NFC-Karten zuweisen.'
            return
        try:
            self.jobs.put_nowait(card)
        except queue.Full:
            self.message = 'Wiedergabeauftrag läuft bereits. Bitte kurz warten.'

    def snapshot(self):
        with self.lock:
            return dict(
                reader=self.reader_status,
                player=self.player_status,
                message=self.message,
                last_uid=self.last_uid,
                scan_revision=self.scan_revision,
                card=self.store.card(self.last_uid) if self.last_uid else None,
                learning=time.monotonic() < self.learn_until,
                learned=self.learned,
            )

    def command(self, action, uri=None, volume=None):
        # Check before delegating: AlarmRadio.command forwards Spotify commands directly,
        # so the Bluetooth check must not live behind the media branch.
        if action == 'play' and (uri or not (self.media and self.media.source)):
            self.check_audio_output()
        kwargs = {}
        if uri is not None:
            kwargs['uri'] = uri
        if volume is not None:
            kwargs['volume'] = volume
        try:
            if self.media:
                return self.media.command(action, **kwargs)
            return self.spotify.command(action, **kwargs)
        except Problem as e:
            raise Problem(self.clarify(str(e))) from e

    def check_audio_output(self):
        """Report an unavailable output while the independent worker reconnects it."""
        mac = bt.mac_in(self.store.get('audio'))
        if mac:
            info = bt.info(mac)
            if not info or not info['connected']:
                if mac in self.bluetooth.suspended:
                    raise Problem('Bluetooth wurde bewusst getrennt. Unter Bluetooth „Verbinden“ wählen.')
                raise Problem(
                    'Bluetooth-Lautsprecher ist noch nicht verbunden. '
                    'Gespeicherte Box einschalten; die automatische Verbindung läuft im Hintergrund.'
                )

    def clarify(self, message):
        """Spotify's own 'device not found' message tells the user to go select the
        Phoniebox in the Spotify app - correct when it just isn't the active device, but
        misleading when librespot never started at all because the configured audio
        output (often a Bluetooth speaker) could not be reached: there is then no device
        to select, and going looking for one in the Spotify app is a dead end. In that
        case player_loop() has already diagnosed the real, more actionable cause (see
        player_status below), so surface that instead - this is what makes a failed
        playback attempt (NFC card or the Play button) show *why* it failed, not just
        that it did."""
        if 'nicht eindeutig erreichbar' in message and self.player_status.startswith('Audioausgang'):
            return self.player_status
        return message

    def execute_card(self, card):
        action = card.get('action', 'music')
        if action == 'music':
            mode = self.store.get('repeat_card')
            if card['uid'] == self.last_music_uid and mode in ('pause', 'toggle'):
                if mode == 'pause':
                    self.command('pause')
                else:
                    self.spotify.cached_at = 0
                    state = self.spotify.state()
                    playing = state.get('is_playing') and (state.get('device') or {}).get('name') == self.store.get(
                        'name'
                    )
                    self.command('pause' if playing else 'play')
            else:
                self.command('play', uri=card['uri'])
            self.last_music_uid = card['uid']
        elif action == 'radio':
            self.play_radio(card)
        else:
            self.command(action, volume=card.get('value', 10))

    def play_radio(self, card):
        """Start a radio station; the same card again stops it (unless 'replay' is set). Live radio has no
        useful pause, so it is stopped and starts live again next time."""
        media = self.media
        if not media:
            raise Problem('Radio ist noch nicht bereit. Dienst neu starten.')
        station = card.get('station', '')
        if self.store.get('repeat_card') != 'replay' and media.is_playing('radio', station):
            media.stop()
            return
        media.alarm_until = 0
        # Keep the current level when something local is playing, otherwise use the start volume.
        media.local('radio', station, media.volume if media.source else self.store.get('volume'))

    def play_loop(self):
        while not self.stop.is_set():
            try:
                card = self.jobs.get(timeout=1)
            except queue.Empty:
                continue
            try:
                self.execute_card(card)
                self.message = 'Ausgeführt: ' + card['name']
            except Problem as e:
                self.message = str(e)
            except Exception:
                self.message = 'Interner Wiedergabefehler. Dienst neu starten.'
            finally:
                self.jobs.task_done()

    def reader_loop(self):
        try:
            from evdev import InputDevice, ecodes
        except ImportError:
            self.reader_status = 'python3-evdev fehlt'
            return
        while not self.stop.is_set():
            phase = 'Gerät öffnen'
            try:
                with closing(InputDevice(READER)) as device:
                    phase = 'Reader exklusiv übernehmen'
                    device.grab()
                    self.reader_status = 'Verbunden · M301 V4'
                    phase = 'Kartendaten lesen'
                    parser = DigitReader()
                    while not self.stop.is_set():
                        if not select.select([device.fd], [], [], 1)[0]:
                            continue
                        for event in device.read():
                            if event.type == ecodes.EV_SYN and event.code == ecodes.SYN_DROPPED:
                                parser = DigitReader()
                                continue
                            if event.type == ecodes.EV_KEY and event.value == 1:
                                key = ecodes.KEY.get(event.code, '')
                                if isinstance(key, list):
                                    key = key[0]
                                uid = parser.feed(key, time.monotonic())
                                if uid:
                                    self.scan(uid)
            except OSError as error:
                self.reader_status = reader_error(error, phase)
                self.stop.wait(3)

    def player_loop(self):
        cache = self.store.directory / 'librespot'
        cache.mkdir(mode=0o700, exist_ok=True)
        while not self.stop.is_set():
            if self.local_audio.is_set():
                self.stop.wait(0.2)
                continue
            self.restart.clear()
            try:
                # Local ALSA level stays at 100%; Spotify softvol controls listening volume.
                subprocess.run(
                    [
                        '/usr/bin/amixer',
                        '-c',
                        self.store.get('mixer_card'),
                        'sset',
                        self.store.get('mixer_control'),
                        '100%',
                    ],
                    check=True,
                    timeout=8,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                )
                device = self.store.get('audio')
                if not device_reachable(device):
                    # librespot's own error output is intentionally not surfaced (to keep
                    # auth tokens out of the journal), so without this check a device that
                    # cannot actually be opened - even an ordinary-looking 'default' silently
                    # redirected to an unavailable Bluetooth speaker - would just look like the
                    # Spotify device vanishing right after being selected, with no explanation
                    # anywhere in the web interface.
                    self.player_status = (
                        'Audioausgang „' + device + '“ nicht erreichbar. Bluetooth verbunden? '
                        'Einstellungen prüfen.'
                    )
                    self.stop.wait(5)
                    continue
                args = [
                    '/usr/local/bin/phoniebox-librespot',
                    '--name',
                    self.store.get('name'),
                    '--backend',
                    'alsa',
                    '--device',
                    device,
                    '--bitrate',
                    '160',
                    '--initial-volume',
                    str(self.store.get('volume')),
                    '--system-cache',
                    str(cache),
                    '--disable-audio-cache',
                ]
                # Suppress upstream output to avoid auth URLs/tokens entering journals.
                with self.audio_lock:
                    if self.local_audio.is_set():
                        continue
                    self.process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                self.player_status = 'librespot läuft · Spotify-Verbindung separat prüfen'
                while not self.stop.is_set() and not self.restart.wait(1):
                    if self.process.poll() is not None:
                        raise OSError('librespot exited')
            except (OSError, subprocess.SubprocessError):
                self.player_status = 'Audio/Player-Start fehlgeschlagen. ALSA-Werte und librespot prüfen.'
                self.stop.wait(5)
            finally:
                if self.process and self.process.poll() is None:
                    self.process.terminate()
                    try:
                        self.process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        self.process.kill()
                        self.process.wait()
