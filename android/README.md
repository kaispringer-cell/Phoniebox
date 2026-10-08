# Phoniebox für Android

Die Weboberfläche der Phoniebox als Android-App, dazu Benachrichtigungen, wenn an der Box etwas nicht stimmt, zum Beispiel „Bluetooth nicht verbunden“.

## Installieren

1. Unter [Releases](https://github.com/kaispringer-cell/phoniebox/releases) beim neuesten Release `android-vX.Y.Z` die Datei `phoniebox-android-X.Y.Z.apk` auf dem Handy herunterladen.
2. Antippen und installieren. Android fragt einmal, ob der Browser bzw. die Dateien-App Apps installieren darf; das erlauben.
3. App öffnen. Beim ersten Start fragt sie, ob sie Benachrichtigungen senden darf, und zeigt den Fingerabdruck des Zertifikats der Box. Wer prüfen will: Die Erstinstallation gibt ihn am Ende aus, auf dem Pi zeigt ihn `openssl x509 -in /etc/phoniebox/tls.crt -noout -fingerprint -sha256`. „Vertrauen“ wählen.

Voraussetzungen: Android 10 oder neuer, Handy im selben WLAN wie die Box, App 1.20.0 oder neuer auf dem Pi (sonst funktioniert die Weboberfläche, die Benachrichtigungen aber nicht). Die App erreicht die Box unter `phoniebox.local`, genau wie der Browser auf dem Handy.

Neuere Versionen lassen sich einfach über die alte installieren.

## Benachrichtigungen

Die Box meldet über `GET /api/notifications` (siehe `notifications.py` im Hauptverzeichnis), was gerade nicht stimmt:

| ID | Titel |
| --- | --- |
| `bluetooth` | Bluetooth nicht verbunden (gespeicherter Lautsprecher nicht verbunden oder nicht dauerhaft gekoppelt) |
| `audio` | Audioausgang nicht erreichbar |
| `player` | Player startet nicht |
| `reader` | NFC-Reader nicht bereit |
| `spotify` | Spotify nicht verbunden |

Ein Problem meldet die Box erst, wenn es 30 Sekunden anhält. Die App zeigt jedes Problem einmal an und entfernt die Benachrichtigung, sobald die Box es nicht mehr meldet. Wer sie wegwischt, sieht sie erst beim nächsten Auftreten wieder. Nach bewusstem „Trennen“ des Lautsprechers in der Weboberfläche kommt keine Meldung.

Die App fragt im Hintergrund etwa alle 15 Minuten nach (häufiger lässt Android das ohne Daueranzeige nicht zu), nur im WLAN, und bei geöffneter App alle 30 Sekunden. Ist die Box nicht erreichbar, etwa weil das Handy unterwegs ist, ändert sich nichts. Abschalten lassen sich die Benachrichtigungen im App-Menü oder in den Android-Einstellungen der App.

Die App hat keine eigene Menüleiste. Das App-Menü öffnet der Button ☰ oben rechts in der Weboberfläche (nur in der App sichtbar, ab App 1.20.1 auf dem Pi, ab 1.20.2 als Dialog im Design der Weboberfläche mit dem aktuellen Status der Box; die Seite findet die App über die JavaScript-Brücke `window.PhonieboxApp`). Ist die Box nicht erreichbar, steht das Menü auf der Fehlerseite. Einträge: Status jetzt prüfen, Benachrichtigungen an/aus, Neu laden, Zertifikat neu bestätigen (nach einer Neuinstallation der Box, die ein neues Zertifikat erzeugt).

## Bauen

Die Action `.github/workflows/android.yml` baut die APK. Lokal mit Android SDK, JDK 17 und Gradle 8.14:

```bash
gradle -p android assembleDebug
# Ergebnis: android/app/build/outputs/apk/debug/app-debug.apk
```

Die Version steht in `android/VERSION`; für ein neues Release erhöhen und einen Abschnitt in `android/CHANGELOG.md` ergänzen. Die APK ist mit dem Debug-Schlüssel `android/debug.keystore` signiert, der absichtlich im Repository liegt: So lässt sich jede neue APK über die vorige installieren. Der Schlüssel schützt nichts; wer ihn hat, kann eine APK bauen, die sich als Update dieser App installieren lässt. Installiert wird sie trotzdem nur, wenn jemand sie auf dem Handy selbst öffnet.

Die App ist reines Java ohne Bibliotheken: `MainActivity` (WebView, Zertifikatsabfrage, Menü), `Box` (Adresse, Zertifikat-Pinning, Abfrage), `Notifier` (Benachrichtigungen), `StatusJob` (Hintergrundprüfung per JobScheduler).
