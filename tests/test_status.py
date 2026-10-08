from unittest.mock import Mock
from tempfile import TemporaryDirectory
from pathlib import Path
from app import create_app
import bluetooth as bt


def test_adapter_startup_is_not_empty_pairing_list():
    run=Mock(return_value=Mock(returncode=1,stdout='No default controller available',stderr=''))
    assert bt.adapter_status(run,uptime=10)['state']=='starting'
    assert bt.adapter_status(run,uptime=200)['state']=='error'


def test_powered_off_is_not_startup():
    run=Mock(return_value=Mock(returncode=0,stdout='Powered: no',stderr=''))
    assert bt.adapter_status(run,uptime=10)['state']=='off'


def test_status_api_and_unique_elements(monkeypatch):
    monkeypatch.setattr(bt,'adapter_status',lambda:{'state':'starting','message':'Bluetooth wird gestartet …'})
    paired=Mock();monkeypatch.setattr(bt,'paired_devices',paired)
    with TemporaryDirectory() as d:
        client=create_app(Path(d)).test_client()
        r=client.get('/api/bluetooth',base_url='http://127.0.0.1:8888')
        assert r.status_code==200 and r.json['adapter']['state']=='starting'
        paired.assert_not_called()
        html=client.get('/',base_url='http://127.0.0.1:8888').text
        for name in ['reader-status','librespot-status','hardware-message','bluetooth-status','refresh-status']:
            assert html.count('id="'+name+'"')==1
            assert html.index('id="settings"')<html.index('id="'+name+'"')
