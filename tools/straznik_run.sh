#!/usr/bin/env bash
# Straznik sciagi huntera — wersja uruchamiana przez cron.
# 1) bierze najnowszy stan z GitHuba, 2) odpala deterministyczne testy spojnosci.
# Kod wyjscia: 0 = OK (lub tylko ostrzezenia), 1 = ALERTY.
set -uo pipefail

REPO="F:/HERMES_ORION/projects/wow-forever-hunter"
SCRIPT="$REPO/tools/straznik.py"

cd "$REPO" || { echo "brak repo $REPO"; exit 1; }

git fetch -q origin 2>/dev/null
if ! git pull -q origin master 2>/dev/null; then
  echo "(git pull nie przeszedl — sprawdzam to, co jest lokalnie)"
fi

python "$SCRIPT"
