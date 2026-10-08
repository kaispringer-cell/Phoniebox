#!/bin/bash
# Read-only diagnostics. Never dump app databases, credentials, keys or full nginx config.
set -u
printf '\n--- nginx-Konfiguration prüfen ---\n'
nginx -t 2>&1 || true
printf '\n--- nginx-Dienst ---\n'
systemctl status nginx --no-pager --full 2>&1 || true
printf '\n--- Letzte nginx-Dienstmeldungen ---\n'
journalctl -u nginx -n 45 --no-pager 2>&1 || true
printf '\n--- Belegte Web-Ports ---\n'
ss -ltnp '( sport = :80 or sport = :443 or sport = :8888 )' 2>&1 || true
printf '\n--- Phoniebox-Dienst ---\n'
systemctl status phoniebox --no-pager --full 2>&1 || true
printf '\n--- Lokale Weboberfläche ---\n'
python3 - <<'PY'
import urllib.request
try:
    r=urllib.request.urlopen('http://127.0.0.1:8888/login',timeout=10)
    print('Loginseite HTTP',r.status)
except Exception as e:
    print(type(e).__name__,str(e))
PY
printf '\n--- librespot-Build vorhanden ---\n'
test ! -x /usr/local/bin/phoniebox-librespot || /usr/local/bin/phoniebox-librespot --version 2>&1
exit 0
