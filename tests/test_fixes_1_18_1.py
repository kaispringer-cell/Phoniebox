from datetime import datetime
from unittest.mock import Mock
from zoneinfo import ZoneInfo
import pytest
import bluetooth as bt
from app import create_app
from alarm_radio import DEFAULT_ALARM, due, alarm_key
from spotify import Problem

MAC = 'AA:BB:CC:DD:EE:FF'
BERLIN = ZoneInfo('Europe/Berlin')


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


def test_play_reports_disconnected_bluetooth_before_spotify(app, monkeypatch):
    store, hw, sp = app.extensions['store'], app.extensions['hardware'], app.extensions['spotify']
    store.put(audio='bluealsa:DEV=' + MAC + ',PROFILE=a2dp')
    monkeypatch.setattr(bt, 'info', Mock(return_value={'connected': False}))
    sp.command = Mock()
    with pytest.raises(Problem, match='noch nicht verbunden'):
        hw.command('play', uri='spotify:album:' + 'a' * 22)
    sp.command.assert_not_called()
    hw.bluetooth.suspend(MAC)
    with pytest.raises(Problem, match='bewusst getrennt'):
        hw.command('play')


def test_play_with_connected_bluetooth_reaches_spotify(app, monkeypatch):
    store, hw, sp = app.extensions['store'], app.extensions['hardware'], app.extensions['spotify']
    store.put(audio='bluealsa:DEV=' + MAC + ',PROFILE=a2dp')
    monkeypatch.setattr(bt, 'info', Mock(return_value={'connected': True}))
    sp.command = Mock()
    hw.command('play')
    sp.command.assert_called_once_with('play', uri=None, volume=None)


def test_unreachable_output_replaces_spotify_device_message(app, monkeypatch):
    hw, sp = app.extensions['hardware'], app.extensions['spotify']
    hw.player_status = 'Audioausgang „x“ nicht erreichbar.'
    sp.command = Mock(side_effect=Problem('Phoniebox nicht eindeutig erreichbar.'))
    with pytest.raises(Problem, match='Audioausgang'):
        hw.command('pause')


def test_local_radio_pause_skips_bluetooth_check(app, monkeypatch):
    store, hw, media = app.extensions['store'], app.extensions['hardware'], app.extensions['media']
    store.put(audio='bluealsa:DEV=' + MAC + ',PROFILE=a2dp')
    info = Mock(return_value={'connected': False})
    monkeypatch.setattr(bt, 'info', info)
    media.source = 'radio'
    media.ipc = Mock(return_value={})
    hw.command('play')
    info.assert_not_called()
    media.ipc.assert_called_once_with(['set_property', 'pause', False])


def test_alarm_volume_does_not_become_start_volume(app, monkeypatch):
    store, sp = app.extensions['store'], app.extensions['spotify']
    store.put(volume=35)
    monkeypatch.setattr(sp, 'device', Mock(return_value='id'))
    monkeypatch.setattr(sp, 'api', Mock(return_value={}))
    sp.command('volume', volume=80, persist=False)
    assert store.get('volume') == 35
    sp.command('volume', volume=60)
    assert store.get('volume') == 60


def test_alarm_changed_later_same_day_rings_again():
    config = {**DEFAULT_ALARM, 'enabled': True, 'days': list(range(7)), 'time': '07:00'}
    morning = datetime(2026, 10, 8, 7, 0, tzinfo=BERLIN)
    assert due(config, morning, '')
    last = alarm_key(config, morning)
    assert not due(config, morning, last)
    later = {**config, 'time': '09:30'}
    assert due(later, datetime(2026, 10, 8, 9, 30, tzinfo=BERLIN), last)


def test_repeated_autumn_hour_rings_once():
    config = {**DEFAULT_ALARM, 'enabled': True, 'days': list(range(7)), 'time': '02:30'}
    first = datetime(2026, 10, 25, 2, 30, fold=0, tzinfo=BERLIN)
    second = datetime(2026, 10, 25, 2, 30, fold=1, tzinfo=BERLIN)
    assert due(config, first, '')
    assert not due(config, second, alarm_key(config, first))


def test_legacy_date_only_marker_still_blocks_that_day():
    config = {**DEFAULT_ALARM, 'enabled': True, 'days': list(range(7)), 'time': '07:00'}
    now = datetime(2026, 10, 8, 7, 0, tzinfo=BERLIN)
    assert not due(config, now, '2026-10-08')
    assert due(config, now, '2026-10-07')
