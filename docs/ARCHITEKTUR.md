# Architektur

Technische Beschreibung für die Weiterentwicklung. Bedienung und Installation stehen in der [README](../README.md).

## Überblick

```text
Browser ──HTTPS──▶ nginx (:443, TLS, Host-Filter) ──HTTP──▶ waitress (127.0.0.1:8888) ──▶ Flask-App (app.py)
                                                                       │
        ┌──────────────────────────────────────────────────────────────┤ ein Prozess, mehrere Threads
        ▼                        ▼                        ▼            ▼
  reader_loop              play_loop                player_loop    AlarmRadio.loop
  (NFC per evdev)          (Karten-Aufträge)        (librespot)    (Wecker, mpv)
        │                        │                        │            │
   USB-Reader             Spotify-Web-API          Spotify Connect     mpv (Radio/Töne)
   413d:2107              (spotify.py)             über ALSA           über ALSA
```

Alles läuft in **einem** Prozess (`run.py`). Mehrere Web-Worker sind nicht zulässig, weil NFC-Reader, OAuth-Zustände und die librespot-Überwachung Singletons sind.

Die Wiedergabe arbeitet zweigleisig:

- **Spotify**: librespot registriert die Box als Connect-Gerät. Die App steuert nur über die Web-API (Play, Pause, Lautstärke …) dieses Gerät fern. Das Audio spielt librespot selbst.
- **Lokal**: Radio und Wecktöne spielt `mpv`. Beide Wege teilen sich denselben ALSA-Ausgang, deshalb wird librespot für lokale Wiedergabe beendet und danach wieder gestartet.

## Module

| Datei | Aufgabe |
| --- | --- |
| `run.py` | Einstiegspunkt: `create_app(start_hardware=True)`, waitress mit 4 Threads auf `127.0.0.1:8888`, sauberes Beenden bei SIGTERM/SIGINT |
| `app.py` | Flask-App: Routen, Formularprüfung, Host-/CSRF-Schutz, Sicherheits-Header, Sitzungs-Cookies |
| `storage.py` | `Store`: SQLite-Zugriff, Einstellungen, verschlüsselte Secrets, Karten, Standardwerte |
| `spotify.py` | `Spotify`: OAuth mit PKCE, Token-Erneuerung, Geräteauswahl, Player-Befehle, 429-Pause, `search()` (Alben/Titel/Playlists für die NFC-Kartenerfassung). `normalize_uri`, `Problem` |
| `hardware.py` | `Hardware`: NFC-Reader (`DigitReader`), Kartenaufträge, librespot-Überwachung, `command()`/`clarify()`/`check_audio_output()` (macht einen fehlgeschlagenen Wiedergabeversuch mit nicht erreichbarem oder zwischenzeitlich getrenntem Audioausgang für den Nutzer sichtbar statt einer irreführenden allgemeinen Spotify-Meldung oder eines wirkungslosen „Wiedergabebefehl gesendet“) |
| `alarm_radio.py` | `AlarmRadio`: mpv-Wiedergabe, Senderliste, Töne, Wecker. `alarm_config`, `due`, `make_tone` |
| `configure_audio.py` | Einmalige Erkennung des analogen Ausgangs beim ersten Dienststart. Erlaubte Ausgangsnamen (`ALSA_LOCAL`, `ALSA_BLUETOOTH`), `analog_device()` und `device_reachable()` (prüft vor dem librespot-Start, ob sich ein ALSA-Gerät tatsächlich öffnen lässt) |
| `bluetooth.py` | Dünner `bluetoothctl`-Wrapper für den Bereich „Bluetooth“ in der Weboberfläche: `scan()`, `pair()`, `connect()`, `disconnect()`, `forget()`, `paired_devices()`, `info()`. Keine D-Bus-Bibliothek, jeder Aufruf ist ein eigener, non-interaktiver `bluetoothctl`-Unterprozess; Scan wird über `bluetoothctl --timeout` begrenzt (das Kommando kehrt sonst nie von selbst zurück) |
| `notifications.py` | `Notices`: aktuelle Probleme (Bluetooth, Audioausgang, Player, NFC-Reader, Spotify) für `GET /api/notifications`, das die Android-App abfragt. Meldet ein Problem erst nach 30 Sekunden (`GRACE`) und liest nur vorhandenen Zustand (`Reconnector.connected`, `player_status`, `reader_status`) |
| `update.py` | Updater (läuft auf dem Pi als root, wird vom Desktop-Installer mitgeliefert und steht nicht in `release.json`), siehe unten |
| `install.sh`, `build_librespot.sh`, `resume.sh`, `diagnose.sh` | Erstinstallation, librespot-Build, Abschluss nach Portkonflikt, Diagnose |
| `deploy/` | `phoniebox.service`, `phoniebox-reboot.path`/`.service` (Neustart-Helfer), `bluealsa-override.conf` (`--keep-alive=5`), `nginx.conf`, udev-Regel `99-phoniebox-nfc.rules` |
| `templates/`, `static/` | Eine Seite (`index.html` auf `base.html`), `app.js` (Polling und Formulare), `style.css` |
| `release.json`, `VERSION` | Manifest und Version des Update-Pakets |
| `tests/` | pytest-Tests (71) |
| `android/` | Android-App (WebView auf `https://phoniebox.local` plus Benachrichtigungen), nicht Teil des App-Pakets. Siehe `android/README.md` |

## Threads und Laufzeitverhalten

`Hardware.start()` und `AlarmRadio.start()` starten Daemon-Threads:

- **`reader_loop`** liest `/dev/input/by-id/usb-413d_2107-event-kbd` per evdev, belegt das Gerät exklusiv (`grab`) und füttert den `DigitReader`. Der Reader wertet nur Ziffern (Hauptblock und Ziffernblock) gefolgt von Enter aus, höchstens 32 Stellen. Zwischen zwei Tasten dürfen höchstens 2 Sekunden liegen, führende Nullen bleiben erhalten, jedes andere Zeichen macht die Eingabe ungültig. Bei Fehlern wird alle 3 Sekunden neu verbunden.
- **`play_loop`** nimmt genau einen Kartenauftrag aus einer Warteschlange der Größe 1 und führt ihn aus. Ist sie voll, erscheint „Wiedergabeauftrag läuft bereits“.
- **`player_loop`** überwacht librespot: setzt den ALSA-Regler mit `amixer` auf 100 %, prüft mit `configure_audio.device_reachable()`, ob sich der eingestellte Ausgang gerade tatsächlich öffnen lässt (z. B. ein per `bluealsa` angebundener, aber nicht verbundener Bluetooth-Lautsprecher – auch hinter einem unauffälligen `default`, das die System-ALSA-Konfiguration umgeleitet haben kann), startet erst dann `/usr/local/bin/phoniebox-librespot` und startet ihn bei Ende oder bei gesetztem `restart`-Event neu (Wartezeit 5 Sekunden nach Fehlern oder einem nicht erreichbaren Ausgang). Ist der Ausgang nicht erreichbar, bleibt `player_status` entsprechend gesetzt und librespot wird gar nicht erst gestartet – ohne das würde ein solcher Fehler erst beim eigentlichen Wiedergabestart auftreten und sähe für Spotify wie ein sofort wieder verschwindendes Gerät aus, weil librespots eigene Fehlerausgabe absichtlich nicht ins Journal gelangt. Während lokaler Wiedergabe (`local_audio` gesetzt) wartet er. Die Ausgabe von librespot wird verworfen, damit keine Anmeldedaten in Journale gelangen. Eine Bluetooth-Trennung *während* laufender Wiedergabe wird bewusst nicht laufend im Hintergrund überwacht (unnötiger Dauer-Overhead für `bluetoothctl`), sondern erst beim nächsten tatsächlichen Wiedergabeversuch erkannt, siehe `Hardware.check_audio_output()`.
- **`AlarmRadio.loop`** ruft einmal pro Sekunde `tick()` auf: Weckzeit prüfen, Alarmdauer prüfen, Ende eines lokalen Streams erkennen.

Kartenerkennung (`Hardware.scan`): dieselbe ID innerhalb von 3 Sekunden wird ignoriert. Im Anlernmodus (60 Sekunden, ausgelöst über `/api/learn`) wird die Karte nur gemeldet, nicht ausgeführt. `snapshot()` liefert der Weboberfläche Reader-Status, Player-Status, letzte Karte und eine Revisionsnummer, damit das Formular nur bei einem neuen Auflegen befüllt wird.

## Datenhaltung

Verzeichnis `PHONIEBOX_DATA` (Standard `/var/lib/phoniebox`, Modus 0700):

| Datei | Inhalt |
| --- | --- |
| `phoniebox.sqlite3` (0600) | Einstellungen, Secrets, Karten |
| `secret.key` (0600) | Fernet-Schlüssel für die Tabelle `secrets`. Fehlt er bei vorhandener Datenbank, wirft `Store` einen Fehler, statt einen neuen Schlüssel zu erzeugen |
| `librespot/` | Systemcache von librespot mit der Spotify-Connect-Anmeldung |
| `tone-*.wav` | Bei Bedarf erzeugte Wecktöne |

Tabellen:

- `settings(key, value)`: Werte als JSON. Bekannte Schlüssel: `name`, `audio`, `mixer_card`, `mixer_control`, `volume`, `client_id`, `repeat_card`, `audio_configured`, `analog_audio`, `alarms`, `alarm_last_dates`, aus Versionen bis 1.17.x außerdem `alarm` und `alarm_last_date` (werden beim ersten Start übernommen und danach nicht mehr geändert). Für `name`, `audio`, `mixer_card`, `mixer_control`, `volume`, `client_id` und `repeat_card` gelten die Standardwerte in `storage.DEFAULTS`. In Datenbanken aus Installationen vor 1.5.3 kann noch ein `password_hash` stehen; er wird ignoriert.
- `secrets(key, value)`: Fernet-verschlüsselte JSON-Werte: `client_secret`, `tokens` (Access-/Refresh-Token und `expires_at`), `session_key`.
- `cards(uid, name, uri)`: `uid` besteht aus 1 bis 32 Ziffern.

Bei Musik-Karten steht in `uri` die Spotify-URI (`spotify:<typ>:<22 Zeichen>` mit Typ `playlist`, `album`, `track` oder `episode`). Steuerkarten speichern `phoniebox:<aktion>:<wert>` mit den Aktionen `play`, `pause`, `next`, `previous`, `volume_up`, `volume_down`, `volume`. Radiosender-Karten speichern `phoniebox:radio:<sender-id>` mit der ID aus `STATIONS` (zum Beispiel `wdr2`). `Store.card_details` zerlegt das für die Anwendung in `action`, `value` (Zahl), `station` und `uri`.

Ausführung von Radiosender-Karten (`Hardware.play_radio`): Ist derselbe Sender gerade in Betrieb (`AlarmRadio.is_playing`) und `repeat_card` nicht `replay`, wird er beendet (`AlarmRadio.stop`). Sonst setzt es `alarm_until` zurück und startet ihn mit `AlarmRadio.local` auf dem Hauptausgang, mit der aktuellen lokalen Lautstärke oder der Startlautstärke. `AlarmRadio.local` merkt sich die Auswahl in `choice` und setzt `Hardware.last_music_uid` zurück, damit eine Musik-Karte danach nicht als „erneut aufgelegt“ gilt und pausiert.

Das Datenbankschema hat `PRAGMA user_version`. Ein Wert von 0 mit den drei Tabellen gilt als Schema 1. Es gibt bisher keine Migration.

## Spotify

- OAuth Authorization Code mit PKCE (S256) und State, Scopes `user-read-playback-state user-modify-playback-state`, Redirect `http://127.0.0.1:8888/callback`.
- `/oauth/start` und `/callback` funktionieren nur, wenn die Anfrage über den Tunnel als Host `127.0.0.1:8888` ankommt. Offene Anmeldungen (höchstens 20) liegen im Speicher und verfallen nach 10 Minuten.
- `Spotify.api` erneuert Tokens (auch einmalig nach einem 401), setzt bei HTTP 429 eine Pause gemäß `Retry-After` und übersetzt Fehlercodes in `Problem`-Meldungen. Erfolgreiche Befehle werden nie als JSON geparst.
- `Spotify.device` sucht das Gerät **nur über den eingestellten Namen** und verlangt genau einen Treffer, der nicht eingeschränkt ist. Es fällt nie auf ein anderes Gerät zurück. Für `play` wird ein inaktives Gerät zuerst per Transfer (ohne Wiedergabe) aktiviert und bis zu 4 Sekunden lang auf Aktivierung geprüft.
- Tracks und Folgen werden mit `uris`, Playlists und Alben mit `context_uri` gestartet.
- Der Status (`/me/player`) wird 15 Sekunden zwischengespeichert; jeder Befehl leert den Zwischenspeicher.

## Lokale Wiedergabe, Radio und Wecker

- `AlarmRadio.local` beendet eine laufende lokale Wiedergabe, setzt `local_audio`, beendet librespot und startet `mpv` mit `--audio-device=alsa/<audio>`, IPC-Socket im Temp-Verzeichnis und (bei Tönen) `--loop-file=inf`. Bis zu 15 Sekunden lang wird über den IPC-Socket geprüft, ob `time-pos` einen Wert liefert; sonst gilt der Start als fehlgeschlagen.
- `stop_local` beendet mpv und gibt `local_audio` frei, worauf `player_loop` librespot neu startet.
- Die zehn Sender stehen in `STATIONS` (ID, Name, URL). Die Töne `bell`, `beep`, `melody` erzeugt `make_tone` als 22,05-kHz-Mono-WAV mit 3 Sekunden Länge.
- Die Wecker (`alarms` in `settings`, eine Liste): je `id` (8 Hex-Zeichen), `enabled`, `time` (HH:MM), `days` (0 = Montag bis 6 = Sonntag), `source` (`tone`, `radio`, `spotify`), `tone`, `station`, `uri`, `volume` (1–100), `duration` (1–60 Minuten), `output` (`analog` oder `bluetooth`, Standard `analog`), `bluetooth_device` (bluealsa-Name, bei `output=bluetooth` Pflicht; bleibt beim Wechsel auf `analog` gespeichert).
- `tick` prüft in einer `BEGIN IMMEDIATE`-Transaktion, welche Wecker fällig sind, und schreibt pro Wecker Datum und Weckzeit nach `alarm_last_dates` (z. B. `2026-10-08 07:00`) im selben Schritt. Dadurch klingelt eine Weckzeit pro Tag höchstens einmal, auch nach einem Neustart oder in der doppelten Winterzeitstunde; eine später am Tag neu eingestellte Zeit klingelt trotzdem. Mehrere fällige Wecker in derselben Minute lösen nur den ersten aus. Verpasste Zeiten werden nicht nachgeholt.
- **Alarmausgang** (`AlarmRadio.alarm_outputs`, `play_on_alarm_output`): Bei Ton und Radio werden die Ausgänge der Reihe nach versucht. `analog` bedeutet nur die Klinke. `bluetooth` bedeutet erst `bluetooth_device`, dann die Klinke. `local(..., device=...)` startet mpv mit diesem Gerät; ohne `device` gilt wie bisher der Hauptausgang (`audio`), also auch für die manuelle Radiowiedergabe. Kann mpv das Gerät nicht öffnen, beendet es sich sofort mit Fehlercode 2 (mit `--audio-device=alsa/bluealsa:…` geprüft), was `local()` als Fehlschlag meldet. Deshalb greift der Wechsel auf die Klinke ohne Wartezeit.
- Die Klinke ermittelt `analog_device()`: gespeicherter Wert `analog_audio` (wird beim ersten Start von `configure_audio.py` gesetzt), sonst Erkennung über `/proc/asound/cards`, sonst der Hauptausgang, falls er eine lokale Karte ist, sonst `default`.
- **Spotify** als Weckquelle spielt über librespot auf dem Hauptausgang. `output` gilt dafür nicht, weil librespot mit einem festen Gerät läuft.
- Schlägt die Quelle fehl oder endet ein Stream während des Alarms, startet `fire` beziehungsweise `tick` den Ersatzton, ebenfalls über die Kette des Alarmausgangs. Der Statustext nennt den Ausgang, zum Beispiel „Wecker läuft (Klinke, da Bluetooth nicht erreichbar)“.
- Befehle während lokaler Wiedergabe (`AlarmRadio.command`): Pause/Play und Lautstärke gehen an mpv, „nächster/vorheriger Titel“ ist nicht möglich, `play` mit URI wechselt zurück zu Spotify.

## HTTP-Schnittstelle

Alle POST-Anfragen brauchen ein CSRF-Token (Formularfeld `csrf` oder Header `X-CSRF-Token`).

| Route | Zweck |
| --- | --- |
| `GET /` | Weboberfläche |
| `GET /health` | `{"ok": true, "version": "…"}`, vom Updater und Installer benutzt |
| `GET, POST /login`, `POST /logout` | Leiten nur auf `/` weiter (Kompatibilität) |
| `POST /settings` | Gerätename, Audioausgang, Mixer, Startlautstärke; startet den Player neu |
| `POST /nfc/settings` | Verhalten beim erneuten Auflegen: `replay`, `pause`, `toggle` |
| `POST /credentials` | Client-ID und Client Secret speichern (löscht bei Änderung die Tokens) |
| `POST /oauth/start`, `GET /callback`, `POST /disconnect` | Spotify verbinden und trennen (nur über den Tunnel, außer `/disconnect`) |
| `POST /cards`, `POST /cards/delete` | Karte anlegen, ändern, löschen |
| `GET /api/spotify/search` | Album-/Titel-/Playlist-Suche für die Kartenerfassung (`?q=…`, mindestens 1 Zeichen; optional `type=track\|album\|playlist` zur Eingrenzung, sonst alle drei gemischt); leeres oder fehlendes `q` liefert `[]` ohne Spotify-Aufruf, ein unbekannter `type` einen `Problem`-Fehler |
| `POST /alarm` | Wecker anlegen oder ändern (Feld `id`) |
| `POST /alarm/enabled`, `POST /alarm/delete` | Wecker ein-/ausschalten, löschen |
| `POST /api/learn`, `POST /api/learn/cancel` | Anlernmodus |
| `GET /api/hardware` | Reader-/Player-Status, letzte Karte |
| `GET /api/player`, `POST /api/player/<aktion>` | Wiedergabestatus und Steuerung |
| `POST /api/media/start`, `POST /api/media/stop`, `GET /api/media` | Radio/Töne |
| `POST /api/alarm/test` | Wecker mit `id` sofort auslösen |
| `GET /api/bluetooth` | Gekoppelte Bluetooth-Geräte mit Status |
| `POST /api/bluetooth/scan` | Bis zu 10 Sekunden nach neuen, noch nicht gekoppelten Geräten suchen |
| `POST /api/bluetooth/pair`, `/connect`, `/disconnect`, `/forget` | Gerät koppeln, verbinden, trennen, entfernen (Formularfeld `mac`) |
| `POST /api/bluetooth/use` | Gerät als Audioausgang übernehmen (`bluealsa:DEV=<mac>,PROFILE=a2dp`), startet den Player neu |

Fehler (`Problem`) werden bei `/api/…` als JSON `{"error": …}` mit Status 400, sonst als Hinweis auf der Startseite ausgegeben.

## Sicherheitsmodell

- **Kein Login** seit 1.2.0. Zugriffsschutz bleibt über Netzwerkgrenze, Host-Prüfung, CSRF und die Tunnelpflicht für die Spotify-Anmeldung.
- Host-Prüfung in `app.py` erlaubt nur `phoniebox.local`, `phoniebox.local:443` und `127.0.0.1:8888`. Klartext-HTTP ist ausschließlich für `127.0.0.1:8888` erlaubt. nginx setzt `Host` und `X-Forwarded-Proto` selbst und leitet Port 80 auf HTTPS um.
- Sitzungs-Cookies heißen `phoniebox_tls` (HTTPS) und `phoniebox_tunnel` (Tunnel) und sind `HttpOnly`, `SameSite=Lax`, 8 Stunden gültig; `Secure` wird pro Anfrage gesetzt.
- Antworten tragen `Cache-Control: no-store`, `X-Frame-Options: DENY`, `Referrer-Policy: no-referrer` und eine strenge Content-Security-Policy (Bilder nur von `i.scdn.co` und `mosaic.scdn.co`). Anfragen sind auf 16 KiB begrenzt.
- Cover-URLs werden nur übernommen, wenn sie auf `https://i.scdn.co/` oder `https://mosaic.scdn.co/` zeigen.
- Der Dienst läuft als `phoniebox` (Gruppen `audio`, `phoniebox-nfc`, seit 1.10.0 auch `bluetooth` für `bluetoothctl`/D-Bus) mit den Härtungsoptionen aus `deploy/phoniebox.service`. Schreibrechte bestehen nur auf `/var/lib/phoniebox`.
- Ein bereits installiertes System, das über den Desktop-Installer per In-Place-Update (nicht Neuinstallation) auf 1.10.0 oder neuer aktualisiert, bekommt `bluez` automatisch nachinstalliert (siehe `packages` unten), aber **nicht** automatisch die Gruppenmitgliedschaft `bluetooth` – `update.py` ändert bewusst keine Benutzer/Gruppen, Dienstdatei oder sonstige Systemkonfiguration außerhalb von `/opt/phoniebox` und `/var/lib/phoniebox`. Einmalig manuell nachholen: `sudo usermod -aG bluetooth phoniebox && sudo systemctl restart phoniebox`.

## Installation und Dateisystem

`install.sh` (als root, ohne Argumente und ohne Rückfragen) prüft: 64-Bit-Trixie, Raspberry Pi 3 Model B, mindestens 8 GiB frei, keine vorhandene Installation (`/opt/phoniebox`, Dienst-, nginx- und `/etc/phoniebox`-Dateien) und keine fremden Dienste auf Port 80/443. Danach: Pakete, Swap (2 GiB, falls RAM und Swap zusammen unter 3 GiB liegen), librespot-Build als `phoniebox-build`, Programm nach `/opt/phoniebox`, Benutzer und Gruppen, udev-Regel, Audio und Hostname, TLS-Zertifikat, nginx und systemd, Neustart nach 12 Sekunden.

| Pfad | Inhalt |
| --- | --- |
| `/opt/phoniebox` | Programm, Eigentümer root |
| `/var/lib/phoniebox` | Daten, siehe oben |
| `/etc/phoniebox` | `tls.key` (0600), `tls.crt` |
| `/usr/local/bin/phoniebox-librespot` | gebautes librespot |
| `/var/cache/phoniebox-build` | Rust-Toolchain und Build-Cache (Ziel und Quellen werden nach Erfolg gelöscht) |
| `/var/backups/phoniebox/<zeitstempel>/` | Sicherungen des Updaters |
| `/etc/nginx/sites-available/phoniebox`, `/etc/systemd/system/phoniebox.service`, `/etc/udev/rules.d/99-phoniebox-nfc.rules` | Konfiguration |

**Ausgabeprotokoll für den Desktop-Installer.** Der Installer wertet feste Zeilen aus. Diese Zeichenketten daher nicht ändern:

- `PHONIEBOX_STAGE:<prozent>:<text>` (Fortschritt)
- `PHONIEBOX_REBOOT_REQUIRED` (Neustart läuft)
- `PHONIEBOX_SUDO_PASSWORD_INPUT` (Eingabeaufforderung von `sudo -S -p`, mit der der Installer `install.sh` startet; kommt von sudo, nicht aus dem Projekt)
- `PHONIEBOX_UPDATE_OK:<version>` (Ausgabe von `update.py` bei Erfolg)

Der Desktop-Installer ist ein eigenes Projekt (Quellpaket `Phoniebox-Installer-Quellcode`: `installer.py` mit Tk-Oberfläche, `remote.py` mit der SSH-Logik über paramiko), das mit PyInstaller zu einem Linux-x86_64-Programm gebaut wird. Er verlässt sich auf Folgendes:

- Er startet `install.sh` ohne Argumente über `sudo -S -p PHONIEBOX_SUDO_PASSWORD_INPUT`.
- Nach dem Neustart ruft er `http://127.0.0.1:8888/login` auf dem Pi ab und erwartet **HTTP 200 nach Weiterleitung**.
- Er liest `/opt/phoniebox/VERSION` und prüft den Reader-Pfad `/dev/input/by-id/usb-413d_2107-event-kbd`.
- Er bringt ein Paket `phoniebox.tar.gz` mit (ab Installer 1.2.0 in Version 1.5.3), berechnet dessen Prüfsumme erst zur Laufzeit und liest die Version aus der `release.json` des Pakets.

Installer bis 1.1.0 haben zusätzlich ein Webpasswort über `PHONIEBOX_WEB_PASSWORD_INPUT` gesendet. Das gibt es seit `install.sh` 1.5.3 nicht mehr; ein alter Installer bringt aber sein eigenes, altes Paket mit und ist davon nicht betroffen.

## Update-Paket und Updater

Ein Update-Paket ist ein `tar.gz` mit dem obersten Verzeichnis `phoniebox/`, das `release.json` enthält:

```json
{
  "format": 1,
  "version": "1.6.0",
  "database_schema": 1,
  "packages": ["python3-flask", "mpv"],
  "files": ["app.py", "run.py", "storage.py", "VERSION"],
  "migrations": []
}
```

- `files` nennt **alle** Dateien, die der Updater übernimmt. Mindestens `app.py`, `run.py`, `storage.py` und `VERSION` müssen enthalten sein. Nicht aufgeführte Dateien (README, Tests, `deploy/`, Skripte) kommen nicht auf den Pi.
- `packages` sind Debian-Pakete, die der Updater bei Bedarf per `apt-get` nachinstalliert.
- `migrations` sind Einträge der Form `{"to": <schema>, "file": "<sql-datei>"}`; die Datei muss auch in `files` stehen. Für jede Schemastufe zwischen installiertem Stand und `database_schema` muss genau eine Migration existieren.
- Die Version in `VERSION` und `release.json` muss übereinstimmen und **größer** als die installierte sein.

Ablauf von `Updater.apply`: Paket entpacken und prüfen (Pfade, Größe, Dateitypen, Python-Syntax) → Version und Schema prüfen → Speicherplatz prüfen → Abhängigkeiten installieren → Dienst stoppen → Vollsicherung von Programm und Daten nach `/var/backups/phoniebox` → Programmverzeichnis austauschen → Migrationen ausführen → Dienst starten → `/health` bis zu 20 Sekunden lang auf die neue Version prüfen. Schlägt ein Schritt nach dem Stoppen fehl, werden Programm und Daten aus der Sicherung zurückgespielt. Ein Lock (`/run/lock/phoniebox-update.lock`) verhindert parallele Updates. Bei Stromausfall gibt es keine automatische Wiederherstellung.

## Konventionen für die Entwicklung

- Formatierung mit `black -S -l 120` (Anführungszeichen bleiben wie sie sind). Sprache der Texte in der Oberfläche und in Fehlermeldungen ist Deutsch, Code und Kommentare größtenteils Englisch.
- Fehler, die der Benutzer sehen soll, als `Problem(...)` auslösen; `app.py` macht daraus Hinweis oder JSON-Fehler.
- Neue Python-Dateien, Vorlagen oder statische Dateien, die auf dem Pi laufen sollen, in `release.json` unter `files` eintragen.
- Änderungen an Dateien, die per Update ausgeliefert werden, brauchen eine höhere Version (`VERSION` und `release.json`). Änderungen nur an Dokumentation nicht.
- Secrets nie in Prozessargumente, Journale oder Templates. `Store.secret` liefert Klartext nur für den Programmgebrauch.
- `AlarmRadio.lock` wird vor `Hardware.audio_lock` genommen (siehe `AlarmRadio.local`). Diese Reihenfolge beibehalten, um Deadlocks zu vermeiden.

## Altlasten und offene Punkte

- `/login` und `/logout` sind nur noch Weiterleitungen. `/login` **nicht entfernen**: `diagnose.sh` und alle Desktop-Installer bis einschließlich 1.2.0 prüfen die Weboberfläche darüber. Der Zweig für HTTP 401 in `static/app.js` wird nicht mehr erreicht.
- Die Beschriftungen der Aktionen („Stop / Pause“, „Wiedergabe fortsetzen“ …) stehen in `app.py` (zweimal, leicht abweichend: „Fortsetzen“ und „Wiedergabe fortsetzen“), in `templates/index.html` und in `static/app.js`.
- Für 1.5.1 fehlen Release Notes.
- `Spotify.command(..., persist=False)` ändert die Lautstärke, ohne sie als Startlautstärke zu speichern (Wecker).
- `deploy/bluealsa-override.conf` richtet nur `install.sh` ein. Der Updater ändert keine systemd-Dateien; bestehende Pis bekommen den Override durch ein App-Update nicht.
- Die Tests des Desktop-Installers gehören zu dessen Quellpaket. Erstinstallation und hörbare Ausgabe sind weiterhin nicht auf echter Hardware getestet.
