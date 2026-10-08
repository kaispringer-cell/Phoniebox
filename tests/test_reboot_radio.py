from pathlib import Path
from unittest.mock import Mock
import pytest
import app as module
from app import create_app
from alarm_radio import STATIONS

BASE = 'http://127.0.0.1:8888'

@pytest.fixture
def setup(tmp_path, monkeypatch):
    app = create_app(tmp_path)
    client = app.test_client()
    client.get('/api/hardware', base_url=BASE)
    with client.session_transaction(base_url=BASE) as session:
        token = session['csrf']
    run = Mock(return_value=Mock(returncode=0))
    monkeypatch.setattr(module.subprocess, 'run', run)
    return app, client, token, run


def test_reboot_csrf_and_queue(setup, tmp_path):
    app, client, token, run = setup
    assert client.get('/api/system/reboot', base_url=BASE).status_code == 405
    assert client.post('/api/system/reboot', base_url=BASE).status_code == 403
    run.assert_not_called()
    r = client.post('/api/system/reboot', headers={'X-CSRF-Token':token}, base_url=BASE)
    assert r.status_code == 202
    assert (tmp_path/'reboot.request').is_file()
    assert (tmp_path/'reboot.request').stat().st_mode & 0o777 == 0o600
    assert run.call_args.args[0] == ['/usr/bin/systemctl','is-active','--quiet','phoniebox-reboot.path']
    assert client.post('/api/system/reboot', headers={'X-CSRF-Token':token}, base_url=BASE).status_code == 200
    assert run.call_count == 1


def test_missing_reboot_service_is_recoverable(setup, tmp_path):
    app, client, token, run = setup
    run.return_value.returncode = 3
    r = client.post('/api/system/reboot', data={'csrf':token}, base_url=BASE)
    assert r.status_code == 503
    assert not (tmp_path/'reboot.request').exists()
    run.return_value.returncode = 0
    assert client.post('/api/system/reboot', data={'csrf':token}, base_url=BASE).status_code == 202


@pytest.mark.parametrize('station', STATIONS, ids=lambda s:s['id'])
def test_radio_logo_follows_station_including_paused_playback(setup, station):
    app, client, _, _ = setup
    media = app.extensions['media']
    media.source, media.choice, media.title = 'radio', station['id'], station['name']
    for paused in (False, True):
        media.paused = paused
        r = client.get('/api/player', base_url=BASE)
        assert r.json['source'] == 'radio'
        assert r.json['playing'] == (not paused)
        logo = client.get(r.json['cover'], base_url=BASE)
        assert logo.status_code == 200 and logo.mimetype == 'image/svg+xml'
    media.source = 'tone'
    assert client.get('/api/player',base_url=BASE).json['cover'] == ''
