import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from app import create_app

BASE = 'http://127.0.0.1:8888'
ALBUM = 'spotify:album:' + 'a' * 22


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


def test_spotify_tab_has_search_and_player_and_keeps_connection(app):
    html = app.test_client().get('/', base_url=BASE).text
    assert html.count('data-view="spotify"') == 2
    for element in ('id="sp-query"', 'id="sp-results"', 'id="sp-tracks"', 'id="spotify-connection"', 'name="client_id"'):
        assert element in html


def test_new_card_dialog_is_outside_every_view(app):
    """The Spotify tab opens the dialog while the NFC view is hidden; a dialog inside a
    hidden view would not show."""
    html = app.test_client().get('/', base_url=BASE).text

    class Parser(HTMLParser):
        stack, inside = [], None

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == 'dialog' and attrs.get('id') == 'new-card':
                self.inside = any('data-view' in a for a in self.stack)
            if tag not in ('input', 'img', 'meta', 'link', 'br'):
                self.stack.append(attrs)

        def handle_endtag(self, tag):
            if tag not in ('input', 'img', 'meta', 'link', 'br') and self.stack:
                self.stack.pop()

    parser = Parser()
    parser.feed(html)
    assert parser.inside is False


def test_album_lists_titles_over_several_pages(app):
    sp = app.extensions['spotify']
    calls = []

    def track(n):
        return dict(name=f'Kapitel {n}', uri='spotify:track:' + str(n % 10) * 22, track_number=n, artists=[], duration_ms=1000)

    def api(method, path, body=None, params=None):
        calls.append((path, params))
        if path == '/albums/' + 'a' * 22:
            return dict(
                name='Hörspiel', artists=[dict(name='Erzähler')], images=[dict(url='https://i.scdn.co/gross'), dict(url='https://i.scdn.co/klein')],
                tracks=dict(items=[track(n) for n in range(1, 51)], next='more'),
            )
        return dict(items=[track(n) for n in range(51, 61)], next=None)

    sp.api = api
    r = app.test_client().get('/api/spotify/album', query_string={'uri': ALBUM}, base_url=BASE).json
    assert r['album']['name'] == 'Hörspiel' and r['album']['uri'] == ALBUM
    assert len(r['tracks']) == 60 and r['tracks'][59]['number'] == 60
    assert r['tracks'][0]['artist'] == 'Erzähler' and r['tracks'][0]['image'] == 'https://i.scdn.co/klein'
    assert calls[1] == ('/albums/' + 'a' * 22 + '/tracks', {'offset': 50, 'limit': 50})


def test_album_rejects_other_links(app):
    r = app.test_client().get('/api/spotify/album', query_string={'uri': 'spotify:playlist:' + 'b' * 22}, base_url=BASE)
    assert r.status_code == 400 and 'Alben' in r.json['error']


def test_spotify_tab_buttons_play_and_link_card():
    js = (Path(__file__).resolve().parent.parent / 'static' / 'app.js').read_text()
    assert re.search(r"label:'Abspielen', onClick:spotifyPlay", js)
    assert re.search(r"label:'Mit NFC verbinden', quiet:true, onClick:openNewCard", js)
    assert 'if (newCard.preset) { newCardPick(newCard.preset); return; }' in js
