#!/bin/bash
# Runs as the unprivileged, dedicated build user.
set -euo pipefail
umask 077
cd /var/cache/phoniebox-build
export CARGO_HOME=/var/cache/phoniebox-build/cargo
export RUSTUP_HOME=/var/cache/phoniebox-build/rustup
export CARGO_TARGET_DIR=/var/cache/phoniebox-build/target
export CARGO_BUILD_JOBS=1
export CARGO_INCREMENTAL=0
export RUSTUP_TOOLCHAIN=1.90.0
# Ein Verbindungsabbruch zum Pi (WLAN, Router) kann einen einzelnen Crate-Download mitten im
# Transfer hängen lassen, ohne dass cargo das von selbst erkennt - beobachtet: 30+ Minuten
# Stillstand beim Herunterladen eines wenige Kilobyte kleinen Crates. CARGO_NET_RETRY erhöht
# cargos eigene Wiederholungen bei erkannten Netzwerkfehlern; CARGO_HTTP_TIMEOUT/
# CARGO_HTTP_LOW_SPEED_LIMIT sorgen dafür, dass ein Transfer, der über 30 Sekunden praktisch
# keine Daten mehr liefert, als Fehler erkannt wird, statt unbegrenzt zu hängen.
export CARGO_NET_RETRY=10
export CARGO_HTTP_TIMEOUT=30
export CARGO_HTTP_LOW_SPEED_LIMIT=1024
export CARGO_HTTP_LOW_SPEED_TIMEOUT=30
if [[ ! -x "$CARGO_HOME/bin/rustup" ]]; then
  curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
    https://static.rust-lang.org/rustup/dist/aarch64-unknown-linux-gnu/rustup-init -o rustup-init
  curl --proto '=https' --tlsv1.2 --fail --location --retry 3 \
    https://static.rust-lang.org/rustup/dist/aarch64-unknown-linux-gnu/rustup-init.sha256 -o rustup-init.sha256
  expected_digest=$(awk '{print $1}' rustup-init.sha256)
  [[ "$expected_digest" =~ ^[a-f0-9]{64}$ ]]
  printf '%s  rustup-init\n' "$expected_digest" | sha256sum --check -
  chmod 700 rustup-init
  ./rustup-init -y --no-modify-path --profile minimal --default-toolchain 1.90.0
fi
"$CARGO_HOME/bin/rustup" toolchain install 1.90.0 --profile minimal
# Netzwerkschritte (Git-Klon/-Fetch, Crate-Download) laufen über denselben Wiederholungs-
# Wrapper: "timeout" beendet einen hängenden Versuch hart nach 10 Minuten, statt unbegrenzt zu
# warten; bei einem echten, nur vorübergehenden Verbindungsabbruch reicht ein erneuter Versuch
# meist aus. Bereits heruntergeladene Daten (Git-Objekte, Cargo-Cache) bleiben dabei erhalten,
# ein Wiederholungsversuch beginnt also nicht bei null.
with_network_retry() {
  local attempt
  for attempt in 1 2 3 4 5; do
    if timeout 600 "$@"; then
      return 0
    fi
    echo "Netzwerkschritt fehlgeschlagen oder hängt (Versuch $attempt von 5) - erneuter Versuch" >&2
    sleep 10
  done
  return 1
}
if [[ ! -d source/.git ]]; then
  with_network_retry git clone --depth 1 --branch v0.8.0 https://github.com/librespot-org/librespot.git source
fi
[[ $(git -C source remote get-url origin) == https://github.com/librespot-org/librespot.git ]]
with_network_retry git -C source fetch --depth 1 origin tag v0.8.0
git -C source checkout --detach v0.8.0
# Abhängigkeiten zuerst separat und mit Netzwerk-Absicherung herunterladen; der eigentliche
# Build läuft danach mit --offline und rührt das Netzwerk nicht mehr an, sodass ein Hänger im
# stundenlangen Kompilierschritt selbst ausgeschlossen ist (dort geht es nur noch um Rechenzeit).
with_network_retry "$CARGO_HOME/bin/cargo" fetch --manifest-path source/Cargo.toml --locked
"$CARGO_HOME/bin/cargo" build --manifest-path source/Cargo.toml --release --locked --offline \
  --no-default-features --features 'native-tls alsa-backend with-libmdns'
