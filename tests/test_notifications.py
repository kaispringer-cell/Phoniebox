import threading
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock
import bluetooth as bt
from app import create_app
from notifications import GRACE, Notices
from storage import Store

MAC = 'AA:BB:CC:DD:EE:FF'


class Clock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def box(tmp_path):
    store = Store(tmp_path)
    store.set_secret('tokens', {'access_token': 'x'})
    hw = Mock(player_status='librespot läuft · Spotify-Verbindung separat prüfen', reader_status='Verbunden · M301 V4')
    hw.bluetooth = Mock(connected=True, message='Gespeicherter Lautsprecher verbunden.')
    clock = Clock()
    return store, hw, clock, Notices(store, hw, clock)


def test_nothing_to_report_when_all_is_well(tmp_path):
    _, _, clock, notices = box(tmp_path)
    clock.now += 3600
    assert notices.current() == []


def test_bluetooth_reported_after_grace_and_cleared_when_back(tmp_path):
    _, hw, clock, notices = box(tmp_path)
    hw.bluetooth.connected = False
    hw.bluetooth.message = 'Lautsprecher noch nicht erreichbar.'
    hw.player_status = 'Audioausgang „bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp“ nicht erreichbar. Bluetooth verbunden? Einstellungen prüfen.'
    assert notices.current() == []
    clock.now += GRACE
    [notice] = notices.current()
    # The unreachable output is the same problem, so it is not reported twice.
    assert notice == dict(id='bluetooth', title='Bluetooth nicht verbunden', text='Lautsprecher noch nicht erreichbar.', since=1000)
    hw.bluetooth.connected = True
    hw.player_status = 'librespot läuft · Spotify-Verbindung separat prüfen'
    assert notices.current() == []
    # A new drop starts a new grace period.
    hw.bluetooth.connected = False
    clock.now += 5
    assert notices.current() == []


def test_unknown_bluetooth_state_is_not_a_problem(tmp_path):
    _, hw, clock, notices = box(tmp_path)
    hw.bluetooth.connected = None
    clock.now += GRACE
    notices.current()
    clock.now += GRACE
    assert notices.current() == []


def test_reader_player_and_spotify_problems(tmp_path):
    store, hw, clock, notices = box(tmp_path)
    hw.reader_status = 'Reader nicht gefunden'
    hw.player_status = 'Audio/Player-Start fehlgeschlagen. ALSA-Werte und librespot prüfen.'
    store.set_secret('tokens', None)
    notices.current()
    clock.now += GRACE
    assert [n['id'] for n in notices.current()] == ['player', 'reader', 'spotify']


def test_reconnector_tracks_connection(tmp_path, monkeypatch):
    store = Store(tmp_path)
    store.put(audio='bluealsa:DEV=' + MAC + ',PROFILE=a2dp')
    worker = bt.Reconnector(store, threading.Event(), threading.Event())
    device = {'paired': True, 'bonded': True, 'trusted': True, 'connected': False}
    monkeypatch.setattr(bt, 'adapter_status', Mock(return_value={'state': 'ready'}))
    monkeypatch.setattr(bt, 'info', Mock(side_effect=lambda mac: dict(device)))
    monkeypatch.setattr(bt, 'connect', Mock(return_value=False))
    monkeypatch.setattr(bt, '_run', Mock(return_value=(0, '')))
    worker.tick()
    assert worker.connected is False
    device['connected'] = True
    worker.tick()
    assert worker.connected is True
    worker.suspend(MAC)
    assert worker.connected is None
    store.put(audio='plughw:0,0')
    worker.resume(MAC)
    worker.tick()
    assert worker.connected is None


def test_notifications_api(monkeypatch):
    with TemporaryDirectory() as d:
        app = create_app(Path(d))
        r = app.test_client().get('/api/notifications', base_url='https://phoniebox.local')
        assert r.status_code == 200
        assert r.json['version'] == (Path(__file__).parent.parent / 'VERSION').read_text().strip()
        assert r.json['notifications'] == []


def test_app_menu_button_is_hidden_outside_the_app():
    with TemporaryDirectory() as d:
        html = create_app(Path(d)).test_client().get('/', base_url='https://phoniebox.local').text
        assert html.count('id="app-menu"') == 1
        assert '<button id="app-menu" class="quiet" type="button" hidden' in html
        assert html.count('<dialog id="app-dialog"') == 1 and 'id="app-notify"' in html
    script = (Path(__file__).parent.parent / 'static' / 'interface.js').read_text()
    assert 'window.PhonieboxApp' in script and 'app.openMenu()' in script


def test_csrf_token_for_the_android_player():
    with TemporaryDirectory() as d:
        client = create_app(Path(d)).test_client()
        token = client.get('/api/csrf', base_url='https://phoniebox.local').json['csrf']
        assert token
        assert client.post('/api/learn/cancel', base_url='https://phoniebox.local').status_code == 403
        r = client.post('/api/learn/cancel', base_url='https://phoniebox.local', headers={'X-CSRF-Token': token})
        assert r.status_code == 200


def test_player_switch_only_for_apps_that_have_it():
    with TemporaryDirectory() as d:
        html = create_app(Path(d)).test_client().get('/', base_url='https://phoniebox.local').text
        assert '<div id="app-player-row" hidden>' in html and 'id="app-player"' in html
        assert '<div id="app-blocked" class="notice error" hidden>' in html
    script = (Path(__file__).parent.parent / 'static' / 'interface.js').read_text()
    assert "typeof app.playerEnabled === 'function'" in script and 'app.setPlayer(player.checked)' in script
    assert "typeof app.notificationsAllowed === 'function'" in script and 'app.openNotificationSettings()' in script


def test_release_manifest_matches_version():
    # The release workflow refuses to build when these two differ.
    import json
    root = Path(__file__).parent.parent
    assert json.loads((root / 'release.json').read_text())['version'] == (root / 'VERSION').read_text().strip()
