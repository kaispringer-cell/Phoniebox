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
