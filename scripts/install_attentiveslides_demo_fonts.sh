#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
font_root="${XDG_DATA_HOME:-$HOME/.local/share}/fonts/attentiveslides"

install -d "$font_root"
install -m 0644 "$repo_root/assets/fonts/literata/Literata-Variable.ttf" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-Regular.woff2" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-SemiBold.woff2" "$font_root/"
install -m 0644 "$repo_root/assets/fonts/ibm-plex-sans/IBMPlexSans-Bold.woff2" "$font_root/"
fc-cache -f "$font_root"
