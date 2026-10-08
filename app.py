"""Flask web app: settings, NFC cards, Spotify OAuth, player API, radio and alarm."""

import hmac
import os
import re
import secrets
import subprocess
import threading
import time
from pathlib import Path
from datetime import timedelta
from flask import Flask, abort, flash, jsonify, redirect, render_template, request, session
from flask.sessions import SecureCookieSessionInterface
from werkzeug.middleware.proxy_fix import ProxyFix
from storage import Store
from spotify import Spotify, Problem, REDIRECT, normalize_uri
from hardware import Hardware
from alarm_radio import (
    ALARM_FORM_FIELDS,
    ALARM_ID,
    AlarmRadio,
    STATIONS,
    TONES,
    alarm_config,
    alarm_draft,
    alarm_summary,
    main_bluetooth_output,
)
from configure_audio import ALSA_BLUETOOTH, ALSA_LOCAL, analog_device
import bluetooth as bt


def create_app(directory=None, start_hardware=False):
    store = Store(directory or os.environ.get('PHONIEBOX_DATA', '/var/lib/phoniebox'))
    key = store.secret('session_key')
    if not key:
        key = secrets.token_hex(32)
        store.set_secret('session_key', key)
    app = Flask(__name__)
    # Backend is loopback-only. Nginx overwrites X-Forwarded-Proto.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1)
    app.config.update(
        SECRET_KEY=key,
        MAX_CONTENT_LENGTH=16384,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=8),
    )
    sp = Spotify(store)
    hw = Hardware(store, sp)
    app.extensions.update(store=store, spotify=sp, hardware=hw)
    media = AlarmRadio(store, hw)
    hw.media = media
    app.extensions['media'] = media
    oauth = {}
    auth_lock = threading.Lock()
    bt_lock = hw.bluetooth.lock
    reboot_lock = threading.Lock()
    reboot_requested = False

    @app.before_request
    def guard():
        if request.host not in ('phoniebox.local', 'phoniebox.local:443', '127.0.0.1:8888'):
            abort(400)
        if not request.is_secure and request.host != '127.0.0.1:8888':
            abort(400)
        # Distinct cookie names keep HTTP tunnel and HTTPS LAN sessions isolated.
        if 'csrf' not in session:
            session['csrf'] = secrets.token_urlsafe(32)
        if request.method == 'POST':
            expected = session.get('csrf', '')
            supplied = request.form.get('csrf', '') or request.headers.get('X-CSRF-Token', '')
            if not expected or not hmac.compare_digest(expected, supplied):
                abort(403)

    @app.after_request
    def headers(response):
        response.headers['Cache-Control'] = 'no-store'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Content-Security-Policy'] = (
            "default-src 'self'; img-src 'self' https://i.scdn.co https://mosaic.scdn.co; style-src 'self'; script-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        return response

    # Flask saves sessions after after_request. Select Secure per request without
    # mutating app.config (which would race between threaded requests).
    class CookieInterface(SecureCookieSessionInterface):
        def get_cookie_secure(self, app):
            return request.is_secure

        def get_cookie_name(self, app):
            return 'phoniebox_tls' if request.is_secure else 'phoniebox_tunnel'

    app.session_interface = CookieInterface()

    @app.context_processor
    def context():
        return dict(csrf=session.get('csrf', ''), device_name=store.get('name'))

    # Keep old bookmarks and installer checks working without authentication.
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        return redirect('/')

    @app.post('/logout')
    def logout():
        session.clear()
        return redirect('/')

    @app.get('/health')
    def health():
        return jsonify(ok=True, version=(Path(__file__).parent / 'VERSION').read_text().strip())

    @app.get('/')
    def index():
        draft = session.pop('alarm_draft', None)
        alarm_error = session.pop('alarm_error', None)
        alarms = media.alarms()
        # The form edits one alarm: after a rejected save the entered values, after
        # "Bearbeiten" (?alarm=<id>) that alarm, otherwise a new one.
        if draft:
            draft_id = (draft.get('id') or [''])[0]
            alarm = alarm_draft(draft, media.alarm(draft_id) or media.new_alarm())
        else:
            alarm = media.alarm(request.args.get('alarm', '')) or media.new_alarm()
        alarm_list = [dict(alarm=a, summary=alarm_summary(a)) for a in sorted(alarms, key=lambda a: a['time'])]
        return render_template(
            'index.html',
            stations=STATIONS,
            tones=TONES,
            alarm=alarm,
            alarm_list=alarm_list,
            alarm_error=alarm_error,
            main_bluetooth=main_bluetooth_output(store),
            card_groups=card_groups(store.cards()),
            action_labels={
                'radio': 'Radio',
                'pause': 'Stop / Pause',
                'play': 'Fortsetzen',
                'next': 'Nächster Titel',
                'previous': 'Vorheriger Titel',
                'volume_up': 'Lauter',
                'volume_down': 'Leiser',
                'volume': 'Lautstärke',
            },
            settings={
                k: store.get(k)
                for k in ('name', 'audio', 'mixer_card', 'mixer_control', 'volume', 'client_id', 'repeat_card')
            },
            analog_device=analog_device(store),
            has_secret=bool(store.secret('client_secret')),
            connected=bool(store.secret('tokens')),
            redirect_uri=REDIRECT,
            tunnel=request.host == '127.0.0.1:8888',
        )

    @app.errorhandler(Problem)
    def problem(error):
        if request.path.startswith('/api/'):
            return jsonify(error=str(error)), 400
        flash(str(error))
        return redirect('/')

    @app.errorhandler(bt.BluetoothError)
    def bluetooth_error(error):
        return jsonify(error='Bluetooth nicht erreichbar: ' + str(error)), 400

    @app.post('/settings')
    def settings():
        name = request.form.get('name', '').strip()
        audio = request.form.get('audio', '').strip()
        card = request.form.get('mixer_card', '').strip()
        control = request.form.get('mixer_control', '').strip()
        if not 1 <= len(name) <= 64 or any(ord(c) < 32 for c in name):
            raise Problem('Gerätename: 1–64 Zeichen ohne Steuerzeichen.')
        if not (ALSA_LOCAL.fullmatch(audio) or ALSA_BLUETOOTH.fullmatch(audio)):
            raise Problem(
                'Ungültiger Audioausgang. Erlaubt sind z. B. plughw:0,0, plughw:Kartename,0, default '
                'oder bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp.'
            )
        if not re.fullmatch(r'[A-Za-z0-9_]{1,32}', card) or not re.fullmatch(r'[A-Za-z0-9 _-]{1,64}', control):
            raise Problem('Ungültige Mixer-Angabe.')
        volume = number(request.form.get('volume', ''))
        store.put(name=name, audio=audio, mixer_card=card, mixer_control=control, volume=volume, audio_configured=True)
        hw.restart.set()
        flash('Einstellungen gespeichert. Der Audioplayer startet neu; laufende Musik wird unterbrochen.')
        return redirect('/#settings')

    def mac_or_problem():
        mac = request.form.get('mac', '').strip().upper()
        if not bt.valid_mac(mac):
            raise Problem('Ungültige Bluetooth-Geräteadresse.')
        return mac

    def active_bluetooth_mac():
        """The MAC of the Bluetooth device the main audio output is currently set to
        (store's 'audio' value), if any - independent of bluetoothctl's own connected
        state, so the Bluetooth screen can show which paired device is actually the
        configured output rather than just which one happens to be connected."""
        return bt.mac_in(store.get('audio'))

    @app.get('/api/bluetooth')
    def bluetooth_status():
        if not bt_lock.acquire(blocking=False):
            return jsonify(paired=[], active=active_bluetooth_mac(), adapter={
                'state': 'busy', 'message': hw.bluetooth.message or 'Bluetooth-Vorgang läuft …'
            })
        try:
            adapter = bt.adapter_status()
            return jsonify(paired=bt.paired_devices() if adapter['state'] == 'ready' else [], active=active_bluetooth_mac(), adapter=adapter, reconnect=hw.bluetooth.message)
        finally:
            bt_lock.release()

    @app.post('/api/bluetooth/scan')
    def bluetooth_scan():
        if not bt_lock.acquire(blocking=False):
            raise Problem('Bluetooth ist gerade mit einem anderen Vorgang beschäftigt. Kurz warten.')
        try:
            return jsonify(found=bt.scan(), paired=bt.paired_devices(), active=active_bluetooth_mac())
        finally:
            bt_lock.release()

    @app.post('/api/bluetooth/pair')
    def bluetooth_pair():
        mac = mac_or_problem()
        if not bt_lock.acquire(blocking=False):
            raise Problem('Bluetooth ist gerade mit einem anderen Vorgang beschäftigt. Kurz warten.')
        try:
            hw.bluetooth.resume(mac)
            ok, message = bt.pair(mac)
        finally:
            bt_lock.release()
        if not ok:
            raise Problem(message)
        return jsonify(ok=True, message=message)

    @app.post('/api/bluetooth/connect')
    def bluetooth_connect():
        mac = mac_or_problem()
        with bt_lock:
            hw.bluetooth.resume(mac)
            bt.power_on()
            ok = bt.connect(mac)
        if not ok:
            raise Problem('Verbindung fehlgeschlagen. Ist der Lautsprecher eingeschaltet und in Reichweite?')
        if active_bluetooth_mac() == mac.upper():
            hw.restart.set()
        return jsonify(ok=True)

    @app.post('/api/bluetooth/disconnect')
    def bluetooth_disconnect():
        mac = mac_or_problem()
        with bt_lock:
            if not bt.disconnect(mac):
                raise Problem('Lautsprecher konnte nicht getrennt werden.')
            hw.bluetooth.suspend(mac)
        return jsonify(ok=True)

    @app.post('/api/bluetooth/forget')
    def bluetooth_forget():
        mac = mac_or_problem()
        with bt_lock:
            if not bt.forget(mac):
                raise Problem('Lautsprecher konnte nicht entfernt werden.')
            hw.bluetooth.suspend(mac)
        return jsonify(ok=True)

    @app.post('/api/bluetooth/use')
    def bluetooth_use():
        mac = mac_or_problem()
        audio = 'bluealsa:DEV=' + mac + ',PROFILE=a2dp'
        if not ALSA_BLUETOOTH.fullmatch(audio):
            raise Problem('Ungültiger Audioausgang.')
        # Connect first: setting this as the output without it actually being connected
        # would just reproduce the original 'device appears in Spotify, then vanishes'
        # bug (1.9.2's device_reachable() preflight would then refuse to start librespot).
        with bt_lock:
            hw.bluetooth.resume(mac)
            bt.power_on()
            connected = bt.connect(mac)
        if not connected:
            raise Problem(
                'Lautsprecher konnte nicht verbunden werden, Audioausgang bleibt unverändert. '
                'Ist er eingeschaltet und in Reichweite?'
            )
        store.put(audio=audio)
        hw.restart.set()
        return jsonify(ok=True, audio=audio, message='Verbunden. Audioausgang gesetzt, Player startet neu.')

    @app.post('/nfc/settings')
    def nfc_settings():
        mode = request.form.get('repeat_card', '')
        if mode not in ('replay', 'pause', 'toggle'):
            raise Problem('Ungültige Aktion beim erneuten Auflegen.')
        store.put(repeat_card=mode)
        flash('NFC-Einstellungen gespeichert.')
        return redirect('/#cards')

    @app.post('/credentials')
    def credentials():
        client = request.form.get('client_id', '').strip()
        secret = request.form.get('client_secret', '').strip()
        if not re.fullmatch(r'[a-fA-F0-9]{32}', client):
            raise Problem('Bitte die 32-stellige Client-ID aus dem Spotify-Dashboard eintragen.')
        if secret and not re.fullmatch(r'[a-fA-F0-9]{32}', secret):
            raise Problem('Bitte das 32-stellige Client Secret aus dem Spotify-Dashboard eintragen.')
        with sp.lock:
            changed = client != store.get('client_id')
            if changed and not secret:
                raise Problem('Bei neuer Client-ID auch das zugehörige Client Secret eintragen.')
            store.put(client_id=client)
            if secret:
                store.set_secret('client_secret', secret)
            if changed or secret:
                store.set_secret('tokens', None)
                sp.cached_at = 0
                with auth_lock:
                    oauth.clear()
        flash('Client-Daten gespeichert. Jetzt Spotify verbinden.')
        return redirect('/#spotify')

    @app.post('/oauth/start')
    def oauth_start():
        if request.host != '127.0.0.1:8888':
            raise Problem(
                'Für die Spotify-Anmeldung den SSH-Tunnel öffnen und http://127.0.0.1:8888 im selben Browser verwenden. Siehe Anleitung.'
            )
        if not store.get('client_id') or not store.secret('client_secret'):
            raise Problem('Zuerst Client-ID und Client Secret speichern.')
        url, pending = sp.authorize()
        nonce = secrets.token_urlsafe(32)
        with auth_lock:
            for k in list(oauth):
                if oauth[k]['expires'] < time.time():
                    del oauth[k]
            if len(oauth) >= 20:
                raise Problem('Zu viele offene Anmeldungen. Bitte zehn Minuten warten.')
            oauth[nonce] = pending
        session['oauth_nonce'] = nonce
        return redirect(url)

    @app.get('/callback')
    def callback():
        if request.host != '127.0.0.1:8888':
            abort(400)
        with auth_lock:
            pending = oauth.pop(session.pop('oauth_nonce', ''), None)
        if (
            not pending
            or pending['expires'] < time.time()
            or not hmac.compare_digest(pending['state'], request.args.get('state', ''))
        ):
            raise Problem('Anmeldung ungültig oder abgelaufen. Im Tunnel erneut starten.')
        if request.args.get('error') or not request.args.get('code'):
            raise Problem('Spotify-Anmeldung wurde abgebrochen.')
        sp.exchange(request.args['code'], pending['verifier'])
        flash('Spotify-Web-API verbunden. Nun in der Spotify-App die Phoniebox als Wiedergabegerät auswählen.')
        return redirect('/#spotify')

    @app.post('/disconnect')
    def disconnect():
        with sp.lock:
            store.set_secret('tokens', None)
            sp.cached_at = 0
            sp.cached = None
        with auth_lock:
            oauth.clear()
        flash(
            'Web-API-Verbindung lokal gelöscht. Die Spotify-Connect-Anmeldung von librespot bleibt bestehen. Vollständig widerrufen: Spotify-Konto → Apps.'
        )
        return redirect('/#spotify')

    @app.get('/api/spotify/search')
    def spotify_search():
        query = request.args.get('q', '').strip()
        kind = request.args.get('type') or None
        if kind is not None and kind not in ('track', 'album', 'playlist'):
            raise Problem('Unbekannter Suchtyp.')
        if not 1 <= len(query) <= 100:
            return jsonify(results=[])
        return jsonify(results=sp.search(query, kind=kind))

    @app.post('/cards')
    def cards():
        uid = request.form.get('uid', '').strip()
        name = request.form.get('name', '').strip()
        action = request.form.get('action', 'music')
        default_names = {
            'pause': 'Stop / Pause',
            'play': 'Wiedergabe fortsetzen',
            'next': 'Nächster Titel',
            'previous': 'Vorheriger Titel',
            'volume_up': 'Lauter',
            'volume_down': 'Leiser',
            'volume': 'Lautstärke',
        }
        if not name:
            name = default_names.get(action, '')
        if not name and action == 'radio':
            name = next((s['name'] for s in STATIONS if s['id'] == request.form.get('station', '')), '')
        if not re.fullmatch(r'[0-9]{1,32}', uid) or not 1 <= len(name) <= 100:
            raise Problem(
                'Karten-ID muss 1–32 Ziffern enthalten; Musik-Karten benötigen einen Namen (maximal 100 Zeichen).'
            )

        if action not in ('music', 'radio', 'play', 'pause', 'next', 'previous', 'volume_up', 'volume_down', 'volume'):
            raise Problem('Unbekannte Kartenaktion.')
        if action == 'music':
            uri = normalize_uri(request.form.get('uri', ''))
        elif action == 'radio':
            station = request.form.get('station', '')
            if not any(s['id'] == station for s in STATIONS):
                raise Problem('Radiosender nicht gefunden.')
            uri = f'phoniebox:radio:{station}'
        else:
            value = number(request.form.get('value', '10')) if action in ('volume_up', 'volume_down', 'volume') else 0
            if action in ('volume_up', 'volume_down') and value == 0:
                raise Problem('Lautstärkeschritt muss mindestens 1 sein.')
            uri = f'phoniebox:{action}:{value}'
        store.save_card(uid, name, uri)
        hw.cancel()
        flash('Karte gespeichert. Die zugeordnete Aktion wird beim Auflegen ausgeführt.')
        return redirect('/#cards')

    @app.post('/cards/delete')
    def delete_card():
        store.delete_card(request.form.get('uid', ''))
        flash('Zuordnung gelöscht.')
        return redirect('/#cards')

    @app.post('/api/learn')
    def learn():
        hw.learn()
        return jsonify(ok=True)

    @app.post('/api/learn/cancel')
    def cancel():
        hw.cancel()
        return jsonify(ok=True)

    @app.get('/api/hardware')
    def hardware():
        return jsonify(hw.snapshot())

    @app.post('/api/system/reboot')
    def reboot():
        nonlocal reboot_requested
        with reboot_lock:
            if reboot_requested:
                return jsonify(message='Neustart wurde bereits angefordert.')
            try:
                ready = subprocess.run(
                    ['/usr/bin/systemctl', 'is-active', '--quiet', 'phoniebox-reboot.path'],
                    timeout=3, check=False, capture_output=True,
                )
                if ready.returncode:
                    return jsonify(error='Neustart-Dienst fehlt oder ist nicht aktiv. Bitte die App mit dem aktuellen Installer aktualisieren.'), 503
                request_file = store.directory / 'reboot.request'
                fd = os.open(request_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                os.close(fd)
            except FileExistsError:
                pass
            except (OSError, subprocess.TimeoutExpired):
                return jsonify(error='Neustart konnte nicht angefordert werden. Bitte erneut versuchen.'), 503
            reboot_requested = True
        return jsonify(message='Neustart angefordert. Die Verbindung wird kurz unterbrochen. Sobald der Pi wieder bereit ist, diese Seite neu laden.'), 202

    @app.get('/api/player')
    def state():
        local = media.state()
        if local['source']:
            return jsonify(
                active=True,
                playing=not local['paused'],
                title=local['title'],
                artist='Radio' if local['source'] == 'radio' else 'Weckton',
                volume=local['volume'],
                duration=0,
                progress=0,
                cover=local.get('cover', ''),
                source=local['source'],
                url='',
            )
        state = sp.state()
        if (state.get('device') or {}).get('name') != store.get('name'):
            return jsonify(
                active=False,
                message='Spotify verbunden. Zum Starten Play drücken oder eine zugeordnete NFC-Karte auflegen.',
            )
        item = state.get('item') or {}
        album = item.get('album') or item.get('show') or {}
        images = item.get('images') or album.get('images') or []
        cover = images[0].get('url', '') if images else ''
        if not cover.startswith(('https://i.scdn.co/', 'https://mosaic.scdn.co/')):
            cover = ''
        return jsonify(
            active=True,
            playing=state.get('is_playing', False),
            title=item.get('name', 'Ohne Titel'),
            artist=', '.join(x.get('name', '') for x in item.get('artists', [])) or album.get('publisher', ''),
            cover=cover,
            progress=state.get('progress_ms') or 0,
            duration=item.get('duration_ms') or 0,
            volume=(state.get('device') or {}).get('volume_percent'),
            url=(item.get('external_urls') or {}).get('spotify', ''),
        )

    @app.post('/api/player/<action>')
    def player(action):
        volume = number(request.form.get('volume', '')) if action in ('volume', 'volume_up', 'volume_down') else None
        hw.command(action, uri=request.form.get('uri') or None, volume=volume)
        return jsonify(ok=True)

    def alarm_id_from_form(required):
        alarm_id = request.form.get('id', '')
        if (alarm_id or required) and not ALARM_ID.fullmatch(alarm_id):
            raise Problem('Ungültiger Wecker.')
        return alarm_id

    @app.post('/alarm')
    def save_alarm():
        alarm_id = alarm_id_from_form(required=False)
        try:
            config = alarm_config(request.form, fallback_bluetooth=main_bluetooth_output(store))
            alarm_id = media.save_alarm(config, alarm_id)
        except Problem as error:
            # Keep what was entered and show why, right in the alarm section. Previously the
            # generic handler redirected to the page top with the old saved values, which
            # looked exactly like "the alarm was not saved" with no visible reason.
            session['alarm_draft'] = {name: request.form.getlist(name) for name in ALARM_FORM_FIELDS}
            session['alarm_error'] = str(error)
            return redirect('/#alarm')
        if config['enabled']:
            flash(f"Wecker {config['time']} gespeichert und aktiv. Zeitzone: Europe/Berlin.")
        else:
            flash(f"Wecker {config['time']} gespeichert, aber nicht aktiv – er klingelt erst mit Haken bei „Wecker aktiv“.")
        return redirect('/#alarm')

    @app.post('/alarm/enabled')
    def toggle_alarm():
        alarm_id = alarm_id_from_form(required=True)
        enabled = request.form.get('enabled') == 'on'
        media.set_enabled(alarm_id, enabled)
        flash(f"Wecker {media.alarm(alarm_id)['time']} {'eingeschaltet' if enabled else 'ausgeschaltet'}.")
        return redirect('/#alarm')

    @app.post('/alarm/delete')
    def delete_alarm():
        alarm_id = alarm_id_from_form(required=True)
        alarm = media.alarm(alarm_id)
        media.delete_alarm(alarm_id)
        flash(f"Wecker {alarm['time']} gelöscht.")
        return redirect('/#alarm')

    @app.post('/api/alarm/test')
    def test_alarm():
        alarm_id = alarm_id_from_form(required=True)
        alarm = media.alarm(alarm_id)
        if not alarm:
            raise Problem('Dieser Wecker existiert nicht mehr.')
        media.fire(alarm)
        return jsonify(ok=True)

    @app.post('/api/media/start')
    def start_media():
        source = request.form.get('source')
        if source not in ('radio', 'tone'):
            raise Problem('Ungültige Quelle.')
        media.alarm_until = 0
        media.local(source, request.form.get('choice', ''), number(request.form.get('volume', '30')))
        return jsonify(ok=True)

    @app.post('/api/media/stop')
    def stop_media():
        media.stop()
        return jsonify(ok=True)

    @app.get('/api/media')
    def media_status():
        return jsonify(media.state())

    if start_hardware:
        hw.start()
        media.start()
    return app


CARD_GROUPS = (
    ('music', 'Musik'),
    ('radio', 'Radio'),
    ('control', 'Steuerung'),
)
CONTROL_ORDER = ('pause', 'play', 'previous', 'next', 'volume_down', 'volume_up', 'volume')


def card_groups(cards):
    """NFC cards grouped by type (music, radio, control) for the card list, each group sorted
    by name; control cards follow the order of the actions in the card form. Empty groups
    are left out."""
    grouped = {key: [] for key, _ in CARD_GROUPS}
    for card in cards:
        grouped[card['action'] if card['action'] in ('music', 'radio') else 'control'].append(card)
    for key, items in grouped.items():
        if key == 'control':
            rank = {action: i for i, action in enumerate(CONTROL_ORDER)}
            items.sort(key=lambda c: (rank.get(c['action'], len(rank)), c['name'].casefold(), c['uid']))
        else:
            items.sort(key=lambda c: (c['name'].casefold(), c['uid']))
    return [dict(key=key, label=label, cards=grouped[key]) for key, label in CARD_GROUPS if grouped[key]]


def number(value):
    try:
        n = int(value)
    except (ValueError, TypeError):
        raise Problem('Lautstärke muss eine ganze Zahl von 0 bis 100 sein.') from None
    if not 0 <= n <= 100:
        raise Problem('Lautstärke muss zwischen 0 und 100 liegen.')
    return n
