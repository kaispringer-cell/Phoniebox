import threading
from unittest.mock import Mock
import pytest
import bluetooth as bt
from storage import Store

MAC='AA:BB:CC:DD:EE:FF'

@pytest.fixture
def setup(tmp_path,monkeypatch):
    store=Store(tmp_path)
    store.put(audio='bluealsa:DEV='+MAC+',PROFILE=a2dp')
    restart,stop=threading.Event(),threading.Event()
    worker=bt.Reconnector(store,restart,stop)
    device={'paired':True,'bonded':True,'trusted':True,'connected':False}
    mocks={
        'adapter_status':Mock(return_value={'state':'ready'}),
        'info':Mock(side_effect=lambda mac:dict(device)),
        'connect':Mock(return_value=True),
        'power_on':Mock(return_value=True),
        '_run':Mock(return_value=(0,'')),
    }
    for name,mock in mocks.items():monkeypatch.setattr(bt,name,mock)
    return store,worker,device,mocks


def test_reconnect_after_boot_and_late_speaker(setup):
    store,w,device,m=setup
    m['adapter_status'].side_effect=[{'state':'starting'},{'state':'ready'},{'state':'ready'}]
    m['connect'].side_effect=[False,True]
    w.tick();m['connect'].assert_not_called()
    w.tick();assert not w.restart.is_set()
    w.tick();assert w.restart.is_set()
    assert m['connect'].call_count==2
    assert not any(c.args[0][0] in ('pair','remove','scan') for c in m['_run'].call_args_list)


def test_connected_speaker_is_not_restarted(setup):
    _,w,device,m=setup;device['connected']=True
    w.tick();m['connect'].assert_not_called();assert not w.restart.is_set()


def test_manual_disconnect_is_respected_and_connect_resumes(setup):
    _,w,_,m=setup
    w.suspend(MAC.lower());w.tick();m['connect'].assert_not_called()
    w.resume(MAC);w.tick();m['connect'].assert_called_once_with(MAC)


def test_missing_pairing_never_repaired_by_pairing_again(setup):
    _,w,device,m=setup;device['paired']=False;device['bonded']=False
    w.tick();m['connect'].assert_not_called();assert 'nicht dauerhaft gekoppelt' in w.message


def test_local_output_never_connects_old_speaker(setup):
    store,w,_,m=setup;store.put(audio='plughw:0,0')
    w.tick();m['adapter_status'].assert_not_called();m['connect'].assert_not_called()


def test_power_and_trust_saved_paired_output(setup):
    _,w,device,m=setup;device['trusted']=False
    m['adapter_status'].return_value={'state':'off'}
    w.tick();m['power_on'].assert_called_once()
    m['_run'].assert_called_once_with(['trust',MAC],timeout=10)
    m['connect'].assert_called_once_with(MAC)


def test_no_auto_connect_after_shutdown(setup):
    _,w,_,m=setup;w.stop.set();w.tick();m['connect'].assert_not_called()


def test_pair_button_preserves_existing_pairing(monkeypatch):
    run=Mock(return_value=(0,''))
    monkeypatch.setattr(bt,'_run',run)
    monkeypatch.setattr(bt,'power_on',Mock(return_value=True))
    monkeypatch.setattr(bt,'info',lambda *a,**kw:{'paired':True,'bonded':True,'connected':True})
    monkeypatch.setattr(bt,'connect',Mock(return_value=True))
    assert bt.pair(MAC)[0]
    assert all(c.args[0][0]!='pair' for c in run.call_args_list)


def test_ui_disconnect_suspends_and_connect_resumes(tmp_path,monkeypatch):
    from app import create_app
    app=create_app(tmp_path);client=app.test_client();base='http://127.0.0.1:8888'
    client.get('/api/hardware',base_url=base)
    with client.session_transaction(base_url=base) as session: token=session['csrf']
    monkeypatch.setattr(bt,'disconnect',lambda mac:True)
    monkeypatch.setattr(bt,'connect',lambda mac:True)
    monkeypatch.setattr(bt,'power_on',lambda:True)
    for action,paused in [('disconnect',True),('connect',False)]:
        r=client.post('/api/bluetooth/'+action,data={'csrf':token,'mac':MAC},base_url=base)
        assert r.status_code==200
        assert (MAC in app.extensions['hardware'].bluetooth.suspended)==paused


def test_status_stays_responsive_during_reconnect(tmp_path):
    from app import create_app
    app=create_app(tmp_path);worker=app.extensions['hardware'].bluetooth
    entered,release=threading.Event(),threading.Event()
    def hold():
        with worker.lock:
            entered.set();release.wait(3)
    thread=threading.Thread(target=hold);thread.start();assert entered.wait(1)
    try:
        response=app.test_client().get('/api/bluetooth',base_url='http://127.0.0.1:8888')
        assert response.status_code==200 and response.json['adapter']['state']=='busy'
    finally:
        release.set();thread.join(4)
