# NFC Phoniebox

Musikbox für den Raspberry Pi: NFC-Karten starten Spotify-Inhalte, eine Weboberfläche verwaltet Karten, Radio, Wecker und Einstellungen. Die Ausgabe läuft über den analogen 3,5-mm-Klinkenanschluss.

- Version: siehe `VERSION` (aktuell 1.20.0)
- Änderungen: [CHANGELOG.md](CHANGELOG.md)
- Technischer Aufbau, Datenmodell, Update-Paket: [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md)

## Funktionen

- **Spotify**: Die Box erscheint als Spotify-Connect-Gerät (librespot, Standardname „NFC Phoniebox“) und wird über die Spotify-Web-API gesteuert. Unterstützt werden Playlists, Alben, einzelne Titel und einzelne Podcastfolgen. Spotify Premium ist erforderlich.
- **NFC-Karten**: Ein USB-Reader (M301 V4, USB-ID `413d:2107`) meldet sich als Tastatur. Eine Karte startet Musik oder löst eine Steueraktion aus (Pause, Fortsetzen, nächster/vorheriger Titel, Lauter, Leiser, feste Lautstärke).
- **Radio und Wecktöne**: zehn Radiosender (WDR, 1LIVE, Deutschlandfunk, BBC international) und drei erzeugte Töne.
- **Wecker**: beliebig viele wöchentlich konfigurierbare Wecker mit Ton, Radio oder Spotify-Inhalt, Zeitzone Europe/Berlin. Der Ausgang ist wählbar: Klinke (Standard) oder Bluetooth mit automatischem Wechsel auf die Klinke.
- **Bluetooth**: Lautsprecher direkt in der Weboberfläche suchen, koppeln, verbinden und als Audioausgang übernehmen – ohne SSH.
- **Weboberfläche**: `https://phoniebox.local`, ohne Anmeldung.
- **Android-App** (`android/`): die Weboberfläche als App, mit Benachrichtigungen bei Problemen der Box, etwa „Bluetooth nicht verbunden“. Siehe [android/README.md](android/README.md).
- **Updates** mit automatischer Sicherung und Rücksetzung bei fehlgeschlagenem Start.

## Voraussetzungen

- Raspberry Pi **3B oder 3B+** mit Raspberry Pi OS Lite **64 Bit, Debian Trixie**. `install.sh` bricht auf anderer Hardware oder anderem System ab.
- Benutzer, Netzwerk und SSH bereits im Raspberry Pi Imager einrichten. Empfohlen ist eine SD-Karte mit 32 GB; mindestens 8 GiB müssen frei sein (Pakete, Rust-Build, temporärer Swap).
- Internetzugang auf dem Pi.
- USB-NFC-Reader M301 V4 und ein Lautsprecher am Klinkenanschluss.
- Ein Spotify-Premium-Konto und eine eigene App im [Spotify Developer Dashboard](https://developer.spotify.com/dashboard).

## Installation

Es handelt sich um eine **Erstinstallation**. Eine vorhandene Installation oder Teilinstallation wird nicht überschrieben; `install.sh` bricht dann ab.

### Mit dem Desktop-Installer

Der grafische Linux-Installer gehört nicht zu diesem Archiv und enthält seit 2.8.14 auch kein App-Paket mehr. Er richtet den Pi über SSH ein; das App-Paket (`phoniebox-x.y.z.tar.gz` mit Oberordner `phoniebox/`) wählt man darin aus. Empfohlen ist Installer 2.8.17 oder neuer. Ältere Installer verlangen noch ein Webpasswort und passen nicht zu `install.sh` ab 1.5.3.

1. Installer starten, Hostname oder IP, Benutzer und Passwort des Pi eingeben, Verbindung prüfen und den SSH-Geräteschlüssel bestätigen.
2. **Phoniebox installieren** drücken. Der Build von librespot dauert auf einem Pi 3B+ mehrere Stunden. Rechner und Pi währenddessen eingeschaltet lassen.
3. Der Pi startet danach automatisch neu. Der Installer prüft anschließend Dienste, HTTP und das Vorhandensein des analogen Audiogeräts. Ob der Ton tatsächlich hörbar ist, kann er nicht beurteilen.
4. **Weboberfläche / Spotify-Anmeldung öffnen** drücken. Der SSH-Tunnel wird automatisch geöffnet.

### Direkt auf dem Pi

```bash
sudo bash install.sh
```

Das Skript stellt keine Fragen und nimmt keine Argumente entgegen. Die Weboberfläche hat keine Anmeldung (siehe „Sicherheit“).

### Was die Installation einrichtet

- Systempakete, Rust 1.90.0 in einem eigenen Build-Benutzer und librespot 0.8.0 (mit `native-tls alsa-backend with-libmdns`)
- Benutzer `phoniebox` ohne sudo-Rechte, Programm in `/opt/phoniebox`, Daten in `/var/lib/phoniebox`
- SQLite-Datenbank, HTTPS mit lokal erzeugtem Zertifikat (nginx), Hostname `phoniebox`, Autostart per systemd
- Zugriffsrecht auf den NFC-Reader (udev-Regel `99-phoniebox-nfc.rules` für den by-id-Link des Readers)
- `dtparam=audio=on` in `/boot/firmware/config.txt`. Die Originale von `config.txt` und `/etc/hosts` bleiben als `.before-phoniebox` erhalten.

Ein eventuell vorhandenes `librespot.service` wird deaktiviert. Die automatischen Paketupdates von Raspberry Pi OS werden nur während der Installation angehalten und danach wieder aktiviert. Bei einem Fehler kann eine Teilinstallation zurückbleiben; der Installer meldet dann keinen Erfolg.

### HTTPS-Zertifikat

Das Zertifikat ist selbst erzeugt (RSA 3072, zehn Jahre gültig). Vor der Browser-Ausnahme den SHA-256-Fingerabdruck in den Zertifikatsdetails mit dem vom Installer ausgegebenen Wert vergleichen. Alternativ bleibt der SSH-Tunnel nutzbar.

## Spotify einmal verbinden

1. Im Developer Dashboard eine App anlegen, das gewünschte Premium-Konto für die App zulassen und diese Redirect URI eintragen:

   ```text
   http://127.0.0.1:8888/callback
   ```

2. Den Anmeldetunnel öffnen (Desktop-Installer) oder von einem Rechner aus selbst: `ssh -L 8888:127.0.0.1:8888 <benutzer>@phoniebox.local`. Danach `http://127.0.0.1:8888` im Browser öffnen. Die Spotify-Anmeldung funktioniert **nur** über diese Adresse.
3. Unter „Spotify“ Client-ID und Client Secret speichern und **Spotify verbinden** drücken. Die Freigabe erfolgt im Browser. Das Tunnelfenster dabei geöffnet lassen.
4. In der Spotify-App einmal „NFC Phoniebox“ (beziehungsweise den eingestellten Gerätenamen) als Wiedergabegerät auswählen. Die Web-API-Anmeldung und die Spotify-Connect-Anmeldung von librespot sind getrennt; librespot speichert seine Anmeldung in einem privaten Cache.

Danach kann der Tunnel geschlossen werden. Im Alltag genügt `https://phoniebox.local`.

## Bedienung

### NFC-Karten

Unter **NFC-Karten** eine Karte auflegen: ID und vorhandene Zuordnung erscheinen automatisch im Formular. Name und Aktion wählen, bei Musik den Spotify-Link, bei Radio den Sender eintragen, speichern.

- Der Spotify-Link darf eine `open.spotify.com`-Adresse oder eine `spotify:`-URI sein (Playlist, Album, Titel, Folge). Alternativ direkt im Formular „Spotify durchsuchen“ nutzen: Typ (Titel, Album, Playlist oder Alles) wählen, Suchbegriff eingeben, **Übernehmen** trägt Link (und Name, falls noch leer) automatisch ein. Die Suche braucht eine verbundene Spotify-Web-API-Anmeldung.
- **+ Neue Karte** führt in drei Schritten durch das Anlegen einer Musik-Karte: Karte auflegen (still, 60 Sekunden Zeit), in Spotify nach Album, Playlist oder Titel suchen und auswählen, Name prüfen und speichern. Ist die Karte schon belegt, sagt der Dialog womit; Speichern ersetzt die alte Zuordnung.
- Der Reader M301 kann Karten nur lesen, nicht beschreiben. Gespeichert wird deshalb die Kartennummer (UID) zusammen mit der Musik in der Datenbank der Box; die Karte selbst bleibt unverändert. Eine Karte funktioniert also nur an der Phoniebox, an der sie angelernt wurde (oder nach Wiederherstellung einer Sicherung).
- **Karte ohne Wiedergabe erfassen** schaltet für 60 Sekunden in den stillen Anlernmodus: aufgelegte Karten starten dann keine Musik.
- **Radiosender-Karte:** Aktion „Radiosender starten“ und einen der Sender (WDR, 1LIVE, Deutschlandfunk, BBC international) wählen. Beim Auflegen wird Spotify getrennt und der Sender spielt über den Hauptausgang. Der Name ist optional, sonst wird der Sendername übernommen. Läuft schon etwas Lokales (Radio oder Ton), bleibt dessen Lautstärke, sonst gilt die Startlautstärke aus den Einstellungen. Dieselbe Karte erneut beendet den Sender; bei „Musik erneut starten“ startet er neu. Eine Musik-Karte danach startet ihre Musik ganz normal.
- Steuerkarten und Radiosender-Karten brauchen keinen Namen. Bei Lautstärkeaktionen gibt es einen Schritt beziehungsweise Zielwert in Prozentpunkten.
- **Dieselbe Musik-Karte erneut auflegen**: Stop/Pause (Standard), Pause/Fortsetzen im Wechsel oder Musik neu starten. Für Radiosender bedeutet Stop/Pause wie Pause/Fortsetzen im Wechsel: der Sender wird beendet und startet beim nächsten Auflegen wieder live.
- Der Reader erkennt keine Kartenentfernung. Dieselbe ID innerhalb von 3 Sekunden wird als ein Auflegen gewertet: Karte entfernen, mindestens 3 Sekunden warten, erneut auflegen.
- Die zuletzt gespielte Musik-Karte wird nur im laufenden Dienst gemerkt. Nach einem Neustart startet sie beim ersten Auflegen wieder neu.
- Als Beispiel für eine Testkarte nennt die frühere README die ID `1549562714`.

### Radio und Wecker

- Unter **Radio und Wecktöne** lässt sich ein Sender oder Ton direkt starten und stoppen. Während lokaler Wiedergabe wird librespot beendet und danach automatisch neu bereitgestellt.
- Jeder **Wecker** hat Uhrzeit, Wochentage, Quelle (Ton, Radio, Spotify-Link), Lautstärke und Dauer (1 bis 60 Minuten). Die Liste zeigt alle Wecker; jeder lässt sich bearbeiten, ein- und ausschalten, testen und löschen. Klingeln zwei Wecker in derselben Minute, läuft nur der zuerst angelegte.
- Verpasste Wecker werden nicht nachgeholt, der Pi muss zur Weckzeit laufen und eine richtige Uhrzeit haben.
- Fällt die gewählte Quelle aus, läuft der eingestellte Ersatzton.
- **Ausgang des Weckers** (nur für Ton und Radio): **Klinke** ist voreingestellt und hängt an keiner Funkverbindung. Bei **Bluetooth** gilt ohne weitere Angabe der aktuelle Bluetooth-Hauptausgang; alternativ den ALSA-Namen eintragen, zum Beispiel `bluealsa:DEV=AA:BB:CC:DD:EE:FF,PROFILE=a2dp`. Ist er zur Weckzeit nicht erreichbar, läuft derselbe Wecker sofort über die Klinke. Die Statuszeile zeigt, worüber er läuft („Wecker läuft (Klinke, da Bluetooth nicht erreichbar)“). Der Wecker richtet sich nach diesem Ausgang, egal was in den Einstellungen als Hauptausgang steht.
- **Spotify als Weckquelle** spielt immer über den Hauptausgang aus den Einstellungen und folgt dieser Auswahl nicht. Wer bei Bluetooth als Hauptausgang einen verlässlichen Wecker will, nimmt Ton oder Radio.
- Der Bluetooth-Lautsprecher muss zur Weckzeit verbunden sein. Die Box verbindet ihn nicht selbst. Hängt er im Standby oder ist mit einem anderen Gerät verbunden, greift der Wechsel auf die Klinke; eine Weckerausgabe über eine Klinke ohne angeschlossenen Lautsprecher bleibt aber stumm.
- Eine Stop-Karte pausiert auch lokale Wiedergabe von Radio oder Wecker. Die automatische Abschaltung nach der eingestellten Dauer entfällt dann.

### Audio

Beim Dienststart erkennt `configure_audio.py` einmalig den Klinkenausgang und speichert einen stabilen Namen wie `plughw:Headphones,0` statt einer wechselnden Kartennummer. Danach gelten die Werte aus der Weboberfläche. Der ALSA-Regler `PCM` wird bei jedem Playerstart auf 100 % gesetzt; die Hörlautstärke regelt Spotify beziehungsweise mpv. Startwert ist 35 %. Das ist keine harte Lautstärkebegrenzung.

Die Weboberfläche akzeptiert als Audioausgang `plughw:<Karte>,<Nr>`, `hw:<Karte>,<Nr>`, `default` oder einen Bluetooth-Lautsprecher über bluealsa (`bluealsa` oder `bluealsa:DEV=<MAC>,PROFILE=a2dp`). Dasselbe Namensschema gilt für den Bluetooth-Lautsprecher des Weckers. Den Namen der Klinke merkt sich die Box zusätzlich (`analog_audio`), sodass der Wecker sie auch dann findet, wenn der Hauptausgang Bluetooth ist.

Seit 1.10.0 prüft `hardware.py` vor jedem Start von librespot, ob der eingestellte Ausgang tatsächlich erreichbar ist (`configure_audio.device_reachable()`). Ist er es nicht, startet librespot gar nicht erst und die Weboberfläche zeigt eine klare Meldung im Player-Status, statt dass das Gerät in Spotify kurz auftaucht und wieder verschwindet.

### Bluetooth

Im Bereich **Bluetooth** der Weboberfläche lassen sich Lautsprecher suchen (10 Sekunden), koppeln, verbinden, trennen und entfernen – ohne SSH. „Als Audioausgang verwenden“ trägt das Gerät als `bluealsa:DEV=<MAC>,PROFILE=a2dp` in die Einstellungen ein und startet den Player neu. Die Kopplung läuft über den eingebauten Agent von `bluetoothctl`, das heißt „Just Works“-Kopplung (typisch bei Lautsprechern ohne eigenes Display) klappt automatisch; ein Gerät, das eine PIN-Bestätigung am Gerät selbst verlangt, kann hier nicht bestätigt werden und läuft in eine Zeitüberschreitung. Vorausgesetzt ist weiterhin, dass `bluealsa` grundsätzlich eingerichtet ist – dieser Bereich kümmert sich nur um Kopplung/Verbindung, nicht um die Audioweiterleitung selbst.

## Updates

Im Desktop-Installer verbinden, unter Updates **Von GitHub laden** wählen (ab Installer 2.8.18) oder ein lokales `phoniebox-x.y.z.tar.gz` auswählen, dann installieren. Der Download holt das neueste Release aus diesem Repository und prüft die mitgelieferte SHA256-Prüfsumme. Lokal nur vertrauenswürdige Pakete verwenden.

Der Updater sichert App und Daten unter `/var/backups/phoniebox`, installiert fehlende Paketabhängigkeiten, führt Datenbankmigrationen aus und stellt bei einem fehlgeschlagenen Starttest den vorherigen Stand wieder her. Karten, Einstellungen und Secrets bleiben erhalten. Kein librespot-Build, keine Änderung an nginx, systemd oder Boot-Einstellungen. Stromausfälle während des Updates sind nicht abgesichert. Details stehen in [docs/ARCHITEKTUR.md](docs/ARCHITEKTUR.md#update-paket-und-updater).

Beim bekannten Port-80-Konflikt zuerst im Installer „lighttpd ersetzen & abschließen“ wählen (`resume.sh`). Das deaktiviert die bisherige lighttpd-Weboberfläche.

## Wartung und Diagnose

```bash
sudo journalctl -u phoniebox -n 60 --no-pager
systemctl status phoniebox nginx --no-pager
curl -s http://127.0.0.1:8888/health      # {"ok": true, "version": "…"}
sudo bash diagnose.sh                     # nur lesend, gibt keine Zugangsdaten aus
```

`diagnose.sh` und `resume.sh` liegen nach der Erstinstallation in `/opt/phoniebox`, nach einem Update aber nicht mehr, weil der Updater nur die in `release.json` genannten Dateien behält. Der Desktop-Installer bringt beide Skripte mit („Diagnose anzeigen“); sonst aus diesem Archiv auf den Pi kopieren.

**Sicherung**: Dienst stoppen, danach `phoniebox.sqlite3`, `secret.key` und das Verzeichnis `librespot/` aus `/var/lib/phoniebox` gemeinsam sichern, Dienst wieder starten. Ohne `secret.key` startet der Dienst mit einer vorhandenen Datenbank absichtlich nicht. Die Sicherung enthält Zugangsdaten und gehört an einen geschützten Ort.

## Sicherheit

- **Es gibt keine Anmeldung.** Jedes Gerät im selben Netz, das `https://phoniebox.local` erreicht, kann Karten und Einstellungen ändern und die Wiedergabe steuern. Keine Router-Portfreigabe ins Internet einrichten.
- Erhalten geblieben sind: CSRF-Prüfung, Host-Prüfung, HTTPS, Sicherheits-Header mit Content-Security-Policy, verschlüsselte Ablage von Client Secret und Tokens (Fernet, Schlüsseldatei mit Rechten 0600).
- Die Spotify-Anmeldung ist nur über den SSH-Tunnel möglich. OAuth nutzt Authorization Code mit PKCE (S256) und einmaligem State.
- Die Anwendung läuft als eigener Benutzer ohne sudo, der Dienst ist per systemd eingeschränkt (`ProtectSystem=strict`, `NoNewPrivileges` und weitere). nginx schreibt kein Zugriffsprotokoll.
- Eine komplette Kopie der SD-Karte enthält auch den Schlüssel zu den Secrets; das ersetzt keine Datenträgerverschlüsselung.

## Entwicklung

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python3 -m pytest -q tests          # 70 Tests
```

Ohne Pi lässt sich die Weboberfläche lokal starten:

```bash
PHONIEBOX_DATA=/tmp/phoniebox-dev python3 run.py
```

Sie ist dann unter `http://127.0.0.1:8888` erreichbar. Reader und Player melden erwartungsgemäß Fehler.

Die Tests simulieren Spotify, SSH- und Neustartbedingungen. Nicht Teil dieses Archivs ist der Desktop-Installer samt seinen Tests. Die vollständige Erstinstallation und die hörbare Ausgabe sind bisher nicht auf echter Hardware als getestet ausgewiesen.

Wer Dateien hinzufügt oder ändert, die per Update ausgeliefert werden, muss `VERSION` und `release.json` erhöhen und neue Dateien in `release.json` eintragen, sonst lehnt der Updater das Paket ab beziehungsweise installiert sie nicht. Einzelheiten stehen in der Architekturdokumentation.

### Release veröffentlichen

Releases entstehen automatisch. Steht in `VERSION` auf `main` eine Version, für die es noch kein Release gibt, lässt die Action `.github/workflows/release.yml` die Tests laufen, baut mit `scripts/build-package.sh` das Paket `phoniebox-X.Y.Z.tar.gz` (alle Dateien unter `phoniebox/`, wie der Updater es verlangt) samt `.sha256` und legt das Release `vX.Y.Z` mit dem passenden CHANGELOG-Abschnitt an. Für eine neue Version genügt es also, `VERSION`, `release.json` und `CHANGELOG.md` zu erhöhen und auf `main` zu mergen. Passen `VERSION` und `release.json` nicht zusammen oder fehlt der CHANGELOG-Abschnitt, bricht die Action ab. Ein von Hand gepushter Tag `vX.Y.Z` funktioniert ebenso. Die automatischen Quellarchive von GitHub sind keine gültigen App-Pakete, weil ihr Ordner anders heißt.

### Android-App

Die APK baut die Action `.github/workflows/android.yml` bei jedem Pull Request mit Änderungen unter `android/` (als Artefakt am Workflow-Lauf) und legt auf `main` ein Release `android-vX.Y.Z` an, sobald es für die Version in `android/VERSION` noch keins gibt. Dieses Release wird nie als „latest“ markiert, damit der Desktop-Installer weiter das App-Paket findet. Das Verzeichnis `android/` gehört nicht zum App-Paket für den Pi.

## Bekannte Einschränkungen

- Der Hostname `phoniebox.local` ist fest eingetragen (nginx, Host-Prüfung, Zertifikat). Der einstellbare Gerätename betrifft nur den Namen in Spotify.
- Feste Zeitzone Europe/Berlin für alle Wecker.
- Bluetooth-Lautsprecher können über den Bereich „Bluetooth“ in der Weboberfläche gesucht, gekoppelt, verbunden und als Audioausgang übernommen werden (`bluetoothctl` über `bluetooth.py`). Vorausgesetzt ist weiterhin, dass `bluealsa` grundsätzlich eingerichtet ist (die eigentliche Audioweiterleitung über BlueALSA gehört nicht zum Funktionsumfang dieses Bereichs). Geräte, die statt „Just Works“ eine PIN-Bestätigung am eigenen Display verlangen, können hier nicht bestätigt werden.
- Die Verfügbarkeit einzelner Radiostreams kann sich ändern. Spotify- und librespot-Kompatibilität kann sich serverseitig ändern.
- Spotify-Recherche der früheren README: 6. September 2026 ([Quota modes](https://developer.spotify.com/documentation/web-api/concepts/quota-modes), [Änderungen Juli 2026](https://developer.spotify.com/documentation/web-api/references/changes/july-2026), [Redirect-Vorgaben](https://developer.spotify.com/documentation/web-api/concepts/redirect_uri), [Player-Endpunkte](https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback)). Der Build folgt den [librespot-0.8.0-Features](https://github.com/librespot-org/librespot/blob/v0.8.0/Cargo.toml). Zu `dtparam=audio=on` siehe die [config.txt-Dokumentation](https://www.raspberrypi.com/documentation/computers/config_txt.html).
