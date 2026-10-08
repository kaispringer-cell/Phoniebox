#!/bin/bash
# Fresh Raspberry Pi OS Trixie 64-bit on Pi 3B+. No preinstalled librespot required.
set -euo pipefail
umask 077
if [[ $EUID -ne 0 ]]; then
  echo 'Der Installer benötigt sudo-Rechte.' >&2
  exit 1
fi
if [[ $# -ne 0 ]]; then
  echo 'Aufruf: sudo bash install.sh' >&2
  exit 1
fi
# Verhindert zwei gleichzeitige Läufe - z. B. wenn eine abgerissene SSH-Verbindung den
# Installer glauben lässt, der erste Versuch sei fehlgeschlagen, während apt-get auf dem Pi
# selbst tatsächlich noch weiterläuft (das merkt nur der Client, nicht der Pi). Ein zweiter
# gleichzeitiger apt-get-Lauf würde sich sonst mit dem ersten um die debconf-Datenbank
# streiten und Pakete in einem halbkonfigurierten Zustand zurücklassen. flock hält die Sperre
# nur über die Lebensdauer dieses Prozesses (Dateideskriptor 9 bleibt bis zum Skriptende
# offen) und gibt sie bei jedem Prozessende automatisch frei, auch bei einem Absturz - keine
# manuelle Bereinigung eines "veralteten" Lockfiles nötig.
exec 9>/run/lock/phoniebox-install.lock
if ! flock -n 9; then
  echo 'Es läuft bereits eine Phoniebox-Installation auf diesem Pi (z. B. von einer zuvor abgerissenen SSH-Verbindung). Bitte warten, bis sie abgeschlossen ist, und danach erneut verbinden - nicht gleichzeitig neu starten.' >&2
  exit 1
fi
# Debians eigener automatischer Update-Timer (apt-daily/apt-daily-upgrade, Teil des apt-Pakets
# selbst) kann auf einem frisch gestarteten Pi von selbst loslaufen und dabei minutenlang die
# debconf-Sperre (/var/cache/debconf/config.dat) belegen - unabhängig von der obigen
# Installer-eigenen flock-Sperre und nicht durch "-o DPkg::Lock::Timeout" abgedeckt, das nur
# die separaten dpkg/apt-Sperrdateien betrifft. Deaktiviert und beendet ihn deshalb hier fest,
# damit er nicht mitten in der Installation dazwischenfunkt; harmlos, falls die Einheiten auf
# diesem Abbild gar nicht existieren.
systemctl stop apt-daily.service apt-daily-upgrade.service unattended-upgrades.service 2>/dev/null || true
systemctl mask --now apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service 2>/dev/null || true
# Die Sperre gilt nur für die Dauer der Installation. Am Ende (auch bei Abbruch, siehe trap
# direkt darunter) werden die automatischen Paket- und Sicherheitsupdates wieder freigegeben;
# sonst bekäme der Pi nie wieder Sicherheitsupdates.
restore_automatic_updates() {
  systemctl unmask apt-daily.service apt-daily-upgrade.service apt-daily.timer apt-daily-upgrade.timer unattended-upgrades.service >/dev/null 2>&1 || true
  systemctl enable apt-daily.timer apt-daily-upgrade.timer >/dev/null 2>&1 || true
  if systemctl cat unattended-upgrades.service >/dev/null 2>&1; then
    systemctl enable unattended-upgrades.service >/dev/null 2>&1 || true
  fi
}
trap restore_automatic_updates EXIT
# Root cause finally confirmed on a real user's Pi via the new describe_process_origin()
# diagnostic (see debconf_lock_holders() below): the recurring "dpkg-reconfigure ...
# keyboard-configuration" debconf-lock holder that 2.8.4-2.8.7 kept fighting reactively is the
# child of userconfig.service ("User configuration dialog") - Raspberry Pi OS' own firstboot
# service that applies the account/hostname/keyboard/locale/Wi-Fi settings rpi-imager's advanced
# options wrote into the boot partition. Its own journal showed it crash-looping entirely on its
# own, independent of anything this installer ever did: "Main process exited, code=exited,
# status=143/n/a" (SIGTERM) every ~60 seconds, restart counter already above 60 by the time this
# was caught - almost certainly systemd's own TimeoutStartSec killing it after it blocks
# indefinitely on the same missing-controlling-terminal problem documented above, then
# restarting it via Restart=on-failure, forever, with no way it would ever resolve on its own no
# matter how long anything waited. All the account/hostname/network settings it is meant to
# apply are already in effect by the time install.sh can even run (this script only starts once
# the installer has already connected over SSH with exactly those settings), so nothing here
# still depends on it succeeding. Stopping and masking it outright - the same pattern already
# used for apt-daily above - prevents it from ever holding the debconf lock in the first place,
# which is a permanent, preventive fix instead of another reactive one. The targeted, 60s-
# retrying keyboard-configuration killswitch in wait_or_clear_debconf_lock() stays in place as a
# safety net for any other Raspberry Pi OS build where this exact service might be named or
# behave differently, but should no longer ever be needed for this specific cause.
systemctl stop userconfig.service 2>/dev/null || true
systemctl mask --now userconfig.service 2>/dev/null || true
# Derselbe automatische Tageslauf existiert auf manchen Abbildern zusätzlich klassisch über
# cron (/etc/cron.daily/apt-compat, von anacron kurz nach dem ersten Boot nachgeholt, wenn es
# einen "überfälligen" Tageslauf sieht) - unabhängig von den oben maskierten systemd-Einheiten.
# apt-compat prüft vor dem eigentlichen Lauf die folgenden Zeitstempel; auf "jetzt" gesetzt,
# hält es sich für heute bereits erledigt.
mkdir -p /var/lib/apt/periodic
touch /var/lib/apt/periodic/update-success-stamp /var/lib/apt/periodic/download-upgradeable-stamp /var/lib/apt/periodic/upgrade-stamp /var/lib/apt/periodic/autoclean-stamp 2>/dev/null || true
source_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
if [[ $(uname -m) != aarch64 ]] || ! grep -q 'VERSION_CODENAME=trixie' /etc/os-release; then
  echo 'Benötigt: Raspberry Pi OS Trixie (64 Bit).' >&2; exit 1
fi
if ! tr -d '\0' < /proc/device-tree/model | grep -q 'Raspberry Pi 3 Model B'; then
  echo 'Diese Ausgabe ist für Raspberry Pi 3B/3B+ mit Klinkenausgang vorbereitet.' >&2; exit 1
fi
if [[ $(df -Pm / | awk 'NR==2 {print $4}') -lt 8192 ]]; then
  echo 'Für Pakete, Rust-Build und temporären Swap werden mindestens 8 GiB freier Speicher benötigt.' >&2; exit 1
fi
for path in /opt/phoniebox /etc/systemd/system/phoniebox.service /etc/nginx/sites-enabled/phoniebox /etc/nginx/sites-available/phoniebox /etc/phoniebox; do
  if [[ -e "$path" ]]; then
    echo "Vorhandene Installation oder Teilinstallation: $path. Keine Nutzerdaten überschrieben." >&2; exit 1
  fi
done
# Detect conflicting web servers before spending an hour on the Rust build.
if command -v ss >/dev/null; then
  listeners=$(ss -H -ltnp '( sport = :80 or sport = :443 )')
  while IFS= read -r listener; do
    if [[ -n "$listener" && "$listener" != *'("nginx"'* ]]; then
      echo 'Port 80 oder 443 wird bereits von einem anderen Dienst verwendet:' >&2
      printf '%s\n' "$listener" >&2
      echo 'Bitte zuerst den Portkonflikt klären. Es wurde kein neuer Build begonnen.' >&2
      exit 1
    fi
  done <<< "$listeners"
fi
export DEBIAN_FRONTEND=noninteractive
export APT_LISTCHANGES_FRONTEND=none
# Die debconf-Datenbank (/var/cache/debconf/config.dat) hat eine eigene, von den dpkg/apt-
# Sperrdateien unabhängige Sperre. Trotz gestopptem/maskiertem apt-daily (oben) und trotz
# korrekter, nicht mehr leerender Sperrprüfung ist dieselbe Fehlermeldung bei einem Nutzer
# wiederholt und exakt reproduzierbar aufgetreten (immer dieselben ersten zwei Pakete,
# unmittelbar nach einer "frei"-Prüfung) - der eigentliche Verursacher ist damit weiterhin
# nicht zweifelsfrei geklärt. Statt weiter zu raten, protokolliert debconf_lock_holders() im
# Fehlerfall automatisch, WER die Sperre zum Zeitpunkt des Scheiterns tatsächlich hält (PID
# und Kommandozeile, über /proc/<pid>/fd), damit ein erneutes Log die Ursache zeigt, statt nur
# das immer gleiche Symptom. apt_retry versucht jeden Paketschritt zusätzlich deutlich
# hartnäckiger (bis zu 8-mal mit wachsender Wartezeit) und repariert den Paketstand zwischen
# den Versuchen erneut - ganz ohne manuelles Eingreifen auf dem Pi.
# Wichtig: Diese Diagnosezeilen dürfen NIE das "PHONIEBOX_STAGE:"-Präfix tragen. remote.py
# fängt jede Zeile mit diesem Präfix ab und wandelt sie in eine Fortschritts-/Prozentanzeige um
# (nur der aktuelle Statustext, wird von der nächsten Stage-Meldung sofort überschrieben) -
# genau damit wurde diese Diagnose bislang unbemerkt verschluckt: Sie lief korrekt, aber die
# PID/Kommandozeile landete nie im kopierbaren Verlauf, selbst wenn der Fehler erneut auftrat.
# Als normale Log-Zeile (kein Präfix) greift stattdessen remote.py's else-Zweig (self.log(line))
# und die Zeile bleibt dauerhaft im Verlauf stehen.
debconf_lock=/var/cache/debconf/config.dat
# Vier aufeinanderfolgende Versuche (2.8.4-2.8.7), das Symptom rund um den bekannten Sperrhalter
# "dpkg-reconfigure ... keyboard-configuration" zu behandeln, haben die eigentliche Frage nie
# beantwortet: WARUM läuft/erscheint dieser Prozess wiederholt, und WER startet ihn? Statt eines
# fünften Rate-Fixes liefert describe_process_origin() das, was bisher fehlte - direkt aus dem
# laufenden System, ganz ohne manuelles Eingreifen: die Elternprozess-Kette (zeigt, ob es
# wirklich immer derselbe Auslöser ist oder ein neuer), den systemd-Dienst, der den Prozess laut
# Kontrollgruppe gestartet hat (cgroup), und dessen jüngste Journal-Einträge (zeigen z. B. ob der
# Dienst neu startet, warum, und wie oft). Erst mit dieser Information lässt sich die tatsächliche
# Ursache benennen statt weiter Symptome abzufangen.
describe_process_origin() {
  local pid=$1 ancestor ppid comm unit chain='' hops
  ancestor=$pid
  for hops in 1 2 3 4 5 6 7 8; do
    [[ -r "/proc/$ancestor/comm" ]] || break
    comm=$(< "/proc/$ancestor/comm")
    chain="${chain:+$chain <- }${ancestor}:${comm}"
    ppid=$(awk '/^PPid:/{print $2}' "/proc/$ancestor/status" 2>/dev/null)
    [[ -n "$ppid" && "$ppid" != 0 ]] || break
    ancestor=$ppid
  done
  printf '  Prozesskette (dieser Prozess <- Eltern <- Großeltern ...): %s\n' "${chain:-unbekannt}"
  unit=$(sed -n 's#.*/\([^/]*\.service\)$#\1#p' "/proc/$pid/cgroup" 2>/dev/null | head -1)
  if [[ -n "$unit" ]]; then
    printf '  Gestartet vom systemd-Dienst: %s\n' "$unit"
    printf '  Journal-Auszug dieses Dienstes (neueste 15 Zeilen):\n'
    journalctl -u "$unit" --no-pager -n 15 2>/dev/null | sed 's/^/    /'
  else
    printf '  Kein systemd-Dienst über die Kontrollgruppe ermittelbar (evtl. direkt von einem übergeordneten Skript gestartet statt von systemd)\n'
  fi
}
debconf_lock_holders() {
  local lock_dev lock_ino pid fd target dev ino cmdline found=false
  read -r lock_dev lock_ino < <(stat -c '%d %i' "$debconf_lock" 2>/dev/null) || return 0
  for pid in /proc/[0-9]*; do
    pid=${pid#/proc/}
    [[ -d "/proc/$pid/fd" ]] || continue
    for fd in "/proc/$pid/fd"/*; do
      read -r dev ino < <(stat -c '%d %i' -L "$fd" 2>/dev/null) || continue
      if [[ "$dev $ino" == "$lock_dev $lock_ino" ]]; then
        cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
        printf 'debconf-Sperre wird gehalten von PID %s: %s\n' "$pid" "${cmdline:-?}"
        describe_process_origin "$pid"
        found=true
      fi
    done
  done
  $found || printf 'Kein Prozess mit offenem Zugriff auf die debconf-Sperre gefunden – vermutlich bereits wieder freigegeben\n'
}
wait_or_clear_debconf_lock() {
  # Wichtig: Die echte debconf-Datenbank wird hier nur zum Sperrtest geöffnet, niemals mit
  # der leerenden Bash-Umleitung ">" - das würde die Datei bei jedem Aufruf auf 0 Byte
  # zurücksetzen und debconf damit selbst kaputt machen, statt nur die Sperre zu prüfen.
  # "<>" öffnet lesend/schreibend, ohne den Inhalt anzutasten.
  #
  # Root-Ursache jetzt tatsächlich im Log eines Nutzers bestätigt (nachdem die Diagnose zuvor
  # unbemerkt verschluckt wurde, siehe Kommentar oben bei debconf_lock_holders): Sperrhalter war
  # "/usr/bin/perl /usr/sbin/dpkg-reconfigure -p critical keyboard-configuration" - das ist KEIN
  # hängengebliebener Altprozess, sondern Raspberry Pi OS' eigene, vollkommen normale Firstboot-
  # Einrichtung (Tastatur-/Locale-Konfiguration, ausgelöst kurz nach dem allerersten Start durch
  # das Image selbst, unabhängig von diesem Installer). Sie läuft von selbst fertig und gibt die
  # Sperre danach frei - sie ist nur manchmal noch aktiv, wenn der Installer (der nach dem
  # gemeldeten SSH-Start sofort loslegt) sie zum ersten Mal trifft. Die bisherige Kill-Liste
  # unten enthielt "dpkg-reconfigur" (der auf 15 Zeichen abgeschnittene /proc/<pid>/comm-Name von
  # dpkg-reconfigure) als vermeintlich sicher zu beendenden Prozess - das heißt, genau dieser
  # laufende Firstboot-Schritt wurde nach 10 Sekunden Wartezeit per SIGTERM abgeschossen, mitten
  # in seiner debconf-Frage. Das erklärt die über die gesamte debconf-Sperren-Serie (2.7.2 bis
  # 2.8.2) hinweg immer identisch fehlschlagenden Pakete (fontconfig-config, x11-common,
  # nginx-common): Sie alle stellen selbst debconf-Fragen, und ein mitten in einer fremden
  # debconf-Transaktion abgeschossener Perl-Prozess kann die gemeinsam genutzte Datenbank in
  # einem Zustand zurücklassen, den "dpkg --configure -a" nicht zuverlässig repariert. Der
  # vermeintliche "Automatik-Fix" war damit über mehrere Versionen hinweg selbst die Ursache.
  # apt, apt-get, dpkg und dpkg-reconfigur sind deshalb jetzt NICHT mehr Teil der Kill-Liste -
  # sie erledigen echte, absichtlich laufende Arbeit (unsere eigene oder, wie hier, die des
  # Systems selbst) und werden nur noch abgewartet. Getötet werden ausschließlich Hintergrund-
  #/Timer-Artefakte, die zu diesem Zeitpunkt ohnehin nicht laufen dürften (ihre auslösenden
  # Timer/Dienste sind weiter oben bereits gestoppt und maskiert) - läuft trotzdem noch eine
  # Instanz, ist das ein echter Überbleibsel-Fall, kein aktiver, absichtlicher Vorgang.
  #
  # Follow-up, same day: even with the above fix shipped, a user's own keyboard-configuration
  # reconfigure sat completely unchanged for 5+ minutes (confirmed same PID, no progress) -
  # normally this firstboot step finishes in well under a minute. Most likely explanation: it
  # was started as "dpkg-reconfigure -p critical keyboard-configuration" (only the "-p" priority
  # filter, no "-f noninteractive" frontend) by Raspberry Pi OS' own firstboot machinery, with no
  # controlling terminal available over SSH-only access - under a real debconf frontend that
  # needs a terminal, that can block forever waiting for input nobody can ever provide, not just
  # run slowly. Unlike the general case above, THIS specific situation is safe to resolve
  # automatically without waiting the full 15 minutes: nothing has been written yet (it is stuck
  # asking a question, not mid-transaction), the keyboard layout is irrelevant to a headless
  # music box, and the safe fix is well-known - end the stuck interactive attempt and redo the
  # exact same reconfiguration non-interactively (DEBIAN_FRONTEND=noninteractive + -f
  # noninteractive), which cannot block on a missing terminal because it is told up front never
  # to ask anything, only to use whatever is already configured. This is intentionally much more
  # narrow than the old, blanket "kill any dpkg-reconfigure" policy this replaced: it only ever
  # matches this one specific, well-understood package by name in the full command line, never a
  # truncated process name, and only after real, confirmed lack of progress (60s - long past
  # what this step should ever normally take, but a small fraction of the full 900s budget).
  # Follow-up, same day again: even this fix wasn't enough on the user's own Pi - the elapsed-
  # time indicator (added for exactly this reason, see gui.py) proved the installer was still
  # genuinely working, not frozen, yet the SAME symptom (stuck right after the "wird beendet"
  # line, no further output) persisted for several more minutes. The one-shot "keyboard_handled"
  # flag below is the likely reason: it only ever acts once per call to this function. If
  # Raspberry Pi OS' firstboot chain relaunches keyboard-configuration's reconfigure again under
  # a NEW PID after the first one is killed (plausible for a multi-step firstboot sequence that
  # retries a failed step), this function would recognise the lock is still held, wait, but never
  # touch the new instance - just loop silently until the full 900s ceiling. Replaced with a
  # timestamp so the same targeted fix can fire again every 60s for as long as the lock keeps
  # being reacquired by this exact, well-understood case - still nowhere near the pace of the
  # general 10s background-artifact sweep above, and still only ever this one named package.
  local waited=0 pid comm cmdline reported=false keyboard_last_handled=-1000
  while true; do
    if ( exec 200<>"$debconf_lock"; flock -n 200 ) 2>/dev/null; then
      return 0
    fi
    if ! $reported; then
      printf 'Es wird auf einen anderen Prozess gewartet, der die Paketverwaltung blockiert\n'
      debconf_lock_holders
      reported=true
    fi
    if (( waited >= 10 )); then
      for pid in /proc/[0-9]*; do
        pid=${pid#/proc/}
        [[ -r "/proc/$pid/comm" ]] || continue
        comm=$(< "/proc/$pid/comm")
        case "$comm" in
          unattended-upgr|apt.systemd.dai|anacron|apt-compat|apt-helper)
            kill "$pid" 2>/dev/null || true ;;
        esac
      done
    fi
    if (( waited >= 60 )) && (( waited - keyboard_last_handled >= 60 )); then
      for pid in /proc/[0-9]*; do
        pid=${pid#/proc/}
        [[ -r "/proc/$pid/cmdline" ]] || continue
        cmdline=$(tr '\0' ' ' < "/proc/$pid/cmdline" 2>/dev/null)
        if [[ "$cmdline" == *dpkg-reconfigure*keyboard-configuration* ]]; then
          printf 'Firstboot-Tastatureinrichtung (PID %s) hängt seit über einer Minute ohne Reaktion - wird beendet und ohne Rückfrage automatisch abgeschlossen (Tastaturbelegung ist für die Phoniebox ohne Bedeutung)\n' "$pid"
          kill "$pid" 2>/dev/null || true
          sleep 1
          kill -9 "$pid" 2>/dev/null || true
          # Belt and braces: DEBIAN_FRONTEND=noninteractive alone should already stop this from
          # ever prompting, but the very first attempt (see above) was ALSO started without a
          # controlling terminal and still blocked indefinitely for reasons this script cannot
          # fully know from the outside - if this replacement attempt hit the same or a similar
          # snag, it must never be allowed to hang the whole installation silently a second time.
          # "timeout" guarantees this call always returns, and "</dev/null" makes any accidental
          # read() fail fast with EOF instead of blocking, even if -f noninteractive were somehow
          # ignored. "-k 5" is required, not cosmetic: plain "timeout 30 …" only SENDS SIGTERM
          # after 30s and then waits for the process to actually exit - a process that ignores
          # SIGTERM (exactly the kind of stuck state already seen once here) would make "timeout"
          # itself hang right along with it. "-k 5" forces a SIGKILL 5s later if TERM didn't
          # work, so this call is bounded no matter what the child does. A timeout/kill here is
          # treated the same as success (|| true) - the loop below re-checks the actual lock file
          # next, not this command's exit code.
          timeout -k 5 30 env DEBIAN_FRONTEND=noninteractive dpkg-reconfigure -f noninteractive keyboard-configuration </dev/null >/dev/null 2>&1 || true
          keyboard_last_handled=$waited
        fi
      done
    fi
    sleep 2
    waited=$((waited + 2))
    # Ohne automatisches Abschießen von apt/dpkg/dpkg-reconfigure braucht ein echter, langsamer
    # Firstboot-Vorgang (langsame SD-Karte, Pi 3B) mehr Geduld als zuvor - deshalb von 300 auf
    # 900 Sekunden angehoben, statt wie zuvor nach 5 Minuten aufzugeben und den eigentlich nur
    # arbeitenden Prozess weiterhin fälschlich als Problem zu behandeln.
    if (( waited >= 900 )); then
      echo 'Die Paketverwaltungs-Sperre wird dauerhaft von einem Prozess gehalten, der sich nicht automatisch beenden ließ.' >&2
      return 1
    fi
  done
}
apt_retry() {
  local attempt delay=5
  for attempt in 1 2 3 4 5 6 7 8; do
    wait_or_clear_debconf_lock || true
    if "$@"; then
      return 0
    fi
    debconf_lock_holders
    if (( attempt < 8 )); then
      printf 'Ein Paketschritt ist an der Paketverwaltungs-Sperre gescheitert – wird wiederholt (Versuch %s von 8, Wartezeit %ss)\n' "$((attempt + 1))" "$delay"
      dpkg --configure -a 2>/dev/null || true
      sleep "$delay"
      delay=$((delay * 2))
      if (( delay > 60 )); then delay=60; fi
    fi
  done
  return 1
}
printf 'PHONIEBOX_STAGE:18:Vorheriger Paketstand wird geprüft\n'
# Selbstheilung: Ein von einem früheren, abgebrochenen Lauf (Stromausfall, abgerissene
# Verbindung ohne die obige Sperre - etwa mit einem älteren Installer) halbkonfiguriert
# zurückgelassener Paketstand wird hier repariert, bevor überhaupt etwas Neues installiert
# wird. Folgenlos und schnell, wenn ohnehin schon alles sauber konfiguriert ist.
apt_retry dpkg --configure -a
apt_retry apt-get -o DPkg::Lock::Timeout=180 -f install -y
printf 'PHONIEBOX_STAGE:20:Systempakete werden installiert\n'
apt_retry apt-get -o DPkg::Lock::Timeout=180 update
apt_retry apt-get -o DPkg::Lock::Timeout=180 install -y \
  python3 python3-flask python3-requests python3-cryptography python3-waitress python3-evdev \
  alsa-utils mpv tzdata nginx openssl ca-certificates avahi-daemon libnss-mdns \
  build-essential pkg-config git curl libasound2-dev libssl-dev protobuf-compiler \
  systemd-timesyncd bluez bluez-alsa-utils libasound2-plugin-bluez
systemctl enable --now systemd-timesyncd
# Zuerst wird versucht, ein bereits fertig gebautes librespot-Binary (arm64, ALSA-Backend)
# aus einem GitHub-Release herunterzuladen - gebaut von einem eigenen, separaten
# GitHub-Actions-Workflow (kaispringer-cell/librespot-build) auf einem nativen arm64-Runner in
# wenigen Minuten, statt stundenlang auf dem Pi selbst zu kompilieren. Jeder Fehlschlag dabei
# (kein Netz, Release nicht erreichbar, falsche Prüfsumme, Binary ohne ALSA-Backend) führt
# automatisch zum bisherigen, unveränderten Bau auf dem Pi weiter unten - keine manuelle
# Entscheidung nötig, im schlechtesten Fall nur eine längere Laufzeit wie bisher.
#
# Die ALSA-Prüfung selbst läuft über "ldd | grep libasound" statt über librespots eigene
# Backend-Auflistung (Aufruf mit dem Fragezeichen als Backend-Namen): Deren Ausgabe kommt über
# println! auf stdout, und der Prozess beendet sich direkt danach mit exit(0)/exit(1) - bei
# einer Pipe (wie hier durch Kommandosubstitution) ist das unzuverlässig, die Zeilen kamen in
# der Praxis nicht an (nur die über den log-Mechanismus auf stderr ausgegebene Versionszeile).
# Ob ALSA tatsächlich eingebunden wurde, zeigt "ldd" direkt und unabhängig von Puffer-/Exit-Timing.
printf 'PHONIEBOX_STAGE:22:librespot – vorgefertigtes Paket wird versucht\n'
librespot_repo=kaispringer-cell/librespot-build
librespot_version=v0.8.0
librespot_asset="phoniebox-librespot-${librespot_version}-arm64"
librespot_release_base="https://github.com/${librespot_repo}/releases/download/librespot-${librespot_version}-arm64"
librespot_prebuilt=false
librespot_tmp=$(mktemp -d)
if curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 2 --max-time 120 \
     -o "$librespot_tmp/$librespot_asset" "$librespot_release_base/$librespot_asset" 2>/dev/null \
   && curl --proto '=https' --tlsv1.2 --fail --silent --show-error --location --retry 2 --max-time 60 \
     -o "$librespot_tmp/$librespot_asset.sha256" "$librespot_release_base/$librespot_asset.sha256" 2>/dev/null \
   && (cd "$librespot_tmp" && sha256sum --check --status "$librespot_asset.sha256"); then
  chmod 755 "$librespot_tmp/$librespot_asset"
  if ldd "$librespot_tmp/$librespot_asset" 2>/dev/null | grep -q libasound; then
    install -m 755 "$librespot_tmp/$librespot_asset" /usr/local/bin/phoniebox-librespot
    librespot_prebuilt=true
    printf 'PHONIEBOX_STAGE:24:librespot – vorgefertigtes Paket übernommen, Bau auf dem Pi entfällt\n'
  fi
fi
rm -rf "$librespot_tmp"

if ! $librespot_prebuilt; then
  printf 'PHONIEBOX_STAGE:26:librespot – kein vorgefertigtes Paket erreichbar oder Prüfung fehlgeschlagen, wird stattdessen auf dem Pi gebaut\n'
  # A dedicated unprivileged account builds Rust code, outside the web service account.
  getent group phoniebox-build >/dev/null || groupadd --system phoniebox-build
  if ! id phoniebox-build >/dev/null 2>&1; then
    useradd --system --gid phoniebox-build --home-dir /var/cache/phoniebox-build --shell /usr/sbin/nologin phoniebox-build
  fi
  install -d -m 700 -o phoniebox-build -g phoniebox-build /var/cache/phoniebox-build
  swap_path=/var/cache/phoniebox-build.swap
  swap_created=false
  cleanup_swap() {
    if $swap_created; then
      if swapoff "$swap_path"; then rm -f -- "$swap_path"; fi
    fi
  }
  trap 'cleanup_swap; restore_automatic_updates' EXIT
  # The 1 GB Pi needs additional memory for linking. Existing swap remains untouched.
  available_memory_kib=$(awk '/^MemTotal:|^SwapTotal:/ {s+=$2} END {print s}' /proc/meminfo)
  if [[ "$available_memory_kib" -lt 3145728 ]]; then
    if [[ -e "$swap_path" ]]; then
      echo 'Temporäre Swapdatei einer früheren Installation vorhanden. Zustand zuerst prüfen.' >&2; exit 1
    fi
    printf 'PHONIEBOX_STAGE:28:Temporärer Arbeitsspeicher für den Build wird eingerichtet\n'
    dd if=/dev/zero of="$swap_path" bs=1M count=2048 status=none
    chmod 600 "$swap_path"
    mkswap "$swap_path" >/dev/null
    swapon "$swap_path"
    swap_created=true
  fi
  printf 'PHONIEBOX_STAGE:30:librespot wird mit ALSA gebaut – dies kann auf dem Pi mehrere Stunden dauern\n'
  install -m 700 -o phoniebox-build -g phoniebox-build "$source_dir/build_librespot.sh" /var/cache/phoniebox-build/build.sh
  runuser -u phoniebox-build -- /bin/bash /var/cache/phoniebox-build/build.sh
  librespot_source=/var/cache/phoniebox-build/target/release/librespot
  ldd "$librespot_source" | grep -q libasound || { echo 'Build enthält kein ALSA-Backend.' >&2; exit 1; }
  install -m 755 "$librespot_source" /usr/local/bin/phoniebox-librespot
  cleanup_swap
  swap_created=false
fi
printf 'PHONIEBOX_STAGE:75:Weboberfläche und Geräterecht werden eingerichtet\n'
getent group phoniebox >/dev/null || groupadd --system phoniebox
getent group phoniebox-nfc >/dev/null || groupadd --system phoniebox-nfc
if ! id phoniebox >/dev/null 2>&1; then
  useradd --system --gid phoniebox --home-dir /var/lib/phoniebox --shell /usr/sbin/nologin phoniebox
fi
# bluez (oben installiert) legt die Systemgruppe "bluetooth" an; phoniebox braucht sie seit
# App-Version 1.10.0 für bluetoothctl (Kopplungsseite). Defensiv trotzdem per getent prüfen,
# falls apt_retry das Paket doch übersprungen haben sollte - dann eben ohne Bluetooth-Gruppe
# weitermachen, statt die ganze Installation daran scheitern zu lassen (siehe bluetooth_group.sh,
# das das bei einem künftigen Update nachholt).
bluetooth_groups=audio,phoniebox-nfc
getent group bluetooth >/dev/null && bluetooth_groups+=,bluetooth
usermod -a -G "$bluetooth_groups" phoniebox
install -d -m 755 /opt/phoniebox
cp -R "$source_dir"/. /opt/phoniebox/
# Entwicklungsdateien gehören nicht auf den Pi.
rm -rf -- /opt/phoniebox/tests /opt/phoniebox/.pytest_cache
find /opt/phoniebox -name __pycache__ -type d -prune -exec rm -rf -- {} +
chown -R root:root /opt/phoniebox
chmod -R a+rX,go-w /opt/phoniebox
install -d -m 700 -o phoniebox -g phoniebox /var/lib/phoniebox
# Datenbank und Schlüssel legt der Dienst beim ersten Start selbst an (configure_audio.py als ExecStartPre).
install -m 644 "$source_dir/deploy/99-phoniebox-nfc.rules" /etc/udev/rules.d/99-phoniebox-nfc.rules
rm -f /etc/udev/rules.d/70-phoniebox-nfc.rules
udevadm control --reload-rules
udevadm trigger --subsystem-match=input
# Enable analogue sound explicitly; retain the original boot/hosts files.
python3 - <<'PY'
from pathlib import Path
import shutil
boot=Path('/boot/firmware/config.txt')
shutil.copy2(boot,str(boot)+'.before-phoniebox')
text=boot.read_text()
boot.write_text(text+'\n# Phoniebox: analoger Klinkenausgang\n[all]\ndtparam=audio=on\n')
hosts=Path('/etc/hosts');shutil.copy2(hosts,str(hosts)+'.before-phoniebox')
lines=hosts.read_text().splitlines()
lines=[line for line in lines if not line.split('#',1)[0].split()[:1]==['127.0.1.1']]
lines.append('127.0.1.1\tphoniebox')
hosts.write_text('\n'.join(lines)+'\n')
PY
hostnamectl set-hostname phoniebox
install -d -m 700 /etc/phoniebox
openssl req -x509 -newkey rsa:3072 -sha256 -days 3650 -nodes \
  -keyout /etc/phoniebox/tls.key -out /etc/phoniebox/tls.crt \
  -subj '/CN=phoniebox.local' -addext 'subjectAltName=DNS:phoniebox.local' \
  -addext 'basicConstraints=critical,CA:FALSE' -addext 'extendedKeyUsage=serverAuth' 2>/dev/null
chmod 600 /etc/phoniebox/tls.key
chmod 644 /etc/phoniebox/tls.crt
install -m 644 "$source_dir/deploy/nginx.conf" /etc/nginx/sites-available/phoniebox
ln -s /etc/nginx/sites-available/phoniebox /etc/nginx/sites-enabled/phoniebox
nginx -t
install -m 644 "$source_dir/deploy/phoniebox.service" /etc/systemd/system/phoniebox.service
install -m 644 "$source_dir/deploy/phoniebox-reboot.path" /etc/systemd/system/phoniebox-reboot.path
install -m 644 "$source_dir/deploy/phoniebox-reboot.service" /etc/systemd/system/phoniebox-reboot.service
rm -f /var/lib/phoniebox/reboot.request
systemctl daemon-reload
systemctl enable --now phoniebox-reboot.path
if systemctl cat librespot.service >/dev/null 2>&1; then systemctl disable --now librespot.service; fi
systemctl enable --now avahi-daemon
systemctl restart avahi-daemon
# bluez' eigener Dienst; bluez-alsa-utils (Debian-Paketname; stellt den bluealsa-Daemon samt
# bluealsa.service, "bluealsa" als bloßer Paketname existiert unter Debian/Raspberry Pi OS
# Trixie nicht - das lieferte apt zunächst nur als Fehlermeldung "no installation candidate"
# zurück) liefert die ALSA-PCM-Bridge (bluealsa:DEV=...), die das Alarm/Radio-Feature der App
# als Bluetooth-Audioausgabe erwartet; libasound2-plugin-bluez liefert das dafür nötige
# ALSA-Plugin, ohne das der PCM-Typ "bluealsa" gar nicht erst existiert. Beide Dienste werden
# hier erst nach der Paketinstallation aktiviert, defensiv per systemctl-cat-Prüfung wie beim
# nginx-Fallback unten - eine fehlende Einheit soll die Installation nicht abbrechen, da
# Bluetooth optional ist.
if systemctl cat bluetooth.service >/dev/null 2>&1; then
  systemctl enable --now bluetooth.service
else
  echo 'bluetooth.service nicht gefunden - Bluetooth-Kopplung wird nicht funktionieren.' >&2
fi
if systemctl cat bluealsa.service >/dev/null 2>&1; then
  # "--keep-alive=5" hält den A2DP-Transport nach einer Pause oder einem Titelwechsel
  # noch 5 Sekunden offen, statt ihn sofort abzubauen und beim nächsten Abspielen neu
  # auszuhandeln. Die systemd-Unit von bluealsa schlägt genau diese Anpassung in ihrem
  # eigenen Kommentar vor. Die SBC-Qualität bleibt bewusst auf dem Standard.
  #
  # Hinweis zu einem Live-Vorfall, der zunächst hier vermutet wurde: Spotify brach über
  # einen Marshall Emberton reproduzierbar nach 2-3 Sekunden ab (Spotify-App zeigte
  # "pausiert"). Ursache war nicht der Pi, sondern Multipoint: Das Handy war gleichzeitig
  # mit dem Emberton verbunden, der Lautsprecher schickte beim Quellenwechsel ein Pause-
  # Signal ans Handy, und dessen Spotify-App pausierte damit die Phoniebox. Ohne das Handy
  # am Lautsprecher lief es einwandfrei. Weder Keep-Alive noch eine niedrigere SBC-Qualität
  # ändern daran etwas; das lässt sich vom Pi aus nicht verhindern.
  install -d -m 755 /etc/systemd/system/bluealsa.service.d
  install -m 644 "$source_dir/deploy/bluealsa-override.conf" /etc/systemd/system/bluealsa.service.d/override.conf
  systemctl daemon-reload
  systemctl enable --now bluealsa.service
  systemctl restart bluealsa.service
else
  echo 'bluealsa.service nicht gefunden - Bluetooth-Audioausgabe wird nicht funktionieren.' >&2
fi
systemctl enable --now phoniebox.service
if ! systemctl enable --now nginx; then
  bash "$source_dir/diagnose.sh"
  echo 'nginx konnte nicht gestartet werden. librespot und Nutzerdaten bleiben erhalten; kein neuer Build nötig.' >&2
  exit 1
fi
if ! systemctl reload nginx; then
  bash "$source_dir/diagnose.sh"
  exit 1
fi
systemctl is-active --quiet phoniebox.service
systemctl is-active --quiet nginx
printf '\nHTTPS-Zertifikat SHA-256:\n'
openssl x509 -in /etc/phoniebox/tls.crt -noout -fingerprint -sha256
restore_automatic_updates
# Free build storage after a successful installation, before reboot.
rm -rf -- /var/cache/phoniebox-build/target /var/cache/phoniebox-build/source
printf 'PHONIEBOX_STAGE:88:Einrichtung abgeschlossen – automatischer Neustart für Audio\n'
# A short delay lets SSH transmit exit status before the Pi restarts.
systemd-run --unit=phoniebox-install-reboot --on-active=12s /usr/bin/systemctl reboot
printf 'PHONIEBOX_REBOOT_REQUIRED\n'
