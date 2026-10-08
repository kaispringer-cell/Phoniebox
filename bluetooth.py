"""BlueZ control with a live pairing agent and explicit durable-bond checks."""

import re
import subprocess
import threading
import selectors
import os
import time

MAC = re.compile(r'[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}')
_DEV_MAC = re.compile(r'(?i)DEV=([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})')


class BluetoothError(Exception):
    """Raised when a bluetoothctl command that lists state (rather than acting on one
    device) itself fails - as opposed to genuinely finding nothing. Silently returning
    an empty list in that case previously made a broken bluetoothctl (e.g. no
    permission to reach the Bluetooth D-Bus service, or the adapter being unavailable)
    look exactly like 'nothing is paired', which hid the real problem."""


def valid_mac(mac):
    return bool(MAC.fullmatch(mac or ''))


def mac_in(alsa_device):
    """Extracts the MAC address from a bluealsa ALSA device string
    ('bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp'), or None if the given device string
    isn't a Bluetooth one (a local ALSA device such as 'plughw:0,0' or 'default')."""
    match = _DEV_MAC.search(alsa_device or '')
    return match[1].upper() if match else None


def _run(args, run=subprocess.run, timeout=15):
    try:
        result = run(['bluetoothctl', *args], capture_output=True, text=True, timeout=timeout)
    except (OSError, subprocess.SubprocessError):
        return 1, ''
    return result.returncode, (result.stdout or '') + (result.stderr or '')


def power_on(run=subprocess.run):
    code, _ = _run(['power', 'on'], run=run, timeout=10)
    return code == 0


def _device_lines(output):
    found = []
    for line in output.splitlines():
        parts = line.strip().split(' ', 2)
        if len(parts) == 3 and parts[0] == 'Device' and valid_mac(parts[1]):
            found.append((parts[1], parts[2].strip()))
    return found


def info(mac, run=subprocess.run):
    if not valid_mac(mac):
        return None
    code, output = _run(['info', mac], run=run, timeout=10)
    if code != 0:
        return None
    device = {'mac': mac, 'name': mac, 'paired': False, 'bonded': False, 'trusted': False, 'connected': False}
    for line in output.splitlines():
        line = line.strip()
        if line.startswith('Name:'):
            device['name'] = line.split(':', 1)[1].strip()
        elif line.startswith('Paired:'):
            device['paired'] = line.split(':', 1)[1].strip().lower() == 'yes'
        elif line.startswith('Bonded:'):
            device['bonded'] = line.split(':', 1)[1].strip().lower() == 'yes'
        elif line.startswith('Trusted:'):
            device['trusted'] = line.split(':', 1)[1].strip().lower() == 'yes'
        elif line.startswith('Connected:'):
            device['connected'] = line.split(':', 1)[1].strip().lower() == 'yes'
    return device


def _paired_devices_output(run):
    """BlueZ's bluetoothctl changed how to list only paired devices between versions:
    older releases have a dedicated 'paired-devices' command, while BlueZ 5.65+ removed
    that command entirely in favour of an optional filter argument to 'devices'
    ('devices Paired') - using the removed command doesn't fail quietly, it errors with
    'Invalid command in menu main: paired-devices', which is exactly the kind of real
    failure BluetoothError exists to surface rather than swallow as 'nothing paired'.
    Try the modern syntax first and fall back to the old one so this works across BlueZ
    versions; a failure that is not just 'this syntax doesn't exist here' is raised
    immediately instead of being masked by trying the fallback too."""
    last_output = ''
    for args in (['devices', 'Paired'], ['paired-devices']):
        code, output = _run(args, run=run, timeout=10)
        if code == 0:
            return output
        last_output = output
        if 'invalid command' not in output.lower():
            break
    raise BluetoothError(
        'bluetoothctl Auflisten gekoppelter Geräte fehlgeschlagen: ' + (last_output.strip() or 'keine Ausgabe')
    )


def paired_devices(run=subprocess.run):
    """List known peers, retaining unbonded entries so users can repair them."""
    code, output = _run(['devices'], run=run, timeout=10)
    if code:
        raise BluetoothError('Bekannte Bluetooth-Geräte konnten nicht abgefragt werden.')
    result = []
    for mac, name in _device_lines(output):
        device = info(mac, run=run)
        if device is None:
            raise BluetoothError('Bluetooth-Gerätestatus konnte nicht abgefragt werden. Bitte erneut versuchen.')
        result.append(device)
    return result


def scan(duration=10, run=subprocess.run):
    """Bounded scan for nearby, not-yet-paired devices. Returns only devices discovered
    during this scan and not already paired, since paired devices are shown separately."""
    power_on(run=run)
    try:
        run(['bluetoothctl', '--timeout', str(duration), 'scan', 'on'], capture_output=True, text=True, timeout=duration + 10)
    except (OSError, subprocess.SubprocessError):
        pass
    code, output = _run(['devices'], run=run, timeout=10)
    if code != 0:
        raise BluetoothError('bluetoothctl devices fehlgeschlagen (Code ' + str(code) + '): ' + (output.strip() or 'keine Ausgabe'))
    already_paired = {d['mac'] for d in paired_devices(run=run)}
    return [{'mac': mac, 'name': name} for mac, name in _device_lines(output) if mac not in already_paired]


def _pair_session(mac, timeout=45, popen=subprocess.Popen):
    """Keep the interactive BlueZ agent alive until Pair finishes; no shell.

    BlueZ 5.82 does not auto-register an agent in non-interactive mode.
    Wait for agent registration before sending Pair and never log agent output.
    """
    if not valid_mac(mac):
        return False
    process = None
    try:
        process = popen(['bluetoothctl', '--agent', 'NoInputNoOutput'],
                        stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT, bufsize=0)
        deadline = time.monotonic() + timeout
        sent = False
        pending = ''
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while time.monotonic() < deadline:
                events = selector.select(min(0.5, max(0, deadline-time.monotonic())))
                if not events:
                    if process.poll() is not None:
                        return False
                    continue
                chunk = os.read(process.stdout.fileno(), 4096)
                if not chunk:
                    return False
                pending = (pending + chunk.decode('utf-8', errors='replace'))[-16384:]
                if not sent and 'Agent registered' in pending:
                    process.stdin.write(('pair ' + mac + '\n').encode())
                    process.stdin.flush()
                    sent = True
                    pending = ''
                elif sent:
                    if 'Pairing successful' in pending:
                        return True
                    if 'Failed to pair' in pending or 'not available' in pending:
                        return False
        return False
    except (OSError, subprocess.SubprocessError):
        return False
    finally:
        if process is not None:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=2)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    pipe.close()


def pair(mac, run=subprocess.run, timeout=45):
    if not valid_mac(mac):
        return False, 'Ungültige Geräteadresse.'
    power_on(run=run)
    device = info(mac, run=run)
    if not device or not device.get('bonded'):
        _pair_session(mac, timeout=timeout)
        device = info(mac, run=run)
    if not device or not device.get('bonded'):
        return False, (
            'Keine dauerhafte Kopplung bestätigt (Bonded: nein). Lautsprecher in den '
            'Kopplungsmodus versetzen und „Dauerhaft koppeln“ erneut wählen. '
            'Falls das wieder scheitert, den Eintrag gezielt entfernen und neu koppeln.'
        )
    _run(['trust', mac], run=run, timeout=10)
    message = 'Dauerhaft gekoppelt und verbunden.' if connect(mac, run=run, timeout=timeout) else 'Dauerhaft gekoppelt. Lautsprecher momentan nicht verbunden.'
    return True, message


def connect(mac, run=subprocess.run, timeout=20):
    """As with pair(), the actual state afterwards decides, not bluetoothctl's own exit
    code/text for 'connect' - an already-connected device is exactly the same kind of
    edge case that made pair()'s text-matching unreliable."""
    if not valid_mac(mac):
        return False
    _run(['connect', mac], run=run, timeout=timeout)
    device = info(mac, run=run)
    return bool(device and device['connected'])


def disconnect(mac, run=subprocess.run, timeout=15):
    if not valid_mac(mac):
        return False
    code, _ = _run(['disconnect', mac], run=run, timeout=timeout)
    return code == 0


def forget(mac, run=subprocess.run, timeout=15):
    if not valid_mac(mac):
        return False
    code, _ = _run(['remove', mac], run=run, timeout=timeout)
    return code == 0


def adapter_status(run=subprocess.run, uptime=None):
    """Report readiness separately from an empty list of paired devices."""
    code, output = _run(['show'], run=run, timeout=5)
    if code == 0 and 'Powered: yes' in output:
        return {'state': 'ready', 'message': 'Bluetooth bereit.'}
    if 'Powered: no' in output:
        return {'state': 'off', 'message': 'Bluetooth-Adapter ausgeschaltet. Unter Bluetooth nach Geräten suchen oder im Installer Geräte einrichten.'}
    if uptime is None:
        try:
            from pathlib import Path
            uptime = float(Path('/proc/uptime').read_text().split()[0])
        except (OSError, ValueError, IndexError):
            uptime = 120
    if 'No default controller' in output and uptime < 120:
        return {'state': 'starting', 'message': 'Bluetooth wird gestartet … Noch kein Adapter bereit.'}
    return {'state': 'error', 'message': 'Bluetooth-Adapter nicht erreichbar: ' + (output.strip() or 'bluetoothctl antwortet nicht.')}


class Reconnector:
    """Reconnect the saved output in a hardware worker, never in the startup path.

    Shares a lock with explicit UI operations. Manual disconnect lasts until an
    explicit connect/use action or service restart. Never scans, pairs or removes.
    """
    def __init__(self, store, restart, stop):
        self.store, self.restart, self.stop = store, restart, stop
        self.lock = threading.RLock()
        self.suspended = set()
        self.message = ''
        # Last known state of the saved speaker for /api/notifications: True connected,
        # False not connected, None unknown, not a Bluetooth output or deliberately disconnected.
        self.connected = None

    def resume(self, mac):
        self.suspended.discard(mac.upper())
        self.message = ''

    def suspend(self, mac):
        self.suspended.add(mac.upper())
        self.connected = None
        self.message = 'Automatische Verbindung nach bewusstem Trennen pausiert. Zum Fortsetzen „Verbinden“ wählen.'

    def tick(self):
        if not self.lock.acquire(blocking=False):
            return
        try:
            mac = mac_in(self.store.get('audio'))
            if not mac:
                self.message = ''
                self.connected = None
                return
            if mac in self.suspended or self.stop.is_set():
                self.connected = None
                return
            adapter = adapter_status()
            if adapter['state'] == 'off':
                power_on()
            if adapter['state'] not in ('ready', 'off'):
                self.message = 'Bluetooth noch nicht bereit. Verbindung wird automatisch erneut versucht.'
                self.connected = None if adapter['state'] == 'starting' else False
                return
            device = info(mac)
            if not device or not device.get('bonded'):
                self.message = 'Gespeicherter Lautsprecher ist nicht dauerhaft gekoppelt. Unter Bluetooth „Dauerhaft koppeln“ wählen.'
                self.connected = False
                return
            if device['connected']:
                self.message = 'Gespeicherter Lautsprecher verbunden.'
                self.connected = True
                return
            if not device['trusted']:
                _run(['trust', mac], timeout=10)
            self.message = 'Gespeicherter Lautsprecher wird verbunden …'
            if connect(mac):
                self.message = 'Gespeicherter Lautsprecher wieder verbunden.'
                self.connected = True
                self.restart.set()
            else:
                self.message = 'Lautsprecher noch nicht erreichbar. Automatischer Verbindungsversuch folgt; erneutes Koppeln ist nicht nötig.'
                self.connected = False
        finally:
            self.lock.release()

    def loop(self):
        while not self.stop.is_set():
            try:
                self.tick()
            except Exception:
                # Keep recovery alive if BlueZ temporarily disappears during boot.
                self.message = 'Bluetooth-Verbindung vorübergehend nicht möglich. Wird erneut versucht.'
                self.connected = False
            self.stop.wait(10)
