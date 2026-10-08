"""Local radio/tone playback and one weekly alarm; all settings live in SQLite."""

import array
from datetime import datetime
import json
import math
import os
import tempfile
from pathlib import Path
import re
import secrets
import socket
import subprocess
import sys
import threading
import time
import wave
from zoneinfo import ZoneInfo
from spotify import Problem, normalize_uri
from configure_audio import ALSA_BLUETOOTH, analog_device

STATIONS = [
    {
        'id': 'bbc1',
        'name': 'BBC Radio 1 (international)',
        'url': 'https://as-hls-ww-live.akamaized.net/pool_01505109/live/ww/bbc_radio_one/bbc_radio_one.isml/bbc_radio_one-audio=96000.norewind.m3u8',
    },
    {
        'id': 'wdr2',
        'name': 'WDR 2 Rheinland',
        'url': 'https://wdr-wdr2-rheinland.icecastssl.wdr.de/wdr/wdr2/rheinland/mp3/128/stream.mp3',
    },
    {
        'id': '1live',
        'name': '1LIVE',
        'url': 'https://wdr-1live-live.icecastssl.wdr.de/wdr/1live/live/mp3/128/stream.mp3',
    },
    {'id': 'wdr3', 'name': 'WDR 3', 'url': 'https://wdr-wdr3-live.icecastssl.wdr.de/wdr/wdr3/live/mp3/128/stream.mp3'},
    {'id': 'wdr4', 'name': 'WDR 4', 'url': 'https://wdr-wdr4-live.icecastssl.wdr.de/wdr/wdr4/live/mp3/128/stream.mp3'},
    {'id': 'wdr5', 'name': 'WDR 5', 'url': 'https://wdr-wdr5-live.icecastssl.wdr.de/wdr/wdr5/live/mp3/128/stream.mp3'},
    {
        'id': 'maus',
        'name': 'Die Maus',
        'url': 'https://wdr-diemaus-live.icecastssl.wdr.de/wdr/diemaus/live/mp3/128/stream.mp3',
    },
    {'id': 'dlf', 'name': 'Deutschlandfunk', 'url': 'https://st01.sslstream.dlf.de/dlf/01/128/mp3/stream.mp3'},
    {
        'id': 'bbc2',
        'name': 'BBC Radio 2 (international)',
        'url': 'https://as-hls-ww-live.akamaized.net/pool_74208725/live/ww/bbc_radio_two/bbc_radio_two.isml/bbc_radio_two-audio=96000.norewind.m3u8',
    },
    {'id': 'bbcworld', 'name': 'BBC World Service', 'url': 'https://stream.live.vc.bbcmedia.co.uk/bbc_world_service'},
]
TONES = {'bell': 'Glockenton', 'beep': 'Signalton', 'melody': 'Melodie'}
DEFAULT_ALARM = {
    'enabled': False,
    'time': '07:00',
    'days': [0, 1, 2, 3, 4],
    'source': 'tone',
    'tone': 'bell',
    'station': 'wdr2',
    'uri': '',
    'volume': 30,
    'duration': 15,
    'output': 'analog',
    'bluetooth_device': '',
}


ALARM_FORM_FIELDS = (
    'id', 'enabled', 'time', 'days', 'source', 'tone', 'station', 'uri', 'volume', 'duration', 'output',
    'bluetooth_device',
)
ALARM_ID = re.compile(r'[0-9a-f]{8}')
DAY_LABELS = ('Mo', 'Di', 'Mi', 'Do', 'Fr', 'Sa', 'So')


def alarm_summary(config):
    """Short, human-readable description of one alarm for the alarm list."""
    days = sorted(config.get('days') or [])
    if days == list(range(7)):
        when = 'täglich'
    elif days == [0, 1, 2, 3, 4]:
        when = 'Mo–Fr'
    elif days == [5, 6]:
        when = 'Sa + So'
    else:
        when = ', '.join(DAY_LABELS[d] for d in days if d in range(7))
    source = config.get('source')
    if source == 'radio':
        station = next((s['name'] for s in STATIONS if s['id'] == config.get('station')), config.get('station'))
        what, where = 'Radio · ' + station, None
    elif source == 'spotify':
        what, where = 'Spotify-Musik', 'Hauptausgang'
    else:
        what, where = 'Weckton · ' + TONES.get(config.get('tone'), ''), None
    if where is None:
        where = 'Bluetooth' if config.get('output') == 'bluetooth' else 'Klinke'
    return ' · '.join([when, what, where, f"{config.get('volume')} %", f"{config.get('duration')} Min."])


def main_bluetooth_output(store):
    """The main audio output, if it is a Bluetooth speaker; otherwise ''."""
    audio = store.get('audio') or ''
    return audio if ALSA_BLUETOOTH.fullmatch(audio) else ''


def alarm_draft(form, saved):
    """What the alarm form showed when saving failed, so a rejected entry is not silently
    replaced by the old saved values. Values stay as typed; alarm_config() validates them."""

    def first(name):
        values = form.get(name) or []
        return values[0] if values else ''

    days = []
    for value in form.get('days') or []:
        try:
            days.append(int(value))
        except ValueError:
            pass
    draft = dict(saved)
    draft.update(
        enabled='on' in (form.get('enabled') or []),
        days=days,
        **{name: first(name) for name in ALARM_FORM_FIELDS if name not in ('enabled', 'days')},
    )
    return draft


def alarm_config(form, fallback_bluetooth=''):
    clock = form.get('time', '')
    if not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', clock):
        raise Problem('Bitte eine gültige Weckzeit wählen.')
    try:
        days = sorted(set(int(d) for d in form.getlist('days')))
        volume = int(form.get('volume', ''))
        duration = int(form.get('duration', ''))
    except (TypeError, ValueError):
        raise Problem('Ungültige Tage, Lautstärke oder Dauer.') from None
    if not days or any(d not in range(7) for d in days):
        raise Problem('Mindestens einen Wochentag wählen.')
    if not 1 <= volume <= 100 or not 1 <= duration <= 60:
        raise Problem('Lautstärke: 1–100 %, Dauer: 1–60 Minuten.')
    source = form.get('source', '')
    tone = form.get('tone', 'bell')
    station = form.get('station', 'wdr2')
    if source not in ('tone', 'radio', 'spotify') or tone not in TONES or station not in {s['id'] for s in STATIONS}:
        raise Problem('Ungültige Weckquelle.')
    uri = normalize_uri(form.get('uri', '')) if source == 'spotify' else ''
    output = form.get('output', 'analog')
    bluetooth = form.get('bluetooth_device', '').strip()
    if output not in ('analog', 'bluetooth'):
        raise Problem('Ungültiger Weckausgang.')
    # Real incident: with a Bluetooth speaker as the only speaker, choosing "Bluetooth" for
    # the alarm but leaving the free-text ALSA name empty made saving fail, and the form
    # jumped back to the old values - it looked as if the alarm was simply not saved. The
    # main output already names that very speaker, so use it when nothing else is given.
    if output == 'bluetooth' and not bluetooth:
        bluetooth = fallback_bluetooth
    if bluetooth and not ALSA_BLUETOOTH.fullmatch(bluetooth):
        raise Problem('Ungültiger Bluetooth-Gerätename. Beispiel: bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp')
    if output == 'bluetooth' and not bluetooth:
        raise Problem(
            'Für den Weckausgang Bluetooth ist kein Lautsprecher bekannt. Unter Bluetooth einen Lautsprecher '
            '„Als Audioausgang verwenden“ oder hier seinen ALSA-Namen eintragen.'
        )
    return dict(
        enabled=form.get('enabled') == 'on',
        time=clock,
        days=days,
        volume=volume,
        duration=duration,
        source=source,
        tone=tone,
        station=station,
        uri=uri,
        output=output,
        bluetooth_device=bluetooth,
    )


def alarm_key(config, now):
    """Marker stored per alarm in alarm_last_dates: date plus alarm time, so a time changed later the same day rings."""
    return now.date().isoformat() + ' ' + config['time']


def due(config, now, last_date):
    # Europe/Berlin handles DST. On the repeated autumn hour ring only once;
    # the skipped spring minute does not ring. Missed alarms are not replayed.
    # A bare date comes from versions up to 1.18.0 and blocks that whole day.
    return (
        config['enabled']
        and now.weekday() in config['days']
        and now.strftime('%H:%M') == config['time']
        and last_date not in (alarm_key(config, now), now.date().isoformat())
    )


def make_tone(path, kind):
    rate = 22050
    data = array.array('h')
    for i in range(rate * 3):
        t = i / rate
        phase = t % 1
        frequency = {'bell': 660, 'beep': 880}.get(kind) or [523, 659, 784][int(t) % 3]
        envelope = (
            max(0, 1 - phase) * min(1, phase * 100) if kind != 'beep' else (min(1, phase * 100) if phase < 0.25 else 0)
        )
        data.append(int(10000 * envelope * math.sin(2 * math.pi * frequency * t)))
    if sys.byteorder != 'little':
        data.byteswap()
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(rate)
        f.writeframes(data.tobytes())


class AlarmRadio:
    def __init__(self, store, hw):
        self.store, self.hw, self.sp = store, hw, hw.spotify
        self.lock = threading.RLock()
        # Separate from self.lock, which is held for many seconds while a stream starts: the
        # alarm list must stay readable for the web page meanwhile.
        self.alarms_lock = threading.RLock()
        self.active_config = None
        self.process = None
        self.stderr_file = None
        self.source = None
        self.title = ''
        self.choice = ''
        self.volume = 30
        self.paused = False
        self.alarm_until = 0
        self.message = ''
        self.stop_event = threading.Event()
        self.socket_path = Path(tempfile.gettempdir()) / f'phoniebox-radio-{os.getpid()}.sock'

    def alarms(self):
        """All saved alarms, oldest first, each with its own 'id'.

        Up to 1.17.x there was exactly one alarm under the setting 'alarm'. On first read it
        becomes the first entry of 'alarms' (together with the date it last rang, so it does
        not ring twice today). The old setting is left untouched, so an older app version
        installed again still finds its alarm."""
        with self.alarms_lock:
            saved = self.store.get('alarms')
            if saved is None:
                saved = []
                legacy = self.store.get('alarm')
                if legacy:
                    alarm_id = self.new_id([])
                    saved = [{**DEFAULT_ALARM, **legacy, 'id': alarm_id}]
                    last = self.store.get('alarm_last_date')
                    if last:
                        self.store.put(alarm_last_dates={alarm_id: last})
                self.store.put(alarms=saved)
            return [{**DEFAULT_ALARM, **alarm} for alarm in saved]

    @staticmethod
    def new_id(alarms):
        taken = {alarm['id'] for alarm in alarms}
        while True:
            alarm_id = secrets.token_hex(4)
            if alarm_id not in taken:
                return alarm_id

    def alarm(self, alarm_id):
        return next((alarm for alarm in self.alarms() if alarm['id'] == alarm_id), None)

    def new_alarm(self):
        """Form values for an alarm that is about to be created. Creating an alarm means
        wanting it to ring, so "Wecker aktiv" starts ticked (nothing rings until it is saved);
        and it starts on the speaker the box actually plays through - with a Bluetooth speaker
        as main output, the jack default would ring into nothing."""
        alarm = {**DEFAULT_ALARM, 'enabled': True, 'id': ''}
        bluetooth = main_bluetooth_output(self.store)
        if bluetooth:
            alarm.update(output='bluetooth', bluetooth_device=bluetooth)
        return alarm

    def save_alarm(self, config, alarm_id=''):
        """Create a new alarm (no id) or replace an existing one; returns its id."""
        with self.alarms_lock:
            alarms = self.alarms()
            if alarm_id:
                index = next((i for i, alarm in enumerate(alarms) if alarm['id'] == alarm_id), None)
                if index is None:
                    raise Problem('Dieser Wecker existiert nicht mehr. Bitte neu anlegen.')
                alarms[index] = {**config, 'id': alarm_id}
            else:
                alarm_id = self.new_id(alarms)
                alarms.append({**config, 'id': alarm_id})
            self.store.put(alarms=alarms)
            return alarm_id

    def set_enabled(self, alarm_id, enabled):
        with self.alarms_lock:
            alarms = self.alarms()
            alarm = next((a for a in alarms if a['id'] == alarm_id), None)
            if not alarm:
                raise Problem('Dieser Wecker existiert nicht mehr.')
            alarm['enabled'] = bool(enabled)
            self.store.put(alarms=alarms)

    def delete_alarm(self, alarm_id):
        with self.alarms_lock:
            alarms = self.alarms()
            remaining = [a for a in alarms if a['id'] != alarm_id]
            if len(remaining) == len(alarms):
                raise Problem('Dieser Wecker existiert nicht mehr.')
            self.store.put(alarms=remaining)

    def start(self):
        threading.Thread(target=self.loop, daemon=True).start()

    def close(self):
        self.stop_event.set()
        with self.lock:
            self.stop_local()

    def ipc(self, command):
        try:
            with socket.socket(socket.AF_UNIX) as sock:
                sock.settimeout(2)
                sock.connect(str(self.socket_path))
                sock.sendall((json.dumps({'command': command}) + '\n').encode())
                return json.loads(sock.recv(4096).split(b'\n')[0])
        except (OSError, ValueError):
            raise Problem('Radioplayer antwortet nicht. Bitte neu starten.') from None

    def stop_local(self):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        if self.stderr_file:
            self.stderr_file.close()
            self.stderr_file = None
        self.socket_path.unlink(missing_ok=True)
        self.process = None
        self.source = None
        self.choice = ''
        self.paused = False
        self.hw.local_audio.clear()

    def local(self, source, choice, volume, device=None):
        with self.lock:
            self.stop_local()
            if source == 'radio':
                station = next((s for s in STATIONS if s['id'] == choice), None)
                if not station:
                    raise Problem('Radiosender nicht gefunden.')
                path = station['url']
                title = station['name']
            else:
                if choice not in TONES:
                    raise Problem('Weckton nicht gefunden.')
                target = self.store.directory / ('tone-' + choice + '.wav')
                make_tone(target, choice)
                path = str(target)
                title = TONES[choice]
            with self.hw.audio_lock:
                self.hw.local_audio.set()
                self.hw.restart.set()
                if self.hw.process and self.hw.process.poll() is None:
                    self.hw.process.terminate()
                    try:
                        self.hw.process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        self.hw.process.kill()
                        self.hw.process.wait(timeout=3)
                try:
                    self.socket_path.unlink(missing_ok=True)
                    args = [
                        '/usr/bin/mpv',
                        '--no-config',
                        '--no-video',
                        '--input-terminal=no',
                        '--msg-level=all=error',
                        '--ytdl=no',
                        '--ao=alsa',
                        '--audio-device=alsa/' + (device or self.store.get('audio')),
                        '--volume=' + str(volume),
                        '--volume-max=100',
                        '--network-timeout=10',
                        '--input-ipc-server=' + str(self.socket_path),
                    ]
                    if source == 'tone':
                        args += ['--loop-file=inf']
                    # A file instead of a pipe: a long stream with many errors must never block mpv.
                    self.stderr_file = tempfile.TemporaryFile()
                    self.process = subprocess.Popen(
                        args + ['--', path], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=self.stderr_file
                    )
                except OSError:
                    self.hw.local_audio.clear()
                    raise Problem('Radioplayer mpv fehlt. Update-Abhängigkeiten installieren.') from None
            self.source = source
            self.title = title
            self.choice = choice
            self.volume = volume
            # Something else is playing now, so a music card must start fresh instead of pausing.
            self.hw.last_music_uid = None
            self.paused = False
            for _ in range(30):
                if self.process.poll() is not None:
                    self.stderr_file.seek(0)
                    detail = self.stderr_file.read(2048).decode('utf-8', 'replace')
                    print('Local audio failed: ' + detail, flush=True)
                    break
                try:
                    result = self.ipc(['get_property', 'time-pos'])
                    if isinstance(result.get('data'), (int, float)):
                        return
                except Problem:
                    pass
                time.sleep(0.5)
            self.stop_local()
            raise Problem(
                'Stream oder Audioausgang nicht erreichbar. Sender kann zeitweise oder regional gesperrt sein.'
            )

    def command(self, action, uri=None, volume=None):
        with self.lock:
            if action == 'pause':
                self.alarm_until = 0
            if self.source:
                if action == 'play' and uri:
                    self.stop_local()
                    for attempt in range(8):
                        try:
                            self.sp.device(activate=True)
                            break
                        except Problem:
                            if attempt == 7:
                                raise
                            time.sleep(1)
                elif action in ('pause', 'play'):
                    self.ipc(['set_property', 'pause', action == 'pause'])
                    self.paused = action == 'pause'
                    return
                elif action in ('volume', 'volume_up', 'volume_down'):
                    self.volume = max(
                        0,
                        min(
                            100,
                            (
                                volume
                                if action == 'volume'
                                else self.volume + (volume if action == 'volume_up' else -volume)
                            ),
                        ),
                    )
                    self.ipc(['set_property', 'volume', self.volume])
                    return
                else:
                    raise Problem('Beim Radio gibt es keinen nächsten/vorherigen Titel. Bitte einen Sender wählen.')
            self.sp.command(action, uri=uri, volume=volume)

    def is_playing(self, source, choice):
        """True while exactly this radio station or tone is playing (not paused)."""
        with self.lock:
            return self.source == source and self.choice == choice and not self.paused

    def stop(self):
        with self.lock:
            self.alarm_until = 0
            if self.source:
                self.stop_local()
            else:
                self.sp.command('pause')

    def alarm_outputs(self, config):
        """ALSA devices to try for the alarm, in order. The 3.5 mm jack is always the last resort."""
        analog = (analog_device(self.store), 'Klinke')
        if config.get('output') == 'bluetooth' and config.get('bluetooth_device'):
            return [(config['bluetooth_device'], 'Bluetooth'), analog]
        return [analog]

    def play_on_alarm_output(self, source, choice, config):
        """Play tone or radio on the selected alarm output; if Bluetooth is not available, use the jack.

        Returns a short description of the output that is playing, for the status message."""
        outputs = self.alarm_outputs(config)
        for index, (device, label) in enumerate(outputs):
            try:
                self.local(source, choice, config['volume'], device=device)
            except Problem:
                if index == len(outputs) - 1:
                    raise
                continue
            return label + ', da ' + outputs[0][1] + ' nicht erreichbar' if index else label

    def fire(self, config):
        with self.lock:
            self.active_config = config
            self.message = 'Wecker läuft'
            self.alarm_until = time.monotonic() + config['duration'] * 60
            try:
                if config['source'] == 'spotify':
                    self.stop_local()
                    # Give the supervised Connect player time to reappear.
                    for attempt in range(8):
                        try:
                            self.sp.device(activate=True)
                            break
                        except Problem:
                            if attempt == 7:
                                raise
                            time.sleep(1)
                    self.sp.command('volume', volume=config['volume'], persist=False)
                    self.sp.command('play', uri=config['uri'])
                else:
                    where = self.play_on_alarm_output(
                        config['source'], config['station'] if config['source'] == 'radio' else config['tone'], config
                    )
                    self.message = 'Wecker läuft (' + where + ')'
            except (Problem, OSError):
                where = self.play_on_alarm_output('tone', config['tone'], config)
                self.message = 'Weckquelle nicht erreichbar – Ersatz-Weckton läuft (' + where + ').'

    def tick(self, now=None):
        with self.lock:
            now = now or datetime.now(ZoneInfo('Europe/Berlin'))
            alarms = self.alarms()
            with self.store.connect() as db:
                db.execute('BEGIN IMMEDIATE')
                row = db.execute("SELECT value FROM settings WHERE key='alarm_last_dates'").fetchone()
                last = json.loads(row[0]) if row else {}
                ringing = [alarm for alarm in alarms if due(alarm, now, last.get(alarm['id'], ''))]
                if ringing:
                    known = {alarm['id'] for alarm in alarms}
                    last = {key: value for key, value in last.items() if key in known}
                    last.update({alarm['id']: alarm_key(alarm, now) for alarm in ringing})
                    db.execute("INSERT OR REPLACE INTO settings VALUES ('alarm_last_dates',?)", (json.dumps(last),))
            # Several alarms at the very same minute ring once, with the first one's settings.
            if ringing:
                self.fire(ringing[0])
            if self.alarm_until and time.monotonic() >= self.alarm_until:
                self.stop()
                self.message = 'Wecker beendet.'
            if self.source and self.process and self.process.poll() is not None:
                alarm = bool(self.alarm_until)
                self.stop_local()
                self.message = 'Stream beendet.'
                if alarm:
                    config = self.active_config or DEFAULT_ALARM
                    where = self.play_on_alarm_output('tone', config['tone'], config)
                    self.message = 'Stream ausgefallen – Ersatz-Weckton läuft (' + where + ').'

    def loop(self):
        while not self.stop_event.wait(1):
            try:
                self.tick()
            except Exception:
                self.message = 'Wecker/Radio konnte nicht ausgeführt werden. Audio und Einstellungen prüfen.'

    def state(self):
        with self.lock:
            return dict(
                source=self.source,
                cover=('/static/stations/' + self.choice + '.svg') if self.source == 'radio' and self.choice in {s['id'] for s in STATIONS} else '',
                title=self.title,
                volume=self.volume,
                paused=self.paused,
                alarm=bool(self.alarm_until),
                message=self.message,
                clock=datetime.now(ZoneInfo('Europe/Berlin')).strftime('%a %d.%m. %H:%M:%S'),
            )
