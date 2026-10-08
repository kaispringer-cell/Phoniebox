import subprocess
import sys
from unittest.mock import Mock
import bluetooth as bt

MAC='54:B7:E5:43:2D:C7'


def test_known_unbonded_speaker_remains_visible():
    def run(args,**kwargs):
        output=('Device '+MAC+' KILBURN II\n') if args[1]=='devices' else 'Name: KILBURN II\nPaired: no\nBonded: no\nTrusted: yes\nConnected: no\n'
        return Mock(returncode=0,stdout=output,stderr='')
    devices=bt.paired_devices(run)
    assert len(devices)==1 and devices[0]['name']=='KILBURN II'
    assert devices[0]['bonded'] is False


def test_paired_without_bond_is_not_success(monkeypatch):
    monkeypatch.setattr(bt,'power_on',lambda **kw:True)
    monkeypatch.setattr(bt,'info',lambda *a,**kw:{'paired':True,'bonded':False})
    agent=Mock(return_value=True);monkeypatch.setattr(bt,'_pair_session',agent)
    assert bt.pair(MAC)[0] is False
    agent.assert_called_once()


def test_completed_bond_succeeds(monkeypatch):
    monkeypatch.setattr(bt,'power_on',lambda **kw:True)
    monkeypatch.setattr(bt,'info',Mock(side_effect=[{'bonded':False},{'bonded':True}]))
    monkeypatch.setattr(bt,'_pair_session',Mock(return_value=True))
    monkeypatch.setattr(bt,'_run',Mock(return_value=(0,'')))
    monkeypatch.setattr(bt,'connect',lambda *a,**kw:True)
    assert bt.pair(MAC)==(True,'Dauerhaft gekoppelt und verbunden.')


def test_agent_registration_precedes_pair_and_process_is_cleaned_up():
    processes=[]
    def popen(args,**kwargs):
        assert args==['bluetoothctl','--agent','NoInputNoOutput']
        script="import sys,time; print('Agent registered',flush=True); line=sys.stdin.readline(); print('Pairing successful' if line.strip()=='pair '+sys.argv[1] else 'Failed to pair',flush=True); time.sleep(5)"
        p=subprocess.Popen([sys.executable,'-u','-c',script,MAC],**kwargs)
        processes.append(p);return p
    assert bt._pair_session(MAC,timeout=2,popen=popen)
    assert processes[0].poll() is not None


def test_agent_timeout_terminates_process():
    processes=[]
    def popen(args,**kwargs):
        p=subprocess.Popen([sys.executable,'-u','-c','import time;time.sleep(5)'],**kwargs)
        processes.append(p);return p
    assert not bt._pair_session(MAC,timeout=.1,popen=popen)
    assert processes[0].poll() is not None
