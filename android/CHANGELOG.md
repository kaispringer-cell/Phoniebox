# 1.3.4

- „Der Player ist nicht bei den anderen Medien-Kacheln. … Auch in der Now-Bar ist von der Phoniebox nichts zu sehen.“ – Laut Diagnose lief der Player, aber Samsung (One UI, Android 16) zeigt die Mediensitzung einer App, die selbst keinen Ton abspielt, nirgends an. Der Player ist jetzt eine gewöhnliche Benachrichtigung mit eigenem Layout: Phoniebox-Symbol in der Statusleiste, in der Liste Albumcover, Titel, Interpret und Zurück, Start/Pause, Weiter; ausgeklappt mit großem Cover und Fortschrittsbalken. Antippen öffnet die App.
- Ohne Mediensitzung landen Kopfhörer- und Bluetooth-Tasten wieder bei Spotify auf dem Handy statt bei der Phoniebox-App.

# 1.3.3

- „In Version 1.3.2 gibt es keine Playerdiagnose. Es klappt immer noch nicht.“ – Das Menü ☰ öffnet die Weboberfläche, und die zeigt die Diagnose erst ab App 1.23.1 auf dem Pi. Die App meldet sich jetzt selbst: Ist der Player 4 Sekunden nach dem Öffnen nicht zu sehen, erscheint einmal pro Start der Dialog „Player startet nicht“ mit dem Befund (Android-Version, Gerät, Berechtigung, Kanal, Dienst, ob Android die Benachrichtigung führt, letztes Ereignis).
- Zusätzlich gibt es die Verknüpfung **Player-Diagnose**: lange auf das App-Symbol drücken.

# 1.3.2

- „Das App-Icon mit der Playersteuerung erscheint immer noch nicht.“ – Neue **Player-Diagnose** im Menü (☰) und in der Seitenleiste (ab App 1.23.1 auf dem Pi): startet den Player und zeigt Android-Version, ob Benachrichtigungen erlaubt sind, den Zustand des Player-Kanals, ob der Dienst läuft und was zuletzt passiert ist, etwa „Start von Android abgelehnt: …“. Bisher schluckte die App solche Fehler stumm.
- Der Player startet erst, nachdem die App vollständig im Vordergrund ist.

# 1.3.1

- „Das Android-Benachrichtigungssystem meldet keine Abfrage, ob Benachrichtigungen angezeigt werden dürfen. Es erscheint auch kein Icon.“ – Android fragt nur einmal nach der Erlaubnis; wurde sie früher abgelehnt oder in den Einstellungen ausgeschaltet, fragt es nie wieder. Die App merkt das jetzt beim Start und bietet an, die Benachrichtigungseinstellungen zu öffnen. Im Menü (☰) gibt es dafür den Eintrag „Benachrichtigungen in Android erlauben“, im Menü der Weboberfläche (ab App 1.22.0 auf dem Pi) einen Hinweis mit Button.
- Der Player nutzt einen neuen Kanal mit normaler Wichtigkeit (ohne Ton und Vibration), damit das Phoniebox-Icon oben in der Statusleiste erscheint. Mit niedriger Wichtigkeit zeigen viele Handys dort keins.

# 1.3.0

- „Ein Phoniebox Icon für den Tray unter Android. Dort klassische Musikplayer-Steuerung mit Albumcover und die Möglichkeit die App zu öffnen.“ – Die App zeigt in der Benachrichtigungsleiste (und ab Android 13 in den Mediensteuerungen der Schnelleinstellungen und auf dem Sperrbildschirm) einen Player: Albumcover, Titel, Interpret, Fortschritt und Zurück, Start/Pause, Weiter. Antippen öffnet die App. Braucht App 1.22.0 auf dem Pi.
- Der Player startet beim Öffnen der App und bleibt, solange die Box erreichbar ist. Bei laufender Musik fragt er alle 5 Sekunden nach, sonst alle 15, bei ausgeschaltetem Bildschirm gar nicht. Ist die Box länger als 2 Minuten nicht erreichbar oder wischt man ihn weg, verschwindet er bis zum nächsten Öffnen der App.
- Ein- und ausschalten im Menü (☰): „Player in der Benachrichtigungsleiste“. Fehler der Box, etwa „Bluetooth-Lautsprecher ist noch nicht verbunden“, erscheinen beim Tippen auf Start als kurze Meldung.

# 1.2.0

- Das App-Menü erscheint als Dialog im Design der Weboberfläche (ab App 1.20.2 auf dem Pi): Status der Box, Benachrichtigungen an/aus, Status prüfen, Neu laden, Zertifikat neu bestätigen. Dafür kennt die Brücke `window.PhonieboxApp` zusätzlich `version()`, `notificationsEnabled()`, `setNotifications()`, `checkNow()` und `resetCertificate()`. Mit älterer Weboberfläche und auf der Fehlerseite bleibt das Android-Menü.

# 1.1.0

- Keine Menüleiste mehr oben: Die App zeigt nur noch die Weboberfläche. Status- und Navigationsleiste haben die Farbe der Seite (hell oder dunkel, wie in der Weboberfläche gewählt).
- Das App-Menü (Status prüfen, Benachrichtigungen an/aus, Neu laden, Zertifikat neu bestätigen) öffnet der Button ☰ oben rechts in der Weboberfläche. Den gibt es ab App 1.20.1 auf dem Pi. Ist die Box nicht erreichbar, steht das Menü auf der Fehlerseite.

# 1.0.0

- Erste Version: zeigt die Weboberfläche der Phoniebox (`https://phoniebox.local`) als App. Links zu Spotify öffnen sich in der Spotify-App bzw. im Browser.
- Benachrichtigungen bei Problemen der Box, zum Beispiel „Bluetooth nicht verbunden“, „NFC-Reader nicht bereit“ oder „Spotify nicht verbunden“. Braucht App 1.20.0 auf dem Pi.
- Prüft im Hintergrund etwa alle 15 Minuten, solange das Handy in einem WLAN ist, und bei geöffneter App alle 30 Sekunden.
- Vertraut beim ersten Öffnen nach Bestätigung genau dem Zertifikat der Box (SHA-256-Fingerabdruck) und sonst keinem.
