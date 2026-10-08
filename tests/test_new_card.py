import re
from pathlib import Path

import pytest

from app import create_app

BASE = 'http://127.0.0.1:8888'
STATIC = Path(__file__).resolve().parent.parent / 'static'
URI = 'spotify:album:' + 'a' * 22


@pytest.fixture
def app(tmp_path):
    return create_app(tmp_path)


def test_every_element_app_js_uses_is_on_the_page(app):
    html = app.test_client().get('/', base_url=BASE).text
    page_ids = set(re.findall(r'id="([^"]+)"', html))
    used = set(re.findall(r"\$\('([^']+)'\)", (STATIC / 'app.js').read_text()))
    used |= {f'nc-{step}' for step in ('scan', 'search', 'save')} | {f'nc-mark-{step}' for step in ('scan', 'search', 'save')}
    for ids in re.findall(r"\{query:'([^']+)',type:'([^']+)',status:'([^']+)',results:'([^']+)'\}", (STATIC / 'app.js').read_text()):
        used |= set(ids)
    assert 'new-card-open' in page_ids and 'new-card' in page_ids
    assert used - page_ids == set()


def test_new_card_is_captured_silently_and_saved_with_spotify_item(app):
    client = app.test_client()
    html = client.get('/', base_url=BASE).text
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
    hw, store = app.extensions['hardware'], app.extensions['store']
    store.save_card('1549562714', 'Alte Musik', 'spotify:playlist:' + 'b' * 22)

    assert client.post('/api/learn', headers={'X-CSRF-Token': csrf}, base_url=BASE).json['ok']
    hw.scan('1549562714')
    h = client.get('/api/hardware', base_url=BASE).json
    assert h['learning'] and h['learned'] == '1549562714' and h['card']['name'] == 'Alte Musik'
    assert hw.jobs.empty()  # nothing plays while the card is being captured

    client.post('/api/learn/cancel', headers={'X-CSRF-Token': csrf}, base_url=BASE)
    r = client.post(
        '/cards',
        data={'csrf': csrf, 'action': 'music', 'uid': '1549562714', 'uri': URI, 'name': 'Kinderlieder'},
        base_url=BASE,
    )
    assert r.status_code == 302
    card = store.card('1549562714')
    assert card['name'] == 'Kinderlieder' and card['uri'] == URI and card['action'] == 'music'
