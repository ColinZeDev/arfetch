#!/usr/bin/env bash

dir="$(cd "$(dirname "$0")" && pwd)"

log() { echo -e "\033[1;32m=> $*\033[0m"; }

log "cleaning old build files/dirs"
for d in build dist; do
    [[ -d "$dir/$d" ]] && rm -rf "$dir/$d"
done
[[ -f "$dir/main.spec" ]] && rm -f "$dir/main.spec"

log "compiling afetch"
pyinstaller --onefile --name arfetch "$dir/main.py"

log "done — binary at $dir/dist/arfetch"