"""Spotify Web API client: OAuth (PKCE), token refresh, device lookup and player commands."""

import base64
import hashlib
import re
import secrets
import threading
import time
from urllib.parse import urlencode, urlparse
import requests

REDIRECT = 'http://127.0.0.1:8888/callback'
SCOPES = 'user-read-playback-state user-modify-playback-state'


class Problem(Exception):
    pass


def normalize_uri(value):
    value = value.strip()
    if value.startswith('https://'):
        u = urlparse(value)
        if u.netloc != 'open.spotify.com':
            raise Problem('Bitte einen Link von open.spotify.com verwenden.')
        parts = u.path.strip('/').split('/')
        if parts and parts[0].startswith('intl-'):
            parts = parts[1:]
        if len(parts) != 2:
            raise Problem('Bitte einen direkten Playlist-, Album-, Titel- oder Folgenlink verwenden.')
        value = 'spotify:' + ':'.join(parts)
    if not re.fullmatch(r'spotify:(playlist|album|track|episode):[A-Za-z0-9]{22}', value):
        raise Problem('Ungültiger Spotify-Link. Erlaubt: Playlist, Album, Titel oder einzelne Podcastfolge.')
    return value


class Spotify:
    def __init__(self, store):
        self.store = store
        self.lock = threading.RLock()
        self.commands = threading.Lock()
        self.blocked_until = 0
        self.cached_at = 0
        self.cached = None
        self.fresh_until = 0

    def authorize(self):
        verifier = secrets.token_urlsafe(64)
        state = secrets.token_urlsafe(32)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        url = 'https://accounts.spotify.com/authorize?' + urlencode(
            dict(
                client_id=self.store.get('client_id'),
                response_type='code',
                redirect_uri=REDIRECT,
                scope=SCOPES,
                state=state,
                code_challenge_method='S256',
                code_challenge=challenge,
            )
        )
        return url, dict(state=state, verifier=verifier, expires=time.time() + 600)

    def token_request(self, data):
        client = self.store.get('client_id')
        secret = self.store.secret('client_secret')
        if not client or not secret:
            raise Problem('Bitte zuerst Client-ID und Client Secret speichern.')
        try:
            r = requests.post(
                'https://accounts.spotify.com/api/token', data=data, auth=(client, secret), timeout=(5, 15)
            )
        except requests.RequestException:
            raise Problem('Spotify-Anmeldung nicht erreichbar. Netzwerk und Uhrzeit des Pi prüfen.') from None
        if r.status_code != 200:
            if r.status_code == 400:
                raise Problem('Spotify-Anmeldung abgelaufen oder ungültig. Bitte erneut verbinden.')
            raise Problem(f'Spotify-Anmeldung fehlgeschlagen (HTTP {r.status_code}). Client-Daten prüfen.')
        t = r.json()
        if not t.get('access_token'):
            raise Problem('Spotify hat kein Zugriffstoken geliefert.')
        return t

    def exchange(self, code, verifier):
        with self.lock:
            t = self.token_request(
                dict(grant_type='authorization_code', code=code, redirect_uri=REDIRECT, code_verifier=verifier)
            )
            self.save_token(t)

    def save_token(self, t, old=None):
        if not t.get('refresh_token') and old:
            t['refresh_token'] = old.get('refresh_token')
        t['expires_at'] = time.time() + t.get('expires_in', 3600)
        self.store.set_secret('tokens', t)
        self.cached_at = 0

    def token(self, force=False):
        with self.lock:
            t = self.store.secret('tokens')
            if not t:
                raise Problem('Spotify ist noch nicht verbunden.')
            if force or t['expires_at'] < time.time() + 60:
                if not t.get('refresh_token'):
                    raise Problem('Bitte Spotify erneut verbinden.')
                new = self.token_request(dict(grant_type='refresh_token', refresh_token=t['refresh_token']))
                self.save_token(new, t)
                t = new
            return t['access_token']

    def api(self, method, path, body=None, params=None):
        with self.lock:
            if time.time() < self.blocked_until:
                raise Problem(
                    f'Spotify-Pause wegen Anfragelimit: noch {int(self.blocked_until-time.time())+1} Sekunden.'
                )
            for attempt in range(2):
                token = self.token(force=attempt == 1)
                # Spotify's own gateway answers a small, well-known fraction of
                # requests (especially transferring playback to a device, e.g.
                # when activating the Phoniebox) with a transient 502/503/504
                # even though the request itself was fine. This has been a
                # long-standing, never-fixed Spotify-side issue (see
                # spotify/web-api#700) and normally clears on its own within a
                # second or two, so a few quick retries here avoid surfacing a
                # spurious error – and a disappearing device – for something
                # that a simple retry would have handled.
                for gateway_attempt in range(3):
                    try:
                        r = requests.request(
                            method,
                            'https://api.spotify.com/v1' + path,
                            headers={'Authorization': 'Bearer ' + token},
                            json=body,
                            params=params,
                            timeout=(5, 15),
                        )
                    except requests.RequestException:
                        raise Problem('Spotify nicht erreichbar. Bitte später erneut versuchen.') from None
                    if r.status_code in (502, 503, 504) and gateway_attempt < 2:
                        time.sleep(0.5 * (gateway_attempt + 1))
                        continue
                    break
                if r.status_code == 401 and attempt == 0:
                    continue
                if r.status_code == 429:
                    try:
                        delay = max(1, int(r.headers.get('Retry-After', '60')))
                    except ValueError:
                        delay = 60
                    self.blocked_until = time.time() + delay
                    raise Problem(
                        f'Spotify-Anfragelimit erreicht. Mindestens {delay} Sekunden warten; bei QUOTA_EXCEEDED kann die Kontingentpause länger dauern.'
                    )
                if r.status_code == 403:
                    raise Problem(
                        'Spotify verweigert die Steuerung (403). Premium, erlaubten Testnutzer, Berechtigungen und Gerätestatus prüfen.'
                    )
                if r.status_code == 404:
                    raise Problem(
                        'Spotify-Gerät oder Inhalt nicht verfügbar. Phoniebox in Spotify auswählen und erneut versuchen.'
                    )
                if r.status_code in (502, 503, 504):
                    raise Problem(
                        f'Spotify ist gerade kurz nicht erreichbar (HTTP {r.status_code}). '
                        'Das Gerät bleibt in Spotify sichtbar – bitte in ein paar Sekunden erneut versuchen.'
                    )
                if r.status_code >= 400:
                    raise Problem(f'Spotify meldet HTTP {r.status_code}. Bitte erneut verbinden oder später versuchen.')
                # Player commands return no useful payload; some gateways send
                # plain text even with HTTP 200. Never parse a successful command.
                if method.upper() != 'GET' or r.status_code == 204 or not r.content:
                    return {}
                try:
                    result = r.json()
                except ValueError:
                    raise Problem(
                        'Spotify liefert vorübergehend eine unlesbare Antwort. Bitte erneut versuchen.'
                    ) from None
                if not isinstance(result, dict):
                    raise Problem('Spotify liefert ein unerwartetes Antwortformat. Bitte erneut versuchen.')
                return result
            raise Problem('Spotify-Anmeldung ungültig. Bitte erneut verbinden.')

    def device(self, activate=False):
        devices = self.api('GET', '/me/player/devices').get('devices', [])
        matches = [d for d in devices if d.get('name') == self.store.get('name') and d.get('id')]
        if len(matches) != 1:
            raise Problem(
                'Phoniebox nicht eindeutig erreichbar. In der Spotify-App das Gerät „'
                + self.store.get('name')
                + '“ auswählen. Gerätenamen müssen eindeutig sein.'
            )
        if matches[0].get('is_restricted'):
            raise Problem('Spotify erlaubt die Steuerung dieses Geräts nicht.')
        device_id = matches[0]['id']
        if activate and matches[0].get('is_active') is False:
            self.activate(device_id)
        return device_id

    def command(self, action, uri=None, volume=None, persist=True):
        with self.commands:
            if action == 'play' and uri:
                self.play_uri(normalize_uri(uri))
                self.fresh()
                return
            device_id = self.device(activate=action == 'play')
            params = {'device_id': device_id}
            if action == 'play':
                self.api('PUT', '/me/player/play', {}, params)
            elif action == 'pause':
                self.api('PUT', '/me/player/pause', params=params)
            elif action in ('next', 'previous'):
                self.api('POST', '/me/player/' + action, params=params)
            elif action in ('volume', 'volume_up', 'volume_down'):
                if action != 'volume':
                    devices = self.api('GET', '/me/player/devices').get('devices', [])
                    target = next((d for d in devices if d.get('id') == device_id), {})
                    current = target.get('volume_percent')
                    if type(current) is not int or target.get('supports_volume') is False:
                        raise Problem('Lautstärke dieses Geräts ist derzeit nicht steuerbar.')
                    volume = current + (volume if action == 'volume_up' else -volume)
                params['volume_percent'] = max(0, min(100, volume))
                self.api('PUT', '/me/player/volume', params=params)
                # Spotify's own volume for this device is ephemeral, held by the running
                # librespot process - it is not what 'Startlautstärke' in the settings
                # otherwise means (the volume a *fresh* librespot process starts at, see
                # hardware.py's player_loop). Without persisting it here, any restart of
                # librespot (e.g. after a radio card interrupted and then a music card
                # resumed Spotify) silently threw away whatever volume the person had
                # actually dialed in and jumped back to the old stored default instead.
                # The alarm passes persist=False: its volume must not become the start volume.
                if persist:
                    self.store.put(volume=params['volume_percent'])
            else:
                raise Problem('Unbekannte Player-Aktion.')
            self.fresh()

    def fresh(self):
        """Spotify reports a changed playback only after a second or two. A state read right
        after a command would otherwise be cached for 15 seconds with the old title."""
        self.cached_at = 0
        self.fresh_until = time.time() + 10

    def play_uri(self, uri):
        """Start a card's album, playlist or title on the Phoniebox.

        Up to 1.18.1 an inactive Phoniebox was first activated with a transfer (play=False),
        which loads whatever the account played last (e.g. an old album from the phone) onto
        the box, and then waited at most 4 seconds for Spotify to report it active. If that
        took longer, the card failed with 'Bitte Play gleich erneut drücken' and had to be
        put on a second time. The play request itself names the device and the new content,
        so Spotify activates the box and starts the right music in one step. Only if Spotify
        rejects that (404, box not known as playable yet), activate and try again."""
        body = {'uris': [uri]} if uri.split(':')[1] in ('track', 'episode') else {'context_uri': uri}
        device_id = self.device()
        params = {'device_id': device_id}
        try:
            self.api('PUT', '/me/player/play', body, params)
        except Problem as first:
            if '404' not in str(first) and 'nicht verfügbar' not in str(first):
                raise
            self.activate(device_id, attempts=16)
            self.api('PUT', '/me/player/play', body, params)

    def activate(self, device_id, attempts=8):
        self.api('PUT', '/me/player', {'device_ids': [device_id], 'play': False})
        for attempt in range(attempts):
            time.sleep(0.5)
            current = self.api('GET', '/me/player/devices').get('devices', [])
            if any(d.get('id') == device_id and d.get('is_active') for d in current):
                return
        raise Problem('Spotify aktiviert die Phoniebox noch. Bitte Play gleich erneut drücken.')

    def state(self):
        with self.lock:
            if time.time() - self.cached_at < 15 and time.time() >= self.fresh_until:
                return self.cached
            state = self.api('GET', '/me/player')
            self.cached, self.cached_at = state, time.time()
            return state

    SEARCH_KINDS = (('track', 'tracks'), ('album', 'albums'), ('playlist', 'playlists'))

    def search(self, query, kind=None, limit=8):
        """Looks up albums, tracks and playlists for the NFC-card form, so a link doesn't
        have to be copied in from open.spotify.com by hand. Returns a flat list ready for
        display, each with a ready-to-save 'uri'. 'kind' restricts this to just one of
        'track', 'album' or 'playlist' - picking a type up front (instead of always
        searching and showing all three mixed together) is what turns a long list to dig
        through into a handful of relevant results."""
        query = (query or '').strip()
        kinds = [(k, key) for k, key in self.SEARCH_KINDS if k == kind] if kind else list(self.SEARCH_KINDS)
        if not query or not kinds:
            return []
        data = self.api('GET', '/search', params={'q': query, 'type': ','.join(k for k, _ in kinds), 'limit': limit})
        results = []
        for kind, key in kinds:
            for item in (data.get(key) or {}).get('items') or []:
                if not item or not item.get('uri'):
                    continue
                images = item.get('images') or (item.get('album') or {}).get('images') or []
                artists = item.get('artists')
                if artists:
                    artist = ', '.join(a.get('name', '') for a in artists)
                else:
                    artist = (item.get('owner') or {}).get('display_name', '') if kind == 'playlist' else ''
                results.append(
                    dict(
                        type=kind,
                        name=item.get('name', ''),
                        artist=artist,
                        uri=item['uri'],
                        url=(item.get('external_urls') or {}).get('spotify', ''),
                        # Smallest of the provided sizes is enough for a small thumbnail.
                        image=images[-1]['url'] if images else '',
                    )
                )
        return results
