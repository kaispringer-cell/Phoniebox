# 1.18.1

- Wiedergabe über einen nicht verbundenen Bluetooth-Lautsprecher meldet wieder „Bluetooth-Lautsprecher ist noch nicht verbunden“ bzw. „bewusst getrennt“. Die Prüfung lag seit 1.10.0 hinter der Weitergabe an Radio/Wecker und lief nie.
- Ein nicht erreichbarer Audioausgang ersetzt die irreführende Spotify-Meldung „nicht eindeutig erreichbar“ auch bei Karten und Tasten.
- Die Lautstärke eines Spotify-Weckers wird nicht mehr als Startlautstärke gespeichert.
- Wird ein Wecker am selben Tag nach dem Klingeln auf eine spätere Zeit geändert, klingelt er erneut. `alarm_last_dates` speichert dafür Datum und Weckzeit; ein reines Datum aus 1.18.0 sperrt weiterhin den ganzen Tag.
- mpv-Fehlerausgabe geht in eine temporäre Datei statt in eine ungelesene Pipe, damit lange Streams nicht hängen bleiben.
- `install.sh` gibt die automatischen Paket- und Sicherheitsupdates am Ende (auch bei Abbruch) wieder frei. Bisher blieben sie dauerhaft maskiert. Bestehende Pis erhalten die Korrektur über Installer 2.8.17 beim nächsten Update.
- `install.sh` kopiert Tests und `__pycache__` nicht mehr nach `/opt/phoniebox`.
- README und Architektur auf mehrere Wecker und den aktuellen Stand gebracht. 8 neue Tests. Installer 2.8.17 verwenden.

# 1.18.0

- „der wecker soll noch bestehende wecker anzeigen und änderbar machen“ – Mehrere Wecker statt genau einem. Der Wecker-Bereich zeigt alle gespeicherten Wecker als Liste (nach Uhrzeit sortiert, mit Tagen, Quelle, Ausgang, Lautstärke, Dauer und Status Aktiv/Aus). Pro Wecker: Bearbeiten (öffnet das Formular mit seinen Werten), Ein-/Ausschalten, Testen, Löschen (mit Rückfrage). Darunter das Formular für einen neuen Wecker bzw. den gerade bearbeiteten.
- Jeder Wecker klingelt an seinen eigenen Tagen höchstens einmal pro Tag. Klingeln zwei Wecker in derselben Minute, läuft nur einer (der zuerst angelegte).
- Der bisherige einzelne Wecker wird beim ersten Start automatisch als erster Eintrag übernommen, samt dem Datum, an dem er zuletzt geklingelt hat (kein doppeltes Klingeln am Update-Tag). Die alte Einstellung bleibt unverändert erhalten, damit eine ältere App-Version ihren Wecker weiterhin findet. Keine Datenbank-Migration nötig (Wecker liegen weiter als Einstellungswert; `database_schema` unverändert).
- „Gespeicherten Wecker jetzt testen“ ersetzt durch „Testen“ am jeweiligen Wecker.
- Tests in `tests/test_alarm_cards.py` erweitert. Installer 2.8.15 weiterverwenden. Noch nicht auf echter Hardware geprüft.

# 1.17.7

- „Der Wecker funktioniert nicht. Nach Erstellung wird er nicht gespeichert.“ – Zwei Ursachen, die bei einem Bluetooth-Lautsprecher als einzigem Lautsprecher zusammenkamen:
  - Ausgang „Bluetooth“ verlangte zusätzlich den ALSA-Namen (`bluealsa:DEV=…`) als Freitext. Blieb das Feld leer, wurde das Speichern abgelehnt; die Meldung stand nur ganz oben auf der Seite, und das Formular sprang auf die alten Werte zurück – es sah aus, als wäre nichts gespeichert worden. Jetzt gilt: leeres Feld = aktueller Bluetooth-Hauptausgang. Ein noch nie gespeicherter Wecker ist auf Bluetooth und diesen Lautsprecher vorbelegt, wenn der Hauptausgang Bluetooth ist (vorher stand er auf Klinke).
  - Wird ein Wecker abgelehnt, bleiben die Eingaben erhalten, und der Grund steht direkt im Wecker-Bereich („Nicht gespeichert: …“).
  - „Wecker aktiv“ war bei einem neuen Wecker nicht angehakt; wer nur Uhrzeit und Tage einstellte, speicherte einen ausgeschalteten Wecker mit der Meldung „Wecker gespeichert“. Neuer Wecker ist jetzt im Formular vorab angehakt (klingeln kann erst ein gespeicherter), und die Meldung sagt ausdrücklich „gespeichert, aber nicht aktiv“, wenn der Haken fehlt.
- „Und die NFC Karten sollen nach Typ sortiert werden.“ – Kartenliste in Gruppen Musik, Radio, Steuerung (mit Anzahl), innerhalb der Gruppe alphabetisch; Steuerkarten in der Reihenfolge der Aktionen im Kartenformular.
- Neue Tests `tests/test_alarm_cards.py`. Installer 2.8.15 weiterverwenden. Noch nicht auf echter Hardware geprüft.

# 1.17.6

- „na, das hatte ich auch vermutet. ohne das handy funktioniert es wieder.“ – Korrektur zu 1.17.4 und 1.17.5: Der Abbruch der Spotify-Wiedergabe nach 2-3 Sekunden über den Marshall Emberton lag nicht am Pi. Das Handy war gleichzeitig mit dem Emberton verbunden (Multipoint). Beim Wechsel der Audioquelle schickte der Lautsprecher ein Pause-Signal ans Handy, dessen Spotify-App damit die Phoniebox pausierte (die App zeigte „pausiert“; librespots Log zeigte die Pause, danach `Drain timed out: Possible Bluetooth transport failure`, weil der Lautsprecher schon wieder aufs Handy umgeschaltet hatte). Ohne das Handy am Lautsprecher läuft es einwandfrei. Vom Pi aus lässt sich das nicht verhindern; Abhilfe ist, das Handy vom Lautsprecher zu trennen oder Multipoint am Lautsprecher abzuschalten.
- `--sbc-quality=low` aus 1.17.5 wieder entfernt: Es half nicht und verschlechterte nur den Klang an allen Lautsprechern.
- `--keep-alive=5` aus 1.17.4 bleibt: harmlos und von bluealsa selbst empfohlen, hält den Transport bei Pausen und Titelwechseln kurz offen. Behoben hat es den Vorfall nicht.
- Installer 2.8.15 weiterverwenden.

# 1.17.5

- „das läuft“ – 1.17.4s `--keep-alive=5` reichte für den Marshall Emberton allein nicht aus: live zeigte `journalctl -u bluealsa` wiederholt `PCM drop`/`Closing PCM` nur ein bis wenige Sekunden nach jedem `PCM resume` - librespot schloss seine ALSA-Verbindung nach einem für uns unsichtbaren (unterdrückten) Fehler selbst wiederholt, vermutlich ein Puffer-Unterlauf durch die ausgehandelte SBC-Bitrate (bit-pool=53, ≈328 kbps). `--sbc-quality=low` im bluealsa-Override senkt Bitpool/Datenrate und behebt es laut Live-Test zuverlässig.
- `deploy/bluealsa-override.conf` entsprechend ergänzt; `install.sh` unverändert (derselbe Override-Mechanismus wie in 1.17.4).
- Installer 2.8.15 weiterverwenden. Nachtrag: Die Diagnose dieses Eintrags war falsch, siehe 1.17.6.

# 1.17.4

- „Problem gelöst. Das sollte dann in eine neue phoniebox“ – Spotify-Wiedergabe brach über bestimmte Bluetooth-Lautsprecher (beobachtet mit einem Marshall Emberton, nicht mit einem Marshall Kilburn II) reproduzierbar nach 2-3 Sekunden ab, während Radio über denselben Lautsprecher nur kurz stotterte statt ganz abzureißen. Ursache: `bluealsa` läuft ohne `--keep-alive` und baut die A2DP-Verbindung bei jeder kurzen Pause/jedem winzigen Puffer-Unterlauf komplett neu auf, statt sie kurz offenzuhalten – radios großzügigere Pufferung überstand das, librespots knappere nicht.
- `install.sh` setzt jetzt automatisch einen systemd-Override (`/etc/systemd/system/bluealsa.service.d/override.conf`) mit `--keep-alive=5`, wie von der bluealsa-Unit selbst als Anpassung vorgeschlagen (siehe deren eigener auskommentierter Beispielaufruf). Gilt für Neuinstallationen und Updates gleichermaßen; bestehende `bluealsa`-Konfiguration wird dabei ersetzt, der Dienst danach neu gestartet.
- Installer 2.8.15 weiterverwenden. Nachtrag: Die Diagnose dieses Eintrags war falsch, siehe 1.17.6.

# 1.17.3

- `install.sh` lädt vor dem Bau von librespot zuerst ein fertig gebautes Binary (arm64, ALSA-Backend, Prüfsumme) aus einem eigenen GitHub-Release (`kaispringer-cell/librespot-build`, gebaut auf einem nativen arm64-Runner in Minuten statt Stunden auf dem Pi). Jeder Fehlschlag dabei (kein Netz, Release nicht erreichbar, falsche Prüfsumme, kein ALSA-Backend) führt automatisch zum bisherigen, unveränderten Bau auf dem Pi selbst zurück – keine manuelle Entscheidung, im schlechtesten Fall keine Verschlechterung.
- Die ALSA-Backend-Prüfung läuft jetzt über `ldd | grep libasound` statt über die Ausgabe von `librespot --backend '?'`: Deren Zeilen werden über `println!` auf stdout geschrieben, der Prozess beendet sich direkt danach mit `exit()` – bei einer Pipe (wie in `install.sh`s Kommandosubstitution) unzuverlässig, in der Praxis kam nur die separate Versionszeile (über den log-Mechanismus auf stderr) an, nie die eigentliche Backend-Liste. Betrifft beide Pfade, den heruntergeladenen wie den selbst gebauten.
- Installer 2.8.15 weiterverwenden. Noch nicht auf echter Hardware geprüft; der GitHub-Actions-Workflow für das Release muss einmalig manuell ausgelöst werden, sonst nimmt jede Installation automatisch weiterhin den bisherigen Bauweg.

# 1.17.2

- Kopplung mit lebendem interaktivem NoInputNoOutput-Agenten; BlueZ 5.82 registriert diesen beim bisherigen Einzelaufruf nicht automatisch.
- Erfolg erst bei Bonded: yes. Bereits dauerhaft gekoppelte Geräte bleiben unverändert.
- Bekannte Geräte ohne Bindung bleiben sichtbar, gekennzeichnet als nicht dauerhaft gekoppelt, mit Aktion „Dauerhaft koppeln“.
- Automatische Wiederverbindung verwendet ebenfalls Bonded. Keine Kopplungsschlüssel werden gelesen, protokolliert oder gelöscht.
- Installer 2.8.14 weiterverwenden. Einmalige dauerhafte Kopplung erforderlich, wenn bislang kein Bond existiert. Noch nicht auf dem betroffenen Pi geprüft.

# 1.17.1

- Gespeicherten Bluetooth-Audioausgang nach Neustart und bei späterem Einschalten im Hintergrund wieder verbinden. Kein Scan oder erneutes Pairing nötig, keine Wartezeit beim App-Start.
- Bewusstes Trennen/Entfernen unterbindet Wiederverbindung bis zu explizitem Verbinden oder einem App-Neustart.
- Bereits gekoppelte Geräte werden beim Koppeln nicht erneut gepairt. Verbindungsstatus in den Einstellungen und im Bluetooth-Bereich.
- Installer 2.8.14 weiterverwenden und dieses separate App-Paket auswählen.

# 1.17.0

- Einstellungen: Raspberry Pi mit Bestätigung neu starten; CSRF-geschützte Anfrage, gezielter systemd-Helfer ohne allgemeine Root-Rechte für die Webapp.
- Player: lokal mitgelieferte Senderlogos bei Radio, auch bei Start über NFC oder Wecker. Vollständige Darstellung in hellem und dunklem Design, Fallback bei Bildfehlern.
- App separat vom Desktop-Installer ausgeliefert. Für bestehende Pis mit Installer 2.8.14 aktualisieren, damit der Neustart-Helfer eingerichtet wird.

# 1.16.0

Statusbereich in den Einstellungen bündelt NFC, Audioplayer, Wiedergabe, Spotify-Anmeldung, Bluetooth, Radio/Wecker, Uhrzeit und Kartenmeldung. Bluetooth unterscheidet Adapterbereitschaft von einer leeren Geräteliste und wird in geöffneten Einstellungen/Bluetooth alle 10 Sekunden geprüft. Keine künstliche Startverzögerung.

# 1.15.4

NFC-Regel für Neuinstallationen identifiziert den Reader über den von udev erzeugten by-id-Link statt angenommener USB-IDs. Die späte Regel weist Gruppe und Modus abschließend zu. Für bestehende Systeme im Installer 2.8.12 Geräte einrichten verwenden; App-Updates allein ändern keine Systemregeln.

# 1.15.3

NFC-Fehler nennen jetzt den Betriebssystemfehler und den betroffenen Schritt (Öffnen, exklusives Übernehmen oder Lesen). Dies ist eine Diagnoseverbesserung, keine unbestätigte Reparatur des Readers.

# 1.15.2 – Auch der Kopfzeilen-Slogan gekürzt (22. September 2026)

- Kopfzeile: „Deine Musik. Zum Anfassen.“ heißt jetzt nur noch „Deine Musik.“.

# 1.15.1 – Slogans aus der Weboberfläche entfernt (22. September 2026)

- Fußzeile: „Musik zum Anfassen.“ und „Deine Karten“ entfernt.
- Startseite: Kicker über der Wiedergabeanzeige heißt jetzt „Willkommen“ statt „Jetzt auf deiner Phoniebox“.
- Rein textliche Änderung an `templates/base.html` und `templates/index.html`, keine Funktionsänderung.

# 1.15.0 – Spotify-Suche nach Typ eingrenzbar (22. September 2026)

- Die in 1.14.0 eingeführte Spotify-Suche im Kartenformular mischte Titel, Alben und Playlists in einer Ergebnisliste – bei mehrdeutigen Suchbegriffen musste man darin erst das Richtige finden. Eine neue Auswahlbox „Spotify durchsuchen: Typ“ (Alles, Titel, Album, Playlist) grenzt die Suche jetzt vorab ein; ein Wechsel des Typs löst bei vorhandenem Suchbegriff sofort eine neue Suche aus.
- `Spotify.search()` bekommt dafür einen neuen optionalen Parameter `kind`; die Route `GET /api/spotify/search` reicht ihn als `type`-Query-Parameter durch und lehnt einen unbekannten Wert mit einer klaren Fehlermeldung ab.
- 3 neue Tests für `spotify.py` und die Route (180 insgesamt).

# 1.14.1 – Lautstärke sprang nach einem Player-Neustart zurück auf den alten Standardwert (22. September 2026)

- `hardware.py`s `player_loop` startet librespot bei jedem (Neu-)Start mit `--initial-volume` aus dem in den Einstellungen gespeicherten Wert. Eine Lautstärkeänderung über den Regler, eine Lauter-/Leiser-/Fest-Karte oder den Wecker wurde aber nur an Spotify geschickt, nie in die Einstellungen zurückgeschrieben – bei jedem Neustart von librespot (zum Beispiel weil zuvor eine Radiosender-Karte lief und danach eine Musik-Karte aufgelegt wurde) sprang die Lautstärke deshalb auf den alten, gespeicherten Wert zurück, unabhängig davon, was zuletzt tatsächlich eingestellt war.
- `Spotify.command()` speichert die neue Lautstärke nach `volume`, `volume_up` und `volume_down` jetzt zusätzlich in den Einstellungen (`Store.put(volume=…)`), sodass sie einen Player-Neustart übersteht. `play`, `pause`, `next` und `previous` bleiben unverändert.
- 3 neue Tests für `spotify.py` (177 insgesamt).

# 1.14.0 – Spotify-Suche bei der NFC-Kartenerfassung (22. September 2026)

- Das Kartenformular hat jetzt ein Suchfeld „Spotify durchsuchen“: sucht (mit 400 ms Verzögerung nach dem Tippen) über die Spotify-Web-API nach Alben, Titeln und Playlists und zeigt Cover, Titel und Interpret/Ersteller als Trefferliste. **Übernehmen** trägt Link und – sofern das Namensfeld noch leer ist – auch den Namen direkt ein. Der Link lässt sich danach weiterhin von Hand anpassen; die Suche ist rein optional und ersetzt das manuelle Einfügen eines `open.spotify.com`-Links nicht, ergänzt es nur.
- Neue Methode `Spotify.search()` und Route `GET /api/spotify/search`. Nutzt dieselbe bereits verbundene Web-API-Anmeldung wie der Rest der Steuerung; ohne verbundenes Spotify erscheint dieselbe Fehlermeldung wie anderswo in der App.
- Die Suche läuft nur bei „Musik starten“ als Aktion; bei Radio- und Steuerkarten ist sie ausgeblendet.
- 7 neue Tests für `spotify.py` und die neue Route (173 insgesamt); der bestehende JavaScript-Formulartest deckt die neuen Formularfelder ab, ohne Anpassung nötig zu haben.

# 1.13.1 – Bluetooth-Trennung mitten in der Wiedergabe wird jetzt erkannt, ohne Dauerpolling (21. September 2026)

- 1.12.0 hat den Fall behoben, dass beim *Starten* eines Songs mit nicht erreichbarem Audioausgang nur eine irreführende Spotify-Meldung erschien. Offen blieb der gemeldete Fall, dass Musik läuft, der Bluetooth-Lautsprecher dann ausgeschaltet wird, und die Weboberfläche bei weiteren Wiedergabebefehlen weiterhin nur „Wiedergabebefehl gesendet.“ zeigt – ohne jeden Hinweis, dass gar kein Ton mehr herauskommt: `bluealsa` lässt librespot in diesem Fall meist einfach weiterlaufen (nimmt Audio klaglos an und verwirft es), sodass librespot nicht abstürzt und Spotify den Befehl weiterhin erfolgreich verarbeitet, weil das Gerät für Spotify noch aktiv aussieht.
- Statt librespot dafür laufend im Hintergrund zu überwachen (unnötiger Dauer-Overhead für `bluetoothctl`, während Musik einfach normal läuft), prüft `Hardware.command()` jetzt genau in dem Moment, in dem tatsächlich abgespielt werden soll – ausgelöst durch eine NFC-Karte oder den Play-Knopf –, ob ein als Ausgang eingestellter Bluetooth-Lautsprecher (`bluetooth.mac_in()`) gerade wirklich verbunden ist. Ist er es nicht, wird sofort mit „Bluetooth-Lautsprecher ist nicht verbunden. Bluetooth erneut verbinden oder Einstellungen prüfen.“ abgebrochen, noch bevor überhaupt Spotify kontaktiert wird.
- `app.py`s `active_bluetooth_mac()` nutzt jetzt dieselbe neue `bluetooth.mac_in()`-Funktion statt einer eigenen Kopie des Regex.
- 6 neue Tests für `hardware.py` und `bluetooth.py` (168 insgesamt).

# 1.12.0 – Fehlgeschlagene Wiedergabe bei nicht erreichbarem Audioausgang jetzt klar erkennbar (21. September 2026)

- Wenn eine NFC-Karte (oder der Play-Knopf) Musik starten sollte, während der eingestellte Audioausgang gerade nicht erreichbar ist (typischerweise ein getrennter Bluetooth-Lautsprecher, siehe 1.9.2), lief `librespot` gar nicht erst und Spotify meldete lediglich „Phoniebox nicht eindeutig erreichbar. In der Spotify-App das Gerät auswählen.“ – eine irreführende Meldung, da es dort gar kein Gerät zum Auswählen gibt.
- `Hardware.command()` erkennt diesen Fall jetzt anhand des bereits von `player_loop()` ermittelten Status und zeigt stattdessen die eigentliche, handlungsleitende Ursache („Audioausgang … nicht erreichbar. Bluetooth verbunden? Einstellungen prüfen.“) – sowohl beim Auflegen einer Karte (als Meldung auf der Startseite) als auch beim direkten Bedienen über die Weboberfläche. Ist der Ausgang tatsächlich erreichbar, bleibt die ursprüngliche Spotify-Meldung (echter Fall von mehreren/keinem eindeutigen Gerät) unverändert.
- Andere Fehlerpfade (Spotify-, Radio-/Wecker- und Bluetooth-Fehler) wurden überprüft: Sie werden bereits über `hw.message`, `hw.player`, `media.message` bzw. die JSON-Fehlerantworten der API-Routen sichtbar gemacht und mussten nicht geändert werden.
- 3 neue Tests für `hardware.py` (162 insgesamt).

# 1.11.2 – Ursache gefunden: `paired-devices` existiert in neueren BlueZ-Versionen nicht mehr (21. September 2026)

- Die durch 1.11.1 sichtbar gemachte Fehlermeldung zeigte die tatsächliche Ursache: `Invalid command in menu main: paired-devices`. Neuere `bluetoothctl`-Versionen (BlueZ 5.65 und neuer) haben den Befehl `paired-devices` ersatzlos entfernt und dafür `devices` um ein optionales Filterargument erweitert (`devices Paired`). `bluetooth.py` benutzte noch die alte Syntax – auf einem Pi mit neuerem BlueZ schlug jedes Auflisten gekoppelter Geräte deshalb fehl, weshalb der Lautsprecher trotz erfolgreicher Kopplung und Verbindung nicht mehr in der Liste erschien.
- `bluetooth.paired_devices()` versucht jetzt zuerst die moderne Syntax (`devices Paired`) und fällt nur bei einer „Invalid command“-Rückmeldung auf die alte (`paired-devices`) zurück, damit das sowohl mit neueren als auch mit älteren BlueZ-Versionen funktioniert. Ein echter Fehler (z. B. Adapter nicht bereit) wird weiterhin sofort als `BluetoothError` gemeldet, ohne die andere Syntax zu versuchen.
- 3 neue Tests für `bluetooth.py` (159 insgesamt).

# 1.11.1 – Fehlgeschlagenes bluetoothctl sah wie „nichts gekoppelt“ aus (21. September 2026)

- `bluetooth.paired_devices()` und `bluetooth.scan()` gaben bei einem fehlschlagenden `bluetoothctl`-Aufruf (z. B. keine D-Bus-Berechtigung, Adapter nicht bereit) bisher stillschweigend eine leere Liste zurück – nicht unterscheidbar von „es ist wirklich nichts gekoppelt“. Ausgelöst durch einen Nutzerbericht: Ein zuvor erfolgreich gekoppelter und verbundener Lautsprecher erschien nach einem Update plötzlich gar nicht mehr in der Liste, ohne jede Fehlermeldung.
- Beide werfen jetzt `BluetoothError` mit `bluetoothctl`s eigener Fehlermeldung, wenn der Befehl selbst fehlschlägt. `app.py` fängt das ab und zeigt die Ursache jetzt direkt im Bluetooth-Bereich an, statt der irreführenden „Noch keine Bluetooth-Geräte gekoppelt“-Meldung.
- Rein diagnostisch: Das behebt nicht die zugrundeliegende Ursache des gemeldeten Falls (die noch unbekannt ist), macht sie aber beim nächsten Auftreten sofort sichtbar, statt sie zu verschleiern.
- 3 neue Tests für `bluetooth.py`, 1 neuer Flask-Routen-Test (157 insgesamt).

# 1.11.0 – Aktiver Bluetooth-Ausgang sichtbar, direkt umschaltbar (21. September 2026)

- Der Bereich „Bluetooth“ zeigt jetzt bei jedem bereits gekoppelten Gerät zusätzlich, ob es gerade der eingestellte Hauptaudioausgang ist („… · Aktueller Audioausgang“), ermittelt aus dem tatsächlich gespeicherten `audio`-Wert (nicht nur aus `bluetoothctl`s Verbindungsstatus, der etwas anderes sein kann).
- „Als Audioausgang verwenden“ verbindet das Gerät jetzt zuerst aktiv (`bluetoothctl connect`), bevor der Ausgang umgestellt wird, und meldet einen klaren Fehler statt eines stillen Wechsels, wenn die Verbindung nicht klappt – vorher hätte ein nicht tatsächlich verbundenes Gerät nur wieder das ursprüngliche „Spotify-Gerät verschwindet“-Verhalten reproduziert (die Erreichbarkeitsprüfung aus 1.9.2 hätte librespot dann gar nicht erst gestartet). Der Knopf entfällt jetzt sinnvollerweise beim bereits aktiven Gerät.
- `bluetooth.connect()` prüft den Erfolg jetzt wie `pair()` (seit 1.10.2) am tatsächlichen Gerätestatus (`bluetoothctl info`) statt am Rückgabewert des `connect`-Unterbefehls, aus demselben Grund: ein bereits verbundenes Gerät ist derselbe unzuverlässige Grenzfall.
- Neue API-Felder: `GET /api/bluetooth` und `POST /api/bluetooth/scan` liefern zusätzlich `active` (die MAC-Adresse des aktuellen Bluetooth-Audioausgangs, oder `null`).
- 4 neue/geänderte Tests für `bluetooth.py`, 5 neue für die Flask-Routen (154 insgesamt).

# 1.10.2 – Bereits gekoppeltes Gerät fälschlich als Kopplungsfehler gemeldet (21. September 2026)

- `bluetooth.pair()` wertete den Erfolg der Kopplung anhand von `bluetoothctl`s eigener Textausgabe aus und suchte darin gezielt nach der Textphrase „already paired“, um ein bereits gekoppeltes Gerät als Erfolg statt Fehler zu behandeln. Tatsächlich meldet `bluetoothctl` diesen Fall aber üblicherweise als `org.bluez.Error.AlreadyExists`, ohne die gesuchte Phrase – ein Lautsprecher, der (wie bei Kai) bereits vorher anderweitig gekoppelt war, wurde dadurch fälschlich als „Kopplung fehlgeschlagen oder Zeitüberschreitung“ gemeldet, obwohl auf Geräteebene gar nichts fehlgeschlagen war.
- Behoben durch einen grundsätzlich robusteren Ansatz statt einer erweiterten Textsuche: Nach dem Kopplungsversuch wird jetzt der tatsächliche Gerätestatus per `bluetoothctl info` abgefragt (`Paired: yes`/`no`) und danach entschieden, statt `bluetoothctl`s eigene, je nach BlueZ-Version unterschiedliche Fehlertexte zu erraten.
- 4 geänderte/neue Tests für `bluetooth.py` (150 insgesamt, unverändert – reine Umstellung der Erfolgsprüfung ohne neue Testfälle).

# 1.10.1 – Fehlermeldung beim Koppeln wurde sofort wieder überschrieben (21. September 2026)

- Nach einem Klick auf „Koppeln“, „Verbinden“, „Trennen“ oder „Entfernen“ im neuen Bluetooth-Bereich (1.10.0) blendete `app.js` zwar bei einem Fehler kurz die eigentliche Meldung ein, überschrieb sie aber im selben Zug sofort wieder mit dem allgemeinen „Noch keine Bluetooth-Geräte gekoppelt“-Text des anschließenden Listen-Refreshs – die tatsächliche Ursache eines Kopplungsfehlers war dadurch nie sichtbar, nur das Endergebnis „weiterhin nicht gekoppelt“.
- Die Meldung (Erfolg oder Fehler) wird jetzt erst nach dem Aktualisieren der Liste gesetzt, sodass sie stehen bleibt. Verbinden/Trennen/Entfernen zeigen jetzt außerdem eine kurze Bestätigung statt gar keiner Rückmeldung.
- Rein clientseitige Korrektur in `static/app.js`, keine Änderung an `bluetooth.py` oder den API-Routen.

# 1.10.0 – Bluetooth-Lautsprecher direkt in der Weboberfläche koppeln (21. September 2026)

- Neuer Bereich „Bluetooth“ in der Weboberfläche: nach Geräten suchen (10 Sekunden, `bluetoothctl --timeout … scan on`), neue Lautsprecher koppeln (Pairing über den eingebauten Agent von `bluetoothctl` – „Just Works“-Kopplung, wie bei den meisten Lautsprechern ohne eigenes Display, läuft automatisch durch; Geräte, die eine PIN-Bestätigung am Gerät selbst verlangen, können weiterhin nicht ohne Anzeige bestätigt werden und laufen in eine Zeitüberschreitung), bereits gekoppelte Geräte verbinden/trennen/entfernen, sowie ein Gerät direkt „als Audioausgang verwenden“ (trägt `bluealsa:DEV=…,PROFILE=a2dp` in die Einstellungen ein und startet den Player neu). Bisher war das nur per SSH und `bluetoothctl` von Hand möglich.
- Grund für diese Version: 1.9.2s neue Erreichbarkeitsprüfung verhindert zwar zuverlässig das sinnlose Auftauchen-und-Verschwinden eines Spotify-Geräts, wenn Bluetooth nicht verbunden ist – lässt das Gerät dann aber komplett aus Spotify Connect verschwinden, bis der Ausgang wieder erreichbar ist. Ohne eine einfache Möglichkeit, den Lautsprecher neu zu verbinden, war das in der Praxis eine Sackgasse.
- Neues Modul `bluetooth.py`: dünner `bluetoothctl`-Wrapper (`scan`, `pair`, `connect`, `disconnect`, `forget`, `paired_devices`, `info`) ohne zusätzliche Python-Abhängigkeit (kein D-Bus-Paket). Scan- und Kopplungsvorgänge sind über ein Lock serialisiert, damit sich nicht zwei gleichzeitige `bluetoothctl`-Aufrufe in die Quere kommen.
- Neue API-Routen `/api/bluetooth`, `/api/bluetooth/scan`, `/pair`, `/connect`, `/disconnect`, `/forget`, `/use`.
- `install.sh` installiert jetzt zusätzlich `bluez` und nimmt den Dienstnutzer `phoniebox` in die Gruppe `bluetooth` auf. Bereits installierte Systeme, die über den Desktop-Installer aktualisieren (nicht neu installieren), müssen dafür einmalig per SSH `sudo usermod -aG bluetooth phoniebox && sudo systemctl restart phoniebox` ausführen – das automatische Nachziehen von Systemgruppen ist bei einem In-Place-Update (`update.py`) bewusst außerhalb des Umfangs, ebenso wie z. B. Änderungen an der Dienstdatei.
- `release.json` bekommt `bluez` und `alsa-utils` als Abhängigkeiten (Letzteres fehlte dort bislang, obwohl `device_reachable()` seit 1.9.2 bereits `aplay` voraussetzt) sowie `bluetooth.py` in der Dateiliste.
- Das Koppeln selbst (`bluetoothctl pair`/`trust`/`connect`) ist auf einem echten Pi nicht getestet, da hierfür reale Bluetooth-Hardware nötig ist – nur mit gemockten `bluetoothctl`-Aufrufen.
- 10 neue Python-Tests für `bluetooth.py` sowie 8 neue Flask-Routen-Tests (150 insgesamt).

# 1.9.2 – Nicht erreichbarer Audioausgang jetzt erkannt und gemeldet (21. September 2026)

- Zweite, unabhängige Ursache für ein verschwindendes Spotify-Gerät gefunden und behoben: Ist der eingestellte ALSA-Audioausgang gerade nicht wirklich zu öffnen – etwa weil `default` durch die System-ALSA-Konfiguration im Hintergrund auf einen gerade nicht verbundenen Bluetooth-Lautsprecher zeigt –, stürzte librespots Player beim eigentlichen Wiedergabestart intern ab. Nach außen sah das genauso aus wie das bekannte 502-Problem aus 1.9.1: Das Gerät erscheint kurz in Spotify und verschwindet sofort wieder, ganz ohne Fehlermeldung in der Phoniebox-Oberfläche, weil librespots eigene Fehlerausgabe absichtlich nicht ins Systemjournal gelangt (wegen möglicher Zugangsdaten darin).
- `configure_audio.py` bekommt `device_reachable(device)`: ein kurzer, unauffälliger Testlauf (`aplay … /dev/zero`, mit `timeout` begrenzt), der prüft, ob sich das eingestellte Gerät tatsächlich öffnen lässt, bevor librespot überhaupt gestartet wird.
- `hardware.py`s `player_loop()` prüft das jetzt vor jedem Start: Ist der Ausgang nicht erreichbar, startet librespot gar nicht erst (kein sinnloses Auftauchen-und-Verschwinden mehr in Spotify), und die Weboberfläche zeigt sofort „Audioausgang „…“ nicht erreichbar. Bluetooth verbunden? Einstellungen prüfen.“ im Player-Status. Sobald das Gerät wieder erreichbar ist (z. B. Bluetooth-Lautsprecher neu verbunden), startet librespot beim nächsten Versuch automatisch wie gewohnt – ganz ohne Neustart des Dienstes.
- 6 neue Python-Tests (132 insgesamt): `device_reachable()` für offen bleibendes Gerät, sofort verweigerndes Gerät und fehlende Werkzeuge/Timeout, sowie zwei Tests für `player_loop()` (kein Start bei nicht erreichbarem Gerät, normaler Start bei erreichbarem Gerät).
- Das ursprünglich gemeldete Problem stammte tatsächlich von genau diesem zweiten Fall (nicht erreichbarer, stillschweigend auf Bluetooth umgeleiteter `default`-Ausgang), nicht vom 502-Fall aus 1.9.1 – beide Ursachen erzeugen aber dasselbe äußere Bild, weshalb beide behoben wurden.

# 1.9.1 – Spotify-Gerät verschwindet mit Fehler 502 (21. September 2026)

- Behoben: Beim Aktivieren der Phoniebox in Spotify (Gerät antippen, per NFC-Karte oder Weboberfläche „Play“ drücken) konnte das Gerät wieder aus der Geräteliste verschwinden und die Weboberfläche meldete „Spotify meldet HTTP 502“. Ursache ist ein seit Jahren bekanntes, von Spotify nie behobenes Problem des eigenen Servers, der die Anfrage zum Übertragen der Wiedergabe gelegentlich mit HTTP 502/503/504 statt mit Erfolg beantwortet, obwohl an der Anfrage nichts falsch war (siehe `spotify/web-api#700`).
- Solche Antworten gelten jetzt als vorübergehend: Bis zu drei Versuche mit kurzer Pause (0,5 s, dann 1 s), bevor ein Fehler gemeldet wird. Damit übersteht die Aktivierung den typischen kurzen Aussetzer von selbst; nur bei anhaltendem Problem erscheint noch eine Meldung, die jetzt auch klarstellt, dass das Gerät in Spotify sichtbar bleibt und ein erneuter Versuch reicht.
- Betroffen waren alle Spotify-Anfragen, am spürbarsten aber das Aktivieren eines noch inaktiven Geräts (`Spotify.device(activate=True)`), weil Spotify dafür laut den Rückmeldungen anderer Entwickler besonders häufig mit 502 antwortet, wenn die Phoniebox das einzige verfügbare Gerät ist.
- Kein Zusammenhang mit librespot: Die für dieses Projekt gebaute Version (librespot v0.8.0) ist weiterhin die aktuelle Veröffentlichung des Projekts; ein Versions-Update ändert an diesem Verhalten nichts, da der Fehler auf Spotifys Server entsteht, nicht in librespot.
- 3 neue Python-Tests (126 insgesamt), die genau dieses Muster nachbilden: ein 502/503 auf dem ersten Versuch, Erfolg beim erneuten Versuch, sowie ein Test, der die Aktivierung eines noch nicht aktiven Geräts mit einem vorübergehenden 502 mitten im Ablauf durchspielt.

# 1.9.0

Hell-/Dunkelmodus mit lokal gespeicherter Auswahl, zunächst nach Systemeinstellung. Navigation zeigt je einen Bereich; Direktlinks und Zurück/Vorwärts bleiben möglich. Ohne JavaScript bleiben alle Bereiche zugänglich.

# 1.8.0

Neue Webgestaltung passend zum Desktop-Installer: Dunkelgrün und Mint, Klangsymbol, helle Formulare und mobil angepasste Bereiche. Funktionen, API und Datenbankschema bleiben unverändert.

# Änderungsverlauf

Neueste Version zuerst. Dieser Verlauf ersetzt die früheren Einzeldateien `RELEASE-*.md` und `TESTRESULTATE.md`. Die Angaben zu Tests stammen aus den ursprünglichen Release Notes.

## 1.7.0 – Radiosender per NFC-Karte (21. September 2026)

- Neue Kartenaktion **Radiosender starten**: Beim Auflegen läuft der gewählte Sender über den Hauptausgang, Spotify wird dafür wie beim Radio in der Weboberfläche getrennt. Gespeichert wird `phoniebox:radio:<sender-id>`. Bestehende Karten sind nicht betroffen.
- Ohne eigenen Namen übernimmt die Karte den Sendernamen. Ein unbekannter Sender wird abgelehnt und ersetzt keine vorhandene Zuordnung.
- Dieselbe Karte erneut beendet den Sender. Bei „Musik erneut starten“ startet er neu. Live-Radio wird nicht pausiert, weil beim Fortsetzen sonst alter Puffer liefe.
- Lautstärke: Läuft schon etwas Lokales, bleibt dessen Lautstärke, sonst gilt die Startlautstärke.
- Eine Musik-Karte nach Radio oder Ton startet ihre Musik jetzt immer neu. Vorher konnte „dieselbe Karte erneut“ nach einem Senderstart nur den Sender pausieren.
- Die Weboberfläche zeigt bei Radio-Karten den Sender, und Bearbeiten und automatisches Laden beim Auflegen füllen die Senderauswahl.
- 123 Python-Tests bestehen (16 neue) sowie der Formulartest, der jetzt auch die Senderauswahl abdeckt. Auf einem Pi ist die Version nicht getestet; der Sender wird über dieselbe Funktion gestartet wie das Radio in der Weboberfläche.

## 1.6.0 – Ausgang des Weckers wählbar (20. September 2026)

- Der Wecker hat einen eigenen Ausgang für Ton und Radio: **Klinke** (Standard) oder **Bluetooth**. Bei Bluetooth trägst du den ALSA-Namen des Lautsprechers ein (`bluealsa:DEV=<MAC>,PROFILE=a2dp`). Ist er zur Weckzeit nicht erreichbar, spielt derselbe Wecker sofort über die Klinke. Das gilt auch für den Ersatzton, der nach einem ausgefallenen Stream oder einer ausgefallenen Quelle läuft.
- Der Wecker nimmt die Klinke unabhängig vom Hauptausgang, auch wenn dieser Bluetooth ist. Dafür merkt sich `configure_audio.py` den Klinkennamen als `analog_audio`; bei bestehenden Installationen wird er beim Wecken aus `/proc/asound/cards` erkannt.
- Der Statustext nennt den benutzten Ausgang, zum Beispiel „Wecker läuft (Klinke, da Bluetooth nicht erreichbar)“. Auf der Weboberfläche steht, welches Gerät „Klinke“ ist.
- **Spotify** als Weckquelle spielt weiter über den Hauptausgang und folgt dieser Auswahl nicht.
- Die Einstellung „ALSA-Audioausgang“ akzeptiert jetzt auch bluealsa-Namen (`bluealsa` oder `bluealsa:DEV=<MAC>,PROFILE=a2dp`), vorher nur `plughw:`, `hw:` und `default`.
- Die Box verbindet Bluetooth-Lautsprecher nicht selbst; das ist bewusst nicht Teil dieser Version.
- Die Radio- und Tonwiedergabe außerhalb des Weckers (Abschnitt „Radio und Wecktöne“) nutzt weiter den Hauptausgang.
- 107 Python-Tests bestehen (27 neue für Ausgangswahl, Rückfall, Namensprüfung und Formulare). Zusätzlich habe ich mit dem echten `mpv` geprüft, dass ein nicht öffnbares Gerät nach etwa 0,1 Sekunden mit Fehlercode 2 endet. Auf einem Pi mit Bluetooth-Lautsprecher ist die Version nicht getestet.

## 1.5.3 – Webpasswort-Altlast entfernt (20. September 2026)

Keine Änderung am Betrieb einer laufenden Box.

- `install.sh` stellt keine Rückfragen mehr und nimmt keine Argumente mehr an. Die Option `--password-stdin` und die Ausgabezeile `PHONIEBOX_WEB_PASSWORD_INPUT` entfallen.
- `admin.py` ist entfernt, auch aus `release.json`. Datenbank und Schlüssel entstehen beim ersten Dienststart durch `configure_audio.py` (`ExecStartPre`), genau wie bisher bei jedem Start geprüft. Das habe ich lokal nachgestellt; auf einem echten Pi ist es nicht getestet.
- Ein vorhandener `password_hash` in bestehenden Datenbanken bleibt unbenutzt liegen.
- Die Erstinstallation braucht den Desktop-Installer ab Version 1.2.0. Updates von 1.5.x aus funktionieren mit jedem Installer, weil `update.py` unverändert ist.
- Der JavaScript-Formulartest liegt jetzt als `tests/test-card-form.cjs` bei. Die Passwort-Reste in den Python-Tests sind entfernt. 80 Python-Tests und der Formulartest bestehen.

## 1.5.2 – Aufräumen und Dokumentation (20. September 2026)

Keine Funktionsänderung.

- Quellcode einheitlich formatiert (black, 120 Zeichen, Anführungszeichen unverändert). Mehrere Anweisungen pro Zeile und einzeilige `if`-Blöcke sind aufgelöst, vor allem in `alarm_radio.py`, `update.py` und `hardware.py`.
- Ungenutzte Importe entfernt, verstreute Importe an den Dateianfang verschoben, Modul-Docstrings ergänzt.
- README neu geschrieben, technische Dokumentation in `docs/ARCHITEKTUR.md` ergänzt.
- Alte Release-Notizen in diese Datei überführt.
- 80 Python-Tests bestehen unverändert.

## 1.5.1

Im Archiv liegen keine Release Notes zu dieser Version. Gegenüber den Notizen zu 1.5.0 enthält die Senderliste im Code zusätzlich „BBC Radio 1 (international)“. Weitere Änderungen sind nicht dokumentiert.

## 1.5.0 – Radio und Wecker

- Wöchentlich konfigurierbarer Wecker: Uhrzeit, Tage, Quelle (Spotify-Link, Radio oder Ton), Lautstärke und Abschaltdauer. Standardmäßig deaktiviert.
- Feste Zeitzone Europe/Berlin. Eine durch die Sommerzeit ausgefallene Zeit wird übersprungen, die doppelte Winterzeit löst nur einmal aus. Nach einer Abschaltung wird nicht nachgeholt; der Pi muss laufen und die Uhrzeit muss stimmen.
- Drei lokal erzeugte WAV-Töne: Glocke, Signal, Melodie. Schlagen Radio oder Spotify beim Start fehl, läuft der gewählte Ersatzton. Das gilt auch, wenn der Radioprozess während des Alarms vorzeitig endet. Bei einer hängenden, aber nicht beendeten Verbindung kann keine lückenlose Erkennung garantiert werden.
- Radiosender: WDR 2, 1LIVE, WDR 3/4/5, Die Maus, Deutschlandfunk, BBC Radio 2 (international) und BBC World Service. Die BBC-Sounds-Beschränkung ist keine pauschale Sperre dieser internationalen Live-Streams. BBC Radio 2 und World Service antworteten vom Nutzer-Pi mit HTTP 200. Die Verfügbarkeit einzelner Sendungen kann sich ändern. Die Links stammen aus WDR-/DLF-Verzeichnissen und geprüften Sender-CDNs; es gibt keine VPN-Umgehung.
- `mpv` und `tzdata` werden vom Updater bei Bedarf installiert. Radio und Spotify teilen sich den analogen Audioausgang; librespot wird für lokale Wiedergabe beendet und danach wieder bereitgestellt.
- NFC-Stop- und Lautstärkekarten steuern auch die lokale Wiedergabe.
- Der Wecker läuft im bestehenden Phoniebox-Dienst (kein Cronjob). Einstellungen und der letzte Wecktag liegen in SQLite.
- 80 Python-Tests bestanden. Echte Audio-Tests sind gesondert zu betrachten.

Quellen der Senderlinks:

- <https://www1.wdr.de/unternehmen/der-wdr/empfang-technik/webradio-100.amp>
- <https://www.deutschlandfunk.de/livestream-100.html>
- <https://help.bbc.com/hc/en-us/articles/42652680528659-Update-on-access-to-BBC-Sounds-outside-the-UK>
- <https://www.radio.de/s/bbcradio2>

## 1.4.1

- Steuerkarten brauchen keinen eigenen Namen mehr. Der Browser erlaubt das Absenden ohne Namen, der Server vergibt die Aktionsbezeichnung. Individuelle Namen bleiben erhalten, Musik-Karten brauchen weiterhin einen Namen.
- 72 Python-Tests und der JavaScript-Formulartest bestanden.

## 1.4.0

- Karten können Musik, Stop/Pause, Fortsetzen, nächsten oder vorherigen Titel, Lauter, Leiser oder eine feste Lautstärke auslösen. Bei Lautstärkeaktionen sind Schritt beziehungsweise Zielwert in Prozentpunkten einstellbar.
- Bekannte Karten laden ihre Aktion automatisch ins Formular.
- Musik-Karten pausieren beim wiederholten Auflegen standardmäßig. Alternativ: Wechsel Pause/Fortsetzen oder erneuter Start. Die zuletzt erfolgreich ausgeführte Musik-Karte wird nur im laufenden Dienst gemerkt; ein Neustart setzt das zurück.
- Stop entspricht Pause mit Erhalt der Position. NFC-Einstellungen brauchen keinen Player-Neustart.
- Steuerzuordnungen liegen in der vorhandenen Kartentabelle als `phoniebox:<aktion>:<wert>`. Bestehende Spotify-URIs bleiben unverändert.
- Die Hardware erkennt keine Kartenentfernung. Dieselbe ID wird innerhalb von 3 Sekunden entprellt; für eine Wiederholung Karte entfernen und mindestens 3 Sekunden warten.
- 64 Python-Tests und der JavaScript-Formulartest bestanden. Getestet wurden: Speicherung aller Steueraktionen, Erhalt von Musik-Karten, wiederholtes Pausieren/Umschalten/Neustarten, Lautstärkebegrenzung und Geräteauswahl, Formularwechsel, CSRF und die bisherigen Update-Rollbacks. Physische Steuerkarten waren noch vom Nutzer zu testen.

## 1.3.0

- Jede aufgelegte NFC-Karte erscheint automatisch im Kartenformular. Bekannte Karten laden Name und URI, unbekannte Karten leeren diese Felder. Nur eine neue Erfassung ersetzt die Formulareingaben; regelmäßige Statusabfragen lassen Bearbeitungen bestehen.
- Bekannte Karten starten weiterhin Musik. Zum stillen Bearbeiten gibt es „Karte ohne Wiedergabe erfassen“.
- 51 Python-Tests und ein JavaScript-Formulartest bestanden.

## 1.2.2

- Behebt den NFC-Thread-Absturz mit python-evdev auf Trixie.
- Erfolgreiche Spotify-Steuerbefehle werden ohne JSON-Zwang verarbeitet.
- Die Phoniebox wird vor Play beziehungsweise NFC-Wiedergabe automatisch aktiviert. Die Aktivierung ist auf das eindeutig passende Gerät begrenzt und wird vor der Wiedergabe überprüft.
- 49 lokale Tests bestanden. Echte Token-Erneuerung, Geräteaktivierung und Wiedergabe wurden auf dem Nutzer-Pi geprüft.

## 1.2.1 – Fehlerkorrekturen (20. September 2026)

- Erfolgreiche Spotify-Playerbefehle werden nicht mehr als JSON interpretiert.
- Ungültige Antworten bei Statusabfragen werden verständlich gemeldet.
- Das NFC-Gerät wird mit `contextlib.closing` verwaltet, weil `InputDevice` auf dem Pi kein Kontextmanager ist.
- Der Hinweis bei inaktivem Player fordert nicht länger unnötig zur manuellen Geräteauswahl auf.
- 47 Tests bestanden.

## 1.2.0 – Weboberfläche ohne Passwort

- Die Weboberfläche öffnet ohne Login. `/login` leitet auf die Startseite weiter, sodass alte Links und die Installer-Diagnose kompatibel bleiben. Der Abmelden-Knopf entfällt. Auch Geräte mit alten Browser-Sitzungen brauchen kein Passwort.
- Alle Netzwerkbenutzer mit Zugriff auf die Phoniebox können Einstellungen ändern. SSH-Authentifizierung, Spotify-OAuth, CSRF, Host-Prüfung, HTTPS und die Verschlüsselung der Secrets bleiben bestehen.
- Vorhandene Passwort-Hashes werden nicht mehr verwendet. Karten, Einstellungen und Spotify-Tokens bleiben erhalten.
- Einspielen per Desktop-Installer ab 1.1.0: Updates → Paket `phoniebox-1.2.0.tar.gz` auswählen → Update installieren. Der Installer 1.1.0 bringt weiterhin sein Paket 1.1.0 mit, deshalb das neue Paket ausdrücklich wählen. Kein erneuter librespot-Build.

## 1.1.0 und früher

Zu diesen Versionen liegen im Archiv keine Notizen vor. Laut früherer README werden Updates ab dem Desktop-Installer 1.1.0 unterstützt.
