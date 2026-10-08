import errno, sys
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from hardware import Hardware

@pytest.mark.parametrize('code,text', [(errno.EACCES,'Zugriff verweigert'),(errno.ENOENT,'Gerätepfad fehlt'),(errno.EIO,'USB-Lesefehler')])
def test_open_error_is_preserved(monkeypatch,code,text):
    device = Mock(side_effect=OSError(code,'failed'))
    monkeypatch.setitem(sys.modules,'evdev',SimpleNamespace(InputDevice=device,ecodes=Mock()))
    h = Hardware(Mock(),Mock())
    monkeypatch.setattr(h.stop,'wait',lambda _:h.stop.set())
    h.reader_loop()
    assert text in h.reader_status
    assert 'Gerät öffnen' in h.reader_status
    assert f'Fehler {code}' in h.reader_status

def test_grab_error_closes_handle_and_reports_busy(monkeypatch):
    device = Mock();device.grab.side_effect=OSError(errno.EBUSY,'busy')
    monkeypatch.setitem(sys.modules,'evdev',SimpleNamespace(InputDevice=lambda _:device,ecodes=Mock()))
    h = Hardware(Mock(),Mock())
    monkeypatch.setattr(h.stop,'wait',lambda _:h.stop.set())
    h.reader_loop()
    assert 'exklusiv belegt' in h.reader_status
    assert 'Reader exklusiv übernehmen' in h.reader_status
    device.close.assert_called_once()
