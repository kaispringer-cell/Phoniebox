import re
from pathlib import Path
from tempfile import TemporaryDirectory

from app import create_app

BASE = 'http://127.0.0.1:8888'
ALBUM = 'spotify:album:' + 'A' * 22


def client_and_store(directory):
    app = create_app(Path(directory))
    client = app.test_client()
    html = client.get('/', base_url=BASE).text
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
    return client, app.extensions['store'], app.extensions['hardware'], csrf, html


def post(client, csrf, **data):
    return client.post('/api/cards/music', base_url=BASE, data=data, headers={'X-CSRF-Token': csrf})


def test_wizard_button_and_dialog_are_on_the_cards_page():
    with TemporaryDirectory() as d:
        *_, html = client_and_store(d)
        cards = re.search(r'<section data-view="cards".*?</section>', html, re.S).group(0)
        assert cards.count('id="new-card"') == 1
        assert cards.count('<dialog id="new-card-dialog"') == 1
        assert 'Neue NFC-Karte' in cards


def test_wizard_saves_music_card_and_returns_link_for_writing():
    with TemporaryDirectory() as d:
        client, store, hw, csrf, _ = client_and_store(d)
        hw.learn()
        r = post(client, csrf, uid='0012345', name='Beispiel-Hörspiel', uri=ALBUM)
        assert r.status_code == 200
        assert r.json['url'] == 'https://open.spotify.com/album/' + 'A' * 22
        card = store.card('0012345')
        assert card['name'] == 'Beispiel-Hörspiel' and card['uri'] == ALBUM and card['action'] == 'music'
        assert not hw.snapshot()['learning']


def test_wizard_accepts_open_spotify_links_and_overwrites_existing_card():
    with TemporaryDirectory() as d:
        client, store, _, csrf, _ = client_and_store(d)
        store.save_card('7', 'Alt', 'phoniebox:pause:0')
        r = post(client, csrf, uid='7', name='Neu', uri='https://open.spotify.com/playlist/' + 'b' * 22)
        assert r.status_code == 200
        assert store.card('7')['uri'] == 'spotify:playlist:' + 'b' * 22


def test_wizard_rejects_missing_card_name_or_bad_link_as_json():
    with TemporaryDirectory() as d:
        client, store, _, csrf, _ = client_and_store(d)
        for data in (
            dict(uid='', name='Muster', uri=ALBUM),
            dict(uid='12a', name='Muster', uri=ALBUM),
            dict(uid='12', name='', uri=ALBUM),
            dict(uid='12', name='Muster', uri='https://example.com/album/x'),
        ):
            r = post(client, csrf, **data)
            assert r.status_code == 400 and r.json['error']
        assert store.cards() == []


def test_wizard_requires_csrf():
    with TemporaryDirectory() as d:
        client, store, *_ = client_and_store(d)
        r = client.post('/api/cards/music', base_url=BASE, data=dict(uid='1', name='Muster', uri=ALBUM))
        assert r.status_code == 403 and store.cards() == []
