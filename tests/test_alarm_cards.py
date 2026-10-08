import re
from pathlib import Path
from tempfile import TemporaryDirectory

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from werkzeug.datastructures import MultiDict

from app import card_groups, create_app
from storage import Store

BASE = 'http://127.0.0.1:8888'
SPEAKER = 'bluealsa:DEV=78:5E:A2:E5:7B:22,PROFILE=a2dp'


def client_and_store(directory):
    app = create_app(Path(directory))
    client = app.test_client()
    html = client.get('/', base_url=BASE).text
    csrf = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
    return client, app.extensions['store'], csrf


def saved(store):
    return store.get('alarms') or []


def berlin(day, clock):
    hour, minute = map(int, clock.split(':'))
    # 2026-09-28 is a Monday (weekday 0).
    return datetime(2026, 9, 28, hour, minute, tzinfo=ZoneInfo('Europe/Berlin')) + timedelta(days=day)


def alarm_form(csrf, **changes):
    fields = dict(
        enabled='on', time='06:30', source='tone', output='analog', bluetooth_device='', tone='bell',
        station='wdr2', uri='', volume='30', duration='15',
    )
    fields.update(changes)
    days = fields.pop('days', ['0', '1'])
    return MultiDict([('csrf', csrf)] + [(k, v) for k, v in fields.items() if v is not None] + [('days', d) for d in days])


def alarm_section(html):
    return re.search(r'<section data-view="alarm".*?</section>', html, re.S).group(0)


def test_bluetooth_alarm_without_alsa_name_uses_the_main_bluetooth_speaker():
    # Real incident: the only speaker is Bluetooth; choosing "Bluetooth" for the alarm but
    # leaving the free-text ALSA name empty rejected the save and looked like "not saved".
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        store.put(audio=SPEAKER)
        r = client.post('/alarm', data=alarm_form(csrf, output='bluetooth'), base_url=BASE)
        assert r.status_code == 302
        [alarm] = saved(store)
        assert alarm['output'] == 'bluetooth' and alarm['bluetooth_device'] == SPEAKER
        assert alarm['enabled'] is True and alarm['time'] == '06:30'


def test_new_alarm_starts_on_the_bluetooth_speaker_if_that_is_the_main_output():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        store.put(audio=SPEAKER)
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert re.search(r'<option value="bluetooth" selected>', section)
        assert 'value="' + SPEAKER + '"' in section
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        store.put(audio='plughw:0,0')
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert re.search(r'<option value="analog" selected>', section)


def test_new_alarm_form_is_pre_ticked_but_nothing_rings_before_saving():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert 'name="enabled" checked' in section
        assert 'Noch kein Wecker gespeichert' in section and 'Neuer Wecker' in section
        assert client.application.extensions['media'].alarms() == []


def test_rejected_alarm_keeps_the_entries_and_shows_why_in_the_alarm_section():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        r = client.post('/alarm', data=alarm_form(csrf, time='05:45', days=[]), base_url=BASE)
        assert r.status_code == 302 and r.headers['Location'].endswith('/#alarm')
        assert saved(store) == []
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert 'role="alert">Nicht gespeichert: Mindestens einen Wochentag wählen.' in section
        # What was typed is still there, not the default 07:00.
        assert 'name="time" value="05:45"' in section
        assert 'name="enabled" checked' in section
        # Shown once; a later reload shows a fresh form again.
        again = alarm_section(client.get('/', base_url=BASE).text)
        assert 'Nicht gespeichert' not in again and 'name="time" value="07:00"' in again


def test_bluetooth_alarm_without_any_known_speaker_still_explains_itself():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        store.put(audio='plughw:0,0')
        client.post('/alarm', data=alarm_form(csrf, output='bluetooth'), base_url=BASE)
        assert saved(store) == []
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert 'Nicht gespeichert: Für den Weckausgang Bluetooth ist kein Lautsprecher bekannt.' in section
        assert '<option value="bluetooth" selected>' in section


def test_saving_an_inactive_alarm_says_so_and_lists_it_as_off():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf, enabled=None), base_url=BASE)
        assert saved(store)[0]['enabled'] is False
        html = client.get('/', base_url=BASE).text
        assert 'Wecker 06:30 gespeichert, aber nicht aktiv' in html
        assert '<span class="badge off">Aus</span>' in alarm_section(html)
        client.post('/alarm', data=alarm_form(csrf, time='07:15'), base_url=BASE)
        assert 'Wecker 07:15 gespeichert und aktiv' in client.get('/', base_url=BASE).text


def test_existing_single_alarm_is_taken_over_into_the_list():
    # Up to 1.17.x there was exactly one alarm under the setting "alarm".
    with TemporaryDirectory() as d:
        legacy = dict(enabled=True, time='06:10', days=[0, 1, 2, 3, 4], source='radio', tone='bell', station='maus',
                      uri='', volume=25, duration=20, output='analog', bluetooth_device='')
        # As on a box updated from 1.17.x: the old alarm is there before the new version first starts.
        Store(Path(d)).put(alarm=legacy, alarm_last_date='2026-09-28')
        client, store, csrf = client_and_store(d)
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert '<span class="alarm-time">06:10</span>' in section
        assert 'Mo–Fr · Radio · Die Maus · Klinke · 25 % · 20 Min.' in section
        [alarm] = saved(store)
        assert {k: alarm[k] for k in legacy} == legacy and re.fullmatch('[0-9a-f]{8}', alarm['id'])
        # It already rang today before the update, so it must not ring a second time.
        assert store.get('alarm_last_dates') == {alarm['id']: '2026-09-28'}
        # The old setting stays, so an older app version installed again still finds it.
        assert store.get('alarm') == legacy
        media = client.application.extensions['media']
        rang = []
        media.fire = rang.append
        media.tick(berlin(0, '06:10'))
        assert rang == []
        media.tick(berlin(1, '06:10'))
        assert [a['time'] for a in rang] == ['06:10']


def test_several_alarms_are_listed_by_time_and_each_can_be_edited():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf, time='08:00', days=['5', '6'], source='radio'), base_url=BASE)
        client.post('/alarm', data=alarm_form(csrf, time='06:30'), base_url=BASE)
        late, early = saved(store)
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert section.index('>06:30<') < section.index('>08:00<')
        assert 'Sa + So · Radio · WDR 2 Rheinland' in section
        # "Bearbeiten" opens the form with that alarm's values and its id.
        edit = alarm_section(client.get('/?alarm=' + late['id'], base_url=BASE).text)
        assert 'Wecker bearbeiten' in edit and 'name="id" value="' + late['id'] + '"' in edit
        assert 'name="time" value="08:00"' in edit and 'Änderungen speichern' in edit
        assert '<option value="radio" selected>' in edit
        # Saving changes that alarm only; no new one appears.
        client.post('/alarm', data=alarm_form(csrf, id=late['id'], time='08:30', days=['5', '6']), base_url=BASE)
        changed, unchanged = saved(store)
        assert changed['id'] == late['id'] and changed['time'] == '08:30' and changed['source'] == 'tone'
        assert unchanged == early


def test_rejected_edit_stays_on_the_alarm_being_edited():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf, time='06:30'), base_url=BASE)
        [alarm] = saved(store)
        client.post('/alarm', data=alarm_form(csrf, id=alarm['id'], time='05:00', days=[]), base_url=BASE)
        section = alarm_section(client.get('/', base_url=BASE).text)
        assert 'Nicht gespeichert: Mindestens einen Wochentag' in section
        assert 'Wecker bearbeiten' in section and 'name="id" value="' + alarm['id'] + '"' in section
        assert saved(store) == [alarm]


def test_alarm_can_be_switched_off_and_on_deleted_and_tested():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf), base_url=BASE)
        [alarm] = saved(store)
        client.post('/alarm/enabled', data=dict(csrf=csrf, id=alarm['id']), base_url=BASE)
        assert saved(store)[0]['enabled'] is False
        assert 'Wecker 06:30 ausgeschaltet.' in client.get('/', base_url=BASE).text
        client.post('/alarm/enabled', data=dict(csrf=csrf, id=alarm['id'], enabled='on'), base_url=BASE)
        assert saved(store)[0]['enabled'] is True
        media = client.application.extensions['media']
        fired = []
        media.fire = fired.append
        r = client.post('/api/alarm/test', data=dict(csrf=csrf, id=alarm['id']), base_url=BASE)
        assert r.status_code == 200 and fired[0]['id'] == alarm['id']
        client.post('/alarm/delete', data=dict(csrf=csrf, id=alarm['id']), base_url=BASE)
        assert saved(store) == []
        assert 'Wecker 06:30 gelöscht.' in client.get('/', base_url=BASE).text
        # A deleted alarm cannot be edited, tested or toggled any more.
        r = client.post('/api/alarm/test', data=dict(csrf=csrf, id=alarm['id']), base_url=BASE)
        assert r.status_code == 400 and 'existiert nicht mehr' in r.json['error']
        client.post('/alarm', data=alarm_form(csrf, id=alarm['id']), base_url=BASE)
        assert saved(store) == []
        assert client.post('/alarm/delete', data=dict(csrf=csrf, id='../x'), base_url=BASE).status_code == 302
        assert saved(store) == []


def test_each_alarm_rings_on_its_own_days_once_per_day():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf, time='06:30', days=['0', '1', '2', '3', '4']), base_url=BASE)
        client.post('/alarm', data=alarm_form(csrf, time='08:00', days=['5', '6']), base_url=BASE)
        client.post('/alarm', data=alarm_form(csrf, time='06:30', days=['0'], enabled=None), base_url=BASE)
        media = client.application.extensions['media']
        rang = []
        media.fire = rang.append
        media.tick(berlin(0, '06:30'))
        media.tick(berlin(0, '06:30'))  # same minute again: no second ring
        media.tick(berlin(0, '08:00'))  # weekend alarm, not on Monday
        media.tick(berlin(5, '08:00'))  # Saturday
        media.tick(berlin(5, '06:30'))  # weekday alarm, not on Saturday
        assert [(a['time'], a['days']) for a in rang] == [('06:30', [0, 1, 2, 3, 4]), ('08:00', [5, 6])]


def test_two_alarms_at_the_same_minute_ring_once():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        client.post('/alarm', data=alarm_form(csrf, time='06:30', tone='bell'), base_url=BASE)
        client.post('/alarm', data=alarm_form(csrf, time='06:30', tone='beep'), base_url=BASE)
        media = client.application.extensions['media']
        rang = []
        media.fire = rang.append
        media.tick(berlin(0, '06:30'))
        media.tick(berlin(0, '06:30'))
        assert [a['tone'] for a in rang] == ['bell']
        assert set(store.get('alarm_last_dates')) == {a['id'] for a in saved(store)}


def test_cards_are_grouped_by_type_and_sorted_by_name():
    cards = [
        dict(uid='1', name='Zoo', action='music', uri='spotify:album:x', value=10, station=''),
        dict(uid='2', name='Leiser', action='volume_down', uri='', value=10, station=''),
        dict(uid='3', name='WDR 2', action='radio', uri='', value=10, station='wdr2'),
        dict(uid='4', name='abc', action='music', uri='spotify:album:y', value=10, station=''),
        dict(uid='5', name='Stop', action='pause', uri='', value=10, station=''),
        dict(uid='6', name='1LIVE', action='radio', uri='', value=10, station='1live'),
    ]
    groups = card_groups(cards)
    assert [g['label'] for g in groups] == ['Musik', 'Radio', 'Steuerung']
    assert [c['name'] for c in groups[0]['cards']] == ['abc', 'Zoo']
    assert [c['name'] for c in groups[1]['cards']] == ['1LIVE', 'WDR 2']
    # Control cards follow the order of the actions in the card form: stop before quieter.
    assert [c['name'] for c in groups[2]['cards']] == ['Stop', 'Leiser']
    assert card_groups([dict(uid='9', name='Nur Radio', action='radio', uri='', value=10, station='wdr2')])[0]['label'] == 'Radio'
    assert card_groups([]) == []


def test_card_page_shows_the_type_groups_in_order():
    with TemporaryDirectory() as d:
        client, store, csrf = client_and_store(d)
        store.save_card('11', 'Stop', 'phoniebox:pause:10')
        store.save_card('12', 'Kinderlieder', 'spotify:playlist:37i9dQZF1DXcBWIGoYBM5M')
        store.save_card('13', 'Die Maus', 'phoniebox:radio:maus')
        html = client.get('/', base_url=BASE).text
        cards = re.search(r'<section data-view="cards".*?</section>', html, re.S).group(0)
        positions = [cards.index('card-group-title">' + label) for label in ('Musik', 'Radio', 'Steuerung')]
        assert positions == sorted(positions)
        assert cards.index('Kinderlieder') < cards.index('Die Maus') < cards.index('<h3>Stop</h3>')
        assert 'Noch keine Karten zugeordnet' not in cards
