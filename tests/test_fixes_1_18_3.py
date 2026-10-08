import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import Mock
import pytest
from app import create_app
import librespot_event

HELPER = Path(librespot_event.__file__)
TRACK = {
    'PLAYER_EVENT': 'track_changed',
    'TRACK_ID': 'abc',
    'URI': 'spotify:track:' + 'b' * 22,
    'NAME': 'Lied der Karte',
    'ARTISTS': 'Erste\nZweite',
    'ALBUM': 'Album der Karte',
    'COVERS': 'https://i.scdn.co/image/gross\nhttps://i.scdn.co/image/klein',
    'DURATION_MS': '200000',
    'ITEM_TYPE': 'Track',
}


def run_helper(path, **env):
    subprocess.run([sys.executable, '-I', str(HELPER)], env={**os.environ, 'PHONIEBOX_PLAYER_STATE': str(path), **env}, check=True)


def test_helper_keeps_track_and_play_state(tmp_path):
    path = tmp_path / 'state.json'
    run_helper(path, **TRACK)
    run_helper(path, PLAYER_EVENT='playing', TRACK_ID='abc', POSITION_MS='5000')
    state = json.loads(path.read_text())
    assert state['name'] == 'Lied der Karte' and state['playing'] and state['position_ms'] == 5000
    run_helper(path, PLAYER_EVENT='volume_changed', VOLUME='100')
    assert json.loads(path.read_text())['name'] == 'Lied der Karte'
    run_helper(path, PLAYER_EVENT='stopped', TRACK_ID='abc')
    assert json.loads(path.read_text())['stopped']


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


def test_start_page_shows_what_librespot_plays_not_stale_web_api(app):
    hw, sp = app.extensions['hardware'], app.extensions['spotify']
    hw.process = Mock(poll=Mock(return_value=None))
    run_helper(hw.player_state_file, **TRACK)
    run_helper(hw.player_state_file, PLAYER_EVENT='playing', TRACK_ID='abc', POSITION_MS='0')
    sp.state = Mock(return_value={
        'device': {'name': app.extensions['store'].get('name'), 'volume_percent': 40},
        'is_playing': True,
        'item': {'name': 'Altes Lied', 'artists': [{'name': 'Nick Drake'}]},
    })
    r = app.test_client().get('/api/player', base_url='http://127.0.0.1:8888').json
    assert r['title'] == 'Lied der Karte' and r['artist'] == 'Erste, Zweite'
    assert r['cover'] == 'https://i.scdn.co/image/gross' and r['playing'] and r['volume'] == 40


def test_without_librespot_report_web_api_is_used(app):
    hw, sp = app.extensions['hardware'], app.extensions['spotify']
    hw.process = None
    sp.state = Mock(return_value={
        'device': {'name': app.extensions['store'].get('name')},
        'item': {'name': 'Aus der Web-API', 'artists': []},
    })
    r = app.test_client().get('/api/player', base_url='http://127.0.0.1:8888').json
    assert r['title'] == 'Aus der Web-API'
