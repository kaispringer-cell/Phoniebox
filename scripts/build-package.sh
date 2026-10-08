#!/bin/sh
# Baut das App-Paket so, wie Installer und update.py es erwarten: alle Dateien unter phoniebox/.
# Aufruf: scripts/build-package.sh [Tag]   (ohne Tag: Version aus VERSION, Paket aus HEAD)
# Ergebnis in dist/: phoniebox-X.Y.Z.tar.gz, phoniebox-X.Y.Z.tar.gz.sha256 und notes.md (CHANGELOG-Abschnitt).
set -eu
cd "$(dirname "$0")/.."
version=$(tr -d '[:space:]' < VERSION)
manifest=$(python3 -c 'import json; print(json.load(open("release.json"))["version"])')
if [ "$version" != "$manifest" ]; then
    echo "VERSION ($version) und release.json ($manifest) passen nicht zusammen." >&2
    exit 1
fi
if [ $# -gt 0 ] && [ "$1" != "v$version" ]; then
    echo "Tag $1 passt nicht zu VERSION $version (erwartet v$version)." >&2
    exit 1
fi
name="phoniebox-$version.tar.gz"
rm -rf dist
mkdir dist
# .gitattributes hält .github/ und scripts/ aus dem Paket heraus. gzip -n: gleiche Quelle, gleiche Prüfsumme.
git archive --format=tar --prefix=phoniebox/ HEAD | gzip -n -9 > "dist/$name"
(cd dist && sha256sum "$name" > "$name.sha256")
# Abschnitt "# X.Y.Z" aus dem CHANGELOG bis zur nächsten Überschrift.
awk -v v="# $version" '$0 == v {found=1; next} found && /^#/ {exit} found {print}' CHANGELOG.md > dist/notes.md
if [ ! -s dist/notes.md ]; then
    echo "Kein Abschnitt \"# $version\" im CHANGELOG.md." >&2
    exit 1
fi
echo "dist/$name"
