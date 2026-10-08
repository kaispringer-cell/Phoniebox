"""ALSA device names: first-boot detection of the analogue jack, and validation of allowed output names."""

import os
from pathlib import Path
import re
import subprocess
from storage import Store

# Local sound cards or the ALSA default.
ALSA_LOCAL = re.compile(r'(?:plughw|hw):[A-Za-z0-9_]+,[0-9]+|default')
# Bluetooth speaker through bluealsa, e.g. bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp
ALSA_BLUETOOTH = re.compile(r'bluealsa(?::[A-Za-z0-9_]+=[A-Za-z0-9:_.-]+(?:,[A-Za-z0-9_]+=[A-Za-z0-9:_.-]+)*)?')


def choose_card(cards):
    for line in cards.splitlines():
        match = re.match(r'\s*\d+\s+\[([^]]+)\].*', line)
        if match and ('headphone' in line.lower() or 'bcm2835 analog' in line.lower()):
            return match[1].strip()
    return None


def analog_device(store, cards=None):
    """ALSA name of the 3.5 mm jack, independent of which output is currently the main one."""
    saved = store.get('analog_audio')
    if saved:
        return saved
    if cards is None:
        try:
            cards = Path('/proc/asound/cards').read_text()
        except OSError:
            cards = ''
    card = choose_card(cards)
    if card and re.fullmatch('[A-Za-z0-9_]+', card):
        return 'plughw:' + card + ',0'
    audio = store.get('audio')
    return audio if ALSA_LOCAL.fullmatch(audio) else 'default'


def device_reachable(device, run=subprocess.run, timeout=1.5):
    """Best-effort check whether an ALSA device can actually be opened right now.

    This catches the case where even an ordinary-looking name like 'default' has been
    silently redirected by the system (for example to an unavailable Bluetooth speaker
    via /etc/asound.conf) to a PCM that cannot currently be opened: librespot itself
    gives no usable signal for that (its own error output is intentionally not
    surfaced, to keep auth tokens out of the journal), so it would otherwise just look
    like the device vanishing from Spotify right after being selected.
    """
    try:
        result = run(
            ['timeout', str(timeout), 'aplay', '-q', '-D', device, '-f', 'S16_LE', '-r', '44100', '-c', '2', '/dev/zero'],
            capture_output=True,
            timeout=timeout + 5,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    # 0: aplay exited on its own (unexpected for /dev/zero, but not a failure).
    # 124: 'timeout' had to kill it, i.e. it was still happily playing silence.
    # Anything else: aplay itself refused to open the device.
    return result.returncode in (0, 124)


def configure(store, cards=None, run=subprocess.run):
    if store.get('audio_configured', False):
        return True
    if cards is None:
        try:
            cards = Path('/proc/asound/cards').read_text()
        except OSError:
            return False
    card = choose_card(cards)
    if not card or not re.fullmatch('[A-Za-z0-9_]+', card):
        return False
    result = run(['/usr/bin/amixer', '-c', card, 'scontrols'], capture_output=True, text=True, timeout=10)
    if result.returncode or "'PCM'" not in result.stdout:
        return False
    device = 'plughw:' + card + ',0'
    store.put(audio=device, analog_audio=device, mixer_card=card, mixer_control='PCM', audio_configured=True)
    return True


if __name__ == '__main__':
    os.umask(0o077)
    if not configure(Store(os.environ.get('PHONIEBOX_DATA', '/var/lib/phoniebox'))):
        print('Analoger Pi-Ausgang noch nicht verfügbar. Einrichtung nach Neustart erneut versuchen.')
