#!/bin/bash
# Finish an existing installation without touching passwords, tokens, cards or builds.
set -euo pipefail
if [[ $EUID -ne 0 ]]; then echo 'sudo-Rechte benötigt.' >&2; exit 1; fi
for required in /opt/phoniebox/run.py /etc/systemd/system/phoniebox.service /usr/local/bin/phoniebox-librespot /var/lib/phoniebox/phoniebox.sqlite3 /etc/nginx/sites-available/phoniebox; do
  [[ -e "$required" ]] || { echo "Einrichtung noch unvollständig: $required fehlt." >&2; exit 1; }
done
printf 'Vorhandene Installation wird abgeschlossen. Kein Neubau, keine Änderung von Zugangsdaten.\n'
nginx -t
# This recovery action explicitly replaces the conflicting lighttpd web server.
lighttpd_was_active=false
lighttpd_was_enabled=false
if systemctl is-active --quiet lighttpd; then
  lighttpd_was_active=true
  if systemctl is-enabled --quiet lighttpd; then lighttpd_was_enabled=true; fi
  echo 'lighttpd wird durch nginx ersetzt. Seine bisherige Weboberfläche wird abgeschaltet.'
  systemctl disable --now lighttpd
fi
if ! systemctl start nginx; then
  # Restore the previously running web service when nginx cannot take over.
  if $lighttpd_was_active; then
    if $lighttpd_was_enabled; then systemctl enable lighttpd; fi
    systemctl start lighttpd
  fi
  journalctl -u nginx -n 25 --no-pager
  ss -ltnp '( sport = :80 or sport = :443 )'
  echo 'Web-Portkonflikt oder nginx-Fehler noch nicht behoben.' >&2
  exit 1
fi
systemctl enable nginx phoniebox
systemctl restart phoniebox
systemctl is-active --quiet phoniebox
systemctl is-active --quiet nginx
printf 'Dienste laufen. Pi startet zur Übernahme der Audioeinstellungen neu.\n'
systemd-run --unit=phoniebox-install-reboot --on-active=12s /usr/bin/systemctl reboot
printf 'PHONIEBOX_REBOOT_REQUIRED\n'
