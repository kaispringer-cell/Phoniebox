"""Called by librespot (--onevent) for every player event; keeps what the box itself plays.

The Spotify Web API's /me/player kept reporting an old album for the Phoniebox while a card's
album was audibly playing. librespot knows what it plays, so its events are the source for the
start page. Runs as a short-lived child of librespot: write one small JSON file and exit."""

import json
import os
import sys
import time
from pathlib import Path

TRACK_FIELDS = ('TRACK_ID', 'URI', 'NAME', 'ARTISTS', 'ALBUM', 'SHOW_NAME', 'COVERS', 'DURATION_MS', 'ITEM_TYPE')


def update(state, env, now):
    event = env.get('PLAYER_EVENT', '')
    if event == 'track_changed':
        playing = state.get('playing', False)
        state = {key.lower(): env.get(key, '') for key in TRACK_FIELDS}
        state.update(playing=playing, position_ms=0, position_at=now)
    elif event in ('playing', 'paused', 'seeked', 'position_correction'):
        if env.get('TRACK_ID') and env.get('TRACK_ID') != state.get('track_id'):
            # Event for a track we have no metadata for (e.g. after a librespot restart).
            state = {'track_id': env.get('TRACK_ID')}
        if event in ('playing', 'paused'):
            state['playing'] = event == 'playing'
        state['position_ms'] = int(env.get('POSITION_MS') or 0)
        state['position_at'] = now
    elif event in ('stopped', 'session_disconnected'):
        state['playing'] = False
        state['stopped'] = True
    else:
        return None
    if event not in ('stopped', 'session_disconnected'):
        state.pop('stopped', None)
    state['updated'] = now
    return state


def main():
    target = os.environ.get('PHONIEBOX_PLAYER_STATE')
    if not target:
        return
    path = Path(target)
    try:
        state = json.loads(path.read_text())
        if not isinstance(state, dict):
            state = {}
    except (OSError, ValueError):
        state = {}
    state = update(state, os.environ, time.time())
    if state is None:
        return
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(state))
    os.replace(temporary, path)


if __name__ == '__main__':
    try:
        main()
    except Exception:
        # Never let a display helper disturb playback.
        sys.exit(0)
