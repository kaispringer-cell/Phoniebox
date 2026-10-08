from unittest.mock import Mock
import pytest
import spotify
from spotify import Problem, Spotify

ALBUM = 'spotify:album:' + 'a' * 22
OLD = 'spotify:album:' + 'n' * 22


class Store:
    def get(self, key):
        return {'name': 'Phoniebox'}[key]

    def put(self, **_):
        pass


def make(responses):
    """Spotify client whose api() answers from a list of (method, path) handlers."""
    sp = Spotify(Store())
    calls = []

    def api(method, path, body=None, params=None):
        calls.append((method, path, body))
        return responses(method, path, body, calls)

    sp.api = api
    return sp, calls


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(spotify.time, 'sleep', lambda _: None)


def devices(active):
    return {'devices': [{'id': 'box', 'name': 'Phoniebox', 'is_active': active}]}


def test_card_plays_inactive_box_without_transfer():
    def responses(method, path, body, calls):
        if path == '/me/player/devices':
            return devices(False)
        if method == 'GET' and path == '/me/player':
            return {'device': {'id': 'box'}, 'context': {'uri': ALBUM}}
        return {}

    sp, calls = make(responses)
    sp.command('play', uri=ALBUM)
    assert ('PUT', '/me/player', {'device_ids': ['box'], 'play': False}) not in calls
    assert [c for c in calls if c[1] == '/me/player/play'] == [('PUT', '/me/player/play', {'context_uri': ALBUM})]


def test_rejected_play_activates_and_retries_instead_of_failing():
    state = {'active': False, 'plays': 0}

    def responses(method, path, body, calls):
        if path == '/me/player/devices':
            return devices(state['active'])
        if path == '/me/player' and method == 'PUT':
            state['active'] = True
            return {}
        if path == '/me/player/play':
            state['plays'] += 1
            if state['plays'] == 1:
                raise Problem('Spotify-Gerät oder Inhalt nicht verfügbar.')
            return {}
        return {'device': {'id': 'box'}, 'context': {'uri': ALBUM}}

    sp, calls = make(responses)
    sp.command('play', uri=ALBUM)
    assert state['plays'] == 2


def test_state_is_not_cached_right_after_a_command():
    sp, _ = make(lambda *a: devices(True) if a[1] == '/me/player/devices' else {})
    sp.command('pause')
    sp.api = Mock(return_value={'item': {'name': 'neu'}})
    sp.state()
    sp.state()
    assert sp.api.call_count == 2
